#!/usr/bin/env python3
"""Audit editable avatar sources. Structural success never implies visual completion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "assets/character-source/contract.json"
ADDON_VERSION = "4.10.5"
ADDON_SHA256 = "f305700eac4d48340c2845cdcad18964335760e4df4171a8f734daa4502a9479"
ADDON_MODULE = "VRM_Addon_for_Blender-release"
PARENTS = {
    "spine": "hips", "head": "spine", "leftEye": "head", "rightEye": "head",
    "leftUpperArm": "spine", "rightUpperArm": "spine",
    "leftLowerArm": "leftUpperArm", "rightLowerArm": "rightUpperArm",
    "leftHand": "leftLowerArm", "rightHand": "rightLowerArm",
    "leftUpperLeg": "hips", "rightUpperLeg": "hips",
    "leftLowerLeg": "leftUpperLeg", "rightLowerLeg": "rightUpperLeg",
    "leftFoot": "leftLowerLeg", "rightFoot": "rightLowerLeg",
}


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate(report: dict, contract: dict) -> dict:
    """Validate actual Blender observations, not artist-supplied pass booleans."""
    issues: list[str] = []
    limits = contract["limits"]
    if report.get("armature_count") != 1:
        issues.append("exactly_one_armature_required")
    bones = report.get("humanoid", {})
    if len(set(bones.values())) != len(bones.values()):
        issues.append("duplicate_humanoid_mapping")
    ancestors = report.get("bone_ancestors", {})
    for name in contract["required_humanoid"]:
        if not bones.get(name) or bones[name] not in ancestors:
            issues.append(f"missing_humanoid:{name}")
    for child, parent in PARENTS.items():
        if child in bones and parent in bones and bones[parent] not in ancestors.get(bones[child], []):
            issues.append(f"invalid_hierarchy:{child}:{parent}")
    if report.get("look_at_type") != "bone":
        issues.append("bone_eye_look_at_required")
    meshes = report.get("meshes", [])
    if not meshes:
        issues.append("no_renderable_mesh")
    for mesh in meshes:
        name = mesh["name"]
        if not mesh.get("vertices"):
            issues.append(f"empty_mesh:{name}")
        if not mesh.get("rig_bound"):
            issues.append(f"mesh_not_bound_to_humanoid:{name}")
        if mesh.get("unweighted_vertices", 0):
            issues.append(f"unweighted_vertices:{name}")
        if mesh.get("max_influences", 0) > limits["vertex_influences"]:
            issues.append(f"too_many_influences:{name}")
        if mesh.get("unnormalized_vertices", 0):
            issues.append(f"unnormalized_weights:{name}")
        if not mesh.get("uv_layers"):
            issues.append(f"missing_uv:{name}")
        if not mesh.get("materials"):
            issues.append(f"missing_material:{name}")
    # Count rendered instances, including linked meshes, not only unique datablocks.
    if report.get("instance_triangles", 0) > limits["triangles_candidate_ceiling"]:
        issues.append("triangle_review_budget_exceeded")
    images = report.get("images", [])
    if len(images) > limits["texture_images"]:
        issues.append("texture_image_count_exceeded")
    if sum(i["width"] * i["height"] for i in images) > limits["texture_pixels_total"]:
        issues.append("texture_pixel_budget_exceeded")
    for image in images:
        if min(image["width"], image["height"]) <= 0:
            issues.append(f"invalid_image:{image['name']}")
        if max(image["width"], image["height"]) > limits["texture_edge"]:
            issues.append(f"texture_edge_exceeded:{image['name']}")
        if not image.get("packed"):
            issues.append(f"unpacked_source_image:{image['name']}")
    if report.get("external_libraries"):
        issues.append("unpacked_external_blend_libraries")
    expressions = report.get("expressions", {})
    renderable_mesh_names = {mesh["name"] for mesh in meshes}
    for name in contract["required_expressions"]:
        binds = expressions.get(name, [])
        # A named key or material-only bind cannot demonstrate eyelid/mouth geometry.
        if not any(b.get("mesh") in renderable_mesh_names and b.get("weight", 0) > 0
                   and b.get("max_delta", 0) > 1e-6 for b in binds):
            issues.append(f"missing_nonzero_expression_bind:{name}")
    return {
        "structural_status": "FAIL" if issues else "PASS",
        "issues": issues,
        "visual_reference_acceptance": "NOT_RUN",
        "runtime_performance_acceptance": "NOT_RUN",
        "final_character_complete": False,
    }


def setup_addon(archive: Path, destination: Path) -> dict:
    """Explicit local dependency install; archive must match the official release digest."""
    if file_sha(archive) != ADDON_SHA256:
        raise ValueError("VRM add-on archive SHA256 does not match the pinned official release")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("destination must be empty; existing dependency is not overwritten")
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > 32 * 1024 * 1024:
            raise ValueError("unexpected expanded add-on size")
        for info in infos:
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in info.filename:
                raise ValueError("unsafe archive path")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("archive symlinks are not allowed")
            if not relative.parts or relative.parts[0] != ADDON_MODULE:
                raise ValueError("unexpected archive root")
        destination.mkdir(parents=True, exist_ok=True)
        bundle.extractall(destination)
        receipt = {"version": ADDON_VERSION, "archive_sha256": ADDON_SHA256, "files": {
            info.filename: hashlib.sha256(bundle.read(info)).hexdigest()
            for info in infos if not info.is_dir()
        }}
    (destination / ".avatar-addon-lock.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return {"version": ADDON_VERSION, "sha256": ADDON_SHA256, "destination": str(destination)}


def verify_addon(destination: Path) -> None:
    receipt = json.loads((destination / ".avatar-addon-lock.json").read_text())
    if receipt.get("archive_sha256") != ADDON_SHA256 or receipt.get("version") != ADDON_VERSION:
        raise ValueError("unexpected add-on installation receipt")
    files = receipt["files"]
    for name, expected in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe add-on receipt path")
        path = destination / relative
        if path.is_symlink() or file_sha(path) != expected:
            raise ValueError(f"installed add-on was modified: {name}")
    for path in (destination / ADDON_MODULE).rglob("*.py"):
        if path.is_symlink() or path.relative_to(destination).as_posix() not in files:
            raise ValueError("unexpected executable file in add-on directory")


def run_worker(args: argparse.Namespace) -> int:
    contract = json.loads(CONTRACT.read_text())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.command == "audit":
        if (output / "candidate.vrm").exists():
            raise ValueError("output already contains a candidate; use a fresh directory to avoid stale evidence")
        if not args.reference or not Path(args.reference).is_file():
            result = {"status": "BLOCKED_REFERENCE_MISSING", "final_character_complete": False}
            (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
            return 2
        if not args.blend or not Path(args.blend).is_file():
            print(json.dumps({"status": "BLOCKED_SOURCE_BLEND_MISSING", "final_character_complete": False}))
            return 2
    scripts = Path(args.addons).resolve().parent
    addon = Path(args.addons).resolve() / ADDON_MODULE
    if not addon.is_dir():
        raise ValueError("Pinned VRM add-on not installed in --addons; use setup-addon first")
    verify_addon(Path(args.addons).resolve())
    command = [args.blender, "--background", "--factory-startup", "--disable-autoexec", "--offline-mode",
               "--python-exit-code", "8", "--python", str(ROOT / "scripts/avatar_blender_worker.py"),
               "--", "--mode", args.command, "--output", str(output)]
    if args.command == "audit":
        command += ["--blend", str(Path(args.blend).resolve())]
    if getattr(args, "export", False):
        command.append("--export")
    if getattr(args, "render", False):
        command.append("--render")
    env = dict(os.environ)
    env["BLENDER_USER_CONFIG"] = str(output / "blender-config")
    env["BLENDER_USER_SCRIPTS"] = str(scripts)
    # Do not inherit unrelated cloud credentials into the offline modeling process.
    for key in list(env):
        if any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            env.pop(key)
    with (output / "blender.log").open("w") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        print(json.dumps({"status": "BLENDER_FAILED", "exit_code": result.returncode, "log": str(output / 'blender.log')}))
        return result.returncode
    if args.command == "inventory":
        print((output / "inventory.json").read_text())
        return 0
    observations = json.loads((output / "observations.json").read_text())
    verdict = evaluate(observations, contract)
    verdict.update({"source_sha256": file_sha(Path(args.blend)),
                    "reference_sha256": file_sha(Path(args.reference)),
                    "blender": observations["blender"],
                    "exported_candidate": observations.get("exported_candidate")})
    (output / "audit.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["structural_status"] == "PASS" else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup-addon", help="Install SHA-pinned official ZIP into a local Blender scripts/addons directory")
    setup.add_argument("--archive", required=True, type=Path)
    setup.add_argument("--addons", default=str(ROOT / ".build/avatar/scripts/addons"), type=Path)
    for name in ("inventory", "audit"):
        child = sub.add_parser(name)
        child.add_argument("--blender", default="/usr/bin/blender")
        child.add_argument("--addons", default=str(ROOT / ".build/avatar/scripts/addons"))
        child.add_argument("--output", default=str(ROOT / f".build/avatar/{name}"))
        if name == "audit":
            child.add_argument("--blend")
            child.add_argument("--reference")
            child.add_argument("--export", action="store_true", help="Export candidate only after structural validation passes")
            child.add_argument("--render", action="store_true", help="Render views from authored AVATAR_* cameras")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup-addon":
            print(json.dumps(setup_addon(args.archive, args.addons), indent=2))
            return 0
        return run_worker(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "ERROR", "reason": str(error), "final_character_complete": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
