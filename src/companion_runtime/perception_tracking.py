"""Optional local CPU face/head-direction estimation; never captures a camera.

No identity recognition, professional eye tracking or persistent face templates.
The host must obtain real OS capture permission and supply its authoritative scope.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import secrets
import stat
import threading
import tempfile
from typing import Any, Callable, Protocol
import urllib.request

from .perception import (PerceptionError, PerceptionLimits, PerceptionManager,
                         PerceptionScope, Record, _NoRedirect)

MEDIAPIPE_VERSION = '1.2.3'
FACE_MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
FACE_MODEL_BYTES = 3_758_596
# Observed from the fixed official object on 2026-11-12, NOT a Google-published SHA.
FACE_MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
_FONT_CACHE: tempfile.TemporaryDirectory[str] | None = None
_FONT_CACHE_LOCK = threading.Lock()


def _prepare_font_cache() -> None:
    # Never put generated caches in the locked addon or beside the model.
    # One private temp directory per process; contains font metadata, no frames.
    global _FONT_CACHE
    with _FONT_CACHE_LOCK:
        if not os.environ.get('MPLCONFIGDIR'):
            if _FONT_CACHE is None:
                _FONT_CACHE = tempfile.TemporaryDirectory(prefix='companion-face-font-cache-')
            os.environ['MPLCONFIGDIR'] = _FONT_CACHE.name


FACE_LIMITS = PerceptionLimits(max_frame_bytes=250_000, max_pixels=307_200, max_edge=640,
                             min_interval_seconds=0.2, max_frame_age_seconds=3,
                             max_result_age_seconds=5, session_ttl_seconds=900,
                             max_requests_per_session=8)


def _unsafe(info: os.stat_result) -> bool:
    return (stat.S_ISLNK(info.st_mode) or
            bool(getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)))


def _check_parents(path: Path) -> None:
    for entry in (path, *path.parents):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise PerceptionError('Unsafe face model storage', 400, 'unsafe_face_model_storage')


def read_face_model(path: Path | str) -> bytes:
    """Fixed-size, fixed-SHA, no-follow read; nothing is executed from the path."""
    path = Path(path).absolute()
    try:
        _check_parents(path.parent)
        info = path.lstat()
        if _unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_size != FACE_MODEL_BYTES:
            raise PerceptionError('Face model is invalid', 503, 'face_model_invalid')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (_unsafe(opened) or not stat.S_ISREG(opened.st_mode) or opened.st_size != FACE_MODEL_BYTES or
                    (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise PerceptionError('Face model is invalid', 503, 'face_model_invalid')
            value = stream.read(FACE_MODEL_BYTES + 1)
        if len(value) != FACE_MODEL_BYTES or hashlib.sha256(value).hexdigest() != FACE_MODEL_SHA256:
            raise PerceptionError('Face model is invalid', 503, 'face_model_invalid')
        return value
    except FileNotFoundError:
        raise PerceptionError('Local face model is not installed', 503, 'face_model_missing') from None
    except PerceptionError:
        raise
    except Exception:
        raise PerceptionError('Face model could not be read', 503, 'face_model_invalid') from None


class FaceModelStore:
    """Explicit owner-triggered small official model install, never a startup fetch."""
    def __init__(self, root_path: str | Path) -> None:
        self.root_path = Path(root_path).absolute()
        self.model_path = self.root_path / 'face_landmarker.task'
        self._lock = threading.RLock()

    def install_official(self, *, consent_confirmed: bool) -> Record:
        if consent_confirmed is not True:
            raise PerceptionError('Explicit model installation consent is required', 403, 'consent_required')
        with self._lock:
            temporary: Path | None = None
            try:
                _check_parents(self.root_path)
                self.root_path.mkdir(mode=0o700, parents=True, exist_ok=True)
                _check_parents(self.root_path)
                if os.name == 'posix':
                    os.chmod(self.root_path, 0o700)
                if self.model_path.exists() or self.model_path.is_symlink():
                    read_face_model(self.model_path)  # Refuse an unsafe/corrupt target; no implicit overwrite.
                    return self._receipt()
                request = urllib.request.Request(FACE_MODEL_URL, headers={'Accept': 'application/octet-stream'})
                with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
                    value = response.read(FACE_MODEL_BYTES + 1)
                if len(value) != FACE_MODEL_BYTES or hashlib.sha256(value).hexdigest() != FACE_MODEL_SHA256:
                    raise PerceptionError('Official face model checksum mismatch', 502, 'face_model_download_failed')
                temporary = self.root_path / ('.face-' + secrets.token_hex(16) + '.tmp')
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                with os.fdopen(os.open(temporary, flags, 0o600), 'wb') as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Recheck the destination after network I/O. Existing files require explicit repair.
                _check_parents(self.root_path)
                if self.model_path.exists() or self.model_path.is_symlink():
                    read_face_model(self.model_path)
                else:
                    os.replace(temporary, self.model_path)
                if os.name == 'posix':
                    os.chmod(self.model_path, 0o600)
                    fd = os.open(self.root_path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                return self._receipt()
            except PerceptionError:
                raise
            except Exception:
                raise PerceptionError('Official face model installation failed', 502, 'face_model_download_failed') from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    @staticmethod
    def _receipt() -> Record:
        return {'installed': True, 'model_sha256': FACE_MODEL_SHA256, 'model_bytes': FACE_MODEL_BYTES,
                'model_source': 'official_mediapipe_float16_v1', 'processing': 'local'}


class FaceEngine(Protocol):
    def status(self) -> Record: ...
    def initialize(self) -> None: ...
    def estimate(self, image: bytes, cancel: threading.Event) -> Record: ...
    def close(self) -> None: ...


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PerceptionError('Invalid local face estimator result', 502, 'face_tracking_failed')
    return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 5)


def project_face_result(result: Any) -> Record:
    """Project task results into bounded pose/expression values; no face identity."""
    faces = result.face_landmarks
    if not faces:
        return {'state': 'no_face', 'face_center_direction': None, 'head_pose_degrees': None, 'expressions': {}}
    if len(faces) != 1:
        return {'state': 'multiple_faces', 'face_center_direction': None, 'head_pose_degrees': None, 'expressions': {}}
    points = faces[0]
    if not 3 <= len(points) <= 500:
        raise PerceptionError('Invalid local face estimator result', 502, 'face_tracking_failed')
    xs = [_number(point.x) for point in points]
    ys = [_number(point.y) for point in points]
    center_x = (min(xs) + max(xs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    names = {'eyeBlinkLeft', 'eyeBlinkRight', 'jawOpen', 'mouthSmileLeft', 'mouthSmileRight',
             'eyeLookDownLeft', 'eyeLookDownRight', 'eyeLookUpLeft', 'eyeLookUpRight',
             'eyeLookInLeft', 'eyeLookInRight', 'eyeLookOutLeft', 'eyeLookOutRight'}
    scores = {item.category_name: _clamp(_number(item.score)) for item in result.face_blendshapes[0]
              if item.category_name in names} if result.face_blendshapes else {}
    expressions = {'blink_left': scores.get('eyeBlinkLeft', 0.0), 'blink_right': scores.get('eyeBlinkRight', 0.0),
                   'jaw_open': scores.get('jawOpen', 0.0),
                   'smile': round((scores.get('mouthSmileLeft', 0.0) + scores.get('mouthSmileRight', 0.0)) / 2, 5)}
    pose: Record | None = None
    matrices = result.facial_transformation_matrixes
    if len(matrices):
        matrix = matrices[0]
        if getattr(matrix, 'shape', None) != (4, 4):
            raise PerceptionError('Invalid local face estimator result', 502, 'face_tracking_failed')
        a = [[_number(float(matrix[row, col])) for col in range(3)] for row in range(3)]
        pose = {'pitch': round(math.degrees(math.atan2(a[2][1], a[2][2])), 3),
                'yaw': round(math.degrees(math.atan2(-a[2][0], math.hypot(a[0][0], a[1][0]))), 3),
                'roll': round(math.degrees(math.atan2(a[1][0], a[0][0])), 3),
                'convention': 'RzRyRx_camera_degrees_estimate'}
    return {'state': 'face', 'face_center_direction': {'x': _clamp((center_x - 0.5) * 2, -1, 1),
            'y': _clamp((0.5 - center_y) * 2, -1, 1)}, 'head_pose_degrees': pose, 'expressions': expressions,
            'eye_blendshape_estimates': {key: value for key, value in scores.items() if key.startswith('eyeLook')},
            'measurement': 'head_and_face_direction_estimate', 'identity_recognition': False}


class MediaPipeFaceEngine:
    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path).absolute()
        self._lock = threading.RLock()
        self._task: Any = None
        self._mp: Any = None
        self._numpy: Any = None
        self._model_bytes: bytes | None = None
        self._signature: tuple[int, int, int, int] | None = None
        self._initialization_error = False

    def status(self) -> Record:
        version: str | None = None
        reason = 'ready'
        try:
            version = importlib.metadata.version('mediapipe')
            if version != MEDIAPIPE_VERSION:
                reason = 'face_dependency_version_mismatch'
            elif importlib.util.find_spec('numpy') is None:
                reason = 'face_dependency_missing'
        except (importlib.metadata.PackageNotFoundError, ValueError):
            reason = 'face_dependency_missing'
        if reason == 'ready':
            try:
                info = self.model_path.lstat()
                signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if self._signature != signature:
                    self._model_bytes = read_face_model(self.model_path)
                    self._signature = signature
            except FileNotFoundError:
                reason = 'face_model_missing'
            except PerceptionError as error:
                reason = error.code
            except OSError:
                reason = 'face_model_invalid'
        if reason == 'ready' and self._initialization_error and self._task is None:
            reason = 'face_runtime_unavailable'
        return {'available': reason == 'ready', 'configured': reason == 'ready',
                'provider': 'mediapipe-face-landmarker', 'processing': 'local',
                'measurement': 'head_and_face_direction_estimate', 'reason': reason,
                'dependency_version': version, 'required_dependency_version': MEDIAPIPE_VERSION,
                'model_sha256': FACE_MODEL_SHA256 if reason == 'ready' else None,
                'model_bytes': FACE_MODEL_BYTES, 'algorithm_loaded': self._task is not None,
                'inference_verified': False, 'professional_eye_tracking': False}

    def initialize(self) -> None:
        with self._lock:
            if self._task is not None:
                return
            capability = self.status()
            if capability['available'] is not True and capability['reason'] != 'face_runtime_unavailable':
                raise PerceptionError('Local face tracking is unavailable', 503, 'face_tracking_unavailable')
            try:
                # Import only after explicit start. Respect an existing Matplotlib cache choice.
                _prepare_font_cache()
                mp = importlib.import_module('mediapipe')
                np = importlib.import_module('numpy')
                BaseOptions = importlib.import_module('mediapipe.tasks.python').BaseOptions
                vision = importlib.import_module('mediapipe.tasks.python.vision')
                FaceLandmarker, FaceLandmarkerOptions, RunningMode = (vision.FaceLandmarker,
                    vision.FaceLandmarkerOptions, vision.RunningMode)
                # Revalidate at actual initialization; status cache is never an execution trust decision.
                model = read_face_model(self.model_path)
                options = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=model,
                    delegate=BaseOptions.Delegate.CPU), running_mode=RunningMode.IMAGE, num_faces=2,
                    output_face_blendshapes=True, output_facial_transformation_matrixes=True)
                self._task = FaceLandmarker.create_from_options(options)
                self._mp, self._numpy = mp, np
                self._initialization_error = False
            except Exception:
                self._task = None
                self._initialization_error = True
                raise PerceptionError('Local face tracking could not initialize', 503, 'face_tracking_unavailable') from None

    def estimate(self, image: bytes, cancel: threading.Event) -> Record:
        if cancel.is_set():
            raise PerceptionError('Face tracking was stopped', 409, 'cancelled')
        with self._lock:
            self.initialize()
            try:
                from PIL import Image
                if not isinstance(image, bytes) or len(image) > FACE_LIMITS.max_frame_bytes:
                    raise PerceptionError('Face tracking frame exceeds the limit', 413, 'frame_too_large')
                with Image.open(io.BytesIO(image)) as source:
                    width, height = source.size
                    if (max(width, height) > FACE_LIMITS.max_edge or width * height > FACE_LIMITS.max_pixels
                            or getattr(source, 'n_frames', 1) != 1):
                        raise PerceptionError('Face tracking image dimensions exceed the limit', 413, 'frame_too_large')
                    pixels = self._numpy.ascontiguousarray(self._numpy.asarray(source.convert('RGB')))
                frame = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=pixels)
                result = project_face_result(self._task.detect(frame))
            except PerceptionError:
                raise
            except Exception:
                raise PerceptionError('Local face tracking failed', 502, 'face_tracking_failed') from None
        if cancel.is_set():
            raise PerceptionError('Face tracking was stopped', 409, 'cancelled')
        return result

    def close(self) -> None:
        with self._lock:
            if self._task is not None:
                self._task.close()
                self._task = None


class _FaceProvider:
    def __init__(self, engine: FaceEngine) -> None:
        self.engine = engine

    def status(self) -> Record:
        return self.engine.status()

    def describe(self, image: bytes, mime_type: str, prompt: str, cancel: threading.Event) -> str:
        return json.dumps(self.engine.estimate(image, cancel), allow_nan=False, separators=(',', ':'))


class FaceTrackingManager:
    """Separate local camera session; a VLM connection is never required."""
    def __init__(self, model_path: str | Path, *,
                 is_scope_current: Callable[[PerceptionScope], bool] | None = None,
                 engine: FaceEngine | None = None) -> None:
        self.engine = engine or MediaPipeFaceEngine(model_path)
        self._scope_check = is_scope_current or (lambda scope: True)
        self._manager = PerceptionManager(_FaceProvider(self.engine), limits=FACE_LIMITS,
                                           is_scope_current=self._scope_check)

    def status(self, owner_id: str) -> Record:
        result = self._manager.status(owner_id)
        result['tracking'] = result.pop('vision')
        result.pop('face_tracking', None)
        return result

    def start(self, scope: PerceptionScope, *, consent_confirmed: bool) -> Record:
        if consent_confirmed is not True:
            raise PerceptionError('Explicit camera consent is required', 403, 'consent_required')
        if not self._scope_check(scope):
            raise PerceptionError('Character context changed', 409, 'scope_changed')
        self.engine.initialize()
        return self._manager.start(scope, 'camera', consent_confirmed=True)

    def frame(self, scope: PerceptionScope, *, session_id: str, request_id: str, image_base64: str,
              mime_type: str, captured_at_ms: int) -> Record:
        result = self._manager.frame(scope, session_id=session_id, request_id=request_id,
            image_base64=image_base64, mime_type=mime_type, captured_at_ms=captured_at_ms)
        tracking = json.loads(str(result['description']))
        return {'session_id': session_id, 'request_id': request_id, 'tracking': tracking,
                'processing': 'local', 'retained': False}

    def stop(self, owner_id: str, session_id: str) -> Record:
        return self._manager.stop(owner_id, session_id)

    def stop_all(self, owner_id: str) -> None:
        self._manager.stop_all(owner_id)

    def close(self) -> None:
        self._manager.configure(None)
        self.engine.close()
