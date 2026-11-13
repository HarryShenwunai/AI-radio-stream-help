#!/usr/bin/env python3
"""Author a single original cup with direct Follow->Manual->mesh Warp geometry.

The constant outer Rotation never sits between the follow lattice and the mesh.
There is no separately interpolated mesh scale/norm. This is an experimental
flattened follow-field authoring tool, not an accepted rig generator: the 810-key
revision failed 43 of 512 independent interior poses. Keep it reproducible for
regression; exact native-chain or native-glue designs need their own acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import itertools
import math
from pathlib import Path

from avatar_live2d_hold_recipe import BODY_AXES, sample_core, similarity
from avatar_live2d_units import CanvasBoundsPx, LocalDeltaFraction


def source_fingerprints(paths):
    """Bind actual inputs and imported geometry helpers before Core evaluation."""
    return {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in paths}


def assert_sources_unchanged(before):
    if source_fingerprints(before) != before:
        raise ValueError("authoring input changed during actual Core sampling")


def validate_observed_grid(samples):
    axes = samples["axes"]
    identifiers = [axis["id"] for axis in axes]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("body axes must be unique")
    keys = []
    for axis in axes:
        values = axis["keys"]
        if (not values or len(set(values)) != len(values)
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in values)):
            raise ValueError("body axis keys must be finite and unique")
        keys.append(values)
    expected = set(itertools.product(*keys))
    observed = set()
    for sample in samples["samples"]:
        pose = sample["pose"]
        if set(pose) != set(identifiers):
            raise ValueError("observed pose must contain exactly the declared body axes")
        signature = tuple(pose[identifier] for identifier in identifiers)
        if signature not in expected:
            raise ValueError("observed body key is outside the declared Cartesian grid")
        if signature in observed:
            raise ValueError("duplicate observed body key")
        observed.add(signature)
    if observed != expected:
        raise ValueError("incomplete actual body grid")


def compile_clean_recipe(samples, project, bounds):
    validate_observed_grid(samples)
    frame = CanvasBoundsPx(*bounds)
    center = [frame.x + frame.width / 2, frame.y + frame.height / 2]
    steps = []

    def add(operation, **request):
        steps.append({"operation": operation, "request": request})

    add("project_open", path=str(project.resolve()), discard_unsaved=True)
    add("object_edit_appearance", edits=[{"action": "bind", "kind": "mesh", "id": "$mesh:cup",
        "parent_id": None, "space": "canvas"}])
    add("rig_edit_structure", edits=[{"action": "delete", "kind": "rotation", "id": "OriginalCupRoot"}])
    rectangle = {"x": frame.x, "y": frame.y, "w": frame.width, "h": frame.height}
    add("canvas_warp", id="OriginalCupManualWarp", name="Independent cup transforms", meshes=["$mesh:cup"],
        add_to="parent_of_selected", bounds=rectangle, rows=1, columns=1)
    seeds, changes = [], []
    for x in (-500, 0, 500):
        for y in (-500, 0, 500):
            for index in range(13):
                angle = -45 + 7.5 * index
                key = {"ParamCupX": x, "ParamCupY": y, "ParamCupRotation": angle}
                seeds.append({"op": "seed", "target": "warp:OriginalCupManualWarp", "key": key})
                changes.append({"target": "warp:OriginalCupManualWarp", "key": key, "operations": [
                    {"type": "rotate", "degrees": angle, "pivot": [.5, .5]},
                    {"type": "translate", "delta": LocalDeltaFraction(x / frame.width, y / frame.height).as_list()}]})
    add("keyform_apply", changes=seeds)
    add("rig_deform", changes=changes)
    add("canvas_warp", id="OriginalCupHoldFollow", name="Direct affine cup body follow", meshes=[],
        add_to="parent_of_deformer", deformer_id="OriginalCupManualWarp", bounds=rectangle, rows=1, columns=1)
    add("canvas_rotation", id="OriginalCupRoot", name="Constant independent cup root", meshes=[],
        add_to="parent_of_deformer", deformer_id="OriginalCupHoldFollow", origin=[0, 0], angle=0, preservePose=True)
    add("parameter_create", parameter_id="ParamCupHold", name="Cup hold", min=0, max=1, default=1)
    seeds, changes = [], []
    poses = set()
    for sample in samples["samples"]:
        pose = sample["pose"]
        signature = tuple(pose[axis["id"]] for axis in samples["axes"])
        if signature in poses:
            raise ValueError("duplicate observed body key")
        poses.add(signature)
        for hold in (0, 1):
            seeds.append({"op": "seed", "target": "warp:OriginalCupHoldFollow", "key": {**pose, "ParamCupHold": hold}})
        transform = similarity(samples["baseline"], sample["palms"], center)
        if all(pose[axis["id"]] == axis["default"] for axis in samples["axes"]):
            if (abs(transform["scale"] - 1) > 1e-10 or abs(transform["degrees"]) > 1e-10
                    or max(map(abs, transform["delta"])) > 1e-8):
                raise ValueError("actual default pose must be identity")
        changes.append({"target": "warp:OriginalCupHoldFollow", "key": {**pose, "ParamCupHold": 1}, "operations": [
            {"type": "scale", "factors": [transform["scale"]] * 2, "pivot": [.5, .5]},
            {"type": "rotate", "degrees": transform["degrees"], "pivot": [.5, .5]},
            {"type": "translate", "delta": LocalDeltaFraction(transform["delta"][0] / frame.width,
                transform["delta"][1] / frame.height).as_list()}]})
    if len(poses) != math.prod(len(axis["keys"]) for axis in samples["axes"]):
        raise ValueError("incomplete actual body grid")
    for start in range(0, len(seeds), 96):
        add("keyform_apply", changes=seeds[start:start + 96])
    for start in range(0, len(changes), 64):
        add("rig_deform", changes=changes[start:start + 64])
    add("project_save_as", path="$source_project")
    add("project_export_model", output_directory="$export_directory")
    if len(steps) > 128:
        raise ValueError("authoring recipe exceeds bounded operation count")
    return {"format": "original-live2d-recipe-v1", "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "core-script", "grip-contract", "project", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cup-bounds", type=float, nargs=4, required=True)
    parser.add_argument("--experimental-flattened-follow", action="store_true",
                        help="Explicitly reproduce a known insufficient approximation; not a final rig")
    args = parser.parse_args()
    if not args.experimental_flattened_follow:
        raise ValueError("flattened follow is experimental and failed independent validation; "
                         "explicit --experimental-flattened-follow required")
    if args.output.exists():
        raise ValueError("write a fresh authoring revision")
    contract = json.loads(args.grip_contract.read_text())
    parameters = {p["id"]: p for p in contract["parameters"]}
    axes = []
    for identifier in BODY_AXES:
        parameter = parameters[identifier]
        lo, rest, hi = (parameter[key] for key in ("min", "default", "max"))
        values = [lo, rest, hi]
        if identifier == "ParamBodyLean":
            values.extend([(lo + rest) / 2, (rest + hi) / 2])
        axes.append({"id": identifier, "values": sorted(set(values))})
    grips = [contract["landmarks"]["grip_" + side + "_palm"] for side in ("r", "l")]
    moc = args.model.parent / json.loads(args.model.read_text())["FileReferences"]["Moc"]
    helpers = [Path(__file__), Path(__file__).with_name("avatar_live2d_hold_recipe.py"),
               Path(__file__).with_name("avatar_live2d_units.py")]
    sources = [args.model, moc, args.core_script, args.grip_contract, args.project, *helpers]
    before = source_fingerprints(sources)
    samples, sampled_moc = sample_core(args.model, args.core_script, grips, axes)
    if sampled_moc.resolve() != moc.resolve():
        raise ValueError("actual Core sampled an unexpected MOC path")
    assert_sources_unchanged(before)
    recipe = compile_clean_recipe(samples, args.project, args.cup_bounds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(recipe, indent=2) + "\n")
    samples["source_sha256"] = before
    samples["source_stability"] = "BEFORE_AND_AFTER_ACTUAL_CORE_SAMPLING"
    samples["status"] = "EXPERIMENTAL_ACTUAL_CORE_SOURCE_KEYS_NOT_EXPORTED_OR_ACCEPTED"
    args.output.with_suffix(".actual-core-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    print(json.dumps({"body_keys": len(samples["samples"]), "operations": len(recipe["steps"]),
                      "representation": "one-cup direct nested Warp, no Rotation or separately interpolated norm below follow"}))


if __name__ == "__main__":
    main()
