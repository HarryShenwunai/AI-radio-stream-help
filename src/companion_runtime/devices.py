"""User-declared hardware availability; never grants or starts device capture."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import secrets
import stat
import threading

from companion_runtime.http_payload import JsonValue


class DevicePreferencesError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DevicePreferences:
    display: bool = True
    camera: bool = True
    microphone: bool = True

    def public(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for name in ('display', 'camera', 'microphone'):
            item: dict[str, JsonValue] = {
                'declared_available': getattr(self, name),
                'detection': 'not_checked',
                'permission': 'not_requested',
            }
            if name == 'display':
                item['purpose'] = 'optional_5inch_avatar_display'
            result[name] = item
        return result


class DevicePreferencesStore:
    """Small global preference file, separate from all character databases.

    Existing malformed storage fails closed: it must not re-enable a previously
    disabled camera by silently treating corrupt data as a first launch. The
    supplied root must be under a trusted application-data directory. Ancestor
    checks do not protect against a malicious concurrent parent-directory owner.
    POSIX modes are private; Windows confidentiality relies on AppData ACLs.
    """

    MAX_BYTES = 1024

    def __init__(self, root_path: str | Path) -> None:
        self.root_path = Path(root_path).absolute()
        self.path = self.root_path / 'device-preferences.json'
        self._lock = threading.RLock()

    @staticmethod
    def _unsafe(info: os.stat_result) -> bool:
        return (stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, 'st_file_attributes', 0)
            & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)))

    def _directory(self) -> None:
        for path in reversed((self.root_path, *self.root_path.parents)):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if self._unsafe(info) or not stat.S_ISDIR(info.st_mode):
                raise DevicePreferencesError('unsafe_device_storage')
        self.root_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        for path in (self.root_path, *self.root_path.parents):
            info = path.lstat()
            if self._unsafe(info) or not stat.S_ISDIR(info.st_mode):
                raise DevicePreferencesError('unsafe_device_storage')
        if os.name == 'posix':
            os.chmod(self.root_path, 0o700)

    @staticmethod
    def _validate(payload: object, old: DevicePreferences) -> DevicePreferences:
        if not isinstance(payload, dict) or set(payload) - {'display', 'camera', 'microphone'}:
            raise DevicePreferencesError('invalid_device_preferences')
        display = payload.get('display', old.display)
        camera = payload.get('camera', old.camera)
        microphone = payload.get('microphone', old.microphone)
        if type(display) is not bool or type(camera) is not bool or type(microphone) is not bool:
            raise DevicePreferencesError('invalid_device_preferences')
        return DevicePreferences(display, camera, microphone)

    def _read(self) -> DevicePreferences:
        self._directory()
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return DevicePreferences()
        if self._unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_size > self.MAX_BYTES:
            raise DevicePreferencesError('invalid_saved_device_preferences')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(self.path, flags), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (self._unsafe(opened) or not stat.S_ISREG(opened.st_mode)
                    or opened.st_size > self.MAX_BYTES
                    or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise DevicePreferencesError('invalid_saved_device_preferences')
            raw = stream.read(self.MAX_BYTES + 1)
        if len(raw) > self.MAX_BYTES:
            raise DevicePreferencesError('invalid_saved_device_preferences')
        # Duplicate keys are refused rather than accepting conflicting switches.
        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise DevicePreferencesError('invalid_saved_device_preferences')
                result[key] = value
            return result
        value: object = json.loads(raw, object_pairs_hook=pairs)
        if not isinstance(value, dict) or set(value) != {'display', 'camera', 'microphone'}:
            raise DevicePreferencesError('invalid_saved_device_preferences')
        return self._validate(value, DevicePreferences())

    def load(self) -> DevicePreferences:
        with self._lock:
            try:
                return self._read()
            except DevicePreferencesError:
                raise
            except Exception:
                raise DevicePreferencesError('invalid_saved_device_preferences') from None

    def snapshot(self) -> dict[str, JsonValue]:
        return self.load().public()

    def save(self, payload: object) -> DevicePreferences:
        with self._lock:
            temporary: Path | None = None
            try:
                value = self._validate(payload, self.load())
                raw = json.dumps(asdict(value), allow_nan=False, sort_keys=True).encode('utf-8')
                self._directory()
                self._read()  # Recheck target before atomic replacement.
                temporary = self.root_path / ('.devices-' + secrets.token_hex(16) + '.tmp')
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                with os.fdopen(os.open(temporary, flags, 0o600), 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                if os.name == 'posix':
                    os.chmod(self.path, 0o600)
                    descriptor = os.open(self.root_path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                return value
            except DevicePreferencesError:
                raise
            except Exception:
                raise DevicePreferencesError('device_preferences_write_failed') from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
