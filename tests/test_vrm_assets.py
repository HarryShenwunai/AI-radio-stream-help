"""Self-authored GLB fixtures exercise real filesystem, geometry and decoders."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from companion_runtime.assets import AssetStore, AssetError
from companion_runtime import vrm_assets as vrm


def glb(doc, binary):
    doc = copy.deepcopy(doc)
    doc["buffers"] = [{"byteLength": len(binary), **doc.get("buffers", [{}])[0]}]
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
    raw += b" " * (-len(raw) % 4)
    binary += b"\0" * (-len(binary) % 4)
    return struct.pack("<III", 0x46546C67, 2, 28 + len(raw) + len(binary)) + struct.pack("<II", len(raw), 0x4E4F534A) + raw + struct.pack("<II", len(binary), 0x004E4942) + binary


def fixture(version="1", textured=False, jpeg=False):
    """An original triangle + 15 humanoid nodes, never third-party artwork."""
    binary = struct.pack("<9f", -.2, 0, 0, .2, 0, 0, 0, .5, 0)
    bones = sorted(vrm.REQUIRED_BONES)
    doc = {"asset": {"version": "2.0", "generator": "self-authored-test"},
           "buffers": [{"byteLength": len(binary)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-.2, 0, 0], "max": [.2, .5, 0]}],
           "nodes": [{"name": bone, **({"mesh": 0} if i == 0 else {})} for i, bone in enumerate(bones)],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "scenes": [{"nodes": list(range(len(bones)))}], "scene": 0,
           "extensionsUsed": ["VRMC_vrm" if version == "1" else "VRM"]}
    if version == "1":
        doc["extensions"] = {"VRMC_vrm": {"specVersion": "1.0", "meta": {"name": "self-created A", "authors": ["test author"], "licenseUrl": "https://vrm.dev/licenses/1.0/"}, "humanoid": {"humanBones": {bone: {"node": i} for i, bone in enumerate(bones)}}}}
    else:
        doc["extensions"] = {"VRM": {"specVersion": "0.0", "meta": {"title": "self-created B", "author": "another author", "texture": -1}, "humanoid": {"humanBones": [{"bone": bone, "node": i} for i, bone in enumerate(bones)]}}}
        # Distinct geometry and node arrangement, not just a renamed asset.
        binary = struct.pack("<9f", 0, 0, 0, .7, 0, 0, 0, .3, .1)
        doc["accessors"][0].pop("min")
        doc["accessors"][0].pop("max")
        doc["nodes"][0].pop("mesh")
        doc["nodes"][-1]["mesh"] = 0
    if textured:
        output = io.BytesIO()
        image = Image.new("RGB" if jpeg else "RGBA", (13, 17), (110, 30, 140) if jpeg else (110, 30, 140, 190))
        info = PngImagePlugin.PngInfo()
        info.add_text("private-marker", "must be removed")
        image.save(output, format="JPEG" if jpeg else "PNG", **({} if jpeg else {"pnginfo": info}))
        image.close()
        texture = output.getvalue()
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(texture)})
        doc["images"] = [{"bufferView": 1, "mimeType": "image/jpeg" if jpeg else "image/png"}]
        doc["textures"] = [{"source": 0}]
        doc["materials"] = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]
        doc["meshes"][0]["primitives"][0]["material"] = 0
        binary += texture
        doc["buffers"][0]["byteLength"] = len(binary)
    return doc, binary


class VRMAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "assets"
        self.store = AssetStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, doc=None, binary=None, data=None, status=None):
        before = self.store.list_assets()
        if data is None:
            data = glb(doc, binary)
        with self.assertRaises(AssetError) as error:
            self.store.import_vrm(data, "my-custom.vrm")
        if status is not None:
            self.assertEqual(error.exception.status, status)
        self.assertEqual(self.store.list_assets(), before)
        self.assertFalse(any(x.name.startswith(".staging-") for x in self.root.iterdir()))
        return error.exception

    def test_two_independent_vrm_versions_and_png_share_library(self):
        a = self.store.import_vrm(glb(*fixture("1")), "任意角色.vrm")
        b = self.store.import_vrm(glb(*fixture("0", textured=True)), "another.VRM")
        output = io.BytesIO()
        with Image.new("RGBA", (10, 12), (20, 40, 180, 255)) as image:
            image.save(output, format="PNG")
        c = self.store.import_png_states({"idle": output.getvalue()})
        self.assertEqual([a["vrm_version"], b["vrm_version"]], ["1", "0"])
        self.assertEqual(len({a["id"], b["id"], c["id"]}), 3)
        self.assertEqual(len(self.store.list_assets()), 3)
        self.assertEqual(a["states"], {})
        for m in (a, b):
            self.assertEqual(self.store.get(m["id"]), m)
            raw = self.store.resolve(m["id"], "model.vrm").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), m["model"]["sha256"])
            self.assertEqual(len(raw), m["model"]["bytes"])
            self.assertNotIn(str(self.root), json.dumps(m))
            with Image.open(self.store.resolve(m["id"], "thumbnail.png")) as im:
                self.assertEqual(im.size, (128, 128))
            for bad in ("../model.vrm", "manifest.json", "/model.vrm", "idle.png", "MODEL.VRM"):
                with self.assertRaises(AssetError):
                    self.store.resolve(m["id"], bad)

    def test_images_reencoded_without_metadata_and_valid_after_repack(self):
        for jpeg in (False, True):
            m = self.store.import_vrm(glb(*fixture(textured=True, jpeg=jpeg)))
            raw = self.store.resolve(m["id"], "model.vrm").read_bytes()
            self.assertNotIn(b"must be removed", raw)
            doc, binary = vrm._container(raw)
            image = doc["images"][0]
            self.assertEqual(image["mimeType"], "image/png")
            view = doc["bufferViews"][image["bufferView"]]
            with Image.open(io.BytesIO(binary[view["byteOffset"]:view["byteOffset"] + view["byteLength"]])) as im:
                self.assertEqual(im.size, (13, 17))
                self.assertFalse(im.info)
            self.assertEqual(m["budgets"]["texture_pixels"], 221)
            again = self.store.import_vrm(raw)
            self.assertEqual(again["model"]["sha256"], m["model"]["sha256"])

    def test_invalid_container_versions_lengths_chunk_order_and_zip(self):
        raw = glb(*fixture())
        wrong_version = bytearray(raw)
        struct.pack_into("<I", wrong_version, 4, 1)
        extra = raw + struct.pack("<II", 0, 0x004E4942)
        extra = extra[:8] + struct.pack("<I", len(extra)) + extra[12:]
        for data in (b"PK\x03\x04zip", b"{}", raw[:-1], raw + b"x", bytes(wrong_version), extra):
            with self.subTest(data=data[:16]):
                self.reject(data=data)
        self.reject(data=b"x" * (vrm.MAX_VRM_BYTES + 1), status=413)

    def test_duplicate_json_fields_and_nested_documents_rejected(self):
        doc, binary = fixture()
        raw = json.dumps(doc).encode()
        raw = b'{"asset":{"version":"2.0"},' + raw[1:]
        raw += b" " * (-len(raw) % 4)
        data = struct.pack("<III", 0x46546C67, 2, 28 + len(raw) + len(binary)) + struct.pack("<II", len(raw), 0x4E4F534A) + raw + struct.pack("<II", len(binary), 0x004E4942) + binary
        self.reject(data=data)
        nested = {}
        cursor = nested
        for _ in range(55):
            cursor["value"] = {}
            cursor = cursor["value"]
        doc["uninterpreted"] = nested
        self.reject(doc, binary, status=413)

    def test_uris_unknown_compression_and_script_fields_rejected(self):
        for field, value in (("uri", "https://remote/model.bin"), ("uri", "data:application/octet-stream;base64,AAAA"), ("script", "evil()")):
            doc, binary = fixture()
            doc["buffers"][0][field] = value
            self.reject(doc, binary)
        for extension in ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu", "ANY_custom_script"):
            doc, binary = fixture()
            doc["extensions"][extension] = {}
            self.reject(doc, binary)
        doc, binary = fixture()
        doc["extensionsUsed"].append("KHR_draco_mesh_compression")
        self.reject(doc, binary)

    def test_extras_removed_and_metadata_bounded_as_plain_text(self):
        doc, binary = fixture()
        doc["extras"] = {"private note": "never published"}
        doc["nodes"][0]["extras"] = {"private": "never published"}
        doc["extensions"]["VRMC_vrm"]["meta"]["name"] = "\0" + "n" * 1000
        m = self.store.import_vrm(glb(doc, binary))
        raw = self.store.resolve(m["id"], "model.vrm").read_bytes()
        self.assertNotIn(b"never published", raw)
        self.assertEqual(len(m["metadata"]["name"]), 120)

    def test_buffer_accessor_and_sparse_ranges(self):
        variants = [lambda d: d["bufferViews"][0].update(byteOffset=4),
                    lambda d: d["bufferViews"][0].update(buffer=1),
                    lambda d: d["accessors"][0].update(count=100),
                    lambda d: d["accessors"][0].update(byteOffset=1),
                    lambda d: d["accessors"][0].update(componentType=999),
                    lambda d: d["accessors"][0].update(type="BAD"),
                    lambda d: d["accessors"][0].update(sparse={"count": 3, "indices": {"bufferView": 999, "componentType": 5123}, "values": {"bufferView": 0}})]
        for mutate in variants:
            doc, binary = fixture()
            mutate(doc)
            self.reject(doc, binary)
        doc, binary = fixture()
        doc["bufferViews"] = [doc["bufferViews"][0]] * 4
        with patch.object(vrm, "MAX_REPACKED_BIN_BYTES", 100):
            self.reject(doc, binary, status=413)

    def test_nan_infinity_json_and_real_geometry_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            doc, binary = fixture()
            doc["nodes"][0]["translation"] = [value, 0, 0]
            self.reject(doc, binary)
            doc, binary = fixture()
            binary = struct.pack("<f", value) + binary[4:]
            self.reject(doc, binary)

    def test_node_cycles_references_skin_and_morph_out_of_bounds(self):
        variants = [lambda d: d["nodes"][0].update(children=[0]),
                    lambda d: d["nodes"][0].update(children=[999]),
                    lambda d: d["nodes"][0].update(children=[1, 1]),
                    lambda d: d["nodes"][0].update(mesh=99),
                    lambda d: d["nodes"][0].update(skin=0),
                    lambda d: d["meshes"][0]["primitives"][0].update(targets=[{"POSITION": 99}]),
                    lambda d: d["scenes"][0].update(nodes=[99])]
        for mutate in variants:
            doc, binary = fixture()
            mutate(doc)
            self.reject(doc, binary)
        doc, binary = fixture()
        doc["nodes"][0]["children"] = [1]
        doc["nodes"][1]["children"] = [0]
        self.reject(doc, binary)

    def test_vrm_version_bones_and_expression_references(self):
        for version in ("0", "1"):
            doc, binary = fixture(version)
            key = "VRMC_vrm" if version == "1" else "VRM"
            doc["extensions"][key]["specVersion"] = "9.0"
            self.reject(doc, binary)
            doc, binary = fixture(version)
            bones = doc["extensions"][key]["humanoid"]["humanBones"]
            if version == "1":
                bones["hips"]["node"] = 999
            else:
                bones[0]["node"] = 999
            self.reject(doc, binary)
        doc, binary = fixture()
        doc["extensions"]["VRMC_vrm"]["expressions"] = {"preset": {"aa": {"morphTargetBinds": [{"node": 0, "index": 100, "weight": 1}]}}}
        self.reject(doc, binary)
        doc, binary = fixture()
        del doc["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]["hips"]
        self.reject(doc, binary)

    def test_valid_indices_sparse_morph_and_expression_preserved(self):
        doc, binary = fixture()
        # Three uint16 triangle indices, then sparse vertex 1 + float delta.
        binary += struct.pack("<3H", 0, 1, 2) + b"\0\0"
        binary += b"\1\0\0\0" + struct.pack("<3f", 0, .1, 0)
        doc["buffers"][0]["byteLength"] = len(binary)
        doc["bufferViews"] += [{"buffer": 0, "byteOffset": 36, "byteLength": 6},
                                {"buffer": 0, "byteOffset": 44, "byteLength": 1},
                                {"buffer": 0, "byteOffset": 48, "byteLength": 12}]
        doc["accessors"] += [{"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 3},
                             {"componentType": 5126, "type": "VEC3", "count": 3, "sparse": {"count": 1, "indices": {"bufferView": 2, "componentType": 5121}, "values": {"bufferView": 3}}}]
        p = doc["meshes"][0]["primitives"][0]
        p.update(indices=1, targets=[{"POSITION": 2}])
        doc["extensions"]["VRMC_vrm"]["expressions"] = {"preset": {"aa": {"morphTargetBinds": [{"node": 0, "index": 0, "weight": 1}]}}}
        m = self.store.import_vrm(glb(doc, binary))
        self.assertTrue(m["capabilities"]["talk"])
        self.assertEqual(m["capabilities"]["expressions"], ["aa"])
        # Same valid structure, bad real index data: reject before publication.
        binary = binary[:36] + struct.pack("<3H", 0, 1, 3) + binary[42:]
        self.reject(doc, binary)

    def test_constraint_dependency_cycles_and_new_versions_rejected(self):
        doc, binary = fixture()
        for i, source in ((0, 1), (1, 0)):
            doc["nodes"][i]["extensions"] = {"VRMC_node_constraint": {"specVersion": "1.0", "constraint": {"rotation": {"source": source, "weight": 1}}}}
        self.reject(doc, binary)
        doc, binary = fixture()
        doc["materials"] = [{"extensions": {"VRMC_materials_mtoon": {"specVersion": "9.0"}}}]
        self.reject(doc, binary)

    def test_valid_animation_and_bad_output_or_time_rejected(self):
        doc, binary = fixture()
        binary += struct.pack("<2f", 0, 1) + struct.pack("<6f", 0, 0, 0, 0, .1, 0)
        doc["buffers"][0]["byteLength"] = len(binary)
        doc["bufferViews"] += [{"buffer": 0, "byteOffset": 36, "byteLength": 8}, {"buffer": 0, "byteOffset": 44, "byteLength": 24}]
        doc["accessors"] += [{"bufferView": 1, "componentType": 5126, "type": "SCALAR", "count": 2},
                             {"bufferView": 2, "componentType": 5126, "type": "VEC3", "count": 2}]
        doc["animations"] = [{"samplers": [{"input": 1, "output": 2}], "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}]}]
        self.assertTrue(self.store.import_vrm(glb(doc, binary))["capabilities"]["model_3d"])
        bad = binary[:36] + struct.pack("<2f", 1, 0) + binary[44:]
        self.reject(doc, bad)
        doc["animations"][0]["channels"][0]["target"]["path"] = "rotation"
        self.reject(doc, binary)

    def test_instanced_draw_budget_is_bounded(self):
        doc, binary = fixture()
        doc["nodes"] += [{"mesh": 0} for _ in range(512)]
        self.reject(doc, binary, status=413)

    def test_image_decoder_crc_budget_and_texture_references(self):
        for bad in (b"<svg onload='evil()'/>", b"\x89PNG\r\n\x1a\nwrong", b"\xff\xd8broken"):
            doc, binary = fixture(textured=True)
            doc["bufferViews"][1]["byteLength"] = len(bad)
            binary = binary[:36] + bad
            doc["buffers"][0]["byteLength"] = len(binary)
            self.reject(doc, binary)
        doc, binary = fixture(textured=True)
        with patch.object(vrm, "MAX_TEXTURE_PIXELS", 100):
            self.reject(doc, binary, status=413)
        doc, binary = fixture(textured=True)
        doc["textures"][0]["source"] = 99
        self.reject(doc, binary)
        doc, binary = fixture(textured=True)
        doc["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"] = 99
        self.reject(doc, binary)
        doc, binary = fixture(textured=True)
        bad = bytearray(binary)
        bad[-15] ^= 1
        self.reject(doc, bytes(bad))

    def test_texture_dimensions_fail_before_image_load(self):
        doc, binary = fixture(textured=True)
        view = doc["bufferViews"][1]
        raw = bytearray(binary[view["byteOffset"]:])
        struct.pack_into(">I", raw, 16, 4097)
        import zlib
        struct.pack_into(">I", raw, 29, zlib.crc32(raw[12:29]) & 0xffffffff)
        binary = binary[:view["byteOffset"]] + bytes(raw)
        with patch.object(Image.Image, "load", side_effect=AssertionError("decoder must not load oversized image")):
            self.reject(doc, binary, status=413)

    def test_atomic_failure_cancel_and_delete_do_not_touch_other_revisions(self):
        first = self.store.import_vrm(glb(*fixture()))
        raw = glb(*fixture("0"))
        event = threading.Event()
        event.set()
        with self.assertRaises(AssetError):
            self.store.import_vrm(raw, cancel_event=event)
        original = Path.write_bytes
        def failing(path, data):
            if path.name == "thumbnail.png":
                raise OSError("simulated full disk")
            return original(path, data)
        with patch.object(Path, "write_bytes", failing):
            self.reject(data=raw, status=503)
        with patch.object(Path, "rename", side_effect=OSError("simulated publication failure")):
            self.reject(data=raw, status=503)
        self.assertEqual(self.store.list_assets(), [first])
        second = self.store.import_vrm(raw)
        self.assertEqual(self.store.delete(second["id"])["deleted"], True)
        self.assertEqual(self.store.list_assets(), [first])
        with self.assertRaises(AssetError):
            self.store.get(second["id"])

    def test_cancel_before_publication_rolls_back(self):
        event = threading.Event()
        original = Path.write_text
        def cancel(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path.name == "manifest.json":
                event.set()
            return result
        with patch.object(Path, "write_text", cancel), self.assertRaises(AssetError):
            self.store.import_vrm(glb(*fixture()), cancel_event=event)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_names_and_corrupt_manifest_are_unavailable(self):
        raw = glb(*fixture())
        for name in ("../x.vrm", "x.glb", "C:x.vrm", "\0x.vrm", "a" * 256 + ".vrm"):
            with self.assertRaises(AssetError):
                self.store.import_vrm(raw, name)
        m = self.store.import_vrm(raw)
        p = self.root / m["id"] / "manifest.json"
        m["model"]["resource"] = "../private-file"
        p.write_text(json.dumps(m))
        with self.assertRaises(AssetError):
            self.store.get(m["id"])
        self.assertEqual(self.store.list_assets(), [])


if __name__ == "__main__":
    unittest.main()
