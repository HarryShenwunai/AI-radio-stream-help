"""Apply only generated eyelid RGB deltas; preserve authored alpha and other assets.

The supplied edit is a candidate, not proof of visual acceptance. Registration
uses the existing 490x390 eye plate coordinate system and ImageMagick.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops


def register(source: Path, baseline: Path, edited: Path, output: Path) -> dict:
    source, baseline, edited, output = [
        p.resolve() for p in (source, baseline, edited, output)
    ]
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Output must be separate from original bound-eye assets")
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((source / "eyes.json").read_text())
    for side in ["L", "R"]:
        for part in ["Lid", "Iris", "Sclera", "Foreground"]:
            shutil.copyfile(
                source / (side + part + ".png"), output / (side + part + ".png")
            )
    shutil.copyfile(source / "eyes.json", output / "eyes.json")

    def run(*args: object) -> None:
        subprocess.run(["magick", *map(str, args)], check=True, timeout=90)

    report = {
        "changed": [],
        "unchanged": [],
        "generated_plate_sha256": hashlib.sha256(edited.read_bytes()).hexdigest(),
    }
    for name, path in [("baseline", baseline), ("edited", edited)]:
        run(path, "-resize", "490x390!", output / (name + ".png"))
    for side in ["L", "R"]:
        x, y, right, bottom = config[side]["box"]
        crop = f"{right - x}x{bottom - y}+{x - 340}+{y - 300}"
        old, new = output / (side + "-old.png"), output / (side + "-new.png")
        for name, dest in [("baseline", old), ("edited", new)]:
            run(output / (name + ".png"), "-crop", crop, "+repage", dest)
        original = source / (side + "Lid.png")
        # Carry only the bounded color difference, retaining prior local shading.
        # Fully transparent pixels retain their original RGB too.
        run(
            original,
            old,
            new,
            "-channel",
            "RGB",
            "-fx",
            "u.a>0 ? min(1,max(0,u+0.65*(u[2]-u[1]))) : u",
            "+channel",
            "-depth",
            "8",
            output / (side + "Lid.png"),
        )
        with Image.open(original) as a, Image.open(output / (side + "Lid.png")) as b:
            a, b = a.convert("RGBA"), b.convert("RGBA")
            if (
                a.size != b.size
                or ImageChops.difference(a.getchannel("A"), b.getchannel("A")).getbbox()
            ):
                raise ValueError("Eyelid refinement moved the authored alpha boundary")
            delta = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
            exterior = a.getchannel("A").point(lambda value: 255 if value == 0 else 0)
            if ImageChops.multiply(delta.convert("L"), exterior).getbbox():
                raise ValueError("Eyelid refinement changed fully transparent pixels")
            report["changed"].append(
                {
                    "layer": side + "Lid",
                    "size": a.size,
                    "alpha_identical": True,
                    "exterior_rgb_identical": True,
                    "rgb_max_delta": max(v[1] for v in delta.getextrema()),
                }
            )
        for part in ["Iris", "Sclera", "Foreground"]:
            name = side + part + ".png"
            if (source / name).read_bytes() != (output / name).read_bytes():
                raise ValueError("Unexpected mutation: " + name)
            report["unchanged"].append(name)
    (output / "lid-contract.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["source", "baseline", "edited", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            register(args.source, args.baseline, args.edited, args.output), indent=2
        )
    )
