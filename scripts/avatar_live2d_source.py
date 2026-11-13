#!/usr/bin/env python3
"""Original PNG layers -> editable PSD -> real GPL PSD2Live CLI export.

This authoring tool does not turn a flat portrait into separated artwork. It accepts
actual independently painted layers. A tiny geometric fixture is explicitly test-only.
No proprietary Editor, example character or fabricated MOC3 bytes are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / ".build/psd2live-3.6.7"


def number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("canvas dimensions and layer offsets must be bounded integers")
    return value


def check_neutral_reference(composite: Image.Image, manifest_path: Path, contract: dict) -> dict:
    """Measure reconstruction fidelity, never aesthetic quality or animation."""
    from io import BytesIO
    from PIL import ImageChops

    if not isinstance(contract, dict):
        raise ValueError("neutral_reference must identify the master and review regions")
    relative = Path(contract.get("file", ""))
    root = manifest_path.parent.resolve()
    reference = root / relative
    if (not relative.parts or relative.is_absolute() or ".." in relative.parts
            or "\\" in str(relative) or reference.is_symlink()
            or not reference.resolve().is_relative_to(root)):
        raise ValueError("neutral reference must be a local source file")
    if reference.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("neutral reference exceeds authoring budget")
    raw = reference.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if contract.get("sha256") != digest:
        raise ValueError("neutral reference SHA-256 mismatch")
    regions = contract.get("regions")
    if not isinstance(regions, dict) or set(regions) != {"face", "hands_cup"}:
        raise ValueError("neutral reference needs face and hands_cup review regions")
    width, height = composite.size
    boxes = {"full": (0, 0, width, height)}
    for name, box in regions.items():
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError("review region must be [x, y, width, height]")
        x, y, w, h = box
        number(x, 0, width - 1)
        number(y, 0, height - 1)
        number(w, 1, width)
        number(h, 1, height)
        if x + w > width or y + h > height:
            raise ValueError("review region outside source canvas")
        boxes[name] = (x, y, x + w, y + h)
    with Image.open(BytesIO(raw)) as source:
        if source.format != "PNG" or source.size != composite.size:
            raise ValueError("neutral reference must be a same-size PNG; no fit or stretch")
        source.load()
        expected = source.convert("RGBA")
    # Both backgrounds reveal lost alpha and light/dark fringes. Invisible RGB
    # under alpha=0 is intentionally irrelevant. No source pixels are edited.
    differences = []
    try:
        for value in (0, 255):
            with Image.new("RGBA", composite.size, (value, value, value, 255)) as bg:
                a = Image.alpha_composite(bg, expected).convert("RGB")
                b = Image.alpha_composite(bg, composite).convert("RGB")
                diff = ImageChops.difference(a, b)
                channels = diff.split()
                worst = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
                differences.append(worst)
                for image in (*channels, diff, a, b):
                    image.close()
        combined = ImageChops.lighter(*differences)
        metrics = {}
        try:
            for name, box in boxes.items():
                with combined.crop(box) as region:
                    histogram = region.histogram()
                count = (box[2] - box[0]) * (box[3] - box[1])
                mean = sum(i * n for i, n in enumerate(histogram)) / count
                fraction = sum(histogram[17:]) / count
                metrics[name] = {"mean_max_channel_error": mean,
                                 "fraction_over_16": fraction,
                                 "passed": mean <= 2 and fraction <= 0.005}
        finally:
            combined.close()
    finally:
        expected.close()
        for image in differences:
            image.close()
    failed = [name for name, row in metrics.items() if not row["passed"]]
    if failed:
        raise ValueError("neutral reconstruction differs from master: " + ", ".join(failed))
    return {"status": "passed_reconstruction_only", "reference_sha256": digest,
            "regions": metrics, "art_quality_acceptance": "NOT_CLAIMED"}


def write_psd(manifest_path: Path, destination: Path, *, require_reference: bool = False) -> dict:
    """Write PSD v1 RGB/8-bit planar layers, preserving decoded RGBA art pixels.

    Layers in the manifest and PSD records are both bottom-to-top.
    Transparent margins may be trimmed only through PSD layer coordinates, never
    by modifying a source PNG. Unicode names use the standard 'luni' tagged block.
    """
    doc = json.loads(manifest_path.read_text())
    if doc.get("format") != "original-live2d-layers-v1":
        raise ValueError("expected original-live2d-layers-v1 source manifest")
    if require_reference and "neutral_reference" not in doc:
        raise ValueError("new source requires a pinned neutral_reference master")
    width = number(doc["canvas"]["width"], 1, 4096)
    height = number(doc["canvas"]["height"], 1, 4096)
    if width * height > 8_000_000:
        raise ValueError("source canvas exceeds authoring budget")
    if not isinstance(doc["layers"], list) or not 1 <= len(doc["layers"]) <= 128:
        raise ValueError("source must contain 1–128 actual layers")
    records, channels, inputs, names = [], [], [], set()
    composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    total_pixels = 0
    try:
        for layer in doc["layers"]:
            name = layer["name"]
            if (not isinstance(name, str) or not name or len(name) > 120 or name in names
                    or any(ord(c) < 32 for c in name)):
                raise ValueError("layer names must be unique printable names")
            names.add(name)
            relative = Path(layer["file"])
            if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
                raise ValueError("source image must be relative to its manifest")
            path = manifest_path.parent / relative
            if (path.is_symlink() or not path.resolve().is_relative_to(manifest_path.parent.resolve())
                    or path.stat().st_size > 16 * 1024 * 1024):
                raise ValueError("source PNG exceeds authoring budget or is a symbolic link")
            x, y = number(layer.get("x", 0), 0, width), number(layer.get("y", 0), 0, height)
            with Image.open(path) as image:
                if image.format != "PNG" or image.mode != "RGBA":
                    raise ValueError("original layers must be RGBA PNG images")
                if x + image.width > width or y + image.height > height:
                    raise ValueError("source layer exceeds canvas placement")
                total_pixels += image.width * image.height
                if total_pixels > 96_000_000:
                    raise ValueError("source layers exceed authoring pixel budget")
                image.load()
                alpha = image.getchannel("A")
                try:
                    bounds = alpha.getbbox()
                finally:
                    alpha.close()
                if bounds is None:
                    raise ValueError("empty layers are not modeling artwork")
                visible = layer.get("visible", True)
                if not isinstance(visible, bool):
                    raise ValueError("layer visibility must be boolean")
                if visible:
                    composite.alpha_composite(image, (x, y))
                crop = image.crop(bounds)
                try:
                    pixels = []
                    for channel in crop.split():
                        try:
                            pixels.append(b"\0\0" + channel.tobytes())  # Raw planar channel, no RLE dependency.
                        finally:
                            channel.close()
                    left, top = x + bounds[0], y + bounds[1]
                    right, bottom = x + bounds[2], y + bounds[3]
                    record = struct.pack(">4iH", top, left, bottom, right, 4)
                    record += b"".join(struct.pack(">hI", channel_id, len(raw))
                                       for channel_id, raw in zip((0, 1, 2, -1), pixels))
                    record += b"8BIMnorm" + bytes((255, 0, 0 if visible else 2, 0))
                    encoded_name = name.encode("latin-1", "replace")[:255]
                    pascal = bytes((len(encoded_name),)) + encoded_name
                    pascal += b"\0" * (-len(pascal) % 4)
                    unicode_name = name.encode("utf-16-be")
                    unicode_data = struct.pack(">I", len(unicode_name) // 2) + unicode_name
                    additional = b"8BIMluni" + struct.pack(">I", len(unicode_data)) + unicode_data
                    additional += b"\0" * (-len(unicode_data) % 4)
                    extra = struct.pack(">II", 0, 0) + pascal + additional
                    record += struct.pack(">I", len(extra)) + extra
                    records.append(record)
                    channels.append(b"".join(pixels))
                finally:
                    crop.close()
            inputs.append({"name": name, "file": relative.as_posix(),
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "visible": visible})
        reconstruction = (check_neutral_reference(composite, manifest_path, doc["neutral_reference"])
                          if "neutral_reference" in doc else {"status": "NOT_RUN"})
        # A negative layer count identifies the composite's first alpha as transparency.
        info = struct.pack(">h", -len(records)) + b"".join(records) + b"".join(channels)
        info += b"\0" * (-len(info) % 2)
        layer_mask = struct.pack(">I", len(info)) + info + struct.pack(">I", 0)
        header = b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 4, height, width, 8, 3)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("source PSD already exists; choose a new revision path")
        with destination.open("xb") as stream:
            stream.write(header + struct.pack(">II", 0, 0) + struct.pack(">I", len(layer_mask)) + layer_mask)
            stream.write(b"\0\0")
            for channel in composite.split():
                try:
                    stream.write(channel.tobytes())
                finally:
                    channel.close()
        return {"source_psd": str(destination.resolve()), "width": width, "height": height,
                "layer_count": len(records), "layers": inputs,
                "psd_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "art_quality_acceptance": "NOT_CLAIMED", "neutral_reconstruction": reconstruction}
    finally:
        composite.close()


def fixture(directory: Path) -> Path:
    if ".build" not in directory.parts and "/tmp/" not in str(directory.resolve()):
        raise ValueError("synthetic fixtures belong in a private build/test directory")
    directory.mkdir(parents=True, exist_ok=True)
    width, height = 384, 512
    definitions = [
        ("back hair", "ellipse", (88, 38, 298, 290), (43, 32, 29, 255)),
        ("topwear", "polygon", ((90, 490), (116, 278), (267, 278), (295, 490)), (72, 124, 171, 255)),
        ("neck", "rectangle", (170, 235, 216, 302), (222, 167, 128, 255)),
        ("face", "ellipse", (112, 72, 271, 270), (239, 188, 146, 255)),
        ("eyewhite-l", "ellipse", (212, 145, 249, 170), (248, 245, 232, 255)),
        ("eyewhite-r", "ellipse", (135, 145, 172, 170), (248, 245, 232, 255)),
        ("iris-l", "ellipse", (224, 147, 239, 167), (38, 73, 87, 255)),
        ("iris-r", "ellipse", (147, 147, 162, 167), (38, 73, 87, 255)),
        ("eyelash-l", "line", (212, 145, 249, 145), (35, 25, 22, 255)),
        ("eyelash-r", "line", (135, 145, 172, 145), (35, 25, 22, 255)),
        ("eyebrow-l", "line", (210, 126, 248, 122), (61, 37, 27, 255)),
        ("eyebrow-r", "line", (134, 122, 172, 126), (61, 37, 27, 255)),
        ("mouth", "ellipse", (169, 205, 212, 232), (90, 36, 42, 255)),
        ("upper teeth", "rectangle", (175, 206, 205, 211), (249, 238, 217, 255)),
        ("tongue", "ellipse", (179, 222, 202, 231), (189, 87, 99, 255)),
        ("front hair 1", "polygon", ((107, 73), (181, 51), (152, 139)), (54, 36, 28, 255)),
        ("front hair 2", "polygon", ((177, 51), (236, 63), (205, 129)), (62, 43, 30, 255)),
        ("front hair 3", "polygon", ((231, 62), (281, 93), (268, 188)), (48, 34, 29, 255)),
    ]
    layers = []
    for index, (name, kind, geometry, color) in enumerate(definitions):
        filename = f"fixture-layer-{index:02d}.png"
        with Image.new("RGBA", (width, height), (0, 0, 0, 0)) as image:
            draw = ImageDraw.Draw(image)
            if kind == "line":
                draw.line(geometry, fill=color, width=4)
            else:
                getattr(draw, kind)(geometry, fill=color)
            image.save(directory / filename, format="PNG")
        layers.append({"name": name, "file": filename})
    manifest = directory / "TEST_ONLY_layers.json"
    manifest.write_text(json.dumps({"format": "original-live2d-layers-v1", "canvas": {"width": width, "height": height},
                                   "purpose": "Original geometric CLI/Core fixture only; not user character artwork",
                                   "layers": layers}, indent=2) + "\n")
    return manifest


def export(psd: Path, output: Path, tool: Path, *, atlas=1024, spacing=48):
    if atlas not in (256, 512, 1024, 2048, 4096):
        raise ValueError("choose a power-of-two atlas within the application's 4096-pixel runtime limit")
    number(spacing, 4, 512)
    if output.exists() and any(output.iterdir()):
        raise ValueError("export output must be a fresh directory")
    output.mkdir(parents=True, exist_ok=True)
    if not tool.is_dir() or not list(tool.glob("psd2live-3.6.7-*.jar")):
        raise ValueError("expected privately extracted, SHA-verified PSD2Live v3.6.7 application jars")
    private_home = ROOT / ".build/psd2live-user"
    command = ["java", "-Xmx1g", "-Djava.awt.headless=true", f"-Duser.home={private_home}",
               "-cp", str(tool.resolve() / "*"), "io.github.psd2live.MainKt", "--lang", "en",
               "--input", str(psd.resolve()), "--output", str(output.resolve()),
               "--atlas", str(atlas), "--mesh-spacing", str(spacing), "--no-see-through"]
    with (output / "authoring-cli.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=300)
    files = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.rglob("*")) if p.is_file()]
    report = {"tool": "psd2live v3.6.7", "command": command, "exit_code": result.returncode,
              "files": files, "core_acceptance": "NOT_RUN", "art_quality_acceptance": "NOT_CLAIMED"}
    (output / "authoring-export-report.json").write_text(json.dumps(report, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(f"real PSD2Live export failed, see {output / 'authoring-cli.log'}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make_fixture = commands.add_parser("fixture")
    make_fixture.add_argument("--output", required=True, type=Path)
    pack = commands.add_parser("pack")
    pack.add_argument("--layers", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    pack.add_argument("--allow-unreviewed-source", action="store_true",
                      help="Historical source/fixture only; does not claim art acceptance")
    compile_model = commands.add_parser("export")
    compile_model.add_argument("--input", required=True, type=Path)
    compile_model.add_argument("--output", required=True, type=Path)
    compile_model.add_argument("--tool-dir", default=TOOL_DIR, type=Path)
    compile_model.add_argument("--atlas", default=1024, type=int)
    compile_model.add_argument("--mesh-spacing", default=48, type=int)
    args = parser.parse_args()
    if args.command == "fixture":
        source = fixture(args.output)
        print(json.dumps(write_psd(source, args.output / "TEST_ONLY_original_layers.psd"), indent=2))
    elif args.command == "pack":
        print(json.dumps(write_psd(args.layers, args.output, require_reference=not args.allow_unreviewed_source), indent=2))
    else:
        print(json.dumps(export(args.input, args.output, args.tool_dir, atlas=args.atlas, spacing=args.mesh_spacing), indent=2))


if __name__ == "__main__":
    main()
