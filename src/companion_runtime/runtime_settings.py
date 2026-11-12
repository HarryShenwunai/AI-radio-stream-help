"""Validated owner runtime preferences, shared by all local characters."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

DEFAULTS = {
    'local_compute': 'cpu', 'local_gpu_layers': 20, 'local_context': 4096,
    'voice_backend': 'kokoro', 'tts_endpoint': 'http://127.0.0.1:9880/tts',
    'tts_text_lang': 'zh', 'tts_prompt_lang': 'zh', 'tts_prompt_text': '',
    'tts_reference_audio': '', 'asr_device': 'cpu', 'asr_compute_type': 'int8',
}


def validate(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('运行配置字段不正确。')
    result = {**DEFAULTS, **value}
    choices = {'local_compute': {'cpu', 'cuda', 'auto'},
               'voice_backend': {'kokoro', 'external', 'system'},
               'local_context': {2048, 4096}, 'asr_device': {'cpu', 'cuda'},
               'asr_compute_type': {'int8', 'float16', 'float32', 'int8_float16'},
               'tts_text_lang': {'zh', 'en', 'ja', 'ko', 'yue', 'auto'},
               'tts_prompt_lang': {'zh', 'en', 'ja', 'ko', 'yue', 'auto'}}
    for key, allowed in choices.items():
        item = result[key]
        if isinstance(item, bool) or not isinstance(item, (str, int)) or item not in allowed:
            raise ValueError('运行配置选项不正确：' + key)
    layers = result['local_gpu_layers']
    allowed_asr = {'cpu': {'int8', 'float32'}, 'cuda': {'float16', 'int8_float16', 'float32'}}
    if result['asr_compute_type'] not in allowed_asr[result['asr_device']]:
        raise ValueError('本地识别设备与计算精度组合不受支持。')
    if isinstance(layers, bool) or not isinstance(layers, int) or not 0 <= layers <= 64:
        raise ValueError('显卡卸载层数需在0–64之间。')
    for key, maximum in [('tts_endpoint', 500), ('tts_prompt_text', 1000), ('tts_reference_audio', 1000)]:
        item = result[key]
        if not isinstance(item, str) or len(item) > maximum or any(ord(c) < 32 for c in item):
            raise ValueError('语音配置格式不正确：' + key)
    parsed = urlsplit(result['tts_endpoint'])
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'})):
        raise ValueError('语音地址需使用本机HTTP或明确的HTTPS服务，不能包含凭证或查询参数。')
    if parsed.hostname in {'169.254.169.254', 'metadata.google.internal', '0.0.0.0'}:
        raise ValueError('这个地址不能作为语音服务。')
    return result


def read(root):
    path = Path(root) / 'runtime.json'
    if not path.exists():
        return dict(DEFAULTS)
    if path.is_symlink() or path.stat().st_size > 16000:
        raise ValueError('本机运行配置不可用，请保留原文件并重新配置。')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def write(root, value):
    value = validate(value)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'runtime.json'
    if target.is_symlink():
        raise ValueError('本机运行配置不能使用符号链接。')
    temporary = root / ('.runtime-' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return value
