"""Real PNG/ZIP parser tests; synthetic artwork is not the user's character."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from companion_runtime.assets import AssetError, AssetStore, STATE_NAMES
from companion_runtime import layered_2d_assets as layered


def png(role, size=(64, 96), *, opaque=False, blank=False):
    with Image.new("RGBA", size, (20, 30, 40, 255) if opaque else (0, 0, 0, 0)) as image:
        draw = ImageDraw.Draw(image)
        if not blank:
            if role == "body":
                draw.rectangle((16, 42, 48, 94), fill=(70, 110, 170, 255))
            elif role == "head":
                draw.ellipse((16, 5, 48, 45), fill=(235, 180, 140, 255))
            elif role == "eyes_open":
                draw.ellipse((23, 20, 27, 25), fill=(20, 30, 40, 255))
                draw.ellipse((37, 20, 41, 25), fill=(20, 30, 40, 255))
            elif role == "eyes_closed":
                draw.line((22, 23, 28, 23), fill=(20, 30, 40, 255), width=2)
                draw.line((36, 23, 42, 23), fill=(20, 30, 40, 255), width=2)
            elif role == "mouth_closed":
                draw.line((29, 33, 35, 33), fill=(130, 45, 40, 255), width=2)
            elif role == "mouth_open":
                draw.ellipse((28, 31, 36, 36), fill=(130, 45, 40, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def document(expressions=True):
    roles = ["body", "head"]
    if expressions:
        roles += ["eyes_open", "eyes_closed", "mouth_closed", "mouth_open"]
    return {"format": "companion-layered-2d", "version": 1, "canvas": {"width": 64, "height": 96},
            "layers": [{"id": role, "role": role, "file": role + ".png", "pivot": [32, 44],
                        "states": [state for state in STATE_NAMES if state in layered.ROLE_STATES.get(role, STATE_NAMES)],
                        "motion": {"breath_y": 1.5, "sway_degrees": .4, "gaze_x": 1, "gaze_y": 1}}
                       for role in roles]}


def package(doc=None, files=None, *, raw_json=None, extras=None):
    doc = document() if doc is None else doc
    files = {layer["file"]: png(layer["role"]) for layer in doc["layers"]} if files is None else files
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("layered2d.json", json.dumps(doc).encode() if raw_json is None else raw_json)
        for file, data in files.items():
            archive.writestr(file, data)
        for file, data in (extras or []):
            archive.writestr(file, data)
    return buffer.getvalue()


class Layered2DAssets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = AssetStore(self.temp.name)

    def assert_rejected(self, data):
        with self.assertRaises(AssetError):
            self.store.import_layered_2d(data, "layers.zip")
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_real_import_persistence_resources_thumbnail_and_no_live2d_claim(self):
        manifest = self.store.import_layered_2d(package(), "layers.zip")
        self.assertEqual(manifest["format"], "layered-2d")
        self.assertEqual(len(manifest["layers"]), 6)
        self.assertTrue(manifest["capabilities"]["talk_blink"])
        self.assertFalse(manifest["live2d"])
        self.assertEqual(manifest["art_review"], "not_run")
        restarted = AssetStore(self.temp.name)
        self.assertEqual(restarted.get(manifest["id"]), manifest)
        model_path = restarted.resolve(manifest["id"], "layers.json")
        model = json.loads(model_path.read_text())
        self.assertEqual(model["layers"], manifest["layers"])
        for name in manifest["resources"]:
            self.assertTrue(restarted.resolve(manifest["id"], name).is_file())
        with Image.open(restarted.resolve(manifest["id"], "thumbnail.png")) as thumb:
            self.assertEqual(thumb.size, (64, 96))
            self.assertGreater(thumb.getpixel((32, 60))[3], 0)
        self.assertEqual(len(restarted.list_assets()), 1)
        restarted.delete(manifest["id"])
        self.assertEqual(restarted.list_assets(), [])

    def test_no_eyes_mouth_means_no_fake_blink_or_talk(self):
        manifest = self.store.import_layered_2d(package(document(False)), "layers.zip")
        for key in ("talk", "blink", "talk_blink"):
            self.assertFalse(manifest["capabilities"][key])

    def test_unsafe_names_unknown_files_missing_files_and_duplicate_entries(self):
        for name in ("../x.png", "/x.png", "folder/x.png", "X.png", "https:x.png", "x\\y.png", "script.js"):
            with self.subTest(name=name):
                self.assert_rejected(package(extras=[(name, b"bad")]))
        self.assert_rejected(package(extras=[("body.png", png("body"))]))
        self.assert_rejected(package(files={"body.png": png("body")}))

    def test_symlink_rejected_without_extracting(self):
        raw = io.BytesIO(package())
        buffer = io.BytesIO()
        with zipfile.ZipFile(raw) as source, zipfile.ZipFile(buffer, "w") as dest:
            for info in source.infolist():
                data = source.read(info)
                if info.filename == "head.png":
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                dest.writestr(info, data)
        self.assert_rejected(buffer.getvalue())

    def test_bad_semantics_script_unknown_motion_nan_and_bool_dimensions(self):
        mutations = [
            lambda d: d.update(script="alert(1)"),
            lambda d: d["canvas"].update(width=True),
            lambda d: d["layers"][0]["motion"].update(sway_degrees=4),
            lambda d: d["layers"][0]["motion"].update(onload="do()"),
            lambda d: d["layers"][0]["motion"].update(gaze_x=float("nan")),
            lambda d: d["layers"][0].update(pivot=[-1, 20]),
            lambda d: d["layers"][1].update(id="body"),
            lambda d: d["layers"][3].update(states=["idle"]),
            lambda d: d["layers"].pop(),
        ]
        for mutate in mutations:
            doc = copy.deepcopy(document())
            mutate(doc)
            with self.subTest(doc=doc):
                self.assert_rejected(package(doc))
        self.assert_rejected(package(raw_json=b'{"format":"companion-layered-2d","format":"x"}'))

    def test_true_transparency_content_dimensions_and_no_duplicate_whole_image(self):
        doc = document(False)
        for head in (png("head", opaque=True), png("head", blank=True),
                     png("head", size=(65, 96)), png("body"), b"not a PNG"):
            self.assert_rejected(package(doc, {"body.png": png("body"), "head.png": head}))

    def test_budget_limits_checked_before_decode(self):
        doc = document(False)
        doc["canvas"] = {"width": 4096, "height": 4096}
        with patch.object(layered, "_normalise", side_effect=AssertionError("should not decode")):
            self.assert_rejected(package(doc))
        with patch.object(layered, "MAX_EXPANDED_BYTES", 100):
            self.assert_rejected(package())
        with patch.object(layered, "MAX_ZIP_BYTES", 10):
            self.assert_rejected(package())

    def test_zip_reads_are_bounded_and_corrupt_or_truncated_data_is_rejected(self):
        calls = []
        original = zipfile.ZipExtFile.read
        def bounded_read(stream, size=-1):
            calls.append(size)
            self.assertGreater(size, 0, "unbounded ZIP inflation is forbidden")
            self.assertLessEqual(size, layered.MAX_PNG_BYTES + 1)
            return original(stream, size)
        with patch.object(zipfile.ZipExtFile, "read", bounded_read):
            manifest = self.store.import_layered_2d(package())
        self.assertEqual(len(calls), 7)
        self.store.delete(manifest["id"])
        raw = package()
        bad = bytearray(raw)
        name_length, extra_length = struct.unpack_from("<HH", bad, 26)
        offset = 30 + name_length + extra_length
        bad[offset] ^= 0xFF
        self.assert_rejected(bytes(bad))
        self.assert_rejected(raw[:-20])

    def test_cancel_write_and_publish_failure_leave_no_partial_revision(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(AssetError):
            self.store.import_layered_2d(package(), cancel_event=cancelled)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        for method in ("write_bytes", "rename"):
            with self.subTest(method=method), patch.object(Path, method, side_effect=OSError("disk failure")):
                self.assert_rejected(package())
        original = layered._normalise
        counter = 0
        def cancel_midway(data):
            nonlocal counter
            counter += 1
            result = original(data)
            if counter == 2:
                cancelled.set()
            return result
        cancelled.clear()
        with patch.object(layered, "_normalise", side_effect=cancel_midway):
            with self.assertRaises(AssetError):
                self.store.import_layered_2d(package(), cancel_event=cancelled)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_tampered_manifest_and_resolve_traversal_rejected(self):
        manifest = self.store.import_layered_2d(package())
        asset_id = manifest["id"]
        with self.assertRaises(AssetError):
            self.store.resolve(asset_id, "../l0000.png")
        path = Path(self.temp.name) / asset_id / "manifest.json"
        manifest["layers"][0]["resource"] = "../escape.png"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(AssetError):
            self.store.get(asset_id)
        self.assertEqual(self.store.list_assets(), [])


if __name__ == "__main__":
    unittest.main()
