"""Blender integration fixture ONLY. This is not the requested character or an art asset.

Creates a tiny synthetic rig and cube to exercise exporter/audit metadata. Write only into
a temporary/build directory; never package it or use its render as product evidence.
"""
import argparse
import json
from pathlib import Path
import sys

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avatar_pipeline import ADDON_MODULE, CONTRACT, PARENTS  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--broken", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
if ".build" not in args.output.parts and "/tmp/" not in str(args.output):
    raise RuntimeError("test fixture may only be written under .build or /tmp")
addon_utils.enable("io_scene_gltf2", default_set=False, persistent=False)
addon_utils.enable(ADDON_MODULE, default_set=True, persistent=True)
for existing in list(bpy.data.objects):
    bpy.data.objects.remove(existing, do_unlink=True)
armature = bpy.data.armatures.new("TEST_ONLY_NOT_CHARACTER_RIG")
rig = bpy.data.objects.new("TEST_ONLY_NOT_CHARACTER_RIG", armature)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
contract = json.loads(CONTRACT.read_text())
for index, name in enumerate(contract["required_humanoid"]):
    bone = armature.edit_bones.new(name)
    bone.head = (0.02 * index, 0, 1 + 0.03 * index)
    bone.tail = (0.02 * index, 0, 1.02 + 0.03 * index)
for name, parent in PARENTS.items():
    armature.edit_bones[name].parent = armature.edit_bones[parent]
bpy.ops.object.mode_set(mode="OBJECT")
extension = armature.vrm_addon_extension
extension.spec_version = "1.0"
for name, human_bone in extension.vrm1.humanoid.human_bones.human_bone_name_to_human_bone().items():
    if name.value in armature.bones:
        human_bone.node.bone_name = name.value
extension.vrm1.look_at.type = "bone"
extension.vrm1.meta.vrm_name = "TEST_ONLY_NOT_CHARACTER"
extension.vrm1.meta.version = "fixture-1"
extension.vrm1.meta.authors.add().value = "Automated integration fixture"
bpy.ops.mesh.primitive_cube_add(size=0.1)
mesh = bpy.context.object
mesh.name = "TEST_ONLY_NOT_CHARACTER_MESH"
material = bpy.data.materials.new("TEST_ONLY_MATERIAL")
material.use_nodes = True
mesh.data.materials.append(material)
modifier = mesh.modifiers.new("Fixture skin", "ARMATURE")
modifier.object = rig
mesh.vertex_groups.new(name="head").add(list(range(len(mesh.data.vertices))), 1.0, "REPLACE")
mesh.shape_key_add(name="Basis")
for index, name in enumerate(contract["required_expressions"]):
    key = mesh.shape_key_add(name=f"test_{name}")
    key.data[0].co.z += 0.001 * (index + 1)
    expression = extension.vrm1.expressions.all_name_to_expression_dict()[name]
    bind = expression.morph_target_binds.add()
    bind.node.mesh_object_name = mesh.name
    bind.index = key.name
    bind.weight = 1.0
if args.broken:
    aa = mesh.data.shape_keys.key_blocks["test_aa"]
    for vertex, basis in zip(aa.data, mesh.data.shape_keys.key_blocks[0].data):
        vertex.co = basis.co
    mesh.vertex_groups["head"].remove([0])
bpy.context.view_layer.update()
for existing in list(bpy.data.objects):
    if existing not in (mesh, rig):
        bpy.data.objects.remove(existing, do_unlink=True)
args.output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(args.output))
print("TEST_FIXTURE_ONLY " + str(args.output))
