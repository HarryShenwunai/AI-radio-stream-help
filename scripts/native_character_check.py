"""Exercise the compiled backend with isolated synthetic user data.

Pass --with-model to use existing local model/voice assets; no downloads or
external provider/account connections are made. Results are single observations.
"""
from pathlib import Path
import argparse
import base64
import datetime as dt
import hashlib
import http.cookiejar
import io
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--binary', default=str(ROOT / '.build/native/companion-backend' / ('companion-backend.exe' if os.name == 'nt' else 'companion-backend')))
parser.add_argument('--with-model', action='store_true')
args = parser.parse_args()
report = {'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'kind': 'compiled backend with synthetic data',
          'platform': platform.platform(), 'checks': {}, 'model_requested': args.with_model, 'human_quality_accepted': False}
process = None
try:
    with tempfile.TemporaryDirectory(prefix='native-characters-') as directory:
        env = {**os.environ, 'COMPANION_DATA': directory, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
        def start():
            proc = subprocess.Popen([args.binary, '--port', '0', '--no-browser'], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    encoding='utf-8', errors='replace')
            first = proc.stdout.readline().strip()
            if 'http://127.0.0.1:' not in first:
                proc.terminate(); proc.wait(timeout=10)
                raise AssertionError('compiled backend did not start')
            return proc, first[first.index('http://127.0.0.1:'):].strip()
        process, base = start()
        def client():
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            opener.open(base, timeout=10).close()
            return opener
        opener = client()
        def get(path):
            with opener.open(base + '/api/' + path, timeout=15) as response:
                return json.load(response)
        def post(path, data, raw=False, timeout=90):
            response = opener.open(urllib.request.Request(base + '/api/' + path, data=json.dumps(data).encode(),
                                    headers={'Content-Type': 'application/json', 'X-Companion': 'local-app'}), timeout=timeout)
            if raw:
                return response
            with response:
                return json.load(response)
        original = get('state');aid = original['active_character_id']
        assert original['version'] == '0.4.0-dev1'
        post('settings', {'voice': False, 'memory_mode': 'off', 'proactive': False, 'expected_character_id': aid})
        def png(color):
            out = io.BytesIO(); Image.new('RGBA', (80, 110), color).save(out, format='PNG')
            return {'filename': '任意中文文件名.png', 'data_base64': base64.b64encode(out.getvalue()).decode()}
        p1 = post('characters/assets/import', {'character_id': aid, 'states': {'idle': png((20,90,170,180))}})['asset']
        assert get('state')['active_character']['appearance_id'] is None
        post('characters/assets/activate', {'character_id': aid, 'asset_id': p1['id']})
        p2 = post('characters/assets/import', {'character_id': aid, 'states': {'idle': png((180,60,30,200)), 'talk': png((200,100,50,200))}})['asset']
        post('characters/assets/activate', {'character_id': aid, 'asset_id': p2['id']})
        post('characters/assets/activate', {'character_id': aid, 'asset_id': p1['id']})
        assert get('state')['active_character']['appearance_id'] == p1['id']
        report['checks']['compiled_png_preview_activate_and_revision_rollback'] = 'passed'
        post('chat', {'text': '记住：我的合成口令是蓝纸风筝', 'request_id': str(uuid.uuid4()), 'expected_character_id': aid})
        bid = post('characters/create', {'name': '合成测试乙'})['active_character_id']
        clean = get('state'); assert clean['active_character_id'] == bid and not clean['memories']
        assert '蓝纸风筝' not in json.dumps(clean['messages'], ensure_ascii=False)
        post('characters/select', {'id': aid})
        assert '蓝纸风筝' in get('state')['memories'][0]['text']
        report['checks']['compiled_identity_isolation_and_return'] = 'passed'
        if args.with_model:
            rid = str(uuid.uuid4()); started = time.monotonic(); first = None; finished = None
            with post('chat/stream', {'text': '我今天有点累，只想安静聊一句，不要提问。', 'request_id': rid, 'expected_character_id': aid}, raw=True) as stream:
                for line in stream:
                    if not line.startswith(b'data:'): continue
                    event = json.loads(line[5:])
                    if event['type'] == 'delta' and first is None: first = time.monotonic() - started
                    if event['type'] == 'error': raise AssertionError(event['error'])
                    if event['type'] == 'done': finished = event
            assert first is not None and finished and finished.get('message')
            report.update({'first_text_seconds': round(first, 3), 'reply_seconds': round(time.monotonic()-started, 3),
                           'synthetic_reply': finished['message']['text']})
            speech = {'text': finished['message']['text'][:700], 'generation_id': finished['generation_id'],
                      'request_id': rid, 'expected_character_id': aid}
            started = time.monotonic()
            with post('speech', speech, raw=True) as response: audio = response.read()
            report['tts_seconds'] = round(time.monotonic()-started, 3)
            with wave.open(io.BytesIO(audio), 'rb') as wav:
                report['audio_seconds'] = round(wav.getnframes()/wav.getframerate(), 3)
                report['sample_rate'] = wav.getframerate()
            report['checks']['real_local_llm_and_kokoro_in_compiled_backend'] = 'passed'
            post('chat/stop', {'request_id': rid, 'generation_id': finished['generation_id'], 'expected_character_id': aid})
            try:
                post('speech', speech, raw=True)
                raise AssertionError('cancelled generation speech accepted')
            except urllib.error.HTTPError as error: assert error.code == 409
            report['checks']['compiled_cancelled_generation_rejects_late_tts'] = 'passed'
            ready = threading.Event(); output = []; errors = []; rid2 = str(uuid.uuid4())
            def slow_reply():
                try:
                    with post('chat/stream', {'text': '请用八句话描述不同的音乐风格。', 'request_id': rid2, 'expected_character_id': aid}, raw=True) as stream:
                        for line in stream:
                            if line.startswith(b'data:'):
                                event = json.loads(line[5:]); output.append(event)
                                if event['type'] == 'delta': ready.set()
                except Exception as error: errors.append(type(error).__name__)
            worker = threading.Thread(target=slow_reply); worker.start(); assert ready.wait(90)
            started = time.monotonic(); post('chat/stop', {'request_id': rid2, 'expected_character_id': aid});worker.join(20)
            assert not worker.is_alive() and not errors and output[-1].get('cancelled')
            report['cancel_seconds'] = round(time.monotonic()-started, 3)
            assert not any(m['role']=='assistant' and m.get('request_id')==rid2 for m in get('state')['messages'])
            report['checks']['real_generation_cancellation_has_no_partial_commit'] = 'passed'
            status_path = Path(f'/proc/{process.pid}/status')
            report['peak_backend_rss_kib'] = None
            if platform.system() == 'Linux' and status_path.is_file():
                status = status_path.read_text(encoding='utf-8')
                report['peak_backend_rss_kib'] = next((int(line.split()[1]) for line in status.splitlines() if line.startswith('VmHWM:')), None)
            else:
                report['rss_not_measured_reason'] = 'Linux /proc VmHWM is unavailable on this platform; no Windows RSS claim.'
        process.terminate();process.wait(timeout=15)
        process, base = start();opener=client()
        restored = get('state')
        assert restored['active_character_id'] == aid and restored['active_character']['appearance_id'] == p1['id']
        assert '蓝纸风筝' in restored['memories'][0]['text']
        report['checks']['compiled_restart_preserves_character_assets_and_private_data'] = 'passed'
        report['passed'] = True
except Exception as error:
    report.update({'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill();process.wait()
    (ROOT/'review').mkdir(exist_ok=True)
    (ROOT/'review/character-native-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
if not report.get('passed'): raise SystemExit(1)
