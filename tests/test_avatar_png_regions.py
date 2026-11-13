"""PNG eye/mouth clips are immutable metadata revisions, not artwork edits."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from companion_runtime.assets import AssetError, AssetStore


def png(color):
    with Image.new("RGBA", (100, 100), color) as image:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


REGIONS = {"eyes": {"x": 20, "y": 20, "width": 60, "height": 12, "feather": 3},
           "mouth": {"x": 35, "y": 48, "width": 30, "height": 12, "feather": 3}}


class PNGAnimationRegions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = AssetStore(self.temp.name)
        self.states = {"idle": png((100, 110, 120, 240)), "talk": png((120, 130, 140, 240)),
                       "blink": png((140, 150, 160, 240)), "talk_blink": png((160, 170, 180, 240))}

    def test_valid_clips_persist_and_do_not_edit_any_png(self):
        original = self.store.import_png_states(self.states)
        with_regions = self.store.import_png_states(self.states, animation_regions=REGIONS)
        self.assertNotIn("animation_regions", original)
        self.assertEqual(with_regions["animation_regions"], REGIONS)
        self.assertEqual(self.store.get(with_regions["id"]), with_regions)
        for state in self.states:
            first = self.store.resolve(original["id"], state + ".png").read_bytes()
            second = self.store.resolve(with_regions["id"], state + ".png").read_bytes()
            self.assertEqual(first, second, "metadata must not change normalized PNG bytes")

    def test_invalid_clips_fail_before_decode_and_leave_no_revision(self):
        invalids = [[], {}, [REGIONS["eyes"]], {"body": REGIONS["eyes"]},
                    {"eyes": {**REGIONS["eyes"], "x": True}},
                    {"eyes": {**REGIONS["eyes"], "x": float("nan")}},
                    {"eyes": {**REGIONS["eyes"], "x": -1}},
                    {"eyes": {**REGIONS["eyes"], "x": 99}},
                    {"eyes": {**REGIONS["eyes"], "width": 0}},
                    {"eyes": {**REGIONS["eyes"], "feather": 4}},
                    {"eyes": {**REGIONS["eyes"], "feather": 17}},
                    {"eyes": {**REGIONS["eyes"], "script": "run()"}},
                    {"eyes": {"x": 0, "y": 0, "width": 100, "height": 31}},
                    {"eyes": REGIONS["eyes"], "mouth": {**REGIONS["mouth"], "y": 25}}]
        with patch("companion_runtime.assets._normalise", side_effect=AssertionError("should not decode")):
            for regions in invalids:
                with self.subTest(regions=regions), self.assertRaises(AssetError):
                    self.store.import_png_states(self.states, animation_regions=regions)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_area_boundary_touching_edges_and_default_feather(self):
        regions = {"eyes": {"x": 0, "y": 0, "width": 100, "height": 30}}
        result = self.store.import_png_states(self.states, animation_regions=regions)
        self.assertEqual(result["animation_regions"]["eyes"]["feather"], 0)
        touching = {"eyes": {"x": 10, "y": 10, "width": 30, "height": 10},
                    "mouth": {"x": 40, "y": 10, "width": 30, "height": 10}}
        self.store.import_png_states(self.states, animation_regions=touching)

    def test_revise_and_clear_create_new_preview_and_preserve_original(self):
        original = self.store.import_png_states(self.states)
        old_bytes = {name: self.store.resolve(original["id"], name+".png").read_bytes() for name in self.states}
        updated = self.store.revise_png_animation_regions(original["id"], REGIONS)
        self.assertNotEqual(updated["id"], original["id"])
        self.assertEqual(self.store.get(original["id"]), original)
        self.assertEqual(updated["animation_regions"], REGIONS)
        cleared = self.store.revise_png_animation_regions(updated["id"], None)
        self.assertNotIn("animation_regions", cleared)
        self.assertNotEqual(cleared["id"], updated["id"])
        for name in self.states:
            self.assertEqual(self.store.resolve(original["id"], name+".png").read_bytes(), old_bytes[name])
            self.assertEqual(self.store.resolve(updated["id"], name+".png").read_bytes(), old_bytes[name])
        count = len(self.store.list_assets())
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(AssetError):
            self.store.revise_png_animation_regions(updated["id"], REGIONS, cancel_event=cancel)
        with self.assertRaises(AssetError):
            self.store.revise_png_animation_regions(updated["id"], {"eyes": {"x": -1}})
        self.assertEqual(len(self.store.list_assets()), count)

    def test_tampered_regions_fail_get_and_are_omitted_from_listing(self):
        manifest = self.store.import_png_states(self.states, animation_regions=REGIONS)
        path = Path(self.temp.name) / manifest["id"] / "manifest.json"
        for invalid in (None, [], {"eyes": {**REGIONS["eyes"], "x": -1}}):
            changed = copy.deepcopy(manifest)
            changed["animation_regions"] = invalid
            path.write_text(json.dumps(changed))
            with self.subTest(invalid=invalid), self.assertRaises(AssetError):
                self.store.get(manifest["id"])
            self.assertEqual(self.store.list_assets(), [])


if __name__ == "__main__":
    unittest.main()
