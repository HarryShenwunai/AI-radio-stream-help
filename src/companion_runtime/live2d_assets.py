"""Bounded Cubism runtime ZIP staging, without installing Cubism Core/SDK.

MOC3 remains opaque beyond its envelope header. Successful import is NOT Core
consistency, rendering, copyright authorization, or publishing-license approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import threading
import unicodedata
from uuid import uuid4
import warnings
import zipfile

from .assets import AssetError, PNG_SIGNATURE, _description
from .vrm_assets import _clean_png, _thumbnail

MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 96 * 1024 * 1024
MAX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_TOTAL_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 256
MAX_RESOURCES = 96
MAX_RATIO = 200
MAX_TEXTURE_PIXELS = 32_000_000
MAX_TEXTURE_EDGE = 4096
MAX_TEXTURES = 32
# Header revisions accepted for subsequent user-Core probing. Do not turn these
# bytes into a claim about an Editor edition or Core ABI: the public JSON specs
# do not document the binary and this importer has no Core consistency checker.
MOC_VERSIONS = {code: f"MOC3 header revision {code}" for code in range(1, 7)}
DISCARDED_AUDIO_WARNING = "动作音频/事件未导入，语音由应用提供。"
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
_RESOURCE = re.compile(r"r[0-9]{4}\.(?:moc3|png|motion3\.json|exp3\.json|physics3\.json|cdi3\.json|pose3\.json|notice\.txt)\Z")


def _fail(message="Live2D 运行包结构不正确。", status=400):
    raise AssetError(message, status)


def _object(value, allowed=None, required=()):
    if not isinstance(value, dict) or (allowed is not None and not set(value).issubset(allowed)) or not set(required).issubset(value):
        _fail("Live2D JSON 含未知字段或缺少必需字段。")
    return value


def _array(value, maximum=4096):
    if not isinstance(value, list):
        _fail()
    if len(value) > maximum:
        _fail("Live2D 对象数量超过当前预算。", 413)
    return value


def _text(value, maximum=256):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or any(not c.isprintable() and unicodedata.category(c) != "Zs" for c in value)
            or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
        _fail("Live2D 名称或参数 ID 不正确。")
    return value


def _number(value, low=-1_000_000, high=1_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        _fail("Live2D 数值不正确或超过当前预算。")
    return value


def _integer(value, low=0, high=100_000):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        _fail("Live2D 数量或索引不正确。")
    return value


def _path(value, directory=False):
    if not isinstance(value, str) or not value or len(value) > 512 or "\\" in value or ":" in value or "?" in value or "#" in value or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value):
        _fail("Live2D ZIP 路径不能包含网址、绝对路径或特殊字符。")
    if directory and value.endswith("/"):
        value = value[:-1]
    parts = value.split("/")
    if any(not p or p in {".", ".."} or p.endswith((".", " ")) or _RESERVED.match(p) for p in parts) or PurePosixPath(value).is_absolute():
        _fail("Live2D ZIP 路径越界或不兼容 Windows。")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        _fail("Live2D ZIP 文件名编码不正确。")
    return value


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            _fail("Live2D JSON 包含重复字段。")
        result[k] = v
    return result


def _walk(value, depth=0):
    if depth > 32:
        _fail("Live2D JSON 嵌套超过预算。", 413)
    if isinstance(value, dict):
        if len(value) > 4096:
            _fail("Live2D JSON 对象超过预算。", 413)
        for k, v in value.items():
            if k.lower() in {"script", "scripts", "javascript", "uri", "url", "onload"}:
                _fail("Live2D 运行包不支持脚本或远程资源。")
            _walk(v, depth + 1)
    elif isinstance(value, list):
        _array(value, 200_000)
        for v in value:
            _walk(v, depth + 1)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value)
    elif isinstance(value, str):
        if len(value) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            _fail("Live2D JSON 文本不正确。")


def _json(data):
    if len(data) > MAX_JSON_BYTES:
        _fail("Live2D 单个 JSON 不得超过 2 MiB。", 413)
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail("Live2D 包含 NaN 或 Infinity。"))
    except (ValueError, UnicodeError, RecursionError):
        _fail("Live2D JSON 无法读取。")
    _object(value)
    _walk(value)
    return value


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _version(doc):
    if doc.get("Version") != 3 or isinstance(doc.get("Version"), bool):
        _fail("当前只支持 Cubism 3 格式 JSON（供 Cubism 3/4/5 运行包使用）。")


def _parameter(value):
    value = _object(value, {"Target", "Id"}, {"Target", "Id"})
    if value["Target"] != "Parameter":
        _fail("Live2D 物理目标只能是 Parameter。")
    _text(value["Id"])


def _vector(value):
    value = _object(value, {"X", "Y"}, {"X", "Y"})
    _number(value["X"])
    _number(value["Y"])


def _auxiliary(doc, kind):
    if kind == "exp3.json":
        _object(doc, {"Version", "Type", "FadeInTime", "FadeOutTime", "Parameters"}, {"Type", "Parameters"})
        if "Version" in doc:
            _version(doc)
        if doc["Type"] != "Live2D Expression":
            _fail("Live2D 表情类型不正确。")
        for key in ("FadeInTime", "FadeOutTime"):
            if key in doc:
                _number(doc[key], 0, 60)
        for row in _array(doc["Parameters"], 512):
            row = _object(row, {"Id", "Value", "Blend"}, {"Id", "Value"})
            _text(row["Id"])
            _number(row["Value"])
            if row.get("Blend", "Add") not in {"Add", "Multiply", "Overwrite"}:
                _fail("Live2D 表情混合方式不正确。")
        return
    if kind != "pose3.json" or "Version" in doc:
        _version(doc)
    if kind == "cdi3.json":
        _object(doc, {"Version", "Parameters", "ParameterGroups", "Parts", "ArtMeshes", "CombinedParameters"}, {"ParameterGroups", "Parts"})
        for key in ("Parameters", "ParameterGroups", "Parts", "ArtMeshes"):
            for row in _array(doc.get(key, []), 4096):
                required = {"Id", "Name", "GroupId"} if key in {"Parameters", "ParameterGroups"} else {"Id", "Name"}
                row = _object(row, required, required)
                _text(row["Id"])
                _text(row["Name"], 512)
                if "GroupId" in row and row["GroupId"] != "":
                    _text(row["GroupId"])
        for pair in _array(doc.get("CombinedParameters", []), 4096):
            if len(_array(pair, 2)) != 2:
                _fail("Live2D 参数组合必须由两个 ID 组成。")
            for parameter in pair:
                _text(parameter)
    elif kind == "pose3.json":
        _object(doc, {"Version", "Type", "FadeInTime", "Groups"}, {"Type", "Groups"})
        if doc["Type"] != "Live2D Pose":
            _fail("Live2D Pose 类型不正确。")
        if "FadeInTime" in doc:
            _number(doc["FadeInTime"], 0, 60)
        for group in _array(doc["Groups"], 128):
            for row in _array(group, 128):
                row = _object(row, {"Id", "Link"}, {"Id"})
                _text(row["Id"])
                for link in _array(row.get("Link", []), 128):
                    _text(link)
    elif kind == "motion3.json":
        _object(doc, {"Version", "Meta", "Curves", "UserData"}, {"Meta", "Curves"})
        meta = _object(doc["Meta"], {"Duration", "Fps", "Loop", "AreBeziersRestricted", "CurveCount", "TotalSegmentCount", "TotalPointCount", "UserDataCount", "TotalUserDataSize", "FadeInTime", "FadeOutTime"}, {"Duration", "Fps", "CurveCount", "TotalSegmentCount", "TotalPointCount"})
        _number(meta["Duration"], 0, 3600)
        _number(meta["Fps"], .01, 240)
        # Official exports may round Duration to two decimals while retaining
        # three-decimal segment endpoints. Permit at most 10 ms / one frame,
        # not an unbounded mismatch and never a reversal of curve time.
        time_limit = meta["Duration"] + min(.01, 1 / meta["Fps"])
        if not isinstance(meta.get("Loop", False), bool) or ("AreBeziersRestricted" in meta and not isinstance(meta["AreBeziersRestricted"], bool)):
            _fail("Live2D 动作循环或曲线标志不正确。")
        for key in ("FadeInTime", "FadeOutTime"):
            if key in meta:
                _number(meta[key], -1, 60)
        curves = _array(doc["Curves"], 512)
        if not curves:
            _fail("Live2D 动作曲线不能为空。")
        segments = points = 0
        for curve in curves:
            curve = _object(curve, {"Target", "Id", "Segments", "FadeInTime", "FadeOutTime"}, {"Target", "Id", "Segments"})
            if curve["Target"] not in {"Parameter", "Model", "PartOpacity"}:
                _fail("Live2D 动作目标不正确。")
            _text(curve["Id"])
            values = _array(curve["Segments"], 100_000)
            if len(values) < 2:
                _fail("Live2D 动作曲线缺少起点。")
            previous = _number(values[0], 0, time_limit)
            _number(values[1])
            points += 1
            pos = 2
            while pos < len(values):
                segment = _integer(values[pos], 0, 3)
                n = 6 if segment == 1 else 2
                if pos + 1 + n > len(values):
                    _fail("Live2D 动作曲线分段不完整。")
                end = _number(values[pos + n - 1], previous, time_limit)
                for i in range(pos + 1, pos + n + 1):
                    _number(values[i])
                previous = end
                points += n // 2
                segments += 1
                pos += n + 1
            for key in ("FadeInTime", "FadeOutTime"):
                if key in curve:
                    _number(curve[key], -1, 60)
        if (_integer(meta["CurveCount"]) != len(curves) or _integer(meta["TotalSegmentCount"]) != segments or _integer(meta["TotalPointCount"]) != points):
            _fail("Live2D 动作计数与实际曲线不一致。")
        # No approved event consumer: remove bounded data rather than requiring
        # users to edit a common official runtime export by hand. _json already
        # rejected executable fields, excessive nesting and non-finite values.
        had_events = bool(doc.get("UserData") or meta.get("UserDataCount", 0) or meta.get("TotalUserDataSize", 0))
        if "UserData" in doc:
            _array(doc["UserData"], 4096)
            doc.pop("UserData")
        for key in ("UserDataCount", "TotalUserDataSize"):
            if key in meta:
                _integer(meta[key], 0, 1_000_000)
                meta[key] = 0
        if had_events:
            return [DISCARDED_AUDIO_WARNING]
    elif kind == "physics3.json":
        _object(doc, {"Version", "Meta", "PhysicsSettings"}, {"Meta", "PhysicsSettings"})
        meta = _object(doc["Meta"], {"PhysicsSettingCount", "TotalInputCount", "TotalOutputCount", "VertexCount", "Fps", "EffectiveForces", "PhysicsDictionary"}, {"PhysicsSettingCount", "TotalInputCount", "TotalOutputCount", "VertexCount", "EffectiveForces", "PhysicsDictionary"})
        forces = _object(meta["EffectiveForces"], {"Gravity", "Wind"}, {"Gravity", "Wind"})
        _vector(forces["Gravity"])
        _vector(forces["Wind"])
        if "Fps" in meta:
            _number(meta["Fps"], 0, 240)
        for row in _array(meta["PhysicsDictionary"], 256):
            row = _object(row, {"Id", "Name"}, {"Id", "Name"})
            _text(row["Id"])
            _text(row["Name"], 512)
        settings = _array(doc["PhysicsSettings"], 256)
        inputs = outputs = vertices = 0
        for setting in settings:
            setting = _object(setting, {"Id", "Input", "Output", "Vertices", "Normalization"}, {"Id", "Input", "Output", "Vertices", "Normalization"})
            _text(setting["Id"])
            vs = _array(setting["Vertices"], 2048)
            if not vs:
                _fail("Live2D 物理链没有顶点。")
            vertices += len(vs)
            if vertices > 4096:
                _fail("Live2D 物理顶点超过4096。", 413)
            for vertex in vs:
                vertex = _object(vertex, {"Position", "Mobility", "Delay", "Acceleration", "Radius"}, {"Position", "Mobility", "Delay", "Acceleration", "Radius"})
                _vector(vertex["Position"])
                for key in ("Mobility", "Delay", "Acceleration", "Radius"):
                    _number(vertex[key], 0, 100_000)
            for key, parameter in (("Input", "Source"), ("Output", "Destination")):
                rows = _array(setting[key], 256)
                inputs += len(rows) if key == "Input" else 0
                outputs += len(rows) if key == "Output" else 0
                for row in rows:
                    required = {parameter, "Weight", "Type", "Reflect"} | ({"VertexIndex", "Scale"} if key == "Output" else set())
                    row = _object(row, required, required)
                    _parameter(row[parameter])
                    _number(row["Weight"], 0, 100)
                    if row["Type"] not in {"X", "Y", "Angle"} or not isinstance(row["Reflect"], bool):
                        _fail("Live2D 物理参数不正确。")
                    if key == "Output":
                        _integer(row["VertexIndex"], 1, len(vs) - 1)
                        _number(row["Scale"])
            norm = _object(setting["Normalization"], {"Position", "Angle"}, {"Position", "Angle"})
            for value in norm.values():
                value = _object(value, {"Minimum", "Default", "Maximum"}, {"Minimum", "Default", "Maximum"})
                lo, default, hi = (_number(value[k]) for k in ("Minimum", "Default", "Maximum"))
                if not lo <= default <= hi or lo == hi:
                    _fail("Live2D 物理归一化范围不正确。")
        actual = {"PhysicsSettingCount": len(settings), "TotalInputCount": inputs, "TotalOutputCount": outputs, "VertexCount": vertices}
        if any(_integer(meta[k]) != v for k, v in actual.items()):
            _fail("Live2D 物理计数与实际结构不一致。")
    else:
        _fail("不支持此 Live2D JSON 类型。")


def _texture(data, used_pixels):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        _fail("尚未安装图片解码组件 Pillow。", 503)
    if data.startswith(PNG_SIGNATURE):
        try:
            data = _clean_png(data)
        except AssetError as error:
            raise AssetError(str(error).replace("VRM", "Live2D"), error.status) from None
        expected = "PNG"
    elif data.startswith(b"\xff\xd8"):
        expected = "JPEG"
    else:
        _fail("Live2D 纹理必须是真正的静态 PNG/JPEG。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                if probe.format != expected or getattr(probe, "n_frames", 1) != 1:
                    _fail("Live2D 纹理格式不正确。")
                if not (1 <= width <= MAX_TEXTURE_EDGE and 1 <= height <= MAX_TEXTURE_EDGE) or used_pixels + width * height > MAX_TEXTURE_PIXELS:
                    _fail("Live2D 纹理超过4096边长或3200万总像素预算。", 413)
                probe.verify()
            with Image.open(io.BytesIO(data)) as decoded:
                decoded.load()
                with Image.new("RGBA", decoded.size) as normalized:
                    normalized.paste(decoded.convert("RGBA"))
                    stream = io.BytesIO()
                    normalized.save(stream, format="PNG", compress_level=6)
        return stream.getvalue(), width, height
    except AssetError:
        raise
    except (ValueError, OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        _fail("Live2D 纹理无法完整解码。")


class _Package:
    def __init__(self, archive, check_cancel):
        self.archive, self.check_cancel = archive, check_cancel
        self.entries, seen, total = {}, set(), 0
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ENTRIES:
            _fail("Live2D ZIP 文件数量超过256或为空。", 413)
        for entry in entries:
            name = _path(entry.filename, entry.is_dir())
            key = unicodedata.normalize("NFC", name).casefold()
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if entry.orig_filename != entry.filename or key in seen or kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR and not entry.is_dir()):
                _fail("Live2D ZIP 含重复路径、符号链接或非普通文件。")
            seen.add(key)
            if entry.flag_bits & 1 or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                _fail("Live2D ZIP 不支持加密或此压缩格式。")
            if entry.is_dir():
                if entry.file_size or kind == stat.S_IFREG:
                    _fail("Live2D ZIP 目录条目不能携带文件内容。")
                continue
            if not 0 < entry.file_size <= MAX_ENTRY_BYTES:
                _fail("Live2D ZIP 单个文件须为1字节至32 MiB。", 413)
            total += entry.file_size
            if total > MAX_UNCOMPRESSED_BYTES or entry.file_size > MAX_RATIO * max(1, entry.compress_size):
                _fail("Live2D ZIP 展开大小或压缩比超过预算。", 413)
            # No executable or arbitrary payload survives even when unreferenced.
            suffix = name.lower()
            if not (suffix.endswith((".moc3", ".png", ".jpg", ".jpeg", ".model3.json", ".motion3.json", ".exp3.json", ".physics3.json", ".cdi3.json", ".pose3.json", ".userdata3.json", ".wav", ".mp3", ".ogg", ".m4a", ".flac", ".txt", ".md")) or PurePosixPath(name).name.lower() == "model3.json" or PurePosixPath(name).name.upper() in {"LICENSE", "NOTICE", "COPYING"}):
                _fail("Live2D ZIP 含脚本、源工程或不支持的文件；请只导出运行包。")
            self.entries[name] = entry
        # A file path cannot also be an ancestor directory (a / a/b).
        keys = {unicodedata.normalize("NFC", n).casefold() for n in self.entries}
        for name in self.entries:
            parts = name.split("/")
            if any(unicodedata.normalize("NFC", "/".join(parts[:i])).casefold() in keys for i in range(1, len(parts))):
                _fail("Live2D ZIP 文件与目录路径冲突。")
        models = [n for n in self.entries if n.lower().endswith(".model3.json") or PurePosixPath(n).name.lower() == "model3.json"]
        if len(models) != 1:
            _fail("Live2D ZIP 必须只包含一个 model3.json。")
        self.model_name = models[0]
        self.base = PurePosixPath(self.model_name).parent
        self.resources, self.source_map = {}, {}
        self.warnings = set()
        self.json_bytes = self.texture_pixels = 0

    def read(self, name):
        self.check_cancel()
        entry = self.entries.get(name)
        if entry is None:
            _fail("Live2D model3.json 引用了包内不存在的文件。")
        with self.archive.open(entry) as stream:
            data = stream.read(entry.file_size + 1)
        if len(data) != entry.file_size:
            _fail("Live2D ZIP 文件长度不一致。")
        return data

    def json(self, name):
        data = self.read(name)
        self.json_bytes += len(data)
        if self.json_bytes > MAX_JSON_TOTAL_BYTES:
            _fail("Live2D 引用的 JSON 合计超过8 MiB。", 413)
        return _json(data)

    def resource(self, relative, kind):
        relative = _path(relative)
        name = str(self.base / relative)
        if not relative.lower().endswith("." + kind):
            if kind != "png" or not relative.lower().endswith((".jpg", ".jpeg")):
                _fail("Live2D 文件引用的后缀或类型不正确。")
        if name not in self.entries:
            _fail("Live2D 引用必须留在 model3.json 所在目录内。")
        if name in self.source_map:
            resource, old_kind = self.source_map[name]
            if old_kind != kind:
                _fail("Live2D 同一资源被作为不同类型引用。")
            return resource
        if len(self.resources) >= MAX_RESOURCES:
            _fail("Live2D 实际引用资源超过96个。", 413)
        resource = f"r{len(self.resources) + 1:04d}.{kind}"
        if kind == "moc3":
            data = self.read(name)
            if len(data) < 64 or data[:4] != b"MOC3" or data[4] not in MOC_VERSIONS or data[5] not in (0, 1):
                _fail("MOC3 文件头或版本不受当前导入器识别。")
            self.moc_version = {"code": data[4], "label": MOC_VERSIONS[data[4]], "byte_order_flag": data[5], "core_verified": False}
        elif kind == "png":
            data, width, height = _texture(self.read(name), self.texture_pixels)
            self.texture_pixels += width * height
        else:
            doc = self.json(name)
            self.warnings.update(_auxiliary(doc, kind) or [])
            data = _json_bytes(doc)
        self.resources[resource] = (data, "image/png" if kind == "png" else "application/octet-stream" if kind == "moc3" else "application/json")
        self.source_map[name] = (resource, kind)
        return resource

    def run(self):
        # Read every advertised entry with CRC enforcement; do not extract paths.
        all_json_bytes = 0
        for name in self.entries:
            data = self.read(name)
            if name.lower().endswith(".json"):
                all_json_bytes += len(data)
                if all_json_bytes > MAX_JSON_TOTAL_BYTES:
                    _fail("Live2D 包内 JSON 合计超过8 MiB。", 413)
                _json(data)
        doc = self.json(self.model_name)
        _object(doc, {"Version", "FileReferences", "Groups", "HitAreas", "Layout"}, {"Version", "FileReferences"})
        _version(doc)
        references = _object(doc["FileReferences"], {"Moc", "Textures", "Motions", "Expressions", "Physics", "DisplayInfo", "Pose", "UserData"}, {"Moc", "Textures"})
        if "UserData" in references:
            name = _path(references.pop("UserData"))
            if not name.lower().endswith(".userdata3.json"):
                _fail("Live2D UserData 引用类型不正确。")
            self.warnings.add(DISCARDED_AUDIO_WARNING)
        references["Moc"] = self.resource(references["Moc"], "moc3")
        textures = _array(references["Textures"], MAX_TEXTURES)
        if not textures:
            _fail("Live2D 运行包至少需要一张纹理。")
        references["Textures"] = [self.resource(name, "png") for name in textures]
        if len(set(references["Textures"])) != len(references["Textures"]):
            _fail("Live2D 纹理列表不能重复引用同一资源。")
        for field, kind in (("Physics", "physics3.json"), ("DisplayInfo", "cdi3.json"), ("Pose", "pose3.json")):
            if field in references:
                references[field] = self.resource(references[field], kind)
        expression_names = []
        for expression in _array(references.get("Expressions", []), 32):
            expression = _object(expression, {"Name", "File"}, {"Name", "File"})
            name = _text(expression["Name"], 80)
            if name in expression_names:
                _fail("Live2D 表情名称重复。")
            expression_names.append(name)
            expression["File"] = self.resource(expression["File"], "exp3.json")
        motions = _object(references.get("Motions", {}))
        if len(motions) > 32:
            _fail("Live2D 动作组超过32。", 413)
        motion_count = 0
        for group, rows in motions.items():
            if group:
                _text(group, 80)
            for motion in _array(rows, 64):
                motion_count += 1
                if motion_count > 64:
                    _fail("Live2D 动作超过64。", 413)
                motion = _object(motion, {"File", "FadeInTime", "FadeOutTime", "Sound"}, {"File"})
                if "Sound" in motion:
                    sound = _path(motion.pop("Sound"))
                    if not sound.lower().endswith((".wav", ".mp3", ".ogg", ".m4a", ".flac")):
                        _fail("Live2D Sound 引用类型不正确。")
                    self.warnings.add(DISCARDED_AUDIO_WARNING)
                for fade in ("FadeInTime", "FadeOutTime"):
                    if fade in motion:
                        _number(motion[fade], -1, 60)
                motion["File"] = self.resource(motion["File"], "motion3.json")
        blink = talk = False
        for group in _array(doc.get("Groups", []), 64):
            group = _object(group, {"Target", "Name", "Ids"}, {"Target", "Name", "Ids"})
            if group["Target"] != "Parameter" or group["Name"] not in {"EyeBlink", "LipSync"}:
                _fail("Live2D 参数分组不在支持范围。")
            for parameter in _array(group["Ids"], 128):
                _text(parameter)
            blink |= group["Name"] == "EyeBlink" and bool(group["Ids"])
            talk |= group["Name"] == "LipSync" and bool(group["Ids"])
        for hit in _array(doc.get("HitAreas", []), 64):
            hit = _object(hit, {"Id", "Name"}, {"Id", "Name"})
            _text(hit["Id"])
            _text(hit["Name"])
        for value in _object(doc.get("Layout", {}), {"width", "height", "x", "y", "center_x", "center_y", "top", "bottom", "left", "right"}).values():
            _number(value, -100, 100)
        self.doc = doc
        self.capabilities = {"live2d": True, "static": False, "talk": talk, "blink": blink, "expressions": expression_names, "motion_groups": list(motions)}
        # Keep explicit author-supplied license notices with the private import;
        # never infer rights from their presence and never render them as HTML.
        self.notices = []
        notice_bytes = 0
        for source in self.entries:
            if not re.fullmatch(r"(?:LICENSE|LICENCE|COPYING|NOTICE)(?:\.(?:txt|md))?", PurePosixPath(source).name, re.I):
                continue
            data = self.read(source)
            notice_bytes += len(data)
            if len(self.notices) >= 8 or notice_bytes > 512 * 1024 or len(self.resources) >= MAX_RESOURCES:
                _fail("Live2D 许可说明超过8份、512 KiB或资源数量预算。", 413)
            try:
                data.decode("utf-8-sig")
            except UnicodeError:
                _fail("Live2D 许可说明须使用 UTF-8 文本。")
            resource = f"r{len(self.resources) + 1:04d}.notice.txt"
            self.resources[resource] = (data, "text/plain; charset=utf-8")
            self.notices.append(resource)
        return _json_bytes(doc)


def import_live2d(store, data: bytes, filename=None, *, cancel_event: threading.Event | None = None):
    if not isinstance(data, bytes) or not data:
        _fail("请选择非空的 Live2D ZIP 运行包。")
    if len(data) > MAX_ZIP_BYTES:
        _fail("Live2D ZIP 不得超过64 MiB。", 413)
    if filename is not None and (not isinstance(filename, str) or not 1 <= len(filename) <= 255 or not filename.lower().endswith(".zip") or any(c in filename for c in "/\\:") or any(ord(c) < 32 for c in filename)):
        _fail("请选择有效的 ZIP 文件名。")
    if not data.startswith(b"PK\x03\x04"):
        _fail("请选择真正的 ZIP 运行包，不支持其他归档格式。")
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            _fail("素材导入已取消。", 409)
    check_cancel()
    with store._lock:
        staging = None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                package = _Package(archive, check_cancel)
                encoded = package.run()
            thumbnail = _thumbnail()
            total = len(encoded) + len(thumbnail) + sum(len(d) for d, _ in package.resources.values())
            if total > MAX_UNCOMPRESSED_BYTES:
                _fail("Live2D 规范化运行包超过96 MiB。", 413)
            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=store.root))
            asset_id = str(uuid4())
            target = store.root / asset_id
            if target.exists() or target.is_symlink():
                _fail("素材标识冲突，请重试。", 409)
            model = {"resource": "model.model3.json", "model3json": "model.model3.json", "mime": "application/json", "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
            manifest = {"id": asset_id, "schema_version": 1, "format": "live2d", "created_at": datetime.now(timezone.utc).isoformat(), "states": {}, "model": model, "resources": {},
                        "thumbnail": _description("thumbnail.png", thumbnail, 128, 128), "total_bytes": total,
                        "moc3_version": package.moc_version, "capabilities": package.capabilities,
                        "notices": package.notices,
                        "warnings": sorted(package.warnings),
                        "runtime": {"requires_user_core": True, "core_bundled": False, "core_consistency_verified": False, "license_verified": False},
                        "budgets": {"texture_pixels": package.texture_pixels, "decoded_texture_bytes": package.texture_pixels * 4, "resources": len(package.resources)}}
            (staging / "model.model3.json").write_bytes(encoded)
            (staging / "thumbnail.png").write_bytes(thumbnail)
            for resource, (content, mime) in package.resources.items():
                check_cancel()
                (staging / resource).write_bytes(content)
                manifest["resources"][resource] = {"resource": resource, "mime": mime, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            if len(encoded_manifest.encode("utf-8")) > 32 * 1024:
                _fail("Live2D 资源清单超过当前预算。", 413)
            (staging / "manifest.json").write_text(encoded_manifest, encoding="utf-8")
            check_cancel()
            staging.rename(target)
            return manifest
        except AssetError:
            raise
        except MemoryError:
            _fail("Live2D 导入内存不足，请缩小运行包。", 503)
        except OSError:
            _fail("Live2D 素材保存失败，请检查磁盘空间。", 503)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError, zipfile.BadZipFile, NotImplementedError, RuntimeError):
            _fail("Live2D ZIP/JSON 无法完整校验或资源引用无效。")
        finally:
            if staging is not None and staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    _fail("Live2D 临时素材清理失败，请检查磁盘。", 503)


def manifest_resources(manifest):
    if manifest.get("states") != {} or not isinstance(manifest.get("resources"), dict) or len(manifest["resources"]) > MAX_RESOURCES:
        raise ValueError("invalid live2d manifest")
    result = [("model.model3.json", manifest["model"], MAX_JSON_BYTES), ("thumbnail.png", manifest["thumbnail"], 4 * 1024 * 1024)]
    for resource, value in manifest["resources"].items():
        if not isinstance(resource, str) or not _RESOURCE.fullmatch(resource):
            raise ValueError("invalid live2d resource")
        result.append((resource, value, MAX_UNCOMPRESSED_BYTES))
    return result
