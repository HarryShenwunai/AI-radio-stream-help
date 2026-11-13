#!/usr/bin/env python3
"""Fit a root cup-follow warp to genuine Core palm attachments at body keys.

Reads the owner's local Core and an original model. No substitute motion engine
or predicted hand coordinates are used. Hold=0 stays independent at every body
key; Hold=1 follows the two observed attachment points. Exported interpolation
and visible art still need independent actual-Core acceptance.
"""
from __future__ import annotations

import argparse
import base64
import cmath
import hashlib
import json
import math
from pathlib import Path
from avatar_live2d_units import CanvasBoundsPx, LocalDeltaFraction, restore_cup_rotation_keys

BODY_AXES = ("ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ",
             "ParamBodyLean", "ParamProportion", "ParamBreath")


def similarity(base, posed, center):
    p0, p1 = (complex(*point) for point in base)
    q0, q1 = (complex(*point) for point in posed)
    if abs(p1 - p0) < 1 or abs(q1 - q0) < 1:
        raise ValueError("distinct real palm attachment points required")
    ratio = (q1 - q0) / (p1 - p0)
    target = q0 + ratio * (complex(*center) - p0)
    delta = target - complex(*center)
    if not .5 < abs(ratio) < 2:
        raise ValueError("unexpected body-follow scale; inspect the actual sampled pose")
    return {"scale": abs(ratio), "degrees": math.degrees(cmath.phase(ratio)),
            "delta": [delta.real, delta.imag]}


def sample_core(model, core, grips, requested_axes=None):
    from playwright.sync_api import sync_playwright
    setting = json.loads(model.read_text())
    moc = model.parent / setting["FileReferences"]["Moc"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
        page = browser.new_page()
        page.add_script_tag(content="(function(){var WebAssembly={};\n" + core.read_text()
                                 + "\nwindow.Live2DCubismCore=Live2DCubismCore;})();")
        result = page.evaluate(r"""input => {
          const C=Live2DCubismCore, bytes=Uint8Array.from(atob(input.moc),x=>x.charCodeAt(0));
          if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('actual Core rejects MOC');
          const moc=C.Moc.fromArrayBuffer(bytes.buffer),model=C.Model.fromMoc(moc),p=model.parameters,d=model.drawables,c=model.canvasinfo;
          const axes=input.axes.map(spec=>{const id=typeof spec==='string'?spec:spec.id;
            const i=p.ids.indexOf(id);if(i<0)throw Error('missing actual body axis '+id);
            const keys=typeof spec==='string'?[p.minimumValues[i],p.defaultValues[i],p.maximumValues[i]]:spec.values;
            if(!keys.includes(p.defaultValues[i])||keys.some(v=>!Number.isFinite(v)||v<p.minimumValues[i]||v>p.maximumValues[i]))throw Error('invalid observed axis probe');
            return {id,min:p.minimumValues[i],default:p.defaultValues[i],max:p.maximumValues[i],index:i,
                    keys:Array.from(new Set(keys))};});
          function point(anchor){const i=d.ids.indexOf(anchor.drawable_id);if(i<0)throw Error('missing actual palm');
            let x=0,y=0;for(let n=0;n<3;n++){const j=anchor.vertex_indices[n],w=anchor.weights[n];
              if(j<0||j>=d.vertexCounts[i])throw Error('stale palm vertex index');x+=d.vertexPositions[i][j*2]*w;y+=d.vertexPositions[i][j*2+1]*w;}
            return [c.CanvasOriginX+x*c.PixelsPerUnit,c.CanvasOriginY-y*c.PixelsPerUnit];}
          p.values.set(p.defaultValues);model.update();const baseline=input.grips.map(point);
          baseline.forEach((xy,i)=>{if(Math.hypot(...xy.map((v,k)=>v-input.grips[i].source_canvas[k]))>.01)throw Error('stale grip landmark');});
          const samples=[];function visit(index,pose){if(index===axes.length){p.values.set(p.defaultValues);
            axes.forEach(a=>p.values[a.index]=pose[a.id]);model.update();samples.push({pose:{...pose},palms:input.grips.map(point)});return;}
            const a=axes[index];for(const value of a.keys){pose[a.id]=value;visit(index+1,pose);}}
          visit(0,{});const result={actual_core_version:C.Version.csmGetVersion(),axes,baseline,samples,
            evaluations:samples.length+1,canvasInfo:{width:c.CanvasWidth,height:c.CanvasHeight,originX:c.CanvasOriginX,originY:c.CanvasOriginY,ppu:c.PixelsPerUnit}};
          model.release();moc._release();return result;
        }""", {"moc": base64.b64encode(moc.read_bytes()).decode(), "axes": requested_axes or BODY_AXES, "grips": grips})
        browser.close()
    return result, moc


def compile_recipe(samples, project, bounds, *, reuse_identity_parent=False, mesh_scale_pivot=None):
    x, y, width, height = bounds
    frame = CanvasBoundsPx(x, y, width, height)
    center = [x + width / 2, y + height / 2]
    if width <= 0 or height <= 0:
        raise ValueError("real cup bounds required")
    steps = []

    def add(operation, **request):
        steps.append({"operation": operation, "request": request})

    add("project_open", path=str(project.resolve()), discard_unsaved=True)
    if not reuse_identity_parent:
        add("canvas_warp", id="OriginalCupHoldFollow", name="Cup hold follows actual palm attachments",
            add_to="parent_of_deformer", deformer_id="OriginalCupRoot", meshes=[],
            bounds={"x": x, "y": y, "w": width, "h": height}, rows=1, columns=1)
    # v3.6.7 drops every child Rotation key here and takes its first (minimum)
    # origin instead of the default. Restore all actual CupX/Y/Rotation keys in
    # the new parent-Warp UV frame before evaluating any held geometry.
        add("keyform_apply", changes=restore_cup_rotation_keys(frame))
        add("parameter_create", parameter_id="ParamCupHold", name="Cup hold", min=0, max=1, default=1)
    seeds, changes = [], []
    for sample in samples["samples"]:
        pose = sample["pose"]
        for hold in (0, 1):
            seeds.append({"op": "seed", "target": "warp:OriginalCupHoldFollow",
                          "key": {**pose, "ParamCupHold": hold}})
            if mesh_scale_pivot is not None:
                seeds.append({"op": "seed", "target": "$target:cup", "key": {**pose, "ParamCupHold": hold}})
        transform = similarity(samples["baseline"], sample["palms"], center)
        is_default = all(pose[axis["id"]] == axis["default"] for axis in samples["axes"])
        if is_default and (abs(transform["scale"] - 1) > 1e-10 or abs(transform["degrees"]) > 1e-10
                           or max(map(abs, transform["delta"])) > 1e-8):
            raise ValueError("actual default body pose must fit an identity transform")
        delta = LocalDeltaFraction(transform["delta"][0] / width, transform["delta"][1] / height)
        changes.append({"target": "warp:OriginalCupHoldFollow", "key": {**pose, "ParamCupHold": 1},
            "operations": [{"type": "scale", "factors": [transform["scale"]] * 2, "pivot": [.5, .5]},
                {"type": "rotate", "degrees": transform["degrees"], "pivot": [.5, .5]},
                {"type": "translate", "delta": delta.as_list()}]})
        if mesh_scale_pivot is not None:
            if len(mesh_scale_pivot) != 2 or any(not 0 <= value <= 1 for value in mesh_scale_pivot):
                raise ValueError("mesh scale pivot must be the measured local origin in normalized rest bounds")
            # A Rotation beneath a Warp transmits origin/direction but retains
            # its authored scale. Apply the observed scale to real cup vertices.
            changes.append({"target": "$target:cup", "key": {**pose, "ParamCupHold": 1},
                "operations": [{"type": "scale", "factors": [transform["scale"]] * 2, "pivot": mesh_scale_pivot}]})
    # First establish the entire identity grid, then deform each observed Hold=1 key.
    # This avoids author_axis default-capture/inverse-placement ambiguity.
    for start in range(0, len(seeds), 96):
        add("keyform_apply", changes=seeds[start:start + 96])
    for start in range(0, len(changes), 64):
        add("rig_deform", changes=changes[start:start + 64])
    add("project_save_as", path="$source_project")
    add("project_export_model", output_directory="$export_directory")
    expected = math.prod(len(axis["keys"]) for axis in samples["axes"])
    if len(changes) != expected * (2 if mesh_scale_pivot is not None else 1) or len(steps) > 128:
        raise ValueError("incomplete body key grid or excessive recipe steps")
    return {"format": "original-live2d-recipe-v1", "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("model", "core-script", "grip-contract", "project", "output"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--cup-bounds", required=True, type=float, nargs=4, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--small-probe", action="store_true")
    parser.add_argument("--reuse-identity-parent", action="store_true")
    parser.add_argument("--mesh-scale-pivot", type=float, nargs=2)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("write a fresh recipe revision")
    contract = json.loads(args.grip_contract.read_text())
    grips = [contract["landmarks"]["grip_" + side + "_palm"] for side in ("r", "l")]
    axes = [{"id": "ParamBodyAngleX", "values": [0, 1]}, {"id": "ParamBreath", "values": [0, .1]}] if args.small_probe else None
    samples, moc = sample_core(args.model, args.core_script, grips, axes)
    recipe = compile_recipe(samples, args.project, args.cup_bounds,
                            reuse_identity_parent=args.reuse_identity_parent, mesh_scale_pivot=args.mesh_scale_pivot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(recipe, indent=2) + "\n")
    sources = [args.model, moc, args.core_script, args.grip_contract, args.project, Path(__file__)]
    samples["source_sha256"] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    samples["status"] = "ACTUAL_CORE_SAMPLES_NOT_EXPORTED_OR_ACCEPTED"
    args.output.with_suffix(".actual-core-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    print(json.dumps({"actual_core_evaluations": samples["evaluations"], "body_grid_keys": len(samples["samples"]),
                      "operations": len(recipe["steps"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
