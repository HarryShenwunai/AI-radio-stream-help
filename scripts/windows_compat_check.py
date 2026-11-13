"""Exercise Windows PE Python/native wheels through Wine on a Linux host.

This is a compatibility check, never a Windows 10/11 hardware acceptance test.
Based on native_character_check.py so the synthetic API scenarios stay comparable.
Only isolated temporary user data is written. Existing model files are reused;
no downloads, external providers, accounts, or Electron sandbox changes occur.
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
import queue
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
parser.add_argument('--backend', type=Path, default=ROOT / '.build/windows-embedded-backend')
parser.add_argument('--wine-root', type=Path, default=Path('/workspace/.windows-tools/wine-root'))
parser.add_argument('--prefix', type=Path, default=Path('/workspace/.windows-tools/prefix'))
parser.add_argument('--xvfb', type=Path, default=Path('/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'))
parser.add_argument('--display', default=':179')
parser.add_argument('--report', type=Path, default=Path('/workspace/.windows-tools/windows-compat-check.json'))
parser.add_argument('--with-model', action='store_true')
args = parser.parse_args()
report = {'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'kind': 'Windows PE backend under Wine with synthetic data; NOT Windows hardware',
          'platform': platform.platform(), 'checks': {}, 'model_requested': args.with_model, 'human_quality_accepted': False}
process = None
xvfb = None
stderr_log = None
wine_env = None

def winpath(path):
    return 'Z:' + str(Path(path).resolve()).replace('/', '\\')

try:
    assert platform.system() == 'Linux', 'This Wine harness requires Linux'
    assert (args.backend / 'python/python.exe').is_file(), 'Windows Python is not ready'
    manifest = args.backend / 'embedded-runtime-manifest.json'
    if manifest.is_file():
        report['embedded_manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    report['wine_version'] = subprocess.check_output([str(args.wine_root / 'usr/lib/wine/wine64'), '--version'], text=True).strip()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    stderr_log = args.report.with_suffix('.stderr.log').open('w', encoding='utf-8')
    xvfb = subprocess.Popen([str(args.xvfb), args.display, '-screen', '0', '1024x768x24', '-nolisten', 'tcp'], stdout=stderr_log, stderr=stderr_log)
    time.sleep(0.8)
    assert xvfb.poll() is None, 'Private Xvfb failed to start'
    wine_env = {**os.environ, 'DISPLAY': args.display, 'WINEPREFIX': str(args.prefix.resolve()),
                'WINEARCH': 'win64', 'WINEDLLOVERRIDES': 'mscoree,mshtml=', 'WINEDEBUG': '-all',
                'WINEDLLPATH': str(args.wine_root / 'usr/lib/x86_64-linux-gnu/wine')}
    command = [str(args.wine_root / 'usr/lib/wine/wine64'), str(args.backend / 'python/python.exe')]
    probe_code = 'import sys,json,sqlite3,_sqlite3,PIL._imaging;print(json.dumps(dict(platform=sys.platform,python=sys.version,sqlite=sqlite3.sqlite_version,sqlite_native=_sqlite3.__file__,pillow_native=PIL._imaging.__file__)))'
    probe = subprocess.run(command + ['-c', probe_code], env=wine_env, text=True, capture_output=True, timeout=60)
    if probe.returncode:
        raise AssertionError('Windows native import probe failed: ' + probe.stderr[-4000:])
    probe_data = json.loads(probe.stdout.strip().splitlines()[-1])
    assert probe_data['platform'] == 'win32' and probe_data['sqlite_native'].endswith('.pyd') and probe_data['pillow_native'].endswith('.pyd')
    report['windows_runtime'] = probe_data
    report['checks']['windows_python_sqlite_pillow_native_imports'] = 'passed'

    with tempfile.TemporaryDirectory(prefix='native-characters-') as directory:
        env = {**wine_env, 'COMPANION_DATA': winpath(directory), 'COMPANION_MODELS': winpath('/workspace/companion/models'), 'COMPANION_VOICES': winpath('/workspace/companion/voices'), 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
        def start():
            proc = subprocess.Popen(command + ['-u', winpath(args.backend / 'app/server.py'), '--port', '0', '--no-browser'], env=env,
                                    stdout=subprocess.PIPE, stderr=stderr_log, text=True,
                                    encoding='utf-8', errors='replace')
            lines = queue.Queue()
            threading.Thread(target=lambda: lines.put(proc.stdout.readline().strip()), daemon=True).start()
            try:
                first = lines.get(timeout=60)
            except queue.Empty:
                proc.terminate(); proc.wait(timeout=10)
                raise AssertionError('Windows backend startup timed out; inspect stderr log')
            if 'http://127.0.0.1:' not in first:
                proc.terminate(); proc.wait(timeout=10)
                raise AssertionError('Windows backend did not start; inspect stderr log')
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
        report['checks']['windows_wine_png_preview_activate_and_revision_rollback'] = 'passed'
        post('chat', {'text': '记住：我的合成口令是蓝纸风筝', 'request_id': str(uuid.uuid4()), 'expected_character_id': aid})
        bid = post('characters/create', {'name': '合成测试乙'})['active_character_id']
        clean = get('state'); assert clean['active_character_id'] == bid and not clean['memories']
        assert '蓝纸风筝' not in json.dumps(clean['messages'], ensure_ascii=False)
        post('characters/select', {'id': aid})
        assert '蓝纸风筝' in get('state')['memories'][0]['text']
        report['checks']['windows_wine_identity_isolation_and_return'] = 'passed'
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
            report['checks']['real_local_llm_and_kokoro_in_windows_wine_backend'] = 'passed'
            post('chat/stop', {'request_id': rid, 'generation_id': finished['generation_id'], 'expected_character_id': aid})
            try:
                post('speech', speech, raw=True)
                raise AssertionError('cancelled generation speech accepted')
            except urllib.error.HTTPError as error: assert error.code == 409
            report['checks']['windows_wine_cancelled_generation_rejects_late_tts'] = 'passed'
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
            report['rss_not_measured_reason'] = 'No Windows RSS measurement; Wine host process RSS is not a Windows hardware benchmark.'
        process.terminate();process.wait(timeout=15)
        process, base = start();opener=client()
        restored = get('state')
        assert restored['active_character_id'] == aid and restored['active_character']['appearance_id'] == p1['id']
        assert '蓝纸风筝' in restored['memories'][0]['text']
        report['checks']['windows_wine_restart_preserves_character_assets_and_private_data'] = 'passed'
        report['passed'] = True
except Exception as error:
    report.update({'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
    if isinstance(error, urllib.error.HTTPError):
        report['http_error_body'] = error.read(4000).decode('utf-8', errors='replace')
    if stderr_log is not None:
        stderr_log.flush()
        log_tail = args.report.with_suffix('.stderr.log').read_text(encoding='utf-8', errors='replace')[-8000:]
        if 'unimplemented function' in log_tail:
            report['wine_compatibility_blocker'] = log_tail
            report['windows_hardware_conclusion'] = 'Not evaluated. Wine missing implementation cannot establish Windows 10/11 failure.'
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill();process.wait()
    if wine_env is not None:
        subprocess.run([str(args.wine_root / 'usr/lib/wine/wineserver64'), '-k'], env=wine_env, timeout=10, check=False)
    if xvfb is not None:
        xvfb.terminate(); xvfb.wait(timeout=10)
    if stderr_log is not None:
        stderr_log.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
if not report.get('passed'): raise SystemExit(1)
