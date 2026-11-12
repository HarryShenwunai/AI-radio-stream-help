"""Trusted offline Blender worker, invoked by avatar_pipeline.py (not an app plugin)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avatar_pipeline import ADDON_MODULE, CONTRACT, evaluate  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def inspect_source() -> dict:
    scene = bpy.context.scene
    rigs = [o for o in scene.objects if o.type == "ARMATURE" and not o.hide_render]
    rig = rigs[0] if len(rigs) == 1 else None
    humanoid: dict[str, str] = {}
    ancestors: dict[str, list[str]] = {}
    expressions: dict[str, list[dict]] = {}
    look_at = None
    if rig:
        extension = rig.data.vrm_addon_extension
        for bone in rig.data.bones:
            ancestors[bone.name] = [parent.name for parent in bone.parent_recursive]
        if extension.spec_version == "1.0":
            for name, value in extension.vrm1.humanoid.human_bones.human_bone_name_to_human_bone().items():
                if value.node.bone_name:
                    humanoid[name.value] = value.node.bone_name
            look_at = extension.vrm1.look_at.type
            for name, expression in extension.vrm1.expressions.all_name_to_expression_dict().items():
                binds = []
                for bind in expression.morph_target_binds:
                    mesh = scene.objects.get(bind.node.mesh_object_name)
                    delta = 0.0
                    if mesh and mesh.type == "MESH" and mesh.data.shape_keys:
                        blocks = mesh.data.shape_keys.key_blocks
                        key = blocks.get(bind.index)
                        basis = blocks[0]
                        if key and key != basis:
                            delta = max(((a.co - b.co).length for a, b in zip(key.data, basis.data)), default=0.0)
                    binds.append({"mesh": bind.node.mesh_object_name, "key": bind.index,
                                  "weight": bind.weight, "max_delta": delta})
                expressions[name] = binds
    meshes = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        bone_names = {b.name for b in rig.data.bones if b.use_deform} if rig else set()
        groups = {group.index for group in obj.vertex_groups if group.name in bone_names}
        bound = bool(rig and (any(m.type == "ARMATURE" and m.object == rig and m.show_render for m in obj.modifiers)
                     or (obj.parent == rig and obj.parent_type == "BONE" and obj.parent_bone in bone_names)))
        rigid = bool(bound and obj.parent_type == "BONE")
        unweighted, unnormalized, influences = 0, 0, 0
        for vertex in obj.data.vertices:
            weights = [g.weight for g in vertex.groups if g.group in groups and g.weight > 1e-8]
            if not rigid:
                unweighted += not weights
                unnormalized += bool(weights and abs(sum(weights) - 1) > 0.01)
                influences = max(influences, len(weights))
        meshes.append({"name": obj.name, "vertices": len(obj.data.vertices), "rig_bound": bound,
                       "unweighted_vertices": unweighted, "unnormalized_vertices": unnormalized,
                       "max_influences": influences, "uv_layers": len(obj.data.uv_layers),
                       "materials": sum(slot.material is not None for slot in obj.material_slots)})
    # Evaluated instance count includes linked objects and collection instances with modifiers.
    triangles = 0
    graph = bpy.context.evaluated_depsgraph_get()
    for instance in graph.object_instances:
        obj = instance.object
        if obj.type != "MESH" or obj.hide_render:
            continue
        mesh = obj.to_mesh()
        try:
            mesh.calc_loop_triangles()
            triangles += len(mesh.loop_triangles)
        finally:
            obj.to_mesh_clear()
    images = [{"name": image.name, "width": image.size[0], "height": image.size[1],
               "packed": bool(image.packed_file or image.packed_files)}
              for image in bpy.data.images if image.type == "IMAGE" and image.users > 0]
    return {"blender": bpy.app.version_string, "offline": not bpy.app.online_access,
            "armature_count": len(rigs), "humanoid": humanoid, "bone_ancestors": ancestors,
            "look_at_type": look_at, "meshes": meshes, "instance_triangles": triangles,
            "images": images, "expressions": expressions,
            "external_libraries": [library.filepath for library in bpy.data.libraries],
            "authored_motion_actions": [action.name for action in bpy.data.actions],
            "cameras": [obj.name for obj in scene.objects if obj.type == "CAMERA"]}


def render_views(output: Path) -> dict:
    """Use authored camera/light intent; do not replace reference-specific art direction."""
    names = ("AVATAR_closeup", "AVATAR_fullbody", "AVATAR_profile", "AVATAR_back")
    cameras = {name: bpy.context.scene.objects.get(name) for name in names}
    missing = [name for name, obj in cameras.items() if obj is None or obj.type != "CAMERA"]
    if missing:
        return {"status": "BLOCKED_AUTHORED_CAMERAS_MISSING", "missing": missing}
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    directory = output / "renders"
    directory.mkdir(exist_ok=True)
    files = []
    for name, camera in cameras.items():
        scene.camera = camera
        scene.render.filepath = str(directory / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    rig = next(obj for obj in scene.objects if obj.type == "ARMATURE" and not obj.hide_render)
    expressions = rig.data.vrm_addon_extension.vrm1.expressions.all_name_to_expression_dict()
    previous = {name: expression.preview for name, expression in expressions.items()}
    try:
        scene.camera = cameras["AVATAR_closeup"]
        for expression in expressions.values():
            expression.preview = 0
        for name in json.loads(CONTRACT.read_text())["required_expressions"]:
            expression = expressions[name]
            expression.preview = 1
            bpy.context.view_layer.update()
            scene.render.filepath = str(directory / f"expression-{name}.png")
            bpy.ops.render.render(write_still=True)
            files.append(scene.render.filepath)
            expression.preview = 0
    finally:
        for name, value in previous.items():
            expressions[name].preview = value
    return {"status": "RENDERED_NOT_VISUALLY_ACCEPTED", "files": files,
            "turntable": "NOT_RUN", "actual_app": "NOT_RUN"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("inventory", "audit"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.output.mkdir(parents=True, exist_ok=True)
    addon_utils.enable("io_scene_gltf2", default_set=False, persistent=False)
    # The add-on's handlers require a preferences entry, even in an ephemeral factory session.
    # default_set=True creates that in memory; we never call save_userpref().
    addon_utils.enable(ADDON_MODULE, default_set=True, persistent=True)
    if not addon_utils.check(ADDON_MODULE)[1]:
        raise RuntimeError("VRM add-on failed to enable")
    if bpy.app.online_access:
        raise RuntimeError("worker must run with --offline-mode")
    if args.mode == "inventory":
        write_json(args.output / "inventory.json", {
            "blender": bpy.app.version_string, "python": sys.version.split()[0],
            "vrm_addon_enabled": addon_utils.check(ADDON_MODULE)[1],
            "vrm_export_operator": bool(bpy.ops.export_scene.vrm.get_rna_type()),
            "gltf_export_operator": bool(bpy.ops.export_scene.gltf.get_rna_type()),
            "offline": not bpy.app.online_access,
            "target_character_created": False,
            "gpu_render_and_windows_performance": "NOT_RUN",
        })
        return
    bpy.ops.wm.open_mainfile(filepath=str(args.blend), use_scripts=False)
    observations = inspect_source()
    verdict = evaluate(observations, json.loads(CONTRACT.read_text()))
    if args.export and verdict["structural_status"] == "PASS":
        destination = args.output / "candidate.vrm"
        temporary = args.output / "candidate.partial.vrm"
        result = bpy.ops.export_scene.vrm(filepath=str(temporary), check_existing=False,
                                         use_addon_preferences=False, export_invisibles=False)
        if "FINISHED" not in result or not temporary.is_file():
            raise RuntimeError("VRM exporter did not produce a candidate")
        if temporary.stat().st_size > json.loads(CONTRACT.read_text())["limits"]["vrm_bytes"]:
            raise RuntimeError("exported candidate exceeds runtime VRM byte budget")
        with temporary.open("rb") as stream:
            if stream.read(4) != b"glTF":
                raise RuntimeError("exporter did not produce a GLB container")
        temporary.replace(destination)
        observations["exported_candidate"] = str(destination)
    if args.render:
        if verdict["structural_status"] == "PASS":
            observations["renders"] = render_views(args.output)
        else:
            observations["renders"] = {"status": "BLOCKED_STRUCTURAL_FAILURE"}
    write_json(args.output / "observations.json", observations)


if __name__ == "__main__":
    main()
