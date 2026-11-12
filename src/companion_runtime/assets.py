"""Bounded local PNG-state imports. No model/network/identity side effects.

Pillow is loaded lazily so the existing text-only application can still start
without optional image dependencies. These are initial application budgets,
not requirements imposed on artists by a file-format standard.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import threading
from typing import Any
from uuid import UUID, uuid4
import warnings
import weakref
import zlib

STATE_NAMES = ("idle", "talk", "blink", "talk_blink")
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_EDGE = 4096
MAX_TOTAL_PIXELS = 8_000_000
MAX_MANIFEST_BYTES = 32 * 1024
THUMBNAIL_EDGE = 256
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ROOT_LOCKS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
_ROOT_LOCKS_LOCK = threading.Lock()


class AssetError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _asset_id(value: str) -> str:
    if not isinstance(value, str):
        raise AssetError("角色素材不存在。", 404)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise AssetError("角色素材不存在。", 404) from None
    if parsed.version != 4 or str(parsed) != value:
        raise AssetError("角色素材不存在。", 404)
    return value


def _png_payload(data: bytes) -> tuple[bytes, int, int]:
    """Check all chunk CRCs; drop metadata before the image decoder sees it."""
    if not data.startswith(PNG_SIGNATURE):
        raise AssetError("请选择真正的静态 PNG 图片。")
    position = len(PNG_SIGNATURE)
    kept = [PNG_SIGNATURE]
    width = height = 0
    seen_header = seen_data = seen_end = False
    while position < len(data):
        if len(data) - position < 12:
            raise AssetError("PNG 文件不完整。")
        length = struct.unpack_from(">I", data, position)[0]
        end = position + length + 12
        if end > len(data):
            raise AssetError("PNG 文件不完整。")
        kind = data[position + 4:position + 8]
        payload = data[position + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if len(kind) != 4 or not all(65 <= x <= 90 or 97 <= x <= 122 for x in kind):
            raise AssetError("PNG 数据块格式不正确。")
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise AssetError("PNG 校验失败，请重新导出图片。")
        if not seen_header:
            if kind != b"IHDR" or length != 13:
                raise AssetError("PNG 图片头不正确。")
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (1 <= width <= MAX_EDGE and 1 <= height <= MAX_EDGE):
                raise AssetError(f"PNG 每条边需在 1–{MAX_EDGE} 像素内。", 413)
            if width * height > MAX_TOTAL_PIXELS:
                raise AssetError("PNG 解码像素超过当前素材预算。", 413)
            if depth == 16:
                raise AssetError("请将图片导出为 8bit PNG；当前不支持 16bit 图片。")
            if compression != 0 or filtering != 0 or interlace not in (0, 1):
                raise AssetError("不支持这种 PNG 编码。")
            seen_header = True
        elif kind == b"IHDR":
            raise AssetError("PNG 包含重复图片头。")
        if kind in (b"acTL", b"fcTL", b"fdAT"):
            raise AssetError("暂不支持动画 PNG，请按状态分别上传静态图片。")
        if kind == b"IDAT":
            seen_data = True
        if kind == b"IEND":
            if length != 0 or not seen_data or end != len(data):
                raise AssetError("PNG 结束数据不正确。")
            seen_end = True
        # A required unknown chunk is not safely decodable. Ancillary metadata
        # (including compressed text/ICC/EXIF) is not part of the imported role.
        if kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS") and not kind[0] & 32:
            raise AssetError("PNG 含不支持的必要数据块。")
        if kind in (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"):
            kept.append(data[position:end])
        position = end
        if seen_end:
            break
    if not seen_header or not seen_data or not seen_end:
        raise AssetError("PNG 文件不完整。")
    return b"".join(kept), width, height


def _normalise(data: bytes) -> tuple[bytes, Any, int, int]:
    cleaned, width, height = _png_payload(data)
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise AssetError("尚未安装图片解码组件 Pillow。", 503) from None
    normal = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(cleaned)) as probe:
                if probe.format != "PNG":
                    raise AssetError("请选择真正的 PNG 图片。")
                probe.verify()
            with Image.open(io.BytesIO(cleaned)) as image:
                image.load()
                if image.size != (width, height):
                    raise AssetError("PNG 尺寸校验失败。")
                # Image.new rather than retaining convert().info removes all
                # uploaded metadata from both the final image and thumbnail.
                normal = Image.new("RGBA", image.size)
                normal.paste(image.convert("RGBA"))
        stream = io.BytesIO()
        normal.save(stream, format="PNG", compress_level=6)
        result = stream.getvalue()
        if len(result) > MAX_FILE_BYTES:
            normal.close()
            raise AssetError("规范化后的 PNG 超过单张素材预算。", 413)
        return result, normal, width, height
    except AssetError:
        if normal is not None:
            normal.close()
        raise
    except MemoryError:
        if normal is not None:
            normal.close()
        raise AssetError("图片解码内存不足，请缩小素材后重试。", 503) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, struct.error,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        if normal is not None:
            normal.close()
        raise AssetError("PNG 无法完整解码，请重新导出图片。") from None


def _description(resource: str, data: bytes, width: int, height: int) -> dict[str, Any]:
    return {"resource": resource, "width": width, "height": height,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class AssetStore:
    def __init__(self, root: Path | str) -> None:
        folder = Path(root)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        if folder.is_symlink() or not folder.is_dir():
            raise AssetError("角色素材目录不可用。", 503)
        self.root = folder.resolve()
        with _ROOT_LOCKS_LOCK:
            key = str(self.root)
            lock = _ROOT_LOCKS.get(key)
            if lock is None:
                lock = threading.RLock()
                _ROOT_LOCKS[key] = lock
            self._lock = lock

    def _folder(self, asset_id: str) -> Path:
        folder = self.root / _asset_id(asset_id)
        if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != self.root:
            raise AssetError("角色素材不存在。", 404)
        return folder

    def import_vrm(self, data: bytes, filename: str | None = None, *,
                   cancel_event: threading.Event | None = None) -> dict[str, Any]:
        from .vrm_assets import import_vrm
        return import_vrm(self, data, filename, cancel_event=cancel_event)

    def import_live2d(self, data: bytes, filename: str | None = None, *,
                      cancel_event: threading.Event | None = None) -> dict[str, Any]:
        from .live2d_assets import import_live2d
        return import_live2d(self, data, filename, cancel_event=cancel_event)

    def import_png_states(self, states: dict[str, bytes],
                          filenames: dict[str, str] | None = None, *,
                          cancel_event: threading.Event | None = None) -> dict[str, Any]:
        if not isinstance(states, dict) or not states or "idle" not in states:
            raise AssetError("请先选择待机状态的 PNG 图片。")
        if any(not isinstance(k, str) or k not in STATE_NAMES for k in states):
            raise AssetError("图片状态只支持 idle、talk、blink、talk_blink。")
        if filenames is not None:
            if not isinstance(filenames, dict) or set(filenames) != set(states):
                raise AssetError("请为每个图片状态提供 PNG 文件名。")
            for name in filenames.values():
                if (not isinstance(name, str) or not 1 <= len(name) <= 255
                        or "/" in name or "\\" in name or any(ord(c) < 32 for c in name)
                        or not name.lower().endswith(".png")):
                    raise AssetError("请选择有效的 PNG 文件名。")
        def check_cancel() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise AssetError("素材导入已取消。", 409)
        check_cancel()
        total_input = 0
        for value in states.values():
            if not isinstance(value, bytes) or not value:
                raise AssetError("图片数据不能为空。")
            if len(value) > MAX_FILE_BYTES:
                raise AssetError("每张 PNG 不得超过 4 MiB。", 413)
            total_input += len(value)
        if total_input > MAX_TOTAL_BYTES:
            raise AssetError("本次图片合计不得超过 8 MiB。", 413)

        with self._lock:
            # Inspect every header before doing potentially expensive decoding.
            dimensions = {}
            for key, value in states.items():
                check_cancel()
                dimensions[key] = _png_payload(value)[1:]
            if len(set(dimensions.values())) != 1:
                raise AssetError("同一角色的状态图片需要使用相同画布尺寸。")
            total_pixels = sum(w * h for w, h in dimensions.values())
            if total_pixels > MAX_TOTAL_PIXELS:
                raise AssetError("全部状态图片合计不得超过 800 万像素。", 413)
            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.root))
            try:
                asset_id = str(uuid4())
                target = self.root / asset_id
                if target.exists() or target.is_symlink():
                    raise AssetError("素材标识冲突，请重试。", 409)
                manifest: dict[str, Any] = {
                    "id": asset_id, "schema_version": 1, "format": "png-states",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "width": dimensions["idle"][0], "height": dimensions["idle"][1],
                    "total_pixels": total_pixels, "states": {},
                    "capabilities": {"static": True, "talk": "talk" in states,
                                     "blink": "blink" in states,
                                     "talk_blink": "talk_blink" in states},
                }
                total_output = 0
                for state in STATE_NAMES:
                    if state not in states:
                        continue
                    check_cancel()
                    encoded, normal, width, height = _normalise(states[state])
                    try:
                        check_cancel()
                        total_output += len(encoded)
                        if total_output > MAX_TOTAL_BYTES:
                            raise AssetError("规范化后的图片合计超过 8 MiB。", 413)
                        resource = state + ".png"
                        (staging / resource).write_bytes(encoded)
                        manifest["states"][state] = _description(resource, encoded, width, height)
                        if state == "idle":
                            normal.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
                            buffer = io.BytesIO()
                            normal.save(buffer, format="PNG", compress_level=6)
                            thumb = buffer.getvalue()
                            (staging / "thumbnail.png").write_bytes(thumb)
                            manifest["thumbnail"] = _description("thumbnail.png", thumb, *normal.size)
                    finally:
                        normal.close()
                manifest["total_bytes"] = total_output + manifest["thumbnail"]["bytes"]
                if manifest["total_bytes"] > MAX_TOTAL_BYTES:
                    raise AssetError("规范化图片与缩略图合计超过 8 MiB。", 413)
                (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                # A published directory is complete. Imports never overwrite an
                # existing revision; activation belongs to the profile layer.
                check_cancel()
                staging.rename(target)
                return manifest
            except AssetError:
                raise
            except OSError:
                raise AssetError("素材保存失败，请检查磁盘空间后重试。", 503) from None
            finally:
                if staging.exists():
                    try:
                        shutil.rmtree(staging)
                    except OSError:
                        raise AssetError("导入未完成，临时素材清理失败，请重试或检查磁盘。", 503) from None

    def get(self, asset_id: str) -> dict[str, Any]:
        with self._lock:
            folder = self._folder(asset_id)
            path = folder / "manifest.json"
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
                raise AssetError("角色素材清单损坏。", 409)
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(manifest, dict) or manifest.get("id") != asset_id
                        or manifest.get("schema_version") != 1):
                    raise ValueError("invalid manifest")
                if manifest.get("format") == "vrm":
                    from .vrm_assets import manifest_resources
                    resources = manifest_resources(manifest)
                elif manifest.get("format") == "live2d":
                    from .live2d_assets import manifest_resources
                    resources = manifest_resources(manifest)
                elif (manifest.get("format") == "png-states"
                        and isinstance(manifest.get("states"), dict)
                        and "idle" in manifest["states"]
                        and set(manifest["states"]).issubset(STATE_NAMES)):
                    resources = [(state + ".png", value, MAX_FILE_BYTES) for state, value in manifest["states"].items()]
                    resources.append(("thumbnail.png", manifest["thumbnail"], MAX_FILE_BYTES))
                else:
                    raise ValueError("invalid manifest")
                for expected, value, maximum in resources:
                    if not isinstance(value, dict) or value.get("resource") != expected:
                        raise ValueError("invalid resource")
                    file = folder / expected
                    if (file.is_symlink() or not file.is_file() or file.resolve().parent != folder
                            or not isinstance(value.get("bytes"), int) or isinstance(value["bytes"], bool)
                            or file.stat().st_size != value["bytes"] or not 0 < value["bytes"] <= maximum):
                        raise ValueError("missing resource")
                return manifest
            except (OSError, ValueError, TypeError, KeyError, UnicodeError):
                raise AssetError("角色素材清单或图片损坏。", 409) from None

    def resolve(self, asset_id: str, resource: str) -> Path:
        if not isinstance(resource, str):
            raise AssetError("素材文件不存在。", 404)
        with self._lock:
            manifest = self.get(asset_id)
            resources = {v["resource"] for v in manifest["states"].values()}
            resources.add(manifest["thumbnail"]["resource"])
            if manifest.get("format") in {"vrm", "live2d"}:
                resources.add(manifest["model"]["resource"])
            if manifest.get("format") == "live2d":
                resources.update(manifest["resources"])
            if resource not in resources:
                raise AssetError("素材文件不存在。", 404)
            return self._folder(asset_id) / resource

    def list_assets(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []
            for folder in sorted(self.root.iterdir(), key=lambda item: item.name):
                if folder.name.startswith("."):
                    continue
                try:
                    result.append(self.get(folder.name))
                except AssetError:
                    # Partial/corrupt folders must not stop the library listing.
                    continue
            return result

    def delete(self, asset_id: str) -> dict[str, Any]:
        """Remove availability atomically; a failed cleanup is reported explicitly.

        The caller must first ensure no active/saved profile references this
        revision. This store deliberately does not own character identity.
        """
        with self._lock:
            folder = self._folder(asset_id)
            trash = self.root / (".trash-" + str(uuid4()))
            try:
                folder.rename(trash)
            except OSError:
                raise AssetError("素材删除失败，请重试。", 503) from None
            pending = False
            try:
                shutil.rmtree(trash)
            except OSError:
                pending = True
            return {"id": asset_id, "deleted": True, "cleanup_pending": pending}
