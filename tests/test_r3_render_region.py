"""Real pixel negative fixtures for narrowly scoped eyelid changes."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from PIL import Image

SPEC = importlib.util.spec_from_file_location(
    "region",
    Path(__file__).resolve().parents[1] / "scripts/r3_both_eyes/check_render_region.py",
)
region = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(region)


class RenderRegionTests(unittest.TestCase):
    def test_one_level_of_drift_outside_the_region_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            original = Image.new("RGBA", (8, 8), (100, 90, 80, 255))
            original.save(p / "before.png")
            changed = original.copy()
            changed.putpixel((2, 2), (150, 90, 80, 255))
            changed.save(p / "after.png")
            result = region.compare(p / "before.png", p / "after.png", (2, 2, 5, 5))
            self.assertEqual(result["changed_pixels"], 1)
            self.assertEqual(result["check"], "edit_region_containment_only")
            self.assertEqual(result["visual_acceptance"], "not_evaluated")
            changed.putpixel((5, 2), (101, 90, 80, 255))
            changed.save(p / "after.png")
            with self.assertRaisesRegex(ValueError, "outside allowed"):
                region.compare(p / "before.png", p / "after.png", (2, 2, 5, 5))

    def test_alpha_drift_and_invalid_regions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            image = Image.new("RGBA", (8, 8), (100, 90, 80, 255))
            image.save(p / "before.png")
            image.putpixel((0, 0), (100, 90, 80, 254))
            image.save(p / "after.png")
            with self.assertRaisesRegex(ValueError, "outside allowed"):
                region.compare(p / "before.png", p / "after.png", (2, 2, 5, 5))
            with self.assertRaisesRegex(ValueError, "outside the render"):
                region.compare(p / "before.png", p / "after.png", (-1, 2, 5, 5))
