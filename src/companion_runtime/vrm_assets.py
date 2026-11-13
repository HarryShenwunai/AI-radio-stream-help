"""Restricted, self-contained VRM 0/1 GLB imports; no networking or identity I/O.

This is an application acceptance profile, not a general glTF validator. Geometry
and textures are bounded before decoding; image metadata and glTF extras are
removed. Only explicitly supported declarative extensions survive publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import threading
from typing import Any
from uuid import uuid4
import warnings
import zlib

from .assets import AssetError, PNG_SIGNATURE, _description

MAX_VRM_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_GEOMETRY_BYTES = 48 * 1024 * 1024
MAX_TEXTURE_PIXELS = 32_000_000
MAX_TEXTURE_EDGE = 4096
MAX_IMAGES = 32
MAX_ACCESSOR_BYTES = 96 * 1024 * 1024
MAX_REPACKED_BIN_BYTES = MAX_VRM_BYTES - MAX_JSON_BYTES
SUPPORTED_EXTENSIONS = frozenset({
    "VRM", "VRMC_vrm", "VRMC_springBone", "VRMC_node_constraint",
    "VRMC_materials_mtoon", "VRMC_materials_hdr_emissiveMultiplier",
    "KHR_materials_unlit", "KHR_texture_transform", "KHR_materials_emissive_strength",
    "KHR_materials_pbrSpecularGlossiness", "KHR_materials_specular",
    "KHR_materials_ior", "KHR_materials_clearcoat", "KHR_materials_sheen",
    "KHR_materials_transmission", "KHR_materials_volume", "KHR_materials_iridescence",
    "KHR_materials_anisotropy", "KHR_materials_dispersion",
})
REQUIRED_BONES = frozenset({"hips", "spine", "head", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightUpperArm", "rightLowerArm", "rightHand", "leftUpperLeg", "leftLowerLeg", "leftFoot",
    "rightUpperLeg", "rightLowerLeg", "rightFoot"})
COMPONENTS = {5120: (1, "b"), 5121: (1, "B"), 5122: (2, "h"), 5123: (2, "H"), 5125: (4, "I"), 5126: (4, "f")}
TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _fail(message: str = "VRM 数据结构不正确或包含不支持的资源。", status: int = 400):
    raise AssetError(message, status)


def _integer(value, low=0, high=2**31 - 1):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        _fail("VRM 索引、数量或字节范围不正确。")
    return value


def _obj(value):
    if not isinstance(value, dict):
        _fail()
    return value


def _array(value, maximum=8192):
    if not isinstance(value, list):
        _fail()
    if len(value) > maximum:
        _fail("VRM 对象数量超过当前运行预算。", 413)
    return value


def _index(value, items):
    return _integer(value, 0, len(items) - 1)


def _text(value, maximum=120):
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if c.isprintable())[:maximum]


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("VRM JSON 包含重复字段。")
        result[key] = value
    return result


def _walk(value, depth=0):
    if depth > 48:
        _fail("VRM JSON 嵌套超过当前预算。", 413)
    if isinstance(value, dict):
        if any(str(k).lower() in {"uri", "script", "scripts", "javascript", "onload"} for k in value):
            _fail("VRM 必须内嵌所有资源，不能包含 URI 或脚本。")
        # extras is application-defined data, never part of this renderer's API.
        value.pop("extras", None)
        if "extensions" in value:
            extensions = _obj(value["extensions"])
            if not set(extensions).issubset(SUPPORTED_EXTENSIONS):
                _fail("VRM 含未支持的扩展；压缩几何、压缩纹理或可执行扩展不可导入。")
            for name, extension in extensions.items():
                extension = _obj(extension)
                if name.startswith("VRMC_") and extension.get("specVersion") not in {"1.0", "1.0-beta"}:
                    _fail("不支持此 VRMC 扩展版本。")
        for k, v in value.items():
            if not isinstance(k, str) or len(k) > 512:
                _fail()
            _walk(v, depth + 1)
    elif isinstance(value, list):
        _array(value, 100_000)
        for v in value:
            _walk(v, depth + 1)
    elif isinstance(value, float) and (not math.isfinite(value) or abs(value) > 3.4028234663852886e38):
        _fail("VRM 包含非有限数值或超过 float32 的数值。")
    elif isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
        _fail("VRM 整数超过浏览器可精确表示范围。")
    elif isinstance(value, str):
        if len(value) > 65536 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            _fail("VRM 文本字段不正确。")


def _container(data: bytes):
    if not isinstance(data, bytes) or not data:
        _fail("请选择非空 VRM 文件。")
    if len(data) > MAX_VRM_BYTES:
        _fail("VRM 文件不得超过 64 MiB。", 413)
    if len(data) < 28 or data[:4] != b"glTF":
        _fail("请选择真正的 VRM GLB 文件；不支持 ZIP 或文本 glTF。")
    magic, version, length = struct.unpack_from("<III", data)
    if version != 2 or length != len(data):
        _fail("VRM GLB 版本或文件长度不正确。")
    chunks = []
    pos = 12
    while pos < len(data):
        if len(chunks) >= 2:
            _fail("VRM 不能包含额外 GLB 数据块。")
        if pos + 8 > len(data):
            _fail("VRM GLB 数据不完整。")
        size, kind = struct.unpack_from("<II", data, pos)
        pos += 8
        if size % 4 or size > len(data) - pos:
            _fail("VRM GLB 数据块越界或未对齐。")
        chunks.append((kind, data[pos:pos + size]))
        pos += size
    if [k for k, _ in chunks] != [0x4E4F534A, 0x004E4942]:
        _fail("VRM 必须只有顺序正确的 JSON 与内嵌 BIN 数据块。")
    if len(chunks[0][1]) > MAX_JSON_BYTES:
        _fail("VRM JSON 不得超过 4 MiB。", 413)
    try:
        doc = json.loads(chunks[0][1].decode("utf-8"), object_pairs_hook=_json_pairs,
                         parse_constant=lambda _: _fail("VRM 包含非有限数值。"))
    except (ValueError, UnicodeError, RecursionError):
        _fail("VRM JSON 无法读取。")
    _obj(doc)
    _walk(doc)
    asset = _obj(doc.get("asset"))
    if asset.get("version") != "2.0" or asset.get("minVersion", "2.0") != "2.0":
        _fail("当前仅支持 glTF 2.0 的 VRM。")
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in doc and (not isinstance(doc[key], list) or len(doc[key]) > 32 or any(not isinstance(x, str) or x not in SUPPORTED_EXTENSIONS for x in doc[key])):
            _fail("VRM 声明了未支持的扩展。")
    if not set(doc.get("extensionsRequired", [])).issubset(doc.get("extensionsUsed", [])):
        _fail("VRM 必需扩展没有在 extensionsUsed 声明。")
    buffers = _array(doc.get("buffers"), 1)
    if len(buffers) != 1:
        _fail("VRM 必须使用单个内嵌 BIN。")
    count = _integer(_obj(buffers[0]).get("byteLength"), 1, MAX_REPACKED_BIN_BYTES)
    binary = chunks[1][1]
    if not count <= len(binary) <= count + 3 or any(binary[count:]):
        _fail("VRM BIN 长度或填充不正确。")
    return doc, binary[:count]


class _Validator:
    def __init__(self, doc, binary, check_cancel):
        self.doc, self.binary, self.check_cancel = doc, binary, check_cancel
        self.views = _array(doc.get("bufferViews", []), 8192)
        self.accessors = _array(doc.get("accessors", []), 8192)
        self.nodes = _array(doc.get("nodes", []), 4096)
        self.meshes = _array(doc.get("meshes", []), 512)
        self.materials = _array(doc.get("materials", []), 256)
        self.images = _array(doc.get("images", []), MAX_IMAGES)
        self.textures = _array(doc.get("textures", []), 256)
        self.view_bytes, self.texture_pixels, self.decoded_bytes, self.accessor_bytes = [], 0, 0, 0

    def refs(self, obj, key, items):
        if key in obj:
            _index(obj[key], items)

    def views_check(self):
        total = 0
        for view in self.views:
            view = _obj(view)
            if view.get("buffer") != 0:
                _fail("VRM bufferView 必须引用内嵌 BIN。")
            offset = _integer(view.get("byteOffset", 0))
            size = _integer(view.get("byteLength"), 1)
            if offset % 4 or offset + size > len(self.binary):
                _fail("VRM bufferView 超出 BIN 范围或未对齐。")
            if "byteStride" in view:
                stride = _integer(view["byteStride"], 4, 252)
                if stride % 4:
                    _fail("VRM byteStride 未按 4 字节对齐。")
            if "target" in view and view["target"] not in (34962, 34963):
                _fail()
            total += size
            if total > MAX_REPACKED_BIN_BYTES:
                _fail("VRM bufferView 展开后超过 60 MiB 预算。", 413)
            self.view_bytes.append(self.binary[offset:offset + size])

    def span(self, view_index, offset, count, unit, stride=None, float_format=None):
        view_index = _index(view_index, self.views)
        offset = _integer(offset)
        stride = unit if stride is None else stride
        size = offset + (count - 1) * stride + unit
        if stride < unit or size > len(self.view_bytes[view_index]):
            _fail("VRM accessor 超出 bufferView 范围。")
        if float_format is not None:
            raw = self.view_bytes[view_index]
            unpack = struct.Struct("<" + float_format)
            for row in range(count):
                if row % 8192 == 0:
                    self.check_cancel()
                if not all(math.isfinite(v) for v in unpack.unpack_from(raw, offset + row * stride)):
                    _fail("VRM 几何包含 NaN 或 Infinity。")
        return view_index

    def accessors_check(self):
        for a in self.accessors:
            a = _obj(a)
            component = a.get("componentType")
            kind = a.get("type")
            if component not in COMPONENTS or kind not in TYPE_COUNTS:
                _fail("VRM accessor 类型不正确。")
            size, fmt = COMPONENTS[component]
            components = TYPE_COUNTS[kind]
            # Matrix columns have four-byte alignment in glTF.
            if kind in {"MAT2", "MAT3"} and size < 4:
                _fail("当前 VRM 不支持小于 32bit 的矩阵 accessor。")
            unit = size * components
            count = _integer(a.get("count"), 1, 6_000_000)
            self.accessor_bytes += unit * count
            if self.accessor_bytes > MAX_ACCESSOR_BYTES:
                _fail("VRM 展开后的几何数据超过 96 MiB 预算。", 413)
            offset = _integer(a.get("byteOffset", 0))
            if offset % size:
                _fail("VRM accessor 未对齐。")
            if "normalized" in a and (not isinstance(a["normalized"], bool) or (a["normalized"] and component in (5125, 5126))):
                _fail("VRM normalized accessor 类型不正确。")
            if "bufferView" in a:
                view = self.views[_index(a["bufferView"], self.views)]
                self.span(a["bufferView"], offset, count, unit, view.get("byteStride"), fmt * components if component == 5126 else None)
            elif offset or "sparse" not in a:
                _fail("VRM accessor 缺少数据。")
            for bound in ("min", "max"):
                if bound in a and (not isinstance(a[bound], list) or len(a[bound]) != components or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in a[bound])):
                    _fail("VRM accessor 边界不正确。")
            if "sparse" in a:
                sparse = _obj(a["sparse"])
                n = _integer(sparse.get("count"), 1, count)
                indices, values = _obj(sparse.get("indices")), _obj(sparse.get("values"))
                c = indices.get("componentType")
                if c not in (5121, 5123, 5125):
                    _fail("VRM sparse 索引类型不正确。")
                width, index_fmt = COMPONENTS[c]
                for item, alignment in ((indices, width), (values, size)):
                    offset = _integer(item.get("byteOffset", 0))
                    view = self.views[_index(item.get("bufferView"), self.views)]
                    if offset % alignment or "byteStride" in view or "target" in view:
                        _fail("VRM sparse 数据未对齐或含不适用的 stride/target。")
                vi = self.span(indices.get("bufferView"), indices.get("byteOffset", 0), n, width)
                start = indices.get("byteOffset", 0)
                previous = -1
                for row in range(n):
                    if row % 8192 == 0:
                        self.check_cancel()
                    index = struct.unpack_from("<" + index_fmt, self.view_bytes[vi], start + row * width)[0]
                    if index <= previous or index >= count:
                        _fail("VRM sparse 索引越界或未排序。")
                    previous = index
                self.span(values.get("bufferView"), values.get("byteOffset", 0), n, unit, float_format=fmt * components if component == 5126 else None)

    def geometry_check(self):
        primitive_count = vertices = 0
        mesh_stats = []
        for mesh in self.meshes:
            mesh = _obj(mesh)
            target_counts = set()
            mesh_primitives, mesh_vertices = 0, 0
            for primitive in _array(mesh.get("primitives"), 512):
                primitive = _obj(primitive)
                primitive_count += 1
                mesh_primitives += 1
                if primitive_count > 512:
                    _fail("VRM 绘制批次超过 512。", 413)
                attributes = _obj(primitive.get("attributes"))
                if "POSITION" not in attributes:
                    _fail("VRM mesh 缺少 POSITION。")
                position = self.accessors[_index(attributes["POSITION"], self.accessors)]
                if position["type"] != "VEC3" or position["componentType"] != 5126:
                    _fail("VRM POSITION 必须是浮点 VEC3。")
                vertices += position["count"]
                mesh_vertices += position["count"]
                if vertices > 2_000_000:
                    _fail("VRM 顶点总数超过 200 万。", 413)
                for attribute, accessor in attributes.items():
                    a = self.accessors[_index(accessor, self.accessors)]
                    if a["count"] != position["count"]:
                        _fail("VRM 顶点属性数量不一致。")
                    valid = True
                    if attribute in {"NORMAL", "TANGENT"}:
                        valid = a["type"] == ("VEC4" if attribute == "TANGENT" else "VEC3") and a["componentType"] == 5126
                    elif attribute.startswith(("TEXCOORD_", "COLOR_", "JOINTS_", "WEIGHTS_")):
                        prefix, suffix = attribute.rsplit("_", 1)
                        valid = suffix.isdigit() and int(suffix) < 8
                        if prefix == "TEXCOORD":
                            valid &= a["type"] == "VEC2" and (a["componentType"] == 5126 or (a["componentType"] in (5121, 5123) and a.get("normalized") is True))
                        elif prefix == "COLOR":
                            valid &= a["type"] in {"VEC3", "VEC4"} and (a["componentType"] == 5126 or (a["componentType"] in (5121, 5123) and a.get("normalized") is True))
                        elif prefix == "JOINTS":
                            valid &= a["type"] == "VEC4" and a["componentType"] in (5121, 5123) and not a.get("normalized", False)
                        else:
                            valid &= a["type"] == "VEC4" and (a["componentType"] == 5126 or (a["componentType"] in (5121, 5123) and a.get("normalized") is True))
                    elif attribute != "POSITION" and not attribute.startswith("_"):
                        valid = False
                    if not valid:
                        _fail("VRM 顶点属性类型不正确或超出支持范围。")
                if "indices" in primitive:
                    a = self.accessors[_index(primitive["indices"], self.accessors)]
                    if a["type"] != "SCALAR" or a["componentType"] not in (5121, 5123, 5125) or "sparse" in a or "bufferView" not in a:
                        _fail("VRM 三角索引类型不正确。")
                    raw = self.view_bytes[a["bufferView"]]
                    width, fmt = COMPONENTS[a["componentType"]]
                    offset = a.get("byteOffset", 0)
                    if "byteStride" in self.views[a["bufferView"]] or a["count"] % 3:
                        _fail("VRM 三角索引 stride 或数量不正确。")
                    for i in range(a["count"]):
                        if i % 8192 == 0:
                            self.check_cancel()
                        if struct.unpack_from("<" + fmt, raw, offset + i * width)[0] >= position["count"]:
                            _fail("VRM mesh 顶点索引越界。")
                elif position["count"] % 3:
                    _fail("VRM 三角顶点数量不正确。")
                self.refs(primitive, "material", self.materials)
                if primitive.get("mode", 4) != 4:
                    _fail("当前仅支持 VRM 三角网格。")
                targets = _array(primitive.get("targets", []), 128)
                if targets:
                    target_counts.add(len(targets))
                for target in targets:
                    for name, index in _obj(target).items():
                        if name not in {"POSITION", "NORMAL", "TANGENT"} or name not in attributes:
                            _fail("VRM morph 属性不正确。")
                        a = self.accessors[_index(index, self.accessors)]
                        if a["count"] != position["count"] or a["componentType"] != 5126 or a["type"] != "VEC3":
                            _fail("VRM morph 维度不正确。")
            if len(target_counts) > 1:
                _fail("VRM mesh 的 morph 数量不一致。")
            if "weights" in mesh:
                weights = _array(mesh["weights"], 128)
                if len(weights) != (next(iter(target_counts)) if target_counts else 0) or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in weights):
                    _fail("VRM morph 默认权重不正确。")
            mesh_stats.append((mesh_primitives, mesh_vertices))
        if not primitive_count:
            _fail("VRM 没有可绘制的模型。")
        self.primitive_count, self.vertices = primitive_count, vertices
        parent = {}
        instanced_primitives = instanced_vertices = 0
        for i, node in enumerate(self.nodes):
            node = _obj(node)
            self.refs(node, "mesh", self.meshes)
            if "mesh" in node:
                batches, points = mesh_stats[node["mesh"]]
                instanced_primitives += batches
                instanced_vertices += points
                if instanced_primitives > 512 or instanced_vertices > 2_000_000:
                    _fail("VRM 节点实例展开后超过绘制批次或顶点预算。", 413)
            self.refs(node, "skin", _array(self.doc.get("skins", []), 256))
            children = _array(node.get("children", []), 4096)
            if len(set(children)) != len(children):
                _fail("VRM 节点包含重复子节点。")
            for child in children:
                _index(child, self.nodes)
                if child in parent or child == i:
                    _fail("VRM 节点树重复引用或包含环。")
                parent[child] = i
            for key, size in (("translation", 3), ("rotation", 4), ("scale", 3), ("matrix", 16)):
                if key in node and (not isinstance(node[key], list) or len(node[key]) != size or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in node[key])):
                    _fail("VRM 节点变换不正确。")
            if "matrix" in node and any(k in node for k in ("translation", "rotation", "scale")):
                _fail("VRM 节点不能同时使用矩阵和 TRS。")
        for i in range(len(self.nodes)):
            if i % 32 == 0:
                self.check_cancel()
            seen = set()
            while i in parent:
                if i in seen:
                    _fail("VRM 节点树包含环。")
                seen.add(i)
                i = parent[i]
        scenes = _array(self.doc.get("scenes", []), 64)
        if not scenes:
            _fail("VRM 缺少场景。")
        self.refs(self.doc, "scene", scenes)
        for scene in scenes:
            for node in _array(_obj(scene).get("nodes", []), 4096):
                _index(node, self.nodes)
                if node in parent:
                    _fail("VRM 场景根节点有父节点。")
        for skin in _array(self.doc.get("skins", []), 256):
            skin = _obj(skin)
            joints = _array(skin.get("joints"), 1024)
            if not joints or len(set(joints)) != len(joints):
                _fail("VRM 关节列表不正确。")
            for node in joints:
                _index(node, self.nodes)
            self.refs(skin, "skeleton", self.nodes)
            if "inverseBindMatrices" in skin:
                a = self.accessors[_index(skin["inverseBindMatrices"], self.accessors)]
                if a["componentType"] != 5126 or a["type"] != "MAT4" or a["count"] != len(joints):
                    _fail("VRM 绑定矩阵维度不正确。")
                if "bufferView" in a and "byteStride" in self.views[a["bufferView"]]:
                    _fail("VRM 绑定矩阵不能使用顶点 stride。")
        checked_joints = set()
        skins = self.doc.get("skins", [])
        for node in self.nodes:
            if "skin" not in node:
                continue
            if "mesh" not in node:
                _fail("VRM skin 节点缺少 mesh。")
            joint_count = len(skins[node["skin"]]["joints"])
            for primitive in self.meshes[node["mesh"]]["primitives"]:
                attributes = primitive["attributes"]
                if not {"JOINTS_0", "WEIGHTS_0"}.issubset(attributes):
                    _fail("VRM skin mesh 缺少 JOINTS_0 或 WEIGHTS_0。")
                for name, index in attributes.items():
                    if not name.startswith("JOINTS_"):
                        continue
                    if "WEIGHTS_" + name.split("_", 1)[1] not in attributes:
                        _fail("VRM 关节和权重属性不配对。")
                    if (index, joint_count) in checked_joints:
                        continue
                    checked_joints.add((index, joint_count))
                    accessor = self.accessors[index]
                    width, fmt = COMPONENTS[accessor["componentType"]]
                    sources = []
                    if "bufferView" in accessor:
                        v = accessor["bufferView"]
                        sources.append((v, accessor.get("byteOffset", 0), accessor["count"], self.views[v].get("byteStride", width * 4)))
                    if "sparse" in accessor:
                        sparse = accessor["sparse"]
                        sources.append((sparse["values"]["bufferView"], sparse["values"].get("byteOffset", 0), sparse["count"], width * 4))
                    for view, offset, count, stride in sources:
                        raw = self.view_bytes[view]
                        for row in range(count):
                            if row % 8192 == 0:
                                self.check_cancel()
                            if any(j >= joint_count for j in struct.unpack_from("<" + fmt * 4, raw, offset + row * stride)):
                                _fail("VRM 顶点关节索引越界。")
        self.instanced_primitives, self.instanced_vertices = instanced_primitives, instanced_vertices
        keyframes = 0
        for animation in _array(self.doc.get("animations", []), 128):
            samplers = _array(_obj(animation).get("samplers", []), 4096)
            for sampler in samplers:
                sampler = _obj(sampler)
                a = self.accessors[_index(sampler.get("input"), self.accessors)]
                _index(sampler.get("output"), self.accessors)
                if a["type"] != "SCALAR" or a["componentType"] != 5126 or sampler.get("interpolation", "LINEAR") not in {"LINEAR", "STEP", "CUBICSPLINE"}:
                    _fail("VRM 动画采样器不正确。")
                keyframes += a["count"]
                if keyframes > 1_000_000:
                    _fail("VRM 动画关键帧超过 100 万。", 413)
                if "bufferView" not in a or "sparse" in a or "byteStride" in self.views[a["bufferView"]]:
                    _fail("当前 VRM 动画时间必须使用紧凑非 sparse accessor。")
                raw, offset, previous = self.view_bytes[a["bufferView"]], a.get("byteOffset", 0), -1.0
                for row in range(a["count"]):
                    if row % 8192 == 0:
                        self.check_cancel()
                    time = struct.unpack_from("<f", raw, offset + row * 4)[0]
                    if time < 0 or time <= previous:
                        _fail("VRM 动画时间必须非负且严格递增。")
                    previous = time
            animated_targets = set()
            for channel in _array(animation.get("channels", []), 4096):
                channel = _obj(channel)
                sampler = samplers[_index(channel.get("sampler"), samplers)]
                target = _obj(channel.get("target"))
                node_index = _index(target.get("node"), self.nodes)
                path = target.get("path")
                if path not in {"translation", "rotation", "scale", "weights"}:
                    _fail("VRM 动画目标不正确。")
                if (node_index, path) in animated_targets:
                    _fail("VRM 动画重复控制同一节点属性。")
                animated_targets.add((node_index, path))
                a, b = self.accessors[sampler["input"]], self.accessors[sampler["output"]]
                expected_count = a["count"] * (3 if sampler.get("interpolation") == "CUBICSPLINE" else 1)
                kind = {"translation": "VEC3", "scale": "VEC3", "rotation": "VEC4", "weights": "SCALAR"}[path]
                if path == "weights":
                    node = self.nodes[node_index]
                    if "mesh" not in node:
                        _fail("VRM morph 动画节点没有 mesh。")
                    morph_count = max(len(p.get("targets", [])) for p in self.meshes[node["mesh"]]["primitives"])
                    if not morph_count:
                        _fail("VRM morph 动画没有目标。")
                    expected_count *= morph_count
                if b["type"] != kind or b["componentType"] != 5126 or b["count"] != expected_count:
                    _fail("VRM 动画输出 accessor 维度不正确。")

    def images_check(self):
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError:
            _fail("尚未安装图片解码组件 Pillow。", 503)
        image_views = set()
        for image in self.images:
            self.check_cancel()
            image = _obj(image)
            index = _index(image.get("bufferView"), self.views)
            if index in image_views:
                _fail("VRM 不支持多个图片重复引用同一 bufferView。")
            image_views.add(index)
            raw = self.view_bytes[index]
            mime = image.get("mimeType")
            if mime not in {"image/png", "image/jpeg"} or (mime == "image/png" and not raw.startswith(PNG_SIGNATURE)) or (mime == "image/jpeg" and not raw.startswith(b"\xff\xd8")):
                _fail("VRM 纹理仅支持内嵌的真实 PNG/JPEG。")
            if mime == "image/png":
                raw = _clean_png(raw)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as probe:
                        if probe.format != ("PNG" if mime == "image/png" else "JPEG"):
                            _fail("VRM 纹理格式与声明不一致。")
                        width, height = probe.size
                        if not (1 <= width <= MAX_TEXTURE_EDGE and 1 <= height <= MAX_TEXTURE_EDGE):
                            _fail("VRM 纹理边长不得超过 4096。", 413)
                        self.texture_pixels += width * height
                        if self.texture_pixels > MAX_TEXTURE_PIXELS:
                            _fail("VRM 纹理总像素不得超过 3200 万。", 413)
                        if getattr(probe, "n_frames", 1) != 1:
                            _fail("VRM 不支持动画纹理。")
                        probe.verify()
                    with Image.open(io.BytesIO(raw)) as decoded:
                        decoded.load()
                        # Re-encode only decoded pixels, stripping EXIF/ICC/text.
                        with Image.new("RGBA", decoded.size) as normalized:
                            normalized.paste(decoded.convert("RGBA"))
                            out = io.BytesIO()
                            normalized.save(out, format="PNG", compress_level=6)
                            self.view_bytes[index] = out.getvalue()
                            image["mimeType"] = "image/png"
            except AssetError:
                raise
            except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                _fail("VRM 纹理无法完整解码。")
            self.decoded_bytes += width * height * 4
        geometry = sum(len(raw) for i, raw in enumerate(self.view_bytes) if i not in image_views)
        if geometry > MAX_GEOMETRY_BYTES:
            _fail("VRM 非纹理 BIN 数据超过 48 MiB。", 413)
        # Sharing a texture view with accessors would make image normalization
        # alter geometry. Image views must be dedicated resources.
        for a in self.accessors:
            used = [a.get("bufferView")]
            if "sparse" in a:
                used += [a["sparse"][k]["bufferView"] for k in ("indices", "values")]
            if any(v in image_views for v in used):
                _fail("VRM 纹理与几何不能共享 bufferView。")
        for image in self.images:
            view = self.views[image["bufferView"]]
            if "byteStride" in view or "target" in view:
                _fail("VRM 纹理 bufferView 含几何属性。")
        for texture in self.textures:
            texture = _obj(texture)
            _index(texture.get("source"), self.images)
            self.refs(texture, "sampler", _array(self.doc.get("samplers", []), 256))
        for sampler in _array(self.doc.get("samplers", []), 256):
            sampler = _obj(sampler)
            for key, allowed in (("magFilter", {9728, 9729}), ("minFilter", {9728, 9729, 9984, 9985, 9986, 9987}), ("wrapS", {33071, 33648, 10497}), ("wrapT", {33071, 33648, 10497})):
                if key in sampler and sampler[key] not in allowed:
                    _fail("VRM 纹理采样参数不正确。")
        def material_refs(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.endswith("Texture") and isinstance(value, dict) and "index" in value:
                        _index(value["index"], self.textures)
                    material_refs(value)
            elif isinstance(obj, list):
                for value in obj:
                    material_refs(value)
        material_refs(self.materials)
        self.geometry_bytes = geometry

    def vrm_check(self):
        extensions = _obj(self.doc.get("extensions"))
        if ("VRM" in extensions) == ("VRMC_vrm" in extensions):
            _fail("VRM 必须声明一个 VRM0 或 VRM1 角色扩展。")
        version = "1" if "VRMC_vrm" in extensions else "0"
        vrm = _obj(extensions["VRMC_vrm" if version == "1" else "VRM"])
        if vrm.get("specVersion", "0.0" if version == "0" else None) != ("1.0" if version == "1" else "0.0"):
            _fail("不支持此 VRM 扩展版本。")
        meta, humanoid = _obj(vrm.get("meta")), _obj(vrm.get("humanoid"))
        bones = humanoid.get("humanBones")
        if version == "1":
            bones = _obj(bones)
        else:
            rows = _array(bones, 128)
            bones = {}
            for row in rows:
                row = _obj(row)
                name = row.get("bone")
                if not isinstance(name, str) or name in bones:
                    _fail("VRM 人形骨骼重复或名称无效。")
                bones[name] = row
        if not REQUIRED_BONES.issubset(bones):
            _fail("VRM 缺少标准必需的人形骨骼。")
        bound = set()
        for bone in bones.values():
            node = _index(_obj(bone).get("node"), self.nodes)
            if node in bound:
                _fail("VRM 人形骨骼重复引用节点。")
            bound.add(node)
        expressions = []
        if version == "1":
            groups = _obj(vrm.get("expressions", {}))
            presets = _obj(groups.get("preset", {}))
            custom = _obj(groups.get("custom", {}))
            if len(presets) + len(custom) > 256:
                _fail("VRM 表情数量超过 256。", 413)
            expressions = [k for k in presets if k in {"neutral", "aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight", "happy", "angry", "sad", "relaxed", "surprised", "lookUp", "lookDown", "lookLeft", "lookRight"}]
            for expression in list(presets.values()) + list(custom.values()):
                expression = _obj(expression)
                for bind in _array(expression.get("morphTargetBinds", []), 4096):
                    bind = _obj(bind)
                    node = self.nodes[_index(bind.get("node"), self.nodes)]
                    mesh = self.meshes[_index(node.get("mesh"), self.meshes)]
                    target = _integer(bind.get("index"))
                    if not any(target < len(p.get("targets", [])) for p in mesh["primitives"]):
                        _fail("VRM 表情 morph 索引越界。")
                for key in ("materialColorBinds", "textureTransformBinds"):
                    for bind in _array(expression.get(key, []), 4096):
                        _index(_obj(bind).get("material"), self.materials)
            authors = meta.get("authors", [])
            license_url = meta.get("licenseUrl", "")
            self.refs(meta, "thumbnailImage", self.images)
            for row in _array(_obj(vrm.get("firstPerson", {})).get("meshAnnotations", []), 512):
                _index(_obj(row).get("node"), self.nodes)
        else:
            mapping = {"neutral": "neutral", "a": "aa", "i": "ih", "u": "ou", "e": "ee", "o": "oh", "blink": "blink", "blink_l": "blinkLeft", "blink_r": "blinkRight", "joy": "happy", "angry": "angry", "sorrow": "sad", "fun": "relaxed", "lookup": "lookUp", "lookdown": "lookDown", "lookleft": "lookLeft", "lookright": "lookRight"}
            for group in _array(_obj(vrm.get("blendShapeMaster", {})).get("blendShapeGroups", []), 256):
                group = _obj(group)
                preset = group.get("presetName")
                if preset in mapping:
                    expressions.append(mapping[preset])
                for bind in _array(group.get("binds", []), 4096):
                    bind = _obj(bind)
                    mesh = self.meshes[_index(bind.get("mesh"), self.meshes)]
                    target = _integer(bind.get("index"))
                    if not any(target < len(p.get("targets", [])) for p in mesh["primitives"]):
                        _fail("VRM 表情 morph 索引越界。")
                for material in _array(group.get("materialValues", []), 4096):
                    _obj(material)
            authors, license_url = [meta.get("author", "")], meta.get("otherLicenseUrl", "")
            if meta.get("texture", -1) != -1:
                self.refs(meta, "texture", self.textures)
            first = _obj(vrm.get("firstPerson", {}))
            if first.get("firstPersonBone", -1) != -1:
                self.refs(first, "firstPersonBone", self.nodes)
            for row in _array(first.get("meshAnnotations", []), 512):
                _index(_obj(row).get("mesh"), self.meshes)
            secondary = _obj(vrm.get("secondaryAnimation", {}))
            colliders = _array(secondary.get("colliderGroups", []), 1024)
            for collider in colliders:
                _index(_obj(collider).get("node"), self.nodes)
            for group in _array(secondary.get("boneGroups", []), 1024):
                group = _obj(group)
                if group.get("center", -1) != -1:
                    self.refs(group, "center", self.nodes)
                for node in _array(group.get("bones", []), 4096):
                    _index(node, self.nodes)
                for collider in _array(group.get("colliderGroups", []), 1024):
                    _index(collider, colliders)
            for material in _array(vrm.get("materialProperties", []), 256):
                for index in _obj(_obj(material).get("textureProperties", {})).values():
                    if index != -1:
                        _index(index, self.textures)
        spring = extensions.get("VRMC_springBone")
        if spring is not None:
            spring = _obj(spring)
            if spring.get("specVersion") not in ("1.0", "1.0-beta"):
                _fail("不支持此 VRM SpringBone 版本。")
            colliders, groups = _array(spring.get("colliders", []), 1024), _array(spring.get("colliderGroups", []), 1024)
            for collider in colliders:
                _index(_obj(collider).get("node"), self.nodes)
            for group in groups:
                for collider in _array(_obj(group).get("colliders", []), 1024):
                    _index(collider, colliders)
            for row in _array(spring.get("springs", []), 1024):
                row = _obj(row)
                self.refs(row, "center", self.nodes)
                for joint in _array(row.get("joints", []), 4096):
                    _index(_obj(joint).get("node"), self.nodes)
                for group in _array(row.get("colliderGroups", []), 1024):
                    _index(group, groups)
        constraints = {}
        for i, node in enumerate(self.nodes):
            constraint = node.get("extensions", {}).get("VRMC_node_constraint")
            if constraint is not None:
                constraint = _obj(constraint)
                if constraint.get("specVersion") not in ("1.0", "1.0-beta"):
                    _fail("不支持此 VRM Constraint 版本。")
                rules = _obj(constraint.get("constraint"))
                if len(rules) != 1 or not set(rules).issubset({"roll", "aim", "rotation"}):
                    _fail("VRM Constraint 类型不正确。")
                rule = _obj(next(iter(rules.values())))
                source = _index(rule.get("source"), self.nodes)
                weight = rule.get("weight", 1)
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
                    _fail("VRM Constraint 权重不正确。")
                constraints[i] = source
        for i in constraints:
            seen = set()
            while i in constraints:
                if i in seen:
                    _fail("VRM Constraint 包含循环依赖。")
                seen.add(i)
                i = constraints[i]
        if not isinstance(authors, list):
            _fail("VRM 作者字段不正确。")
        self.version = version
        self.metadata = {"name": _text(meta.get("name", meta.get("title", ""))),
                         "authors": [_text(a, 80) for a in authors[:16] if isinstance(a, str)],
                         "license_url": _text(license_url, 512)}
        self.expressions = sorted(set(expressions))

    def run(self):
        self.views_check()
        self.accessors_check()
        self.geometry_check()
        self.images_check()
        self.vrm_check()
        self.check_cancel()
        parts, offset = [], 0
        for view, raw in zip(self.views, self.view_bytes):
            pad = b"\0" * (-offset % 4)
            parts.append(pad)
            offset += len(pad)
            view["byteOffset"], view["byteLength"] = offset, len(raw)
            parts.append(raw)
            offset += len(raw)
            if offset > MAX_REPACKED_BIN_BYTES:
                _fail("VRM 规范化 BIN 超过当前预算。", 413)
        binary = b"".join(parts)
        self.doc["buffers"] = [{"byteLength": len(binary)}]
        encoded = json.dumps(self.doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        encoded += b" " * (-len(encoded) % 4)
        binary += b"\0" * (-len(binary) % 4)
        total = 28 + len(encoded) + len(binary)
        if total > MAX_VRM_BYTES:
            _fail("VRM 规范化后超过 64 MiB。", 413)
        result = struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + struct.pack("<II", len(binary), 0x004E4942) + binary
        return result


def _clean_png(data):
    """Remove ancillary PNG metadata before Pillow parses compressed text/ICC."""
    pos, chunks, header, end = 8, [PNG_SIGNATURE], False, False
    while pos < len(data):
        if pos + 12 > len(data):
            _fail("VRM PNG 纹理不完整。")
        length = struct.unpack_from(">I", data, pos)[0]
        last = pos + 12 + length
        if last > len(data):
            _fail("VRM PNG 纹理数据越界。")
        kind, payload = data[pos + 4:pos + 8], data[pos + 8:last - 4]
        if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack_from(">I", data, last - 4)[0]:
            _fail("VRM PNG 纹理 CRC 校验失败。")
        if not header:
            if kind != b"IHDR" or length != 13:
                _fail("VRM PNG 图片头不正确。")
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (1 <= width <= MAX_TEXTURE_EDGE and 1 <= height <= MAX_TEXTURE_EDGE):
                _fail("VRM 纹理边长不得超过 4096。", 413)
            if depth == 16:
                _fail("VRM PNG 纹理目前只支持 8bit。")
            header = True
        elif kind == b"IHDR":
            _fail("VRM PNG 有重复图片头。")
        if kind in {b"acTL", b"fcTL", b"fdAT"}:
            _fail("VRM 不支持动画纹理。")
        if kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"} and not kind[0] & 32:
            _fail("VRM PNG 有未知必要数据块。")
        if kind in {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}:
            chunks.append(data[pos:last])
        if kind == b"IEND":
            if length or last != len(data):
                _fail("VRM PNG 结束数据不正确。")
            end = True
        pos = last
    if not header or not end:
        _fail("VRM PNG 纹理不完整。")
    return b"".join(chunks)


def _thumbnail():
    from PIL import Image, ImageDraw
    with Image.new("RGBA", (128, 128), (35, 40, 62, 255)) as image:
        draw = ImageDraw.Draw(image)
        draw.ellipse((46, 20, 82, 56), fill=(173, 181, 220, 255))
        draw.rounded_rectangle((28, 64, 100, 112), radius=22, fill=(173, 181, 220, 255))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


def import_vrm(store, data: bytes, filename: str | None = None, *, cancel_event: threading.Event | None = None):
    if filename is not None and (not isinstance(filename, str) or not 1 <= len(filename) <= 255 or not filename.lower().endswith(".vrm") or any(c in filename for c in "/\\:") or any(ord(c) < 32 for c in filename)):
        _fail("请选择有效的 .vrm 文件名。")
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            _fail("素材导入已取消。", 409)
    check_cancel()
    with store._lock:
        staging = None
        try:
            doc, binary = _container(data)
            validator = _Validator(doc, binary, check_cancel)
            encoded = validator.run()
            thumbnail = _thumbnail()
            check_cancel()
            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=store.root))
            asset_id = str(uuid4())
            target = store.root / asset_id
            if target.exists() or target.is_symlink():
                _fail("素材标识冲突，请重试。", 409)
            manifest = {"id": asset_id, "schema_version": 1, "format": "vrm", "vrm_version": validator.version,
                        "created_at": datetime.now(timezone.utc).isoformat(), "states": {},
                        "metadata": validator.metadata, "model": {"resource": "model.vrm", "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(), "mime": "model/gltf-binary"},
                        "thumbnail": _description("thumbnail.png", thumbnail, 128, 128),
                        "total_bytes": len(encoded) + len(thumbnail),
                        "capabilities": {"model_3d": True, "static": False, "talk": any(x in validator.expressions for x in ("aa", "ih", "ou", "ee", "oh")), "blink": "blink" in validator.expressions, "expressions": validator.expressions},
                        "budgets": {"texture_pixels": validator.texture_pixels, "decoded_texture_bytes": validator.decoded_bytes,
                                    "geometry_bytes": validator.geometry_bytes, "accessor_bytes": validator.accessor_bytes,
                                    "vertices": validator.vertices, "primitives": validator.primitive_count,
                                    "instanced_vertices": validator.instanced_vertices, "instanced_primitives": validator.instanced_primitives,
                                    "images": len(validator.images)}}
            (staging / "model.vrm").write_bytes(encoded)
            (staging / "thumbnail.png").write_bytes(thumbnail)
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            check_cancel()
            staging.rename(target)
            return manifest
        except AssetError:
            raise
        except MemoryError:
            _fail("VRM 导入内存不足，请缩小模型。", 503)
        except OSError:
            _fail("VRM 保存失败，请检查磁盘空间后重试。", 503)
        except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, RecursionError):
            _fail("VRM 数据结构不正确或引用越界。")
        finally:
            if staging is not None and staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    _fail("VRM 临时素材清理失败，请检查磁盘。", 503)


def manifest_resources(manifest):
    if manifest.get("vrm_version") not in {"0", "1"} or manifest.get("states") != {}:
        raise ValueError("invalid VRM manifest")
    return [("model.vrm", manifest["model"], MAX_VRM_BYTES), ("thumbnail.png", manifest["thumbnail"], 4 * 1024 * 1024)]
