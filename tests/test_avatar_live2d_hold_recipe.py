"""Protect conditional cup independence and actual attachment-fit geometry."""
import importlib.util
import math
from pathlib import Path
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SPEC = importlib.util.spec_from_file_location(
    "hold_recipe", Path(__file__).resolve().parents[1] / "scripts/avatar_live2d_hold_recipe.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ObservedCupFollowTests(unittest.TestCase):
    def test_fit_reconstructs_both_observed_attachments(self):
        base = [[10, 20], [110, 20]]
        posed = [[30, 40], [30, 190]]
        center = [60, 70]
        fit = MODULE.similarity(base, posed, center)
        self.assertAlmostEqual(fit["degrees"], 90)
        self.assertAlmostEqual(fit["scale"], 1.5)
        self.assertEqual(fit["delta"], [-105, 45])
        angle = math.radians(fit["degrees"])
        for p, expected in zip(base, posed):
            dx, dy = p[0] - center[0], p[1] - center[1]
            result = [center[0] + fit["delta"][0] + fit["scale"] * (dx * math.cos(angle) - dy * math.sin(angle)),
                      center[1] + fit["delta"][1] + fit["scale"] * (dx * math.sin(angle) + dy * math.cos(angle))]
            for actual, desired in zip(result, expected):
                self.assertAlmostEqual(actual, desired)

    def test_hold_zero_never_receives_body_deformation(self):
        samples = {"axes": [{"id": "ParamBreath", "default": 0, "keys": [0, 1]}], "baseline": [[0, 0], [100, 0]],
                   "samples": [{"pose": {"ParamBreath": value}, "palms": [[0, value], [100, value]]}
                               for value in [0, 1]]}
        recipe = MODULE.compile_recipe(samples, Path("/tmp/own-project.psd2live"), [0, 0, 100, 100])
        warp = next(step["request"] for step in recipe["steps"] if step["operation"] == "canvas_warp")
        self.assertEqual(warp["meshes"], [])  # Required even for parent_of_deformer in v3.6.7.
        seeds = [change for step in recipe["steps"] if step["operation"] == "keyform_apply"
                 for change in step["request"]["changes"] if change["target"] == "warp:OriginalCupHoldFollow"]
        self.assertEqual(len([seed for seed in seeds if seed["key"]["ParamCupHold"] == 0]), 2)
        for step in recipe["steps"]:
            if step["operation"] == "rig_deform":
                self.assertTrue(all(change["key"]["ParamCupHold"] == 1 for change in step["request"]["changes"]))

    def test_missing_body_key_and_degenerate_grips_fail(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            MODULE.similarity([[0, 0], [0, 0]], [[0, 0], [1, 1]], [0, 0])
        incomplete = {"axes": [{"id": "ParamBreath", "default": 0, "keys": [0, 1]}], "baseline": [[0, 0], [100, 0]],
                      "samples": [{"pose": {"ParamBreath": 0}, "palms": [[0, 0], [100, 0]]}]}
        with self.assertRaisesRegex(ValueError, "incomplete body key grid"):
            MODULE.compile_recipe(incomplete, Path("/tmp/own-project.psd2live"), [0, 0, 100, 100])


if __name__ == "__main__":
    unittest.main()
