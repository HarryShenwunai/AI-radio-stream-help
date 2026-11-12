"""Bounded original 2D layer packages. This format is not Cubism/Live2D.

Only independent transparent PNG resources and declarative bounded transforms are
supported. Import proves structure/decodability, not artistic independence or quality.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
from uuid import uuid4
import zipfile
import zlib

from .assets import AssetError, STATE_NAMES, _description, _normalise, _png_payload

MAX_ZIP_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_PNG_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024
MAX_LAYERS = 16
MAX_TOTAL_PIXELS = 32_000_000
MAX_CANVAS_PIXELS = 8_000_000
MAX_EDGE = 4096
MAX_RATIO = 200
SOURCE_FILE = re.compile(r"[a-z][a-z0-9_-]{0,47}\.png\Z")
RESOURCE = re.compile(r"l[0-9]{4}\.png\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
ALL_STATES = set(STATE_NAMES)
ROLES = {"body", "head", "hair_back", "hair_front", "eyes_open", "eyes_closed",
         "mouth_closed", "mouth_open", "accessory"}
ROLE_STATES = {
    "eyes_open": {"idle", "talk"}, "eyes_closed": {"blink", "talk_blink"},
    "mouth_closed": {"idle", "blink"}, "mouth_open": {"talk", "talk_blink"},
}
MOTION_LIMITS = {"breath_y": 12, "sway_degrees": 3, "gaze_x": 16, "gaze_y": 16}


def _fail(message="2D 分层包结构不正确。", status=400):
    raise AssetError(message, status)


def _object(value, allowed, required):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(allowed):
        _fail("2D 分层清单含未知字段或缺少必需字段。")
    return value


def _integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        _fail("2D 分层数量或尺寸不正确。")
    return value


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        _fail("2D 分层锚点或动作幅度不正确。")
    return value


def validate_document(doc, *, runtime=False):
    _object(doc, {"format", "version", "canvas", "layers"}, {"format", "version", "canvas", "layers"})
    if doc["format"] != "companion-layered-2d" or _integer(doc["version"], 1, 1) != 1:
        _fail("请选择 companion-layered-2d v1 格式。")
    canvas = _object(doc["canvas"], {"width", "height"}, {"width", "height"})
    width = _integer(canvas["width"], 1, MAX_EDGE)
    height = _integer(canvas["height"], 1, MAX_EDGE)
    if width * height > MAX_CANVAS_PIXELS:
        _fail("单层画布超过 800 万像素。", 413)
    layers = doc["layers"]
    if not isinstance(layers, list) or not 2 <= len(layers) <= MAX_LAYERS:
        _fail("2D 分层包需要 2–16 个图层。")
    if width * height * len(layers) > MAX_TOTAL_PIXELS:
        _fail("2D 图层解码总像素超过 3200 万。", 413)
    field = "resource" if runtime else "file"
    normalized, ids, files, role_counts = [], set(), set(), {}
    for layer in layers:
        _object(layer, {"id", "role", field, "pivot", "states", "motion"}, {"id", "role", field, "pivot", "states"})
        identifier, role, file = layer["id"], layer["role"], layer[field]
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in ids:
            _fail("图层 ID 必须唯一，且只含小写英文字母、数字、横线或下划线。")
        if not isinstance(role, str) or role not in ROLES:
            _fail("不支持此 2D 图层用途。")
        pattern = RESOURCE if runtime else SOURCE_FILE
        if not isinstance(file, str) or not pattern.fullmatch(file) or file in files:
            _fail("图层 PNG 文件名不正确或重复。")
        pivot = layer["pivot"]
        if not isinstance(pivot, list) or len(pivot) != 2:
            _fail("每个图层需要画布内的二维锚点。")
        pivot = [_number(pivot[0], 0, width), _number(pivot[1], 0, height)]
        states = layer["states"]
        if (not isinstance(states, list) or not states or any(not isinstance(s, str) for s in states)
                or len(set(states)) != len(states) or not set(states) <= ALL_STATES):
            _fail("图层状态只支持 idle、talk、blink、talk_blink。")
        if role in ROLE_STATES and set(states) != ROLE_STATES[role]:
            _fail("眼睛或嘴部图层的状态组合不正确。")
        if role in {"body", "head", "hair_back", "hair_front"} and set(states) != ALL_STATES:
            _fail("身体、头部和头发基础层需要在全部状态可见。")
        motion = _object(layer.get("motion", {}), MOTION_LIMITS, set())
        motion = {key: _number(motion.get(key, 0), 0, maximum) for key, maximum in MOTION_LIMITS.items()}
        normalized.append({"id": identifier, "role": role, field: file, "pivot": pivot,
                           "states": [s for s in STATE_NAMES if s in states], "motion": motion})
        ids.add(identifier)
        files.add(file)
        role_counts[role] = role_counts.get(role, 0) + 1
    if role_counts.get("body") != 1 or role_counts.get("head") != 1:
        _fail("2D 分层包需要各一个独立的 body 和 head 层。")
    for first, second in (("eyes_open", "eyes_closed"), ("mouth_closed", "mouth_open")):
        if role_counts.get(first, 0) != role_counts.get(second, 0) or role_counts.get(first, 0) > 1:
            _fail("睁闭眼或开闭嘴图层需要成对提供，且不能重复。")
    return {"format": "companion-layered-2d", "version": 1,
            "canvas": {"width": width, "height": height}, "layers": normalized}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("2D 分层清单包含重复字段。")
        result[key] = value
    return result


def _json(data):
    if len(data) > MAX_JSON_BYTES:
        _fail("2D 图层清单超过 64 KiB。", 413)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail("2D 清单不能包含 NaN 或 Infinity。"))
    except (ValueError, UnicodeError, RecursionError):
        _fail("2D 图层清单无法读取。")
    return validate_document(value)


def _read_entry(bundle, name):
    info = bundle.getinfo(name)
    # Never use ZipExtFile.read(-1): forged declared sizes must not request an
    # unbounded deflate allocation before ZipFile checks the resulting CRC.
    with bundle.open(info) as stream:
        value = stream.read(info.file_size + 1)
    if len(value) != info.file_size:
        _fail("ZIP 文件实际大小与清单不符。")
    return value


def import_layered_2d(store, data: bytes, filename: str | None = None, *,
                      cancel_event: threading.Event | None = None):
    if not isinstance(data, bytes) or not data or len(data) > MAX_ZIP_BYTES:
        _fail("2D 分层 ZIP 不能为空且不得超过 32 MiB。", 413)
    if filename is not None and (not isinstance(filename, str) or not filename.lower().endswith(".zip")
            or not 1 <= len(filename) <= 255 or any(c in filename for c in "/\\")
            or any(ord(c) < 32 for c in filename)):
        _fail("请选择有效的 2D 分层 ZIP 文件。")

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            _fail("素材导入已取消。", 409)

    check_cancel()
    try:
        bundle = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, ValueError, zipfile.BadZipFile):
        _fail("2D 分层 ZIP 无法读取。")
    with bundle, store._lock:
        infos = bundle.infolist()
        if not 3 <= len(infos) <= MAX_LAYERS + 1:
            _fail("ZIP 文件数量不符合 2D 图层预算。", 413)
        seen, expanded = set(), 0
        for info in infos:
            check_cancel()
            name = info.filename
            if info.orig_filename != name:
                _fail("ZIP 文件名不能包含截断或隐藏字符。")
            if name != "layered2d.json" and not SOURCE_FILE.fullmatch(name):
                _fail("ZIP 仅允许根目录的 layered2d.json 和小写 PNG 文件。")
            if name in seen:
                _fail("ZIP 包含重复文件。")
            seen.add(name)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir() or kind not in (0, stat.S_IFREG) or info.flag_bits & 1:
                _fail("ZIP 不支持目录、链接、特殊文件或加密内容。")
            maximum = MAX_JSON_BYTES if name == "layered2d.json" else MAX_PNG_BYTES
            expanded += info.file_size
            if not 0 < info.file_size <= maximum or expanded > MAX_EXPANDED_BYTES:
                _fail("ZIP 展开内容超过 2D 素材预算。", 413)
            if info.file_size > max(1, info.compress_size) * MAX_RATIO:
                _fail("ZIP 压缩比例超过当前预算。", 413)
        if "layered2d.json" not in seen:
            _fail("ZIP 缺少 layered2d.json。")
        try:
            doc = _json(_read_entry(bundle, "layered2d.json"))
            expected = {"layered2d.json"} | {layer["file"] for layer in doc["layers"]}
            if seen != expected:
                _fail("ZIP 文件与图层清单不一致。")
            # Read all bounded headers before allocating any decoded full-size image.
            raw = {}
            for layer in doc["layers"]:
                check_cancel()
                value = _read_entry(bundle, layer["file"])
                _, width, height = _png_payload(value)
                if (width, height) != (doc["canvas"]["width"], doc["canvas"]["height"]):
                    _fail("所有 2D 图层需要与声明画布尺寸完全一致。")
                raw[layer["file"]] = value
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error):
            _fail("2D ZIP 数据损坏或使用了不支持的压缩方式。")

        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=store.root))
        try:
            from PIL import Image
            thumb_size = (doc["canvas"]["width"], doc["canvas"]["height"])
            # Composite only thumbnail-sized layers, rather than retaining sixteen full images.
            scale = min(1, 256 / max(thumb_size))
            thumb_size = (max(1, round(thumb_size[0] * scale)), max(1, round(thumb_size[1] * scale)))
            thumbnail = Image.new("RGBA", thumb_size, (0, 0, 0, 0))
            resources, layers, digests = {}, [], set()
            total = 0
            try:
                for index, layer in enumerate(doc["layers"]):
                    check_cancel()
                    encoded, image, width, height = _normalise(raw.pop(layer["file"]))
                    try:
                        alpha = image.getchannel("A")
                        try:
                            minimum, maximum = alpha.getextrema()
                        finally:
                            alpha.close()
                        if minimum == 255 or maximum == 0:
                            _fail("图层必须含实际透明背景和可见内容。")
                        resource = f"l{index:04d}.png"
                        description = _description(resource, encoded, width, height)
                        if description["sha256"] in digests:
                            _fail("不同图层不能重复使用完全相同的整张图片。")
                        digests.add(description["sha256"])
                        total += len(encoded)
                        if total > MAX_EXPANDED_BYTES:
                            _fail("规范化 2D 素材超过 32 MiB。", 413)
                        (staging / resource).write_bytes(encoded)
                        resources[resource] = description
                        normalized = {key: value for key, value in layer.items() if key != "file"}
                        normalized["resource"] = resource
                        layers.append(normalized)
                        if "idle" in layer["states"]:
                            resized = image.resize(thumb_size, Image.Resampling.LANCZOS)
                            try:
                                thumbnail.alpha_composite(resized)
                            finally:
                                resized.close()
                    finally:
                        image.close()
                buffer = io.BytesIO()
                thumbnail.save(buffer, format="PNG", compress_level=6)
                thumb_data = buffer.getvalue()
            finally:
                thumbnail.close()
            check_cancel()
            model = {"format": "companion-layered-2d", "version": 1, "canvas": doc["canvas"], "layers": layers}
            model_data = json.dumps(model, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            (staging / "layers.json").write_bytes(model_data)
            (staging / "thumbnail.png").write_bytes(thumb_data)
            roles = {layer["role"] for layer in layers}
            blink, talk = "eyes_closed" in roles, "mouth_open" in roles
            asset_id = str(uuid4())
            target = store.root / asset_id
            if target.exists() or target.is_symlink():
                _fail("素材标识冲突，请重试。", 409)
            manifest = {
                "id": asset_id, "schema_version": 1, "format": "layered-2d",
                "created_at": datetime.now(timezone.utc).isoformat(), "canvas": doc["canvas"],
                "width": doc["canvas"]["width"], "height": doc["canvas"]["height"],
                "layers": layers, "resources": resources, "states": {},
                "model": {"resource": "layers.json", "bytes": len(model_data),
                          "sha256": hashlib.sha256(model_data).hexdigest()},
                "thumbnail": _description("thumbnail.png", thumb_data, *thumb_size),
                "total_bytes": total + len(model_data) + len(thumb_data),
                "total_pixels": doc["canvas"]["width"] * doc["canvas"]["height"] * len(layers),
                "capabilities": {"static": True, "layered": True, "talk": talk, "blink": blink,
                                 "talk_blink": talk and blink,
                                 "gaze_parallax": any(layer["motion"]["gaze_x"] or layer["motion"]["gaze_y"] for layer in layers)},
                "art_review": "not_run", "live2d": False,
            }
            if manifest["total_bytes"] > MAX_EXPANDED_BYTES:
                _fail("规范化素材与缩略图合计超过 32 MiB。", 413)
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            check_cancel()
            staging.rename(target)
            return manifest
        except AssetError:
            raise
        except OSError:
            _fail("2D 素材保存失败，请检查磁盘空间。", 503)
        finally:
            if staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    _fail("2D 导入临时文件清理失败，请重试。", 503)


def manifest_resources(manifest):
    if manifest.get("states") != {}:
        _fail("2D 分层清单已损坏。", 409)
    doc = validate_document({"format": "companion-layered-2d", "version": 1,
                             "canvas": manifest["canvas"], "layers": manifest["layers"]}, runtime=True)
    if doc["layers"] != manifest["layers"]:
        _fail("2D 分层清单未规范化。", 409)
    resources = manifest["resources"]
    names = {layer["resource"] for layer in doc["layers"]}
    if not isinstance(resources, dict) or set(resources) != names:
        _fail("2D 图层资源清单已损坏。", 409)
    return [(name, resources[name], MAX_PNG_BYTES) for name in sorted(names)] + [
        ("layers.json", manifest["model"], MAX_JSON_BYTES),
        ("thumbnail.png", manifest["thumbnail"], MAX_PNG_BYTES),
    ]
