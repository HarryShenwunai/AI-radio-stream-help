"""Actual Handler upload/preview/activation/resource lifecycle for synthetic layers.

The tiny geometric fixture proves format behavior, not target character art quality.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import unittest

from PIL import Image

import test_character_http as http_fixture
import test_layered_2d_assets as layer_fixture
import test_avatar_png_regions as region_fixture


class Layered2DHTTPTests(unittest.TestCase):
    # Reuse setup/helpers without inheriting/re-discovering the PNG test suite.
    setUp = http_fixture.CharacterHTTPTests.setUp
    tearDown = http_fixture.CharacterHTTPTests.tearDown
    request = http_fixture.CharacterHTTPTests.request
    post = http_fixture.CharacterHTTPTests.post
    state = http_fixture.CharacterHTTPTests.state
    create = http_fixture.CharacterHTTPTests.create
    select = http_fixture.CharacterHTTPTests.select
    import_asset = http_fixture.CharacterHTTPTests.import_asset
    activate = http_fixture.CharacterHTTPTests.activate
    appearance_id = http_fixture.CharacterHTTPTests.appearance_id
    assets = http_fixture.CharacterHTTPTests.assets

    def upload_payload(self, package=None):
        return {"character_id": self.initial_id, "format": "layered-2d",
                "model": {"filename": "test-only-layers.zip", "data_base64": base64.b64encode(
                    layer_fixture.package() if package is None else package).decode()}}

    def test_real_http_preview_resources_auth_activate_switch_rollback_delete(self):
        before = self.appearance_id()
        result = self.post("characters/assets/import", self.upload_payload())
        asset = result["asset"]
        self.assertEqual(asset["format"], "layered-2d")
        self.assertEqual(self.appearance_id(), before, "preview must not activate")
        self.assertEqual(asset["states"], {})
        self.assertTrue(asset["capabilities"]["talk_blink"])
        self.assertEqual(asset["art_review"], "not_run")
        self.assertFalse(asset["live2d"])
        self.assertNotIn(self.tmp.name, json.dumps(asset))
        self.assertEqual(len(asset["resources_urls"]), 6)
        self.assertIn("?character_id=" + self.initial_id, asset["model_url"])
        status, headers, body = self.request("GET", asset["model_url"])
        self.assertEqual(status, 200, body)
        self.assertIn("json", headers.get("Content-Type", ""))
        model = json.loads(body)
        self.assertEqual(model["layers"], asset["layers"])
        for url in [asset["model_url"], asset["thumbnail"]["url"], *asset["resources_urls"].values()]:
            status, _, body = self.request("GET", url)
            self.assertEqual(status, 200, (url, body))
            if url != asset["model_url"]:
                with Image.open(io.BytesIO(body)) as image:
                    image.load()
                    self.assertEqual(image.mode, "RGBA")
            status, _, _ = self.request("GET", url, auth=False)
            self.assertIn(status, (401, 403))
        self.activate(self.initial_id, asset["id"])
        self.assertEqual(self.appearance_id(), asset["id"])
        appearance = self.state()["active_character"]["appearance"]
        self.assertEqual(appearance["model_url"], asset["model_url"])
        self.post("characters/assets/delete", {"character_id": self.initial_id, "asset_id": asset["id"]}, expected=409)
        other = self.create("HTTP测试角色")
        other_asset = self.import_asset(other)
        self.activate(other, other_asset["id"])
        self.select(self.initial_id)
        self.assertEqual(self.appearance_id(), asset["id"])
        # Revert only the explicit original profile appearance; preserve other profiles.
        self.activate(self.initial_id, before)
        self.post("characters/assets/delete", {"character_id": self.initial_id, "asset_id": asset["id"]})
        status, _, _ = self.request("GET", asset["model_url"])
        self.assertEqual(status, 404)
        self.assertNotIn(asset["id"], {a["id"] for a in self.assets(self.initial_id)})
        self.select(other)
        self.assertEqual(self.appearance_id(), other_asset["id"])

    def test_unauthorized_origin_and_embedded_code_are_rejected_without_execution(self):
        before, count = self.appearance_id(), len(self.assets(self.initial_id))
        payload = self.upload_payload()
        status, _, _ = self.request("POST", "/api/characters/assets/import", payload, auth=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/characters/assets/import", payload, origin="https://foreign.invalid")
        self.assertEqual(status, 403)
        canary = Path(self.tmp.name) / "SHOULD_NOT_EXECUTE"
        code = f"from pathlib import Path; Path({str(canary)!r}).write_text('executed')".encode()
        package = layer_fixture.package(extras=[("script.py", code)])
        self.post("characters/assets/import", self.upload_payload(package), expected=400)
        doc = layer_fixture.document()
        doc["layers"][0]["motion"]["onload"] = code.decode()
        self.post("characters/assets/import", self.upload_payload(layer_fixture.package(doc)), expected=400)
        self.assertFalse(canary.exists())
        self.assertEqual(self.appearance_id(), before)
        self.assertEqual(len(self.assets(self.initial_id)), count)

    def test_png_regions_upload_and_revision_preview_preserve_active_and_png_bytes(self):
        before = self.appearance_id()
        raw = region_fixture.png((130, 160, 180, 240))
        payload = {"character_id": self.initial_id, "format": "png-states",
                   "animation_regions": region_fixture.REGIONS,
                   "states": {name: {"filename": name+".png", "data_base64": base64.b64encode(raw).decode()}
                              for name in ("idle", "talk", "blink", "talk_blink")}}
        first = self.post("characters/assets/import", payload)["asset"]
        self.assertEqual(first["animation_regions"], region_fixture.REGIONS)
        self.assertEqual(self.appearance_id(), before)
        self.activate(self.initial_id, first["id"])
        status, _, original_png = self.request("GET", first["states"]["idle"]["url"])
        self.assertEqual(status, 200)
        changed_regions = {"eyes": {"x": 20, "y": 20, "width": 60, "height": 12}}
        revision_payload = {"character_id": self.initial_id, "asset_id": first["id"],
                            "animation_regions": changed_regions}
        changed = self.post("characters/assets/regions", revision_payload)["asset"]
        self.assertNotEqual(changed["id"], first["id"])
        self.assertEqual(changed["animation_regions"]["eyes"]["feather"], 0)
        self.assertEqual(self.appearance_id(), first["id"], "region preview cannot activate")
        status, _, revised_png = self.request("GET", changed["states"]["idle"]["url"])
        self.assertEqual(status, 200)
        self.assertEqual(original_png, revised_png)
        status, _, still_original = self.request("GET", first["states"]["idle"]["url"])
        self.assertEqual(status, 200)
        self.assertEqual(original_png, still_original)
        active = self.state()["active_character"]["appearance"]
        self.assertEqual(active["animation_regions"], region_fixture.REGIONS)
        count = len(self.assets(self.initial_id))
        bad = {**revision_payload, "animation_regions": [changed_regions["eyes"]]}
        self.post("characters/assets/regions", bad, expected=400)
        self.assertEqual(len(self.assets(self.initial_id)), count)
        self.assertEqual(self.appearance_id(), first["id"])
        status, _, _ = self.request("POST", "/api/characters/assets/regions", revision_payload, auth=False)
        self.assertEqual(status, 403)
        self.activate(self.initial_id, changed["id"])
        cleared = self.post("characters/assets/regions", {"character_id": self.initial_id,
                            "asset_id": changed["id"], "animation_regions": None})["asset"]
        self.assertNotIn("animation_regions", cleared)
        self.assertEqual(self.appearance_id(), changed["id"])


if __name__ == "__main__":
    unittest.main()
