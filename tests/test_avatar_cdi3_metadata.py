"""Bounded PSD2Live display labels; no executable fields or fake MOC is involved."""
import copy
import json
import unittest

from companion_runtime.assets import AssetError
from companion_runtime import live2d_assets as live


class CDI3DrawableMetadata(unittest.TestCase):
    def setUp(self):
        self.doc = {"Version": 3, "Parameters": [], "ParameterGroups": [], "Parts": [],
                    "Drawables": [{"Id": "ArtMeshFace", "Name": "Face"},
                                  {"Id": "ArtMeshIridesL", "Name": "iris-l"}]}

    def validate(self, doc):
        parsed = live._json(json.dumps(doc).encode())
        live._auxiliary(parsed, "cdi3.json")
        return parsed

    def test_real_extension_labels_are_preserved_without_rewriting(self):
        self.assertEqual(self.validate(self.doc), self.doc)
        mixed = {**self.doc, "ArtMeshes": [{"Id": "EditorMesh", "Name": "Existing metadata"}]}
        self.assertEqual(self.validate(mixed), mixed)

    def test_drawable_rows_keep_strict_shape_text_and_count_limits(self):
        values = [{}, "not-an-array", ["not-an-object"], [{"Id": "x"}],
                  [{"Id": "x", "Name": "label", "code": "run()"}],
                  [{"Id": "x" * 257, "Name": "label"}],
                  [{"Id": "x", "Name": "y" * 513}],
                  [{"Id": "x", "Name": "bad\0label"}],
                  [{"Id": "x", "Name": "label"}] * 4097]
        for value in values:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(AssetError):
                self.validate({**self.doc, "Drawables": value})

    def test_no_general_unknown_field_script_or_remote_resource_relaxation(self):
        for name in ("Script", "onload", "url", "UnexpectedExtension"):
            doc = copy.deepcopy(self.doc)
            doc[name] = "not allowed"
            with self.subTest(field=name), self.assertRaises(AssetError):
                self.validate(doc)


if __name__ == "__main__":
    unittest.main()
