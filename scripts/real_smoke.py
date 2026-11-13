"""Opt-in real local model/TTS smoke check on synthetic input, not quality acceptance.

Uses COMPANION_MODELS and COMPANION_VOICES when set. Never downloads assets or
connects a platform account. Requires the optional local inference dependencies.
"""
from pathlib import Path
import datetime as dt
import importlib.util
import io
import json
import platform
import resource
import tempfile
import threading
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('smoke_app', ROOT / 'app/server.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
report = {'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
          'kind': 'single real local model and Kokoro observation on synthetic input',
          'platform': platform.system(), 'version': app.VERSION,
          'human_quality_accepted': False, 'upstream_or_platform_test': False}
try:
    with tempfile.TemporaryDirectory(prefix='companion-real-smoke-') as data:
        app.DATA = Path(data)
        app.init()
        app.set_settings({'memory_mode': 'off', 'voice': True, 'conversation_mode': 'listen'})
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        first = []
        result = app.chat({'text': '我今天有点累，陪我聊一句，不要提问。', 'request_id': request_id},
                          on_delta=lambda token: first.append(time.monotonic() - started) if not first else None)
        report.update({'first_text_seconds': round(first[0], 3),
                       'reply_seconds': round(time.monotonic() - started, 3),
                       'reply': result['message']['text'], 'generation_id': result['generation_id']})
        speech = {'text': result['message']['text'][:700], 'generation_id': result['generation_id'],
                  'request_id': request_id}
        started = time.monotonic()
        audio = app.speech_for_payload(speech)
        report['tts_seconds'] = round(time.monotonic() - started, 3)
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            report.update({'audio_seconds': round(wav.getnframes() / wav.getframerate(), 3),
                           'sample_rate': wav.getframerate(), 'audio_bytes': len(audio)})
        assert app.cancel_chat({'request_id': request_id, 'generation_id': result['generation_id']})['stopping']
        try:
            app.speech_for_payload(speech)
            raise AssertionError('cancelled audio was accepted')
        except app.AppError as error:
            assert error.status == 409
        report['completed_generation_late_speech_rejected'] = True
        ready = threading.Event()
        stopped = []
        rid = str(uuid.uuid4())
        def generate():
            stopped.append(app.chat({'text': '用几句话聊聊音乐。', 'request_id': rid},
                                    on_delta=lambda token: ready.set()))
        worker = threading.Thread(target=generate)
        worker.start()
        assert ready.wait(90), 'real model did not produce a token'
        started = time.monotonic()
        app.cancel_chat({'request_id': rid})
        worker.join(30)
        assert not worker.is_alive() and stopped[0]['cancelled']
        report['cooperative_cancel_seconds'] = round(time.monotonic() - started, 3)
        with app.db() as connection:
            assert connection.execute("SELECT count(*) FROM messages WHERE request_id=? AND role='assistant'", (rid,)).fetchone()[0] == 0
        report['cancelled_reply_not_saved'] = True
        report['max_rss_kib_linux'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['passed'] = True
except Exception as error:
    report.update({'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
finally:
    (ROOT / 'review/phase1-real-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
if not report['passed']:
    raise SystemExit(1)
