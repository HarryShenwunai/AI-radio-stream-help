"""Optional local ASR and an owner-configured GPT-SoVITS HTTP provider.

No model downloads occur during transcription. Audio stays in memory; no input
recording, transcript or provider credential is logged by this module.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import http.client
import importlib.metadata
import importlib.util
import io
import ipaddress
import json
import math
from pathlib import Path
import struct
import threading
import time
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request
import wave


class VoiceError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'voice_error'):
        super().__init__(message)
        self.status, self.code = status, code


class VoiceCancelled(VoiceError):
    def __init__(self):
        super().__init__('声音操作已停止，结果不会继续使用。', 409, 'cancelled')


def _cancelled(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise VoiceCancelled()


@dataclass(frozen=True)
class AudioLimits:
    max_bytes: int = 6_000_000
    max_seconds: float = 60
    min_seconds: float = 0.1
    sample_rates: tuple[int, ...] = (8000, 16000, 22050, 24000, 32000, 44100, 48000)
    channels: tuple[int, ...] = (1,)

    def __post_init__(self):
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or self.max_bytes < 44:
            raise ValueError('invalid audio byte limit')
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (self.max_seconds, self.min_seconds)):
            raise ValueError('invalid audio duration limit')
        if not 0 <= self.min_seconds <= self.max_seconds <= 600:
            raise ValueError('invalid audio duration range')
        if not self.sample_rates or any(type(v) is not int or not 8000 <= v <= 96000 for v in self.sample_rates):
            raise ValueError('invalid audio sample rates')
        if not self.channels or any(type(v) is not int or v not in (1, 2) for v in self.channels):
            raise ValueError('invalid audio channels')


@dataclass(frozen=True)
class WavInfo:
    duration_seconds: float
    sample_rate: int
    channels: int
    frames: int
    pcm_bytes: int


def validate_wav(data: bytes, limits: AudioLimits | None = None) -> WavInfo:
    """Accept complete RIFF PCM16 WAV only, never disguised WebM/MP3/float WAV."""
    limits = limits or AudioLimits()
    if not isinstance(data, bytes):
        raise VoiceError('录音需要完整的 WAV 字节。', 400, 'invalid_audio')
    if len(data) > limits.max_bytes:
        raise VoiceError('录音文件过大，请缩短后重试。', 413, 'audio_too_large')
    if len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise VoiceError('仅支持 PCM16 WAV 录音。', 415, 'unsupported_audio')
    if struct.unpack_from('<I', data, 4)[0] + 8 != len(data):
        raise VoiceError('WAV 长度不完整或含额外数据。', 400, 'invalid_audio')
    # Validate every RIFF chunk instead of trusting the first data chunk alone.
    offset, fmt_count, data_count, audio_length = 12, 0, 0, 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise VoiceError('WAV 区块不完整。', 400, 'invalid_audio')
        tag, size = data[offset:offset + 4], struct.unpack_from('<I', data, offset + 4)[0]
        start, end = offset + 8, offset + 8 + size
        if end > len(data):
            raise VoiceError('WAV 音频数据被截断。', 400, 'invalid_audio')
        if tag == b'fmt ':
            fmt_count += 1
            if size < 16 or struct.unpack_from('<H', data, start)[0] != 1:
                raise VoiceError('仅支持无压缩 PCM16 WAV。', 415, 'unsupported_audio')
            _, fmt_channels, fmt_rate, byte_rate, alignment, bits = struct.unpack_from('<HHIIHH', data, start)
            if bits != 16 or alignment != fmt_channels * 2 or byte_rate != fmt_rate * alignment:
                raise VoiceError('WAV 采样格式或帧对齐无效。', 415, 'unsupported_audio')
        elif tag == b'data':
            data_count += 1
            audio_length = size
        offset = end + (size & 1)
        if offset > len(data):
            raise VoiceError('WAV 对齐字节缺失。', 400, 'invalid_audio')
    if fmt_count != 1 or data_count != 1:
        raise VoiceError('WAV 必须包含单个音频轨。', 400, 'invalid_audio')
    try:
        with wave.open(io.BytesIO(data), 'rb') as wav:
            rate, channels, width, frames = wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
            if width != 2 or wav.getcomptype() != 'NONE' or rate not in limits.sample_rates or channels not in limits.channels:
                raise VoiceError('录音需为支持采样率的单声道 PCM16 WAV。', 415, 'unsupported_audio')
            expected = frames * channels * width
            if audio_length != expected or len(wav.readframes(frames)) != expected:
                raise VoiceError('WAV 音频帧不完整。', 400, 'invalid_audio')
            duration = frames / rate
            if not limits.min_seconds <= duration <= limits.max_seconds:
                raise VoiceError(f'录音时长需在 {limits.min_seconds:g}–{limits.max_seconds:g} 秒内。', 413, 'audio_duration')
            return WavInfo(duration, rate, channels, frames, expected)
    except VoiceError:
        raise
    except (wave.Error, EOFError, ValueError, struct.error):
        raise VoiceError('无法读取这段 WAV 录音。', 400, 'invalid_audio') from None


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcription:
    text: str
    segments: tuple[TranscriptSegment, ...]
    duration_seconds: float
    language: str
    elapsed_seconds: float
    backend: str = 'faster-whisper'
    device: str = 'cpu'


class LocalASR:
    """One lazy local model with bounded single-flight inference.

    Cancellation rejects results before/after model work and each segment. It
    cannot forcibly terminate a native inference call already in progress.
    """
    def __init__(self, model_dir: str | Path, *, device: str = 'cpu', compute_type: str | None = None,
                 cpu_threads: int = 4, limits: AudioLimits | None = None, model_factory: Callable | None = None):
        if device not in ('cpu', 'cuda'):
            raise ValueError('ASR device must be cpu or cuda')
        compute_type = compute_type or ('int8' if device == 'cpu' else 'float16')
        allowed = ('int8', 'float32') if device == 'cpu' else ('float16', 'int8_float16', 'float32')
        if compute_type not in allowed or type(cpu_threads) is not int or not 1 <= cpu_threads <= 32:
            raise ValueError('invalid ASR compute configuration')
        self.model_dir, self.device, self.compute_type = Path(model_dir), device, compute_type
        self.cpu_threads, self.limits = cpu_threads, limits or AudioLimits()
        self._model_factory, self._model = model_factory, None
        self._lock = threading.Lock()

    def diagnostics(self) -> dict:
        dependency = self._model_factory is not None or importlib.util.find_spec('faster_whisper') is not None
        files_present = all((self.model_dir / name).is_file() for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'))
        result = {'backend': 'faster-whisper', 'dependency_installed': dependency,
                  'model_present': files_present, 'ready': dependency and files_present,
                  'loaded': self._model is not None, 'device': self.device, 'compute_type': self.compute_type,
                  'cpu_threads': self.cpu_threads, 'local_only': True, 'recording_uploaded_to_cloud': False,
                  'max_audio_seconds': self.limits.max_seconds, 'max_audio_bytes': self.limits.max_bytes,
                  'ready_meaning': 'dependencies and model files present; loaded indicates actual model creation'}
        incompatible_av = False
        if self._model_factory is None:
            for package in ('faster-whisper', 'ctranslate2', 'av'):
                try:
                    version = importlib.metadata.version(package)
                    result.setdefault('versions', {})[package] = version
                    if package == 'av' and int(version.split('.')[0]) >= 19:
                        incompatible_av = True
                except (importlib.metadata.PackageNotFoundError, ValueError):
                    pass
        if not dependency:
            result['reason'] = '尚未安装本地识别组件。请安装 app/requirements-asr.txt。'
        elif incompatible_av:
            result.update(ready=False, reason='当前 PyAV 与识别器不兼容，请按 requirements-asr.txt 固定版本重新安装。')
        elif not files_present:
            result['reason'] = '未找到完整本地识别模型，请先显式下载模型或配置模型目录。'
        elif self.device == 'cuda':
            try:
                import ctranslate2
                count = ctranslate2.get_cuda_device_count()
                result['cuda_devices'] = count
                if not count:
                    result.update(ready=False, reason='未发现可用 CUDA 设备；请检查驱动与 CUDA/cuDNN，或选用 CPU。')
            except Exception:
                result.update(ready=False, reason='CUDA 识别运行库未就绪，请检查 CUDA 12/cuDNN 9 或使用 CPU。')
        return result

    def _load(self):
        if self._model is not None:
            return self._model
        status = self.diagnostics()
        if not status['ready']:
            raise VoiceError(status['reason'], 503, 'asr_unavailable')
        try:
            if self._model_factory is None:
                # Silero VAD uses ONNX Runtime too; keep its telemetry policy
                # aligned with the application's local Kokoro path.
                try:
                    import onnxruntime
                    onnxruntime.disable_telemetry_events()
                except ImportError:
                    pass
                from faster_whisper import WhisperModel
                factory = WhisperModel
            else:
                factory = self._model_factory
            self._model = factory(str(self.model_dir), device=self.device, compute_type=self.compute_type,
                                  cpu_threads=self.cpu_threads, num_workers=1, local_files_only=True)
            return self._model
        except Exception:
            raise VoiceError('本地识别模型加载失败，请检查文件版本、内存和运行库。', 503, 'asr_load_failed') from None

    def transcribe_wav(self, data: bytes, cancel: threading.Event | None = None) -> Transcription:
        _cancelled(cancel)
        info = validate_wav(data, self.limits)
        if not self._lock.acquire(False):
            raise VoiceError('上一段录音还在识别，请稍后重试。', 409, 'asr_busy')
        started, segments = time.monotonic(), []
        try:
            model = self._load()
            _cancelled(cancel)
            stream, metadata = model.transcribe(io.BytesIO(data), language='zh', beam_size=3,
                                                condition_on_previous_text=False, vad_filter=True,
                                                vad_parameters={'min_silence_duration_ms': 350},
                                                temperature=0, word_timestamps=False)
            try:
                for item in stream:
                    _cancelled(cancel)
                    text = str(item.text).strip()
                    start, end = float(item.start), float(item.end)
                    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start or end > info.duration_seconds + 1:
                        raise VoiceError('识别模型返回了无效时间戳。', 502, 'asr_invalid_result')
                    if len(segments) >= 600 or sum(len(s.text) for s in segments) + len(text) > 4000:
                        raise VoiceError('识别结果过长，请分段录音。', 413, 'transcript_too_long')
                    if text:
                        segments.append(TranscriptSegment(start, end, text))
            finally:
                if hasattr(stream, 'close'):
                    stream.close()
            _cancelled(cancel)
            text = ''.join(item.text for item in segments).strip()
            if not text:
                raise VoiceError('没有识别到清晰语音，可以重录或使用文字。', 422, 'no_speech')
            return Transcription(text, tuple(segments), info.duration_seconds,
                                 str(getattr(metadata, 'language', 'zh')), time.monotonic() - started,
                                 device=self.device)
        except VoiceError:
            raise
        except Exception:
            _cancelled(cancel)
            raise VoiceError('本地语音识别失败，请重录；录音不会发送到云端。', 503, 'asr_failed') from None
        finally:
            self._lock.release()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VoiceError('语音服务发生地址跳转，已停止请求。', 502, 'tts_redirect')


def validate_tts_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or len(endpoint) > 2000 or any(ord(c) < 32 for c in endpoint):
        raise VoiceError('语音服务地址格式不正确。', 400, 'invalid_tts_endpoint')
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        raise VoiceError('语音服务地址格式不正确。', 400, 'invalid_tts_endpoint') from None
    if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VoiceError('语音地址必须为无账号、查询参数或片段的 HTTP(S) 地址。', 400, 'invalid_tts_endpoint')
    try:
        address = ipaddress.ip_address(host)
        if address.is_unspecified or address.is_link_local or address.is_multicast:
            raise VoiceError('这个地址不能用作语音服务。', 400, 'invalid_tts_endpoint')
        loopback = address.is_loopback
    except ValueError:
        loopback = host.lower() == 'localhost'
        if host.lower() in ('metadata.google.internal', 'instance-data.ec2.internal'):
            raise VoiceError('这个地址不能用作语音服务。', 400, 'invalid_tts_endpoint')
    if parsed.scheme == 'http' and not loopback:
        raise VoiceError('远程语音服务需要 HTTPS；HTTP 仅允许本机。', 400, 'invalid_tts_endpoint')
    return endpoint.rstrip('/')


@dataclass(frozen=True)
class ExternalTTSConfig:
    endpoint: str
    ref_audio_path: str
    prompt_text: str = ''
    prompt_lang: str = 'zh'
    text_lang: str = 'zh'
    timeout_seconds: float = 30
    max_bytes: int = 20_000_000
    api_key: str = field(default='', repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'endpoint', validate_tts_endpoint(self.endpoint))
        for name in ('ref_audio_path', 'prompt_text', 'prompt_lang', 'text_lang', 'api_key'):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > (4000 if name in ('prompt_text', 'api_key') else 1024) or '\x00' in value:
                raise VoiceError('语音参考配置格式不正确。', 400, 'invalid_tts_config')
        if any(ord(char) < 32 for char in self.api_key):
            raise VoiceError('语音服务凭证含无效控制字符。', 400, 'invalid_tts_config')
        if not self.ref_audio_path.strip() or not self.prompt_lang.strip() or not self.text_lang.strip():
            raise VoiceError('请配置有权使用的参考音频路径与语言。', 400, 'invalid_tts_config')
        if type(self.max_bytes) is not int or not 44 <= self.max_bytes <= 40_000_000:
            raise ValueError('invalid TTS byte limit')
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 90:
            raise ValueError('invalid TTS timeout')


class ExternalTTS:
    """GPT-SoVITS api_v2 contract; config is supplied by the authenticated owner.

    This is not the Zerolan-specific GPT-SoVITS fork protocol. Model outputs can
    only supply reply text, never endpoint/reference paths or model switching.
    """
    def __init__(self, config: ExternalTTSConfig, *, opener=None):
        self.config = config
        self._opener = opener or urllib.request.build_opener(_NoRedirect())

    def synthesize(self, text: str, cancel: threading.Event | None = None) -> bytes:
        _cancelled(cancel)
        if not isinstance(text, str) or not 1 <= len(text) <= 700:
            raise VoiceError('朗读文字需在 700 字以内。', 400, 'invalid_tts_text')
        config = self.config
        body = {'text': text, 'text_lang': config.text_lang, 'ref_audio_path': config.ref_audio_path,
                'prompt_text': config.prompt_text, 'prompt_lang': config.prompt_lang,
                'media_type': 'wav', 'streaming_mode': False, 'batch_size': 1}
        headers = {'Content-Type': 'application/json', 'Accept': 'audio/wav'}
        if config.api_key:
            headers['Authorization'] = 'Bearer ' + config.api_key
        request = urllib.request.Request(config.endpoint, data=json.dumps(body, ensure_ascii=False).encode(),
                                         headers=headers, method='POST')
        started, chunks, total = time.monotonic(), [], 0
        try:
            with self._opener.open(request, timeout=config.timeout_seconds) as response:
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isdecimal() or int(length) > config.max_bytes):
                    raise VoiceError('语音服务返回文件过大或长度无效。', 502, 'tts_response_too_large')
                reader = getattr(response, 'read1', response.read)
                while True:
                    _cancelled(cancel)
                    if time.monotonic() - started > config.timeout_seconds:
                        raise VoiceError('语音服务超时。', 504, 'tts_timeout')
                    chunk = reader(min(65536, config.max_bytes - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > config.max_bytes:
                        raise VoiceError('语音服务返回文件过大。', 502, 'tts_response_too_large')
                    chunks.append(chunk)
                _cancelled(cancel)
                if length is not None and total != int(length):
                    raise VoiceError('语音服务返回文件不完整。', 502, 'tts_invalid_audio')
        except VoiceError:
            raise
        except urllib.error.HTTPError as error:
            raise VoiceError(f'语音服务返回 HTTP {error.code}。', 502, 'tts_http_error') from None
        except (TimeoutError, urllib.error.URLError, OSError, http.client.HTTPException):
            _cancelled(cancel)
            raise VoiceError('语音服务连接失败或超时，请检查已配置的地址。', 502, 'tts_connection_failed') from None
        audio = b''.join(chunks)
        try:
            validate_wav(audio, AudioLimits(max_bytes=config.max_bytes, max_seconds=180,
                                           sample_rates=(8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000),
                                           channels=(1, 2)))
        except VoiceError:
            raise VoiceError('语音服务未返回有效的 PCM16 WAV。', 502, 'tts_invalid_audio') from None
        _cancelled(cancel)
        return audio


ASR_MODELS = {
    'tiny': ('Systran/faster-whisper-tiny', 'd90ca5fe260221311c53c58e660288d3deb8d356'),
    'base': ('Systran/faster-whisper-base', None),
    'small': ('Systran/faster-whisper-small', None),
}


def download_asr_model(name: str, directory: str | Path) -> dict:
    """Explicit owner/CLI setup action; never called by transcribe_wav."""
    if name not in ASR_MODELS:
        raise VoiceError('可下载模型为 tiny、base 或 small。', 400, 'invalid_asr_model')
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError:
        raise VoiceError('请先安装 app/requirements-asr.txt。', 503, 'asr_unavailable') from None
    repo, pinned = ASR_MODELS[name]
    directory = Path(directory)
    existing = directory / 'source.json'
    if existing.is_file():
        try:
            prior = json.loads(existing.read_text())
            if prior.get('repo') != repo:
                raise VoiceError('目录已有另一识别模型，请为新模型选择不同目录。', 409, 'asr_model_directory')
            expected_names = {'config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'}
            if ({item['name'] for item in prior['files']} == expected_names
                    and (pinned is None or prior.get('revision') == pinned)
                    and all((directory / item['name']).is_file() and hashlib.sha256((directory / item['name']).read_bytes()).hexdigest() == item['sha256'] for item in prior['files'])):
                return prior
        except VoiceError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            pass
    files = ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt')
    try:
        info = HfApi().model_info(repo, revision=pinned, files_metadata=True)
        revision = info.sha
        snapshot_download(repo_id=repo, revision=revision, local_dir=str(directory), allow_patterns=list(files))
    except Exception:
        raise VoiceError('识别模型下载未完成。已下载内容保留，请检查网络后重试。', 503, 'asr_download_failed') from None
    records = []
    by_name = {item.rfilename: item for item in info.siblings}
    for filename in files:
        path = directory / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        upstream = by_name[filename]
        lfs = getattr(upstream, 'lfs', None)
        expected = getattr(lfs, 'sha256', None) if lfs is not None else None
        if expected is not None and digest != expected:
            raise VoiceError('本地识别模型 SHA256 校验失败。', 503, 'asr_model_hash')
        records.append({'name': filename, 'bytes': path.stat().st_size, 'sha256': digest})
    result = {'repo': repo, 'revision': revision, 'files': records, 'downloaded_by_explicit_action': True}
    (directory / 'source.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def _main():
    parser = argparse.ArgumentParser(description='Local ASR setup/diagnostic; never records the microphone')
    parser.add_argument('action', choices=('download', 'status', 'transcribe'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--model', choices=tuple(ASR_MODELS), default='tiny')
    parser.add_argument('--wav')
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args()
    try:
        if args.action == 'download':
            result = download_asr_model(args.model, args.directory)
        else:
            asr = LocalASR(args.directory, device=args.device)
            if args.action == 'status':
                result = asr.diagnostics()
            else:
                if not args.wav:
                    parser.error('--wav is required for transcribe')
                result = asdict(asr.transcribe_wav(Path(args.wav).read_bytes()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except VoiceError as error:
        print(json.dumps({'error': str(error), 'code': error.code, 'status': error.status}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    _main()
