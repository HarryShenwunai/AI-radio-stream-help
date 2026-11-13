#!/usr/bin/env python3
"""Compile declared source parts/texture anchors into real authoring operations.

This is an authoring recipe, not a completed character. It refuses absent parts
and anchors. Exported Core geometry and visible artwork still require separate
acceptance. CupHold compensation is deliberately not invented by this builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def point(value):
    import math
    result = [value["x"], value["y"]]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in result):
        raise ValueError("source anchor must be two finite canvas coordinates")
    return result


def compile_recipe(manifest, body_anchors, hands, wrist_anchors):
    layers = {layer["name"]: layer for layer in manifest["layers"]}
    if len(layers) != len(manifest["layers"]):
        raise ValueError("source layer names must be unique")
    required = {"topwear", "cup", "upper lip", "lower lip", "mouth", "mouth close", "upper teeth", "tongue"}
    for side in ("l", "r"):
        required.update({"upperarm-" + side, "forearm-" + side, "hand-" + side})
        required.update("finger-" + finger + "-" + side for finger in ("thumb", "index", "middle", "ring", "little"))
    if missing := required - layers.keys():
        raise ValueError("missing actual source parts: " + ", ".join(sorted(missing)))
    if not layers["mouth close"].get("visible", True):
        raise ValueError("closed-mouth artwork must be a real enabled source layer")
    fingers = {item["name"]: item for item in hands["fingers"]}
    if set(fingers) != {name for name in required if name.startswith("finger-")}:
        raise ValueError("need actual texture-support anchors for all ten fingers")
    steps = []

    def add(operation, **request):
        steps.append({"operation": operation, "request": request})

    add("project_import_psd", path="$input", discard_unsaved=True)
    add("settings_update", changes={"atlasSize": 4096, "meshSpacing": 40, "alphaThreshold": 8,
        "mouthOutlineEnabled": False, "seeThroughBrows": False, "seeThroughEyes": False,
        "runtimeTarget": "Cubism50", "exportHiddenDrawables": False})
    for name in sorted(layers):
        if name.startswith(("upperarm-", "forearm-", "hand-", "finger-", "cuff-front-")):
            role = "handwear"
        elif name == "cup":
            role = "objects"
        elif name in ("upper lip", "lower lip", "mouth close"):
            role = "face_detail"
        elif name == "mouth":
            role = "mouth_open"
        elif name.startswith("lower eyelash-"):
            role = "eyelash"
        else:
            continue
        side = "left" if name.endswith("-l") else "right" if name.endswith("-r") else "none"
        add("layer_classify", layer_id="$layer:" + name, role=role, side=side)
    add("rig_generate")
    edits = [{"action": "bind", "kind": "mesh", "id": "$mesh:" + name,
              "parent_id": "$parent:topwear", "space": "canvas"}
             for name in sorted(layers) if name.startswith(("upperarm-", "forearm-", "hand-", "finger-", "cuff-front-"))]
    edits.append({"action": "bind", "kind": "mesh", "id": "$mesh:cup", "parent_id": None, "space": "canvas"})
    add("object_edit_appearance", edits=edits)
    rotation_axes = []

    def rotation(identifier, names, pivot, parameter, extent):
        add("canvas_rotation", id=identifier, name=identifier, meshes=["$mesh:" + name for name in names],
            add_to="parent_of_selected", origin=point(pivot), angle=0, preservePose=True)
        rotation_axes.append((identifier, parameter, extent))

    for side in ("l", "r"):
        suffix = side.upper()
        digits = sorted(name for name in fingers if name.endswith("-" + side))
        hand = ["hand-" + side, *digits]
        rim = ["cuff-front-" + side] if "cuff-front-" + side in layers else []
        forearm = ["forearm-" + side, *rim, *hand]
        rotation("OriginalShoulder" + suffix, ["upperarm-" + side, *forearm],
                 body_anchors["shoulder_" + side]["target"], "ParamArm" + suffix, 4)
        rotation("OriginalElbow" + suffix, forearm,
                 body_anchors["elbow_" + side]["target"], "ParamForearm" + suffix, 6)
        rotation("OriginalWrist" + suffix, hand, wrist_anchors[side], "ParamHand" + suffix, 10)
        for name in digits:
            digit = name.split("-")[1].title()
            rotation("OriginalFinger" + digit + suffix, [name],
                     fingers[name]["texture_supported_anchors"]["root_target"],
                     "ParamFinger" + digit + suffix, 12)
    for _, parameter, extent in rotation_axes:
        add("parameter_create", parameter_id=parameter, name=parameter, min=-extent, max=extent, default=0)
    keys = []
    for identifier, parameter, extent in rotation_axes:
        for value in (-extent, 0, extent):
            keys.append({"op": "set", "target": "rotation:" + identifier,
                         "key": {parameter: value}, "geometry": {"angle": value}})
    cup = layers["cup"]
    cx, cy = cup.get("x", 0) + cup["width"] / 2, cup.get("y", 0) + cup["height"] / 2
    add("canvas_rotation", id="OriginalCupRoot", name="Independent cup root", meshes=["$mesh:cup"],
        add_to="parent_of_selected", origin=[cx, cy], angle=0, preservePose=True)
    for parameter, extent in (("ParamCupX", 500), ("ParamCupY", 500), ("ParamCupRotation", 45)):
        add("parameter_create", parameter_id=parameter, name=parameter, min=-extent, max=extent, default=0)
    add("parameter_create", parameter_id="ParamCupVisible", name="Cup visible", min=0, max=1, default=1)
    for x in (-500, 0, 500):
        for y in (-500, 0, 500):
            for angle in (-45, 0, 45):
                keys.append({"op": "set", "target": "rotation:OriginalCupRoot",
                    "key": {"ParamCupX": x, "ParamCupY": y, "ParamCupRotation": angle},
                    "geometry": {"originX": cx + x, "originY": cy + y, "angle": angle, "scale": 1}})
    for visible in (0, 1):
        keys.append({"op": "set", "target": "$target:cup", "key": {"ParamCupVisible": visible},
                     "channels": {"opacity": visible}})
    # Explicit channels avoid release-specific closed/open auto-classification ambiguities.
    for name in ("mouth", "upper teeth", "tongue", "upper lip", "lower lip", "mouth close"):
        for opening, visible in ((0, 0), (.2, 1), (1, 1)):
            if name == "mouth close":
                visible = 1 - visible
            keys.append({"op": "set", "target": "$target:" + name,
                         "key": {"ParamMouthOpenY": opening}, "channels": {"opacity": visible}})
    # API accepts at most 128 edits per atomic request.
    for start in range(0, len(keys), 96):
        add("keyform_apply", changes=keys[start:start + 96])
    add("project_save_as", path="$source_project")
    add("project_export_model", output_directory="$export_directory")
    if len(steps) > 128:
        raise ValueError("recipe exceeds authoring runner operation bound")
    return {"format": "original-live2d-recipe-v1", "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--hands", required=True, type=Path)
    parser.add_argument("--wrists", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("write a new authoring revision")
    recipe = compile_recipe(json.loads(args.layers.read_text()), json.loads(args.body.read_text())["rig_anchors"],
                            json.loads(args.hands.read_text()), json.loads(args.wrists.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(recipe, indent=2) + "\n")


if __name__ == "__main__":
    main()
