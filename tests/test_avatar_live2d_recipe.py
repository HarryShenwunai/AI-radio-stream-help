"""Refuse ambiguous imported objects rather than rigging a different layer."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SPEC = importlib.util.spec_from_file_location(
    "avatar_recipe", Path(__file__).resolve().parents[1] / "scripts/avatar_live2d_recipe.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeReadClient:
    def __init__(self, items):
        self.items = items

    def call(self, operation, request):
        if operation != "workspace_inspect":
            raise AssertionError("mutating operation invoked during validation")
        return {"items": self.items}, []


class AuthoringRecipeTests(unittest.TestCase):
    def test_actual_parent_is_resolved_without_guessing_generator_id(self):
        client = FakeReadClient([{"name": "topwear", "target": "mesh:RealBody17",
                                  "parentId": "RealBreathParent42"}])
        self.assertEqual(MODULE.resolve({"parent_id": "$parent:topwear"}, client, {}),
                         {"parent_id": "RealBreathParent42"})

    def test_ambiguous_name_and_unknown_variable_fail(self):
        items = [{"name": "hand", "target": "mesh:" + suffix} for suffix in ["L", "R"]]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.named(FakeReadClient(items), "mesh", "hand")
        with self.assertRaisesRegex(ValueError, "unknown recipe variable"):
            MODULE.resolve("$invented", FakeReadClient([]), {})

    def test_arbitrary_shell_and_source_paint_are_rejected_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            for operation in ["shell", "raster_paint", "arbitrary_script"]:
                recipe = {"format": "original-live2d-recipe-v1", "steps": [
                    {"operation": operation, "request": {}}]}
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "unsupported"):
                    MODULE.run(FakeReadClient([]), recipe, {}, Path(directory) / "audit.json")


if __name__ == "__main__":
    unittest.main()
