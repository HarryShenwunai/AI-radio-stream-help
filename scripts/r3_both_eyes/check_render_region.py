"""Reject any rendered pixel drift outside the explicitly allowed edit rectangle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw


def compare(before: Path, after: Path, region: tuple[int, int, int, int]) -> dict:
    with Image.open(before) as a, Image.open(after) as b:
        if a.size != b.size:
            raise ValueError("Render dimensions differ")
        left, top, right, bottom = region
        if not 0 <= left < right <= a.width or not 0 <= top < bottom <= a.height:
            raise ValueError("Allowed edit rectangle is outside the render")
        delta = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))
        maximum = ImageChops.lighter(
            ImageChops.lighter(delta.getchannel("R"), delta.getchannel("G")),
            ImageChops.lighter(delta.getchannel("B"), delta.getchannel("A")),
        )
        outside = Image.new("L", a.size, 255)
        ImageDraw.Draw(outside).rectangle((left, top, right - 1, bottom - 1), fill=0)
        escaped = ImageChops.multiply(maximum, outside)
        if escaped.getbbox():
            raise ValueError(
                "Pixel drift outside allowed eye region: " + str(escaped.getbbox())
            )
        return {
            "check": "edit_region_containment_only",
            "visual_acceptance": "not_evaluated",
            "size": a.size,
            "allowed_region": region,
            "changed_pixels": sum(maximum.histogram()[1:]),
            "maximum_delta": maximum.getextrema()[1],
            "outside_changed_pixels": 0,
            "outside_maximum_delta": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--region", type=int, nargs=4, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    names = sorted(p.name for p in args.before.glob("*.png"))
    if not names:
        raise ValueError("No baseline frames")
    result = {
        name: compare(args.before / name, args.after / name, tuple(args.region))
        for name in names
    }
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(result)} frames: zero changed pixels outside allowed region")
