"""Wrong-unit counterexamples fail before any remote authoring mutation."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from avatar_live2d_units import (BezierHandleFraction, CanvasBoundsPx, CanvasPointPx,
    KeyTimeSeconds, LocalDeltaFraction, restore_cup_rotation_keys, validate_operation_units)


class AuthoringUnitTests(unittest.TestCase):
    def test_canvas_pixel_and_parent_warp_uv_are_distinct(self):
        box = CanvasBoundsPx(745, 1038, 293, 295)
        self.assertEqual(box.uv(CanvasPointPx(891.5, 1185.5)), [.5, .5])
        keys = restore_cup_rotation_keys(box)
        self.assertEqual(len(keys), 27)
        neutral = next(k for k in keys if all(value == 0 for value in k["key"].values()))
        self.assertEqual(neutral["geometry"], {"originX": .5, "originY": .5, "angle": 0, "scale": 1})
        self.assertEqual({k["key"]["ParamCupRotation"] for k in keys}, {-45, 0, 45})

    def test_pixels_and_absolute_bezier_handles_fail(self):
        with self.assertRaisesRegex(ValueError, "canvas pixels"):
            LocalDeltaFraction(0, 10)
        with self.assertRaisesRegex(ValueError, "fractions"):
            BezierHandleFraction(2.33, 240)
        with self.assertRaises(ValueError):
            KeyTimeSeconds(-.1)
        with self.assertRaises(ValueError):
            CanvasPointPx(float("inf"), 1)

    def test_wrong_selector_and_motion_units_rejected(self):
        with self.assertRaisesRegex(ValueError, "normalized"):
            validate_operation_units("rig_deform", {"changes": [{"operations": [{
                "type": "translate", "delta": [0, .1], "selection": {"rect": [450, 540, 565, 610]}}]}]})
        with self.assertRaisesRegex(ValueError, "fractions"):
            validate_operation_units("motion_put", {"clip": {"curves": [{"keys": [
                {"time": 0, "value": 0, "out": [1.5, 240]}]}]}})


if __name__ == "__main__":
    unittest.main()
