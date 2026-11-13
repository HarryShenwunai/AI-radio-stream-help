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

    def pin_reference(self):
        with Image.new("RGBA", (32, 32), (0, 0, 0, 0)) as master:
            for item in self.doc["layers"]:
                if item.get("visible", True):
                    with Image.open(self.root / item["file"]) as layer:
                        master.alpha_composite(layer, (item.get("x", 0), item.get("y", 0)))
            master.save(self.root / "master.png")
        self.doc["neutral_reference"] = {
            "file": "master.png",
            "sha256": hashlib.sha256((self.root / "master.png").read_bytes()).hexdigest(),
            "regions": {"face": [10, 3, 12, 10], "hands_cup": [4, 14, 24, 17]},
        }

    def test_pinned_neutral_export_preserves_art_without_claiming_quality(self):
        self.pin_reference()
        report = source.write_psd(self.write_manifest(), self.root / "reviewed.psd",
                                  require_reference=True)
        self.assertEqual(report["neutral_reconstruction"]["status"], "passed_reconstruction_only")
        self.assertEqual(report["neutral_reconstruction"]["regions"]["face"]["mean_max_channel_error"], 0)
        self.assertEqual(report["art_quality_acceptance"], "NOT_CLAIMED")

    def test_one_local_face_defect_cannot_hide_in_global_average(self):
        self.pin_reference()
        with Image.open(self.root / "face.png") as old:
            edited = old.copy()
        edited.putpixel((6, 5), (0, 0, 0, 255))
        edited.save(self.root / "face.png")
        edited.close()
        target = self.root / "bad-face.psd"
        with self.assertRaisesRegex(ValueError, "master: face$"):
            source.write_psd(self.write_manifest(), target, require_reference=True)
        self.assertFalse(target.exists())

    def test_hand_cup_region_rejects_changed_visible_pixels(self):
        self.pin_reference()
        with Image.open(self.root / "body.png") as old:
            edited = old.copy()
        ImageDraw.Draw(edited).rectangle((10, 20, 12, 22), fill=(255, 255, 255, 255))
        edited.save(self.root / "body.png")
        edited.close()
        target = self.root / "bad-hand.psd"
        with self.assertRaisesRegex(ValueError, "hands_cup"):
            source.write_psd(self.write_manifest(), target, require_reference=True)
        self.assertFalse(target.exists())

    def test_reference_hash_and_size_are_pinned(self):
        self.pin_reference()
        self.doc["neutral_reference"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            source.write_psd(self.write_manifest(), self.root / "bad-hash.psd")
        with Image.new("RGBA", (64, 32)) as wrong:
            wrong.save(self.root / "master.png")
        self.doc["neutral_reference"]["sha256"] = hashlib.sha256((self.root / "master.png").read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "same-size"):
            source.write_psd(self.write_manifest(), self.root / "bad-size.psd")

    def test_reviewed_path_requires_master_and_valid_both_regions(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            source.write_psd(self.write_manifest(), self.root / "missing.psd", require_reference=True)
        self.pin_reference()
        self.doc["neutral_reference"]["regions"].pop("face")
        with self.assertRaisesRegex(ValueError, "face and hands_cup"):
            source.write_psd(self.write_manifest(), self.root / "missing-region.psd")
        self.pin_reference()
        self.doc["neutral_reference"]["regions"]["face"] = [30, 3, 12, 10]
        with self.assertRaisesRegex(ValueError, "outside"):
            source.write_psd(self.write_manifest(), self.root / "bad-region.psd")

    def test_alpha_change_on_black_art_is_detected_over_white(self):
        with Image.open(self.root / "face.png") as old:
            edited = old.copy()
        ImageDraw.Draw(edited).rectangle((4, 4, 7, 7), fill=(0, 0, 0, 255))
        edited.save(self.root / "face.png")
        self.pin_reference()
        edited.putpixel((6, 5), (0, 0, 0, 0))
        edited.save(self.root / "face.png")
        edited.close()
        with self.assertRaisesRegex(ValueError, "face"):
            source.write_psd(self.write_manifest(), self.root / "alpha-hole.psd")

    def test_hidden_rgb_does_not_create_false_visual_failure(self):
        self.pin_reference()
        with Image.open(self.root / "body.png") as old:
            edited = old.copy()
        edited.putpixel((0, 0), (255, 0, 255, 0))
        edited.save(self.root / "body.png")
        edited.close()
        report = source.write_psd(self.write_manifest(), self.root / "invisible-rgb.psd")
        self.assertEqual(report["neutral_reconstruction"]["status"], "passed_reconstruction_only")

    def test_pack_cli_requires_reference_unless_historical_override_is_explicit(self):
        import subprocess
        import sys
        manifest = self.write_manifest()
        target = self.root / "cli.psd"
        command = [sys.executable, str(ROOT / "scripts/avatar_live2d_source.py"),
                   "pack", "--layers", str(manifest), "--output", str(target)]
        rejected = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("requires a pinned neutral_reference", rejected.stderr)
        self.assertFalse(target.exists())
        legacy = subprocess.run([*command, "--allow-unreviewed-source"], capture_output=True, text=True)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout)["neutral_reconstruction"]["status"], "NOT_RUN")
        self.pin_reference()
        command[-1] = str(self.root / "cli-reviewed.psd")
        reviewed = subprocess.run(command[:command.index("--layers") + 1] +
                                  [str(self.write_manifest()), "--output", command[-1]],
                                  capture_output=True, text=True)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertEqual(json.loads(reviewed.stdout)["neutral_reconstruction"]["status"], "passed_reconstruction_only")


if __name__ == "__main__":
    unittest.main()
