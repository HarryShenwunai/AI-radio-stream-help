"""Prevent asset registration from changing identity pixels or original workspaces."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "r3_mattes", ROOT / "scripts/r3_both_eyes/prepare_transparent_stage.py"
)
matte = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matte)


class MatteContractTests(unittest.TestCase):
    def test_original_directory_and_ancestors_are_never_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "original"
            source.mkdir()
            for output in [source, source / "nested", source.parent]:
                with self.subTest(output=output), self.assertRaises(ValueError):
                    matte.separate_workspace(output, source)
            matte.separate_workspace(source.parent / "candidate", source)

    def test_symlink_cannot_hide_an_original_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "original"
            source.mkdir()
            alias = Path(tmp) / "alias"
            alias.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                matte.separate_workspace(alias, source)

    def test_alpha_extraction_preserves_rgb_and_face_holes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            image = Image.new("RGBA", (3, 3), (80, 70, 60, 255))
            image.putpixel((0, 0), (80, 70, 60, 0))
            image.save(p / "source.png")
            image.putpixel((1, 0), (80, 70, 60, 128))
            image.save(p / "out.png")
            self.assertTrue(
                matte.check_hair(p / "source.png", p / "out.png")["rgb_identical"]
            )
            image.putpixel((0, 0), (80, 70, 60, 128))
            image.save(p / "out.png")
            with self.assertRaisesRegex(ValueError, "face/neck"):
                matte.check_hair(p / "source.png", p / "out.png")

    def test_regenerated_hair_color_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            image = Image.new("RGBA", (3, 3), (80, 70, 60, 255))
            image.putpixel((0, 0), (80, 70, 60, 0))
            image.save(p / "source.png")
            image.putpixel((1, 1), (110, 80, 60, 255))
            image.save(p / "out.png")
            with self.assertRaisesRegex(ValueError, "RGB changed"):
                matte.check_hair(p / "source.png", p / "out.png")

    def test_face_overlap_gaps_fail_even_when_rgb_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            old = Image.new("RGBA", (3, 3), (80, 70, 60, 255))
            old.save(p / "old.png")
            mask = Image.new("L", (3, 3), 0)
            mask.putpixel((1, 1), 255)
            mask.save(p / "mask.png")
            new = old.copy()
            new.putpixel((0, 0), (80, 70, 60, 0))
            new.save(p / "new.png")
            self.assertEqual(
                matte.check_face_overlap(p / "old.png", p / "new.png", p / "mask.png")[
                    "protected_authored_hair_pixels"
                ],
                1,
            )
            new.putpixel((1, 1), (80, 70, 60, 0))
            new.save(p / "new.png")
            with self.assertRaisesRegex(ValueError, "opened a gap"):
                matte.check_face_overlap(p / "old.png", p / "new.png", p / "mask.png")

    def test_high_depth_protection_cannot_saturate_into_false_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            Image.new("RGBA", (3, 3), (80, 70, 60, 255)).save(p / "old.png")
            Image.new("RGBA", (3, 3), (80, 70, 60, 1)).save(p / "new.png")
            # 300/65535 is almost transparent, but PIL convert("L") saturates it.
            Image.new("I;16", (3, 3), 300).save(p / "mask.png")
            with self.assertRaisesRegex(ValueError, "8-bit grayscale"):
                matte.check_face_overlap(p / "old.png", p / "new.png", p / "mask.png")

    def test_rescaled_subject_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            Image.new("RGBA", (3, 3)).save(p / "source.png")
            Image.new("RGBA", (4, 3)).save(p / "out.png")
            with self.assertRaisesRegex(ValueError, "dimensions"):
                matte.check_hair(p / "source.png", p / "out.png")


if __name__ == "__main__":
    unittest.main()
