#!/usr/bin/env python3
"""Replay bounded rig-authoring operations against an isolated PSD2Live service.

The upstream GPL mcp_proxy client is an explicit external developer-tool input,
not bundled into the companion runtime. No source-paint or arbitrary code steps
are accepted. Resolve mesh/layer IDs by actual current names after regeneration.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from avatar_live2d_units import validate_operation_units

ALLOWED = {
    "project_import_psd", "project_open", "project_save_as", "project_export_model",
    "settings_update", "layer_classify", "rig_generate", "rig_edit_structure",
    "keyform_apply", "rig_deform", "author_axis", "parameter_create", "parameter_update",
    "canvas_rotation", "canvas_warp", "expression_put", "motion_put", "physics_put",
    "canvas_glue", "canvas_glue_edit", "canvas_topology", "object_edit_appearance",
    "workspace_inspect", "workspace_overview",
}


def named(client, kind: str, name: str) -> str | None:
    scope = "layers" if kind == "layer" else "objects"
    data, _ = client.call("workspace_inspect", {"scope": scope, "query": name, "limit": 64})
    items = [item for item in data["items"] if item.get("name") == name]
    if kind != "layer":
        items = [item for item in items if item.get("target", "").startswith("mesh:")]
    if len(items) != 1:
        raise ValueError(f"expected exactly one actual {kind} named {name!r}, got {len(items)}")
    if kind == "layer":
        return items[0]["id"]
    if kind == "parent":
        return items[0]["parentId"]
    target = items[0]["target"]
    return target if kind == "target" else target.split(":", 1)[1]


def resolve(value, client, variables):
    if isinstance(value, dict):
        return {key: resolve(item, client, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, client, variables) for item in value]
    if isinstance(value, str) and value.startswith("$"):
        if value in variables:
            return variables[value]
        for kind in ("layer", "target", "mesh", "parent"):
            prefix = "$" + kind + ":"
            if value.startswith(prefix):
                return named(client, kind, value[len(prefix):])
        raise ValueError(f"unknown recipe variable: {value}")
    return value


def run(client, recipe, variables, audit_path: Path):
    if not isinstance(recipe, dict) or recipe.get("format") != "original-live2d-recipe-v1":
        raise ValueError("expected original-live2d-recipe-v1")
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
        raise ValueError("recipe needs 1–128 declarative steps")
    for step in steps:
        if (not isinstance(step, dict) or set(step) != {"operation", "request"}
                or step["operation"] not in ALLOWED or not isinstance(step["request"], dict)):
            raise ValueError("unsupported recipe step; no painting, script or shell operations are allowed")
        validate_operation_units(step["operation"], step["request"])
    audit = {"status": "RUNNING", "art_acceptance": "NOT_CLAIMED", "steps": []}
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    for index, step in enumerate(steps):
        operation = step["operation"]
        request = resolve(step["request"], client, variables)
        schema, _ = client.call("workspace_get_operation", {"id": operation})
        properties = schema["request_schema"].get("properties", {})
        if "request_id" in properties:
            request.setdefault("request_id", "original-authoring-" + uuid.uuid4().hex)
        if "state" in properties or "project_id" in properties:
            project = client.project()
            if "state" in properties:
                request.setdefault("state", project["state"])
            if "project_id" in properties:
                request.setdefault("project_id", project["project_id"])
        try:
            result, _ = client.call(operation, request)
        except Exception as error:
            audit["status"] = "FAILED"
            audit["failed_step"] = index
            audit["error_type"] = type(error).__name__
            audit_path.write_text(json.dumps(audit, indent=2) + "\n")
            raise
        audit["steps"].append({"index": index, "operation": operation, "request": request, "result": result})
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        print(json.dumps({"step": index, "operation": operation, "status": "COMPLETED"}))
    audit["status"] = "COMPLETED_NOT_VISUALLY_ACCEPTED"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", required=True, type=Path, help="Upstream v3.6.7 mcp_proxy.py, development dependency")
    parser.add_argument("--connection-log", required=True, type=Path, help="Private headless startup log; token is never printed")
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--source-project", required=True, type=Path)
    parser.add_argument("--export-directory", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()
    # The log belongs to the explicitly started, private local authoring process.
    lines = args.connection_log.read_text().splitlines()
    endpoint = next(line[9:] for line in lines if line.startswith("endpoint "))
    token = next(line[6:] for line in lines if line.startswith("token "))
    spec = importlib.util.spec_from_file_location("psd2live_upstream_client", args.proxy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recipe = json.loads(args.recipe.read_text())
    variables = {"$input": str(args.input.resolve()), "$source_project": str(args.source_project.resolve()),
                 "$export_directory": str(args.export_directory.resolve())}
    with module.Client(endpoint, token, timeout=180) as client:
        run(client, recipe, variables, args.audit)


if __name__ == "__main__":
    main()
