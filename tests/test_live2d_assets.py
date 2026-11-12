"""Synthetic runtime envelopes only; never claim fabricated MOC3 is playable."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, PngImagePlugin

from companion_runtime.assets import AssetError, AssetStore
from companion_runtime import live2d_assets as live


def png(size=(20, 30), colour=(60, 80, 190, 170)):
    stream = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("untrusted-source-note", "remove this metadata")
    with Image.new("RGBA", size, colour) as image:
        image.save(stream, format="PNG", pnginfo=info)
    return stream.getvalue()


def files(extended=False):
    model = {"Version": 3, "FileReferences": {"Moc": "actor.moc3", "Textures": ["tex/0.png"]},
             "Groups": [{"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]}, {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]}]}
    items = {"actor.moc3": b"MOC3" + bytes([5, 0]) + b"\0" * 58,
             "tex/0.png": png(), "LICENSE.txt": b"Self-created test envelope; not a Cubism model."}
    if extended:
        model["FileReferences"].update(Expressions=[{"Name": "own-expression", "File": "x.exp3.json"}],
            Motions={"Idle": [{"File": "idle.motion3.json"}]}, Physics="actor.physics3.json", DisplayInfo="actor.cdi3.json", Pose="actor.pose3.json")
        items["tex/0.png"] = png((70, 40), (30, 160, 50, 240))
        items["actor.moc3"] = b"MOC3" + bytes([3, 0]) + b"\0" * 122
        items["x.exp3.json"] = {"Version": 3, "Type": "Live2D Expression", "Parameters": [{"Id": "ParamMouthForm", "Value": 1, "Blend": "Add"}]}
        items["idle.motion3.json"] = {"Version": 3, "Meta": {"Duration": 1, "Fps": 30, "Loop": True, "CurveCount": 1, "TotalSegmentCount": 1, "TotalPointCount": 2}, "Curves": [{"Target": "Parameter", "Id": "ParamAngleX", "Segments": [0, 0, 0, 1, 10]}]}
        items["actor.physics3.json"] = {"Version": 3, "Meta": {"PhysicsSettingCount": 1, "TotalInputCount": 0, "TotalOutputCount": 1, "VertexCount": 2, "EffectiveForces": {"Gravity": {"X": 0, "Y": -1}, "Wind": {"X": 0, "Y": 0}}, "PhysicsDictionary": [{"Id": "hair", "Name": "synthetic chain"}]}, "PhysicsSettings": [{"Id": "hair", "Input": [], "Output": [{"Destination": {"Target": "Parameter", "Id": "ParamHair"}, "VertexIndex": 1, "Scale": 1, "Weight": 100, "Type": "Angle", "Reflect": False}], "Vertices": [{"Position": {"X": 0, "Y": 0}, "Mobility": 1, "Delay": 1, "Acceleration": 1, "Radius": 0}, {"Position": {"X": 0, "Y": 1}, "Mobility": 1, "Delay": 1, "Acceleration": 1, "Radius": 1}], "Normalization": {"Position": {"Minimum": -10, "Default": 0, "Maximum": 10}, "Angle": {"Minimum": -30, "Default": 0, "Maximum": 30}}}]}
        items["actor.cdi3.json"] = {"Version": 3, "Parameters": [{"Id": "ParamAngleX", "GroupId": "", "Name": "Angle"}], "ParameterGroups": [], "Parts": []}
        items["actor.pose3.json"] = {"Version": 3, "Type": "Live2D Pose", "Groups": [[{"Id": "PartA", "Link": ["PartB"]}]]}
    items["actor.model3.json"] = model
    return items


def archive(items, prefix="", compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as z:
        for name, value in items.items():
            z.writestr(prefix + name, json.dumps(value).encode() if isinstance(value, dict) else value)
    return stream.getvalue()


class Live2DAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "assets"
        self.store = AssetStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, items=None, data=None, status=None):
        before = self.store.list_assets()
        with self.assertRaises(AssetError) as error:
            self.store.import_live2d(archive(items) if data is None else data, "own-character.zip")
        if status is not None:
            self.assertEqual(error.exception.status, status)
        self.assertEqual(self.store.list_assets(), before)
        self.assertFalse(any(x.name.startswith(".staging-") for x in self.root.iterdir()))

    def test_two_independent_envelopes_get_list_resolve_without_core_claim(self):
        a = self.store.import_live2d(archive(files()), "自选角色.zip")
        b = self.store.import_live2d(archive(files(True), prefix="runtime/"))
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["moc3_version"]["code"], 5)
        self.assertEqual(b["moc3_version"]["code"], 3)
        self.assertFalse(a["runtime"]["core_consistency_verified"])
        self.assertFalse(b["runtime"]["license_verified"])
        self.assertEqual(self.store.get(b["id"]), b)
        self.assertEqual(len(self.store.list_assets()), 2)
        self.assertEqual(b["capabilities"]["expressions"], ["own-expression"])
        self.assertEqual(b["capabilities"]["motion_groups"], ["Idle"])
        self.assertTrue(b["capabilities"]["talk"] and b["capabilities"]["blink"])
        self.assertEqual(len(b["notices"]), 1)
        self.assertIn(b"Self-created", self.store.resolve(b["id"], b["notices"][0]).read_bytes())
        model = json.loads(self.store.resolve(b["id"], "model.model3.json").read_text())
        self.assertTrue(model["FileReferences"]["Moc"].startswith("r"))
        for resource in b["resources"]:
            self.assertTrue(self.store.resolve(b["id"], resource).is_file())
        for resource in ("actor.moc3", "../r0001.moc3", "manifest.json", "LICENSE.txt", "r9999.png"):
            with self.assertRaises(AssetError):
                self.store.resolve(b["id"], resource)

    def test_textures_metadata_stripped_and_package_names_not_preserved(self):
        m = self.store.import_live2d(archive(files(), prefix="私人目录/"))
        model = json.loads(self.store.resolve(m["id"], m["model"]["resource"]).read_text())
        texture = self.store.resolve(m["id"], model["FileReferences"]["Textures"][0])
        self.assertNotIn(b"remove this metadata", texture.read_bytes())
        self.assertNotIn("私人目录", json.dumps(m, ensure_ascii=False))
        with Image.open(texture) as im:
            self.assertEqual(im.size, (20, 30))
            self.assertFalse(im.info)

    def test_public_spec_optional_versions_loop_and_displayinfo_extensions(self):
        items = files(True)
        del items["x.exp3.json"]["Version"]
        del items["actor.pose3.json"]["Version"]
        del items["idle.motion3.json"]["Meta"]["Loop"]
        items["actor.cdi3.json"].update(ArtMeshes=[{"Id": "Drawable1", "Name": "test mesh"}], CombinedParameters=[["ParamAngleX", "ParamAngleY"]])
        self.assertEqual(self.store.import_live2d(archive(items))["format"], "live2d")

    def test_zip_traversal_absolute_url_windows_names_and_backslashes(self):
        for name in ("../evil.txt", "/evil.txt", "C:/evil.txt", "a\\evil.txt", "https://host/e.txt", "CON.txt", "dir./x.txt", "a//b.txt", "./x.txt"):
            items = files()
            items[name] = b"x"
            self.reject(items)

    def test_symlink_case_duplicate_and_file_directory_conflict(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            for n, v in files().items():
                z.writestr(n, json.dumps(v).encode() if isinstance(v, dict) else v)
            link = zipfile.ZipInfo("evil.txt")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, "../../outside")
        self.reject(data=stream.getvalue())
        items = files()
        items["TEX/0.PNG"] = png()
        self.reject(items)
        items = files()
        items["tex"] = b"x"
        self.reject(items)

    def test_zip_crc_truncation_compression_bombs_and_limits(self):
        raw = archive(files(), compression=zipfile.ZIP_STORED)
        bad = bytearray(raw)
        offset = raw.find(b"MOC3")
        bad[offset + 8] ^= 1
        self.reject(data=bytes(bad))
        self.reject(data=raw[:-20])
        self.reject(data=b"not a zip")
        items = files()
        items["bomb.txt"] = b"a" * 1_000_000
        self.reject(items, status=413)
        with patch.object(live, "MAX_ENTRIES", 2):
            self.reject(files(), status=413)
        with patch.object(live, "MAX_UNCOMPRESSED_BYTES", 100):
            self.reject(files(), status=413)

    def test_model_reference_boundary_scripts_remote_and_multiple_roots(self):
        for reference in ("../other.moc3", "/root.moc3", "https://host/a.moc3", "data:moc3;base64,AA", "missing.moc3"):
            items = files()
            items["actor.model3.json"]["FileReferences"]["Moc"] = reference
            self.reject(items)
        for filename in ("run.js", "x.html", "run.exe", "x.dll", "x.wasm", "archive.zip", "source.psd"):
            items = files()
            items[filename] = b"fake program"
            self.reject(items)
        items = files()
        items["second.model3.json"] = copy.deepcopy(items["actor.model3.json"])
        self.reject(items)

    def test_root_model_can_use_generic_model3_name(self):
        items = files()
        items["model3.json"] = items.pop("actor.model3.json")
        self.assertEqual(self.store.import_live2d(archive(items))["format"], "live2d")

    def test_moc_header_unknown_version_and_nonbinary_moc_rejected(self):
        for moc in (b"MOC3", b"not a model" * 10, b"MOC3" + bytes([99, 0]) + b"\0" * 58):
            items = files()
            items["actor.moc3"] = moc
            self.reject(items)

    def test_unknown_fields_sound_userdata_and_json_nan_rejected(self):
        items = files()
        items["actor.model3.json"]["RunScript"] = "evil()"
        self.reject(items)
        items = files(True)
        items["actor.model3.json"]["FileReferences"]["Motions"]["Idle"][0]["Sound"] = "https://remote/clip.wav"
        self.reject(items)
        items = files(True)
        items["idle.motion3.json"]["Curves"][0]["Segments"][1] = float("nan")
        self.reject(items)
        items = files(True)
        items["idle.motion3.json"]["UserData"] = [{"Time": 0, "Script": "run"}]
        self.reject(items)

    def test_embedded_sound_userdata_and_events_are_dropped_without_manual_edit(self):
        items = files(True)
        items["actor.model3.json"]["FileReferences"]["UserData"] = "actor.userdata3.json"
        items["actor.model3.json"]["FileReferences"]["Motions"]["Idle"][0]["Sound"] = "sounds/idle.wav"
        items["actor.userdata3.json"] = {"Version": 3, "UserData": [{"Target": "ArtMesh", "Id": "test", "Value": "discarded-original-tag"}]}
        # Never decoded or claimed playable; this is discarded package payload.
        items["sounds/idle.wav"] = b"discarded-audio-marker"
        items["idle.motion3.json"]["UserData"] = [{"Time": .25, "Value": "discarded-event-marker"}]
        items["idle.motion3.json"]["Meta"].update(UserDataCount=1, TotalUserDataSize=22)
        m = self.store.import_live2d(archive(items))
        self.assertIn(live.DISCARDED_AUDIO_WARNING, m["warnings"])
        model = json.loads(self.store.resolve(m["id"], m["model"]["resource"]).read_text())
        self.assertNotIn("UserData", model["FileReferences"])
        self.assertNotIn("Sound", model["FileReferences"]["Motions"]["Idle"][0])
        motion_name = model["FileReferences"]["Motions"]["Idle"][0]["File"]
        motion = json.loads(self.store.resolve(m["id"], motion_name).read_text())
        self.assertNotIn("UserData", motion)
        self.assertEqual(motion["Meta"]["UserDataCount"], 0)
        published = b"".join(self.store.resolve(m["id"], r).read_bytes() for r in m["resources"])
        self.assertNotIn(b"discarded-", published)
        self.assertFalse(any(r.endswith((".wav", ".userdata3.json")) for r in m["resources"]))
        for bad in ("../escape.wav", "/root.wav", "https://x/clip.wav", "data:audio/wav;base64,AA"):
            invalid = copy.deepcopy(items)
            invalid["actor.model3.json"]["FileReferences"]["Motions"]["Idle"][0]["Sound"] = bad
            self.reject(invalid)
        invalid = copy.deepcopy(items)
        invalid["actor.model3.json"]["FileReferences"]["UserData"] = "../outside.userdata3.json"
        self.reject(invalid)

    def test_japanese_fullwidth_space_is_text_but_controls_remain_rejected(self):
        items = files(True)
        items["actor.cdi3.json"]["Parameters"][0]["Name"] = "左目\u3000開閉"
        m = self.store.import_live2d(archive(items))
        model = json.loads(self.store.resolve(m["id"], m["model"]["resource"]).read_text())
        cdi = json.loads(self.store.resolve(m["id"], model["FileReferences"]["DisplayInfo"]).read_text())
        self.assertEqual(cdi["Parameters"][0]["Name"], "左目\u3000開閉")
        for bad in ("bad\nname", "bad\rname", "hidden\u202ename", "bad\ud800name"):
            invalid = copy.deepcopy(items)
            invalid["actor.cdi3.json"]["Parameters"][0]["Name"] = bad
            self.reject(invalid)

    def test_motion_duration_export_rounding_has_small_bounded_tolerance(self):
        items = files(True)
        motion = items["idle.motion3.json"]
        motion["Meta"].update(Duration=5.33, Fps=30)
        motion["Curves"][0]["Segments"][-2] = 5.333
        self.assertEqual(self.store.import_live2d(archive(items))["format"], "live2d")
        for end, fps in ((5.35, 30), (5.338, 240), (-1, 30)):
            invalid = copy.deepcopy(items)
            invalid["idle.motion3.json"]["Meta"]["Fps"] = fps
            invalid["idle.motion3.json"]["Curves"][0]["Segments"][-2] = end
            self.reject(invalid)

    def test_motion_counts_and_physics_output_ranges_rejected(self):
        items = files(True)
        items["idle.motion3.json"]["Meta"]["CurveCount"] = 100000
        self.reject(items)
        items = files(True)
        items["actor.physics3.json"]["PhysicsSettings"][0]["Output"][0]["VertexIndex"] = 100
        self.reject(items)
        items = files(True)
        items["actor.physics3.json"]["PhysicsSettings"][0]["Normalization"]["Angle"]["Maximum"] = -99
        self.reject(items)

    def test_real_texture_validation_and_budget(self):
        items = files()
        items["tex/0.png"] = b"<svg onload='evil()'/>"
        self.reject(items)
        with patch.object(live, "MAX_TEXTURE_PIXELS", 100):
            self.reject(files(), status=413)
        items = files()
        broken = bytearray(items["tex/0.png"])
        broken[-15] ^= 1
        items["tex/0.png"] = bytes(broken)
        self.reject(items)

    def test_atomic_write_publish_failures_cancel_and_delete(self):
        first = self.store.import_live2d(archive(files()))
        with patch.object(Path, "write_bytes", side_effect=OSError("full disk")):
            self.reject(files(True), status=503)
        with patch.object(Path, "rename", side_effect=OSError("publication failed")):
            self.reject(files(True), status=503)
        event = threading.Event()
        original = Path.write_text
        def cancelling(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            event.set()
            return result
        with patch.object(Path, "write_text", cancelling), self.assertRaises(AssetError):
            self.store.import_live2d(archive(files(True)), cancel_event=event)
        self.assertEqual(self.store.list_assets(), [first])
        self.assertFalse(any(p.name.startswith(".staging-") for p in self.root.iterdir()))
        self.assertTrue(self.store.delete(first["id"])["deleted"])
        self.assertEqual(self.store.list_assets(), [])


if __name__ == "__main__":
    unittest.main()
