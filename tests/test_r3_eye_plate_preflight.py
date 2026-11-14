"""Reject coordinate errors before copying or rendering candidate assets."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

SPEC = importlib.util.spec_from_file_location(
    "lid",
    Path(__file__).resolve().parents[1]
    / "scripts/r3_both_eyes/register_lid_refinement.py",
)
lid = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lid)


class PlatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a, self.b = self.root / "a.png", self.root / "b.png"
        self.config = {
            "L": {"box": [565, 380, 685, 470]},
            "R": {"box": [700, 410, 810, 500]},
        }

    def plates(self, a, b):
        Image.new("RGB", a).save(self.a)
        Image.new("RGB", b).save(self.b)

    def test_canonical_and_uniformly_scaled_plates(self):
        for size in [(490, 390), (980, 780)]:
            self.plates(size, size)
            result = lid.validate_plates(self.a, self.b, self.config)
            self.assertEqual(result["visual_acceptance"], "not_evaluated")
            self.assertEqual(result["landmark_registration"], "not_verified")

    def test_rejects_distortion_mismatch_and_upscaling(self):
        for a, b, message in [
            ((490, 390), (491, 390), "dimensions"),
            ((490, 400), (490, 400), "aspect"),
            ((245, 195), (245, 195), "smaller"),
        ]:
            with self.subTest(a=a, b=b):
                self.plates(a, b)
                with self.assertRaisesRegex(ValueError, message):
                    lid.validate_plates(self.a, self.b, self.config)

    def test_rejects_outside_and_non_integer_boxes(self):
        self.plates((490, 390), (490, 390))
        for box in [[700, 410, 831, 500], [700, 410, 699, 500], [700.0, 410, 810, 500]]:
            self.config["R"]["box"] = box
            with self.assertRaises(ValueError):
                lid.validate_plates(self.a, self.b, self.config)

    def test_invalid_input_does_not_create_output_or_run_renderer(self):
        self.plates((490, 390), (490, 400))
        source = self.root / "source"
        source.mkdir()
        (source / "eyes.json").write_text(json.dumps(self.config))
        output = self.root / "output"
        with patch.object(lid.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                lid.register(source, self.a, self.b, output)
            run.assert_not_called()
        self.assertFalse(output.exists())
