#!/usr/bin/env python3
"""Bind source-canvas landmarks to genuine Core rest triangles, without editing art.

Input is an independently captured Core snapshot, not PSD bounds or generated
parameter names. A landmark outside the actual triangle mesh fails explicitly.
The resulting barycentric indices/weights can be sampled at any later Core pose
for held-cup grip error, fingertip displacement and seam regression checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected finite numeric coordinates")
    return float(value)


def source_points(drawable, canvas):
    values = drawable["vertexPositions"]
    if not isinstance(values, list) or not 6 <= len(values) <= 200000 or len(values) % 2:
        raise ValueError("invalid actual Core vertex buffer")
    ppu = finite(canvas["ppu"])
    if ppu <= 0:
        raise ValueError("Core PPU must be positive")
    ox, oy = finite(canvas["originX"]), finite(canvas["originY"])
    return [(ox + finite(values[i]) * ppu, oy - finite(values[i + 1]) * ppu)
            for i in range(0, len(values), 2)]


def bind_point(points, triangles, point):
    """Return an actual enclosing triangle; never substitute a nearby mesh."""
    x, y = map(finite, point)
    if not isinstance(triangles, list) or len(triangles) % 3 or len(triangles) > 600000:
        raise ValueError("invalid actual Core triangle buffer")
    candidates = []
    for offset in range(0, len(triangles), 3):
        ids = triangles[offset:offset + 3]
        if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(points) for i in ids):
            raise ValueError("triangle index outside real vertex buffer")
        (ax, ay), (bx, by), (cx, cy) = [points[i] for i in ids]
        denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denominator) < 1e-12:
            continue
        a = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / denominator
        b = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / denominator
        weights = [a, b, 1 - a - b]
        if min(weights) >= -1e-8:
            candidates.append((min(weights), ids, weights))
    if not candidates:
        raise ValueError("landmark is outside the actual Core triangle mesh")
    _, ids, weights = max(candidates, key=lambda item: item[0])
    # Round-off on an edge is corrected, not a geometrically outside landmark.
    weights = [max(0.0, w) for w in weights]
    total = sum(weights)
    return {"vertex_indices": ids, "weights": [w / total for w in weights], "source_canvas": [x, y]}


def build(snapshot, landmarks):
    if snapshot.get("status") == "measured_private_original_model_snapshot":
        if snapshot.get("sources_unchanged") is not True:
            raise ValueError("Core snapshot sources changed while measuring")
        observed = snapshot["measurement"]
        if observed.get("consistency") != 1 or any(
                finite(p["value"]) != finite(p["default"]) for p in observed["parameters"]):
            raise ValueError("requires consistent MOC evaluated at actual parameter defaults")
        snapshot = {"format": "actual-live2d-core-rest-v1", "canvasInfo": observed["canvasInfo"],
                    "parameters": observed["parameters"],
                    "drawables": [{**item, "vertexPositions": item["positions"],
                                   "indices": item["triangleIndices"]} for item in observed["drawables"]]}
    if snapshot.get("format") != "actual-live2d-core-rest-v1":
        raise ValueError("requires a genuine independently captured Core rest snapshot")
    canvas = snapshot["canvasInfo"]
    drawables = snapshot["drawables"]
    if not isinstance(drawables, list) or not 1 <= len(drawables) <= 4096:
        raise ValueError("invalid Core drawable list")
    by_id = {item["id"]: item for item in drawables}
    if len(by_id) != len(drawables):
        raise ValueError("Core drawable IDs must be unique")
    result = {}
    for name, landmark in landmarks.items():
        item = by_id[landmark["drawable_id"]]
        mapped = bind_point(source_points(item, canvas), item["indices"], landmark["source_canvas"])
        result[name] = {"drawable_id": item["id"], **mapped}
    return {"format": "actual-live2d-landmark-contract-v1", "landmarks": result,
            "parameters": snapshot.get("parameters", []), "canvasInfo": canvas,
            "scope": "actual rest-mesh mapping only; motion, texture alpha and artwork acceptance not claimed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--landmarks", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("write a new revision; never overwrite an existing contract")
    result = build(json.loads(args.snapshot.read_text()), json.loads(args.landmarks.read_text()))
    result["source_sha256"] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (args.snapshot, args.landmarks)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
