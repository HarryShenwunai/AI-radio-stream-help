"""Real PSD binary authoring checks, without invoking an installed editor/Core."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("avatar_live2d_source", ROOT / "scripts/avatar_live2d_source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class EditablePSDSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with Image.new("RGBA", (32, 32), (0, 0, 0, 0)) as body:
            ImageDraw.Draw(body).rectangle((4, 14, 27, 30), fill=(70, 120, 170, 255))
            body.save(self.root / "body.png")
        with Image.new("RGBA", (12, 10), (0, 0, 0, 0)) as face:
            ImageDraw.Draw(face).ellipse((0, 0, 11, 9), fill=(230, 175, 130, 240))
            face.save(self.root / "face.png")
        self.doc = {"format": "original-live2d-layers-v1", "canvas": {"width": 32, "height": 32},
                    "layers": [{"name": "topwear", "file": "body.png"},
                               {"name": "脸", "file": "face.png", "x": 10, "y": 3}]}

    def write_manifest(self):
        path = self.root / "source.json"
        path.write_text(json.dumps(self.doc))
        return path

    def test_real_psd_decodes_identical_composite_and_source_pixels_are_unchanged(self):
        originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob("*.png")}
        target = self.root / "original.psd"
        result = source.write_psd(self.write_manifest(), target)
        self.assertEqual(result["layer_count"], 2)
        self.assertEqual(result["art_quality_acceptance"], "NOT_CLAIMED")
        self.assertIn("脸".encode("utf-16-be"), target.read_bytes())
        with Image.new("RGBA", (32, 32), (0, 0, 0, 0)) as expected:
            for item in self.doc["layers"]:
                with Image.open(self.root / item["file"]) as layer:
                    expected.alpha_composite(layer, (item.get("x", 0), item.get("y", 0)))
            with Image.open(target) as decoded:
                # PSD storage is bottom-to-top. The merged preview alone would
                # miss a reversed editable stack that puts back hair over eyes.
                self.assertEqual(decoded.layers[0][0], "topwear")
                decoded.load()
                self.assertEqual(decoded.format, "PSD")
                self.assertEqual(decoded.mode, "RGBA")
                self.assertEqual(decoded.tobytes(), expected.tobytes())
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob("*.png")}, originals)

    def test_hidden_layer_is_retained_without_changing_composite(self):
        self.doc["layers"][1]["visible"] = False
        target = self.root / "hidden.psd"
        result = source.write_psd(self.write_manifest(), target)
        self.assertEqual(result["layer_count"], 2)
        self.assertFalse(result["layers"][1]["visible"])
        with Image.open(target) as decoded, Image.open(self.root / "body.png") as expected:
            self.assertEqual(decoded.tobytes(), expected.tobytes())

    def test_invalid_canvas_placement_and_path_do_not_create_psd(self):
        for field, value in (("x", True), ("x", 30), ("file", "../face.png"), ("file", "/face.png")):
            with self.subTest(field=field, value=value):
                self.doc["layers"][1][field] = value
                target = self.root / "bad.psd"
                with self.assertRaises((ValueError, OSError)):
                    source.write_psd(self.write_manifest(), target)
                self.assertFalse(target.exists())
                self.doc["layers"][1] = {"name": "face", "file": "face.png", "x": 10, "y": 3}

    def test_no_overwrite_of_editable_source(self):
        target = self.root / "protected.psd"
        target.write_bytes(b"preserve original")
        with self.assertRaises(ValueError):
            source.write_psd(self.write_manifest(), target)
        self.assertEqual(target.read_bytes(), b"preserve original")

    def test_atlas_outside_runtime_contract_rejected_without_running_java(self):
        for atlas in (128, 1000, 8192):
            with self.subTest(atlas=atlas), self.assertRaises(ValueError):
                source.export(self.root / "missing.psd", self.root / "out", self.root / "missing-tool", atlas=atlas)
        self.assertFalse((self.root / "out").exists())


if __name__ == "__main__":
    unittest.main()
