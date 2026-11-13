"""Register AI-extracted alpha into original R3 pixels; never replace source art.

Requires existing local R3 source layers, bound-eye artwork and imagegen cutouts.
Image generation is external; this tool only registers and validates supplied assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops


def separate_workspace(work: Path, *sources: Path) -> None:
    work = work.resolve()
    for source in sources:
        source = source.resolve()
        if work == source or work in source.parents or source in work.parents:
            raise ValueError(
                "Output workspace must not overlap original source directories"
            )


def check_hair(original: Path, registered: Path) -> dict:
    with Image.open(original) as source, Image.open(registered) as output:
        source = source.convert("RGBA")
        output = output.convert("RGBA")
        if source.size != output.size:
            raise ValueError("Hair registration changed layer dimensions")
        if ImageChops.difference(
            source.convert("RGB"), output.convert("RGB")
        ).getbbox():
            raise ValueError("Hair RGB changed; preserve original identity pixels")
        if ImageChops.subtract(
            output.getchannel("A"), source.getchannel("A")
        ).getbbox():
            raise ValueError("Hair matte filled original transparent face/neck pixels")
        if output.getchannel("A").getextrema() != (0, 255):
            # Some extracted mattes are slightly translucent even in dense hair.
            low, high = output.getchannel("A").getextrema()
            if low != 0 or high < 240:
                raise ValueError(
                    "Hair matte lacks a transparent exterior or dense interior"
                )
        return {
            "same_size": True,
            "rgb_identical": True,
            "alpha_never_expands_original": True,
            "alpha_extrema": output.getchannel("A").getextrema(),
        }


def check_face_overlap(original: Path, registered: Path, protection: Path) -> dict:
    with (
        Image.open(original) as old,
        Image.open(registered) as new,
        Image.open(protection) as region,
    ):
        old_alpha, new_alpha = (
            old.convert("RGBA").getchannel("A"),
            new.convert("RGBA").getchannel("A"),
        )
        if old.size != new.size or region.size != old.size:
            raise ValueError("Face overlap registration dimensions differ")
        if region.mode != "L":
            raise ValueError(
                "Face protection must use 8-bit grayscale; normalize before checking"
            )
        mask = region.point(lambda value: 255 if value >= 254 else 0)
        occupied = old_alpha.point(lambda value: 255 if value >= 128 else 0)
        mask = ImageChops.multiply(mask, occupied)
        count = mask.histogram()[255]
        if not count:
            raise ValueError("Face overlap protection has no authored hair pixels")
        loss = ImageChops.subtract(old_alpha, new_alpha, scale=1, offset=-1)
        if ImageChops.multiply(loss, mask).getbbox():
            raise ValueError(
                "Hair extraction opened a gap at the authored face overlap"
            )
        return {
            "protected_authored_hair_pixels": count,
            "maximum_allowed_alpha_loss": 1,
        }


def prepare(
    work: Path, source: Path, eyes: Path, hair: Path, steam: Path, magick: str
) -> dict:
    work, source, eyes, hair, steam = [
        p.resolve() for p in (work, source, eyes, hair, steam)
    ]
    separate_workspace(work, source, eyes)
    manifest = json.loads((source / "layers.json").read_text())
    for cutout, original in [
        (hair, source / "Hair_shell.png"),
        (steam, source / "Steam.png"),
    ]:
        with Image.open(cutout) as supplied, Image.open(original) as old:
            if supplied.mode != "RGBA" or supplied.getchannel("A").getextrema()[0] != 0:
                raise ValueError("Cutout must contain actual transparent pixels")
            if (
                abs((supplied.width / supplied.height) / (old.width / old.height) - 1)
                > 0.05
            ):
                raise ValueError(
                    "Cutout framing differs from original layer aspect ratio"
                )
    target = work / "source"
    target.mkdir(parents=True, exist_ok=True)
    for row in manifest["layers"]:
        name = row["file"]
        if Path(name).name != name or not name.endswith(".png"):
            raise ValueError("Layer source must be a local PNG basename")
        shutil.copyfile(source / name, target / name)
    shutil.copyfile(source / "layers.json", target / "layers.json")
    for side in ["L", "R"]:
        for part in ["Sclera", "Iris", "Lid", "Foreground"]:
            name = side + part + ".png"
            shutil.copyfile(eyes / name, work / name)
    shutil.copyfile(eyes / "eyes.json", work / "eyes.json")

    def run(*args: object) -> None:
        subprocess.run([magick, *map(str, args)], check=True, timeout=90)

    with Image.open(source / "Hair_shell.png") as original:
        size = f"{original.width}x{original.height}!"
    old_alpha, new_alpha, registered = [
        work / name
        for name in [
            "original-hair-alpha.png",
            "generated-hair-alpha.png",
            "registered-hair-alpha.png",
        ]
    ]
    run(source / "Hair_shell.png", "-alpha", "extract", old_alpha)
    run(hair, "-resize", size, "-alpha", "extract", new_alpha)
    run(old_alpha, new_alpha, "-compose", "Multiply", "-composite", registered)
    # The extraction may move the face opening even if the outer hair aligns.
    # Preserve the old hair alpha around the actual authored face, including a
    # feathered overlap margin; only exterior background matting may change.
    layers = {row["name"]: row for row in manifest["layers"]}
    face_row, hair_row = layers["Neck_face"], layers["Hair_shell"]
    with Image.open(source / "Hair_shell.png") as original:
        canvas_size = f"{original.width}x{original.height}"
    face_alpha = work / "face-alpha.png"
    protection = work / "face-protection.png"
    protected_hair = work / "protected-hair-alpha.png"
    offset = f"{face_row['x'] - hair_row['x']:+d}{face_row['y'] - hair_row['y']:+d}"
    run(source / "Neck_face.png", "-alpha", "extract", face_alpha)
    run(
        "-size",
        canvas_size,
        "xc:black",
        face_alpha,
        "-geometry",
        offset,
        "-compose",
        "Lighten",
        "-composite",
        "-blur",
        "0x20",
        "-level",
        "0%,1%",
        "-depth",
        "8",
        protection,
    )
    run(old_alpha, protection, "-compose", "Multiply", "-composite", protected_hair)
    run(registered, protected_hair, "-compose", "Lighten", "-composite", registered)
    run(
        source / "Hair_shell.png",
        registered,
        "-alpha",
        "off",
        "-compose",
        "CopyOpacity",
        "-composite",
        target / "Hair_shell.png",
    )
    with Image.open(source / "Steam.png") as original:
        size = f"{original.width}x{original.height}!"
    run(steam, "-resize", size, target / "Steam.png")
    unchanged = []
    for row in manifest["layers"]:
        name = row["file"]
        if name not in {"Hair_shell.png", "Steam.png"}:
            if (source / name).read_bytes() != (target / name).read_bytes():
                raise ValueError("Unexpected source mutation: " + name)
            unchanged.append(name)
    report = {
        "hair": check_hair(source / "Hair_shell.png", target / "Hair_shell.png"),
        "unchanged_layers": unchanged,
        "changed_layers": ["Hair_shell.png", "Steam.png"],
        "cutout_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [hair, steam]
        },
        "face_overlap": check_face_overlap(
            source / "Hair_shell.png", target / "Hair_shell.png", protection
        ),
        "limits": "Asset registration only; actual Core pose and visual checks are required.",
    }
    (work / "source-contract.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["work-dir", "source-dir", "eyes-dir", "hair-cutout", "steam-cutout"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--magick", default="magick")
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                args.work_dir,
                args.source_dir,
                args.eyes_dir,
                args.hair_cutout,
                args.steam_cutout,
                args.magick,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
