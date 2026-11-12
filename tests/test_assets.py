"""Real decoder/filesystem checks on synthetic PNGs; no third-party artwork."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
import zlib

from PIL import Image, PngImagePlugin
from companion_runtime import assets
from companion_runtime.assets import AssetError, AssetStore


def png(size=(24, 40), colour=(120, 60, 160, 130), *, note=None):
    image = Image.new("RGBA", size, colour)
    stream = io.BytesIO()
    options = {}
    if note is not None:
        info = PngImagePlugin.PngInfo()
        info.add_text("author-private-note", note)
        options["pnginfo"] = info
    image.save(stream, format="PNG", **options)
    image.close()
    return stream.getvalue()


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def crafted_header(width, height, *, depth=8):
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, 6, 0, 0, 0))
    return assets.PNG_SIGNATURE + header + chunk(b"IDAT", zlib.compress(b"\0\0\0\0\0")) + chunk(b"IEND", b"")


class AssetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "assets"
        self.store = AssetStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_two_independent_images_and_arbitrary_source_names_are_importable(self):
        first = self.store.import_png_states({"idle": png((24, 40))}, {"idle": "自选角色.png"})
        second = self.store.import_png_states({"idle": png((70, 16), (10, 90, 70, 255))}, {"idle": "OTHER-NAME.PNG"})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second["width"], 70)
        self.assertEqual(len(self.store.list_assets()), 2)
        self.assertNotIn("自选角色", json.dumps(first, ensure_ascii=False))
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_static_image_remains_usable_without_optional_states(self):
        result = self.store.import_png_states({"idle": png()})
        self.assertEqual(set(result["states"]), {"idle"})
        self.assertEqual(result["capabilities"], {"static": True, "talk": False, "blink": False, "talk_blink": False})
        self.assertEqual(self.store.resolve(result["id"], "idle.png").read_bytes()[:8], assets.PNG_SIGNATURE)
        with self.assertRaises(AssetError):
            self.store.resolve(result["id"], "talk.png")

    def test_four_states_manifest_sizes_hashes_and_thumbnail(self):
        states = {state: png((280, 420), (n * 40, 80, 120, 255)) for n, state in enumerate(assets.STATE_NAMES)}
        result = self.store.import_png_states(states)
        self.assertEqual(result["total_pixels"], 280 * 420 * 4)
        self.assertTrue(all(result["capabilities"].values()))
        for state, desc in result["states"].items():
            encoded = self.store.resolve(result["id"], desc["resource"]).read_bytes()
            self.assertEqual(len(encoded), desc["bytes"])
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), desc["sha256"])
        with Image.open(self.store.resolve(result["id"], "thumbnail.png")) as thumb:
            self.assertLessEqual(max(thumb.size), 256)
        self.assertEqual(self.store.get(result["id"]), result)

    def test_uploaded_metadata_is_not_saved_and_rgba_pixels_survive(self):
        original = png(colour=(7, 90, 230, 17), note="private marker do not preserve")
        result = self.store.import_png_states({"idle": original})
        encoded = self.store.resolve(result["id"], "idle.png").read_bytes()
        self.assertNotIn(b"private marker", encoded)
        with Image.open(io.BytesIO(encoded)) as decoded:
            self.assertEqual(decoded.mode, "RGBA")
            self.assertEqual(decoded.getpixel((1, 1)), (7, 90, 230, 17))
            self.assertNotIn("author-private-note", decoded.info)

    def test_compressed_metadata_is_removed_before_text_decoder(self):
        raw = png()
        # A highly expanding optional text chunk must not be decompressed just
        # to display a role. The chunk CRC remains checked before it is removed.
        metadata = chunk(b"zTXt", b"note\0\0" + zlib.compress(b"X" * 2_000_000))
        supplied = raw[:-12] + metadata + raw[-12:]
        result = self.store.import_png_states({"idle": supplied})
        self.assertNotIn(b"zTXt", self.store.resolve(result["id"], "idle.png").read_bytes())

    def test_palette_transparency_survives_normalisation(self):
        image = Image.new("P", (9, 13))
        image.putpalette([240, 40, 50] * 256)
        image.info["transparency"] = 0
        output = io.BytesIO()
        image.save(output, format="PNG")
        image.close()
        result = self.store.import_png_states({"idle": output.getvalue()})
        with Image.open(self.store.resolve(result["id"], "idle.png")) as converted:
            self.assertEqual(converted.getpixel((0, 0))[3], 0)

    def test_invalid_state_names_and_missing_idle(self):
        for supplied in [{}, {"talk": png()}, {"idle": png(), "../other": png()}, {"idle": png(), "owner": png()}]:
            with self.subTest(keys=list(supplied)), self.assertRaises(AssetError):
                self.store.import_png_states(supplied)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_filenames_are_only_display_input_and_do_not_choose_paths(self):
        for name in ["../x.png", "C:\\x.png", "bad\x00.png", "image.jpeg", "https://x/a.png", "x" * 260 + ".png"]:
            with self.subTest(name=name), self.assertRaises(AssetError):
                self.store.import_png_states({"idle": png()}, {"idle": name})
        with self.assertRaises(AssetError):
            self.store.import_png_states({"idle": png()}, {})
        self.assertFalse(list(self.root.iterdir()))

    def test_false_extension_or_other_format_is_rejected(self):
        output = io.BytesIO()
        Image.new("RGB", (10, 10)).save(output, format="JPEG")
        for data in [b"not an image", output.getvalue(), b"<svg onload='x'/>"]:
            with self.subTest(data=data[:10]), self.assertRaises(AssetError):
                self.store.import_png_states({"idle": data}, {"idle": "pretend.png"})
        self.assertFalse(list(self.root.iterdir()))

    def test_bad_crc_and_truncation_and_trailing_payload_are_rejected(self):
        raw = png()
        corrupt = bytearray(raw)
        corrupt[-15] ^= 1
        for data in [raw[:-1], bytes(corrupt), raw + b"trailing", raw[:16]]:
            with self.subTest(length=len(data)), self.assertRaises(AssetError):
                self.store.import_png_states({"idle": data})
        self.assertFalse(list(self.root.iterdir()))

    def test_unknown_critical_and_animated_chunks_are_rejected(self):
        raw = png()
        for kind in [b"ABCD", b"acTL", b"fcTL", b"fdAT"]:
            altered = raw[:-12] + chunk(kind, b"\0" * 8) + raw[-12:]
            with self.subTest(kind=kind), self.assertRaises(AssetError):
                self.store.import_png_states({"idle": altered})

    def test_duplicate_header_and_invalid_compressed_pixels_are_rejected(self):
        raw = png()
        duplicate = raw[:33] + raw[8:33] + raw[33:]
        for data in [duplicate, crafted_header(200, 200)]:
            with self.assertRaises(AssetError):
                self.store.import_png_states({"idle": data})
        self.assertFalse(list(self.root.iterdir()))

    def test_large_declared_dimensions_are_rejected_before_decoder(self):
        for width, height in [(0, 1), (4097, 1), (3000, 3000), (2**32 - 1, 3)]:
            with self.subTest(width=width, height=height), patch.object(assets, "_normalise") as decoder:
                with self.assertRaises(AssetError) as caught:
                    self.store.import_png_states({"idle": crafted_header(width, height)})
                self.assertEqual(caught.exception.status, 413)
                decoder.assert_not_called()

    def test_16bit_is_explicitly_unsupported_not_silently_clipped(self):
        with self.assertRaisesRegex(AssetError, "16bit"):
            self.store.import_png_states({"idle": crafted_header(10, 10, depth=16)})

    def test_per_file_and_total_encoded_budgets(self):
        with self.assertRaises(AssetError) as caught:
            self.store.import_png_states({"idle": b"x" * (assets.MAX_FILE_BYTES + 1)})
        self.assertEqual(caught.exception.status, 413)
        with patch.object(assets, "MAX_TOTAL_BYTES", 100):
            with self.assertRaises(AssetError) as caught:
                self.store.import_png_states({"idle": png(), "talk": png()})
            self.assertEqual(caught.exception.status, 413)
        self.assertFalse(list(self.root.iterdir()))

    def test_state_size_mismatch_and_total_pixels_fail_before_decoding(self):
        for supplied in [{"idle": png(), "talk": png((25, 40))},
                         {"idle": png((60, 60)), "talk": png((60, 60))}]:
            limit = 4000 if supplied["idle"] == png((60, 60)) else assets.MAX_TOTAL_PIXELS
            with patch.object(assets, "MAX_TOTAL_PIXELS", limit), patch.object(assets, "_normalise") as decoder:
                with self.assertRaises(AssetError):
                    self.store.import_png_states(supplied)
                decoder.assert_not_called()
        self.assertFalse(list(self.root.iterdir()))

    def test_normalised_output_and_thumbnail_share_total_disk_budget(self):
        supplied = png()
        normal, image, _, _ = assets._normalise(supplied)
        image.close()
        # The input fits but the thumbnail plus normalised state must not evade
        # the total stored-image bound.
        with patch.object(assets, "MAX_TOTAL_BYTES", max(len(supplied), len(normal)) + 1):
            with self.assertRaises(AssetError) as caught:
                self.store.import_png_states({"idle": supplied})
            self.assertEqual(caught.exception.status, 413)
        self.assertFalse(list(self.root.iterdir()))

    def test_save_failure_cleans_staging_and_preserves_older_revision(self):
        original = self.store.import_png_states({"idle": png()})
        real_write = Path.write_bytes
        def fail_talk(path, value):
            if path.name == "talk.png":
                raise OSError("synthetic disk full")
            return real_write(path, value)
        with patch.object(Path, "write_bytes", fail_talk):
            with self.assertRaises(AssetError) as caught:
                self.store.import_png_states({"idle": png(), "talk": png()})
            self.assertEqual(caught.exception.status, 503)
        self.assertEqual([p.name for p in self.root.iterdir()], [original["id"]])
        self.assertEqual(self.store.get(original["id"]), original)

    def test_cancel_before_and_during_import_leaves_no_partial_revision(self):
        stopped = threading.Event()
        stopped.set()
        with self.assertRaisesRegex(AssetError, "取消"):
            self.store.import_png_states({"idle": png()}, cancel_event=stopped)
        stopped.clear()
        real = assets._normalise
        def cancel_after_decode(value):
            result = real(value)
            stopped.set()
            return result
        with patch.object(assets, "_normalise", cancel_after_decode):
            with self.assertRaisesRegex(AssetError, "取消"):
                self.store.import_png_states({"idle": png()}, cancel_event=stopped)
        self.assertFalse(list(self.root.iterdir()))

    def test_resolve_blocks_traversal_unknown_resources_and_manifest(self):
        item = self.store.import_png_states({"idle": png()})
        for resource in ["../manifest.json", "manifest.json", "idle.png/../manifest.json", "/etc/passwd", "IDLE.png", "talk.png", None]:
            with self.subTest(resource=resource), self.assertRaises(AssetError) as error:
                self.store.resolve(item["id"], resource)
            self.assertEqual(error.exception.status, 404)
        for identifier in ["../outside", "no-id", item["id"].upper(), str(uuid4())]:
            with self.subTest(identifier=identifier), self.assertRaises(AssetError):
                self.store.resolve(identifier, "idle.png")

    def test_symlinks_are_not_followed_during_resolve_or_delete(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_text("keep")
        fake_id = str(uuid4())
        try:
            (self.root / fake_id).symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows account lacks the privilege to create test symlinks')
            raise
        with self.assertRaises(AssetError):
            self.store.delete(fake_id)
        self.assertEqual(marker.read_text(), "keep")
        item = self.store.import_png_states({"idle": png()})
        path = self.root / item["id"] / "idle.png"
        path.unlink()
        path.symlink_to(marker)
        with self.assertRaises(AssetError):
            self.store.resolve(item["id"], "idle.png")
        self.store.delete(item["id"])
        self.assertTrue(marker.exists())

    def test_corrupt_manifest_or_missing_file_does_not_break_listing(self):
        first = self.store.import_png_states({"idle": png()})
        second = self.store.import_png_states({"idle": png((32, 24))})
        path = self.root / first["id"] / "manifest.json"
        document = json.loads(path.read_text())
        document["states"]["idle"]["resource"] = "../../outside"
        path.write_text(json.dumps(document))
        with self.assertRaises(AssetError) as error:
            self.store.get(first["id"])
        self.assertEqual(error.exception.status, 409)
        self.assertEqual([item["id"] for item in self.store.list_assets()], [second["id"]])
        (self.root / second["id"] / "idle.png").unlink()
        self.assertEqual(self.store.list_assets(), [])

    def test_delete_and_cleanup_failure_are_explicit(self):
        item = self.store.import_png_states({"idle": png()})
        self.assertEqual(self.store.delete(item["id"]), {"id": item["id"], "deleted": True, "cleanup_pending": False})
        with self.assertRaises(AssetError):
            self.store.get(item["id"])
        item = self.store.import_png_states({"idle": png()})
        with patch.object(assets.shutil, "rmtree", side_effect=OSError("locked")):
            result = self.store.delete(item["id"])
        self.assertTrue(result["cleanup_pending"])
        self.assertEqual(self.store.list_assets(), [])
        self.assertTrue(any(p.name.startswith(".trash-") for p in self.root.iterdir()))

    def test_store_instances_share_root_lock_and_imports_have_distinct_ids(self):
        second = AssetStore(self.root)
        self.assertIs(self.store._lock, second._lock)
        imported = []
        threads = [threading.Thread(target=lambda store=store: imported.append(store.import_png_states({"idle": png()}))) for store in [self.store, second]]
        for worker in threads:worker.start()
        for worker in threads:worker.join(5)
        self.assertEqual(len(imported), 2)
        self.assertEqual(len({item["id"] for item in imported}), 2)
        self.assertEqual(len(self.store.list_assets()), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
