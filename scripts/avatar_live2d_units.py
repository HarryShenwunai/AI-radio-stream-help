"""Explicit units at the local Live2D authoring boundary; never repaint pixels."""
from dataclasses import dataclass
import math


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("authoring values must be finite numbers")
    return float(value)


@dataclass(frozen=True, slots=True)
class CanvasPointPx:
    x: float
    y: float

    def __post_init__(self):
        number(self.x)
        number(self.y)


@dataclass(frozen=True, slots=True)
class CanvasBoundsPx:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        for value in (self.x, self.y, self.width, self.height):
            number(value)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("canvas bounds require positive dimensions")

    def uv(self, point: CanvasPointPx):
        # Extrapolation is intentional: CupX/Y can carry the prop outside the box.
        return [(point.x - self.x) / self.width, (point.y - self.y) / self.height]


@dataclass(frozen=True, slots=True)
class LocalDeltaFraction:
    x: float
    y: float

    def __post_init__(self):
        if max(abs(number(self.x)), abs(number(self.y))) > 2:
            raise ValueError("local delta exceeds two target bounds; canvas pixels may have been supplied")

    def as_list(self):
        return [self.x, self.y]


@dataclass(frozen=True, slots=True)
class KeyTimeSeconds:
    value: float

    def __post_init__(self):
        if number(self.value) < 0:
            raise ValueError("key time seconds must be nonnegative")


@dataclass(frozen=True, slots=True)
class BezierHandleFraction:
    time: float
    value: float

    def __post_init__(self):
        if not 0 <= number(self.time) <= 1 or not 0 <= number(self.value) <= 1:
            raise ValueError("Bezier handles are 0..1 fractions, not absolute seconds or parameter values")


def restore_cup_rotation_keys(bounds: CanvasBoundsPx):
    """Work around v3.6.7 parent-warp insertion dropping a Rotation's full grid."""
    keys = []
    for x in (-500, 0, 500):
        for y in (-500, 0, 500):
            origin = bounds.uv(CanvasPointPx(bounds.x + bounds.width / 2 + x,
                                             bounds.y + bounds.height / 2 + y))
            for angle in (-45, 0, 45):
                keys.append({"op": "set", "target": "rotation:OriginalCupRoot",
                    "key": {"ParamCupX": x, "ParamCupY": y, "ParamCupRotation": angle},
                    "geometry": {"originX": origin[0], "originY": origin[1], "angle": angle, "scale": 1}})
    return keys


def validate_operation_units(operation, request):
    changes = request.get("changes", []) if operation == "rig_deform" else request.get("shapes", [])
    if operation in ("rig_deform", "author_axis"):
        for change in changes:
            for transform in change.get("operations", []):
                if transform.get("type") == "translate":
                    LocalDeltaFraction(*transform["delta"])
                selection = transform.get("selection", {})
                if "feather" in selection and not 0 <= number(selection["feather"]) <= .5:
                    raise ValueError("selection feather is a normalized 0..0.5 fraction")
                if "rect" in selection and max(abs(number(v)) for v in selection["rect"]) > 2:
                    raise ValueError("selection rectangles use normalized rest coordinates, not canvas pixels")
    if operation == "motion_put":
        for curve in request["clip"].get("curves", []):
            previous = -1
            for key in curve["keys"]:
                KeyTimeSeconds(key["time"])
                if key["time"] <= previous:
                    raise ValueError("motion key times must strictly increase")
                previous = key["time"]
                for name in ("in", "out"):
                    if name in key:
                        BezierHandleFraction(*key[name])
