"""Source-to-authoring architecture gates, not visual character acceptance."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "character_recipe", Path(__file__).resolve().parents[1] / "scripts/avatar_live2d_character_recipe.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source_contract():
    names = ["topwear", "cup", "upper lip", "lower lip", "mouth", "mouth close", "upper teeth", "tongue"]
    for side in ("l", "r"):
        names.extend(part + "-" + side for part in ("upperarm", "forearm", "hand", "cuff-front"))
        names.extend("finger-" + finger + "-" + side for finger in ("thumb", "index", "middle", "ring", "little"))
    manifest = {"layers": [{"name": name, "width": 200, "height": 100, "visible": True} for name in names]}
    body = {part + "_" + side: {"target": {"x": 200, "y": 300}}
            for part in ("shoulder", "elbow") for side in ("l", "r")}
    hands = {"fingers": [{"name": name, "texture_supported_anchors": {"root_target": {"x": 20, "y": 30}}}
                          for name in names if name.startswith("finger-")]}
    wrists = {side: {"x": 200, "y": 300} for side in ("l", "r")}
    return manifest, body, hands, wrists


class OriginalCharacterRecipeTests(unittest.TestCase):
    def test_cup_is_root_bound_and_excluded_from_all_hand_rotations(self):
        recipe = MODULE.compile_recipe(*source_contract())
        edits = next(step["request"]["edits"] for step in recipe["steps"]
                     if step["operation"] == "object_edit_appearance")
        cup = next(edit for edit in edits if edit["id"] == "$mesh:cup")
        self.assertIsNone(cup["parent_id"])
        for step in recipe["steps"]:
            if step["operation"] == "canvas_rotation" and step["request"]["id"] != "OriginalCupRoot":
                self.assertNotIn("$mesh:cup", step["request"]["meshes"])

    def test_cuff_rim_inherits_elbow_but_not_wrist_or_fingers(self):
        recipe = MODULE.compile_recipe(*source_contract())
        rotations = {step["request"]["id"]: step["request"] for step in recipe["steps"]
                     if step["operation"] == "canvas_rotation"}
        self.assertIn("$mesh:cuff-front-r", rotations["OriginalElbowR"]["meshes"])
        self.assertNotIn("$mesh:cuff-front-r", rotations["OriginalWristR"]["meshes"])

    def test_missing_source_part_or_hidden_closed_mouth_fails(self):
        manifest, body, hands, wrists = source_contract()
        invalid = copy.deepcopy(manifest)
        invalid["layers"] = [layer for layer in invalid["layers"] if layer["name"] != "finger-thumb-r"]
        with self.assertRaisesRegex(ValueError, "missing actual source parts"):
            MODULE.compile_recipe(invalid, body, hands, wrists)
        next(layer for layer in manifest["layers"] if layer["name"] == "mouth close")["visible"] = False
        with self.assertRaisesRegex(ValueError, "real enabled source layer"):
            MODULE.compile_recipe(manifest, body, hands, wrists)

    def test_source_guides_are_required_and_no_unimplemented_hold_parameter_created(self):
        manifest, body, hands, wrists = source_contract()
        with self.assertRaisesRegex(ValueError, "all ten fingers"):
            MODULE.compile_recipe(manifest, body, {"fingers": hands["fingers"][:-1]}, wrists)
        recipe = MODULE.compile_recipe(manifest, body, hands, wrists)
        parameters = [step["request"]["parameter_id"] for step in recipe["steps"]
                      if step["operation"] == "parameter_create"]
        self.assertNotIn("ParamCupHold", parameters)
        self.assertEqual(len(parameters), 20)


if __name__ == "__main__":
    unittest.main()
