"""Real Chromium/HTTP regression with local model and synthetic-WAV fixtures.

No microphone, external API, trained voice, live room or production data is used.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import io
import json
import math
import struct
import sys
import tempfile
import threading
import time
import traceback
import wave

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import test_stream_http as fixture

app = fixture.app
REPORT = ROOT / 'review/phase1-browser.json'
ARTIFACTS = Path('/workspace/dist')


def synthetic_wav():
    output = io.BytesIO()
    rate = 24000
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b''.join(struct.pack('<h', int(900 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate * 5)))
    return output.getvalue()


class ControlledSpeech:
    """Delay only the next synthesis; concurrent fresh calls remain responsive."""
    def __init__(self):
        self.wav = synthetic_wav()
        self.lock = threading.Lock()
        self.next_delay = None
        self.calls = 0

    def delay_next(self):
        gate = {'started': threading.Event(), 'release': threading.Event(), 'finished': threading.Event()}
        with self.lock:
            assert self.next_delay is None
            self.next_delay = gate
        return gate

    def __call__(self, text):
        with self.lock:
            self.calls += 1
            gate, self.next_delay = self.next_delay, None
        if gate is not None:
            gate['started'].set()
            if not gate['release'].wait(12):
                raise AssertionError('Test failed to release synthetic speech fixture')
            gate['finished'].set()
        return self.wav


class QuietHandler(app.Handler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            # Browser AbortController intentionally closes pending speech requests.
            pass


INIT_SCRIPT = r"""
window.__audioEvents=[];window.__speechCalls=[];
const originalPlay=HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play=function(){
 const generation=typeof voiceContext==='undefined'?null:voiceContext?.generation_id||null;
 window.__audioEvents.push({type:'play',src:this.src,generation,time:performance.now()});
 return originalPlay.apply(this,arguments);
};
const originalPause=HTMLMediaElement.prototype.pause;
HTMLMediaElement.prototype.pause=function(){
 window.__audioEvents.push({type:'pause',src:this.src,time:performance.now()});
 return originalPause.apply(this,arguments);
};
const originalFetch=window.fetch;
window.fetch=function(input,init){
 if(input==='/api/speech'){
  const record={payload:JSON.parse(init.body),aborted:false};window.__speechCalls.push(record);
  if(init.signal)init.signal.addEventListener('abort',()=>record.aborted=true);
 }
 return originalFetch.apply(this,arguments);
};
"""


def main():
    report = {
        'date': '2026-11-12',
        'version': app.VERSION,
        'status': 'RUNNING',
        'browser': 'Chromium /usr/bin/chromium, headless',
        'model': 'local mock streaming provider; no model quality evaluation',
        'audio': 'real 24kHz mono PCM WAV; 440Hz synthetic test tone; TTS replaced by controlled local fixture',
        'autoplay': 'test launch permits autoplay; default-browser autoplay restrictions are not validated',
        'new_integration_scope': 'local application, HTTP, browser media lifecycle only; no Zerolan/Bilibili/AR/MC runtime connection',
        'checks': {},
    }
    speech = ControlledSpeech()
    original_synthesize, original_state = app.synthesize, app.state
    app.synthesize = speech

    def state_with_fixture_voice():
        state = original_state()
        state['local_voice_available'] = True
        return state

    app.state = state_with_fixture_voice
    servers = []
    try:
        with tempfile.TemporaryDirectory(prefix='phase1-browser-') as data:
            app.DATA = Path(data)
            app.init()
            app.GENERATIONS = app.GenerationRegistry(max_entries=256, retention_seconds=600)
            provider = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Provider)
            server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
            servers = [provider, server]
            for instance in servers:
                threading.Thread(target=instance.serve_forever, daemon=True).start()
            app.set_settings({'engine': 'api', 'api_base': f'http://127.0.0.1:{provider.server_port}/v1', 'api_model': 'slow', 'voice': False, 'quiet_start': 0, 'quiet_end': 0})
            url = f'http://127.0.0.1:{server.server_port}'
            headers = {'X-Companion': 'local-app'}
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--autoplay-policy=no-user-gesture-required'])
                page = browser.new_page(viewport={'width': 1440, 'height': 960})
                page.add_init_script(INIT_SCRIPT)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url, wait_until='networkidle')
                page.locator('[data-mode=listen]').click()
                page.wait_for_function('()=>document.querySelector("[data-mode=listen]").getAttribute("aria-pressed")==="true"')
                page.locator('#memory-toggle').click()
                page.wait_for_function('()=>document.querySelector("#memory-toggle").textContent==="只聊当下"')
                page.reload(wait_until='networkidle')
                assert page.locator('[data-mode=listen]').get_attribute('aria-pressed') == 'true'
                assert page.locator('#memory-toggle').inner_text() == '只聊当下'
                report['checks']['modes_and_memory_preference_persist'] = 'passed'

                page.locator('#message-input').fill('只想随便聊聊')
                page.locator('#send').click()
                page.locator('[data-stream] .bubble').filter(has_text='慢慢回复').wait_for()
                assert page.locator('#send').is_disabled()
                page.locator('#stop-generation').click()
                page.wait_for_function('()=>!document.querySelector("#send").disabled')
                assert page.locator('[data-stream]').count() == 0
                assert page.locator('.message.user').count() == 1
                state = page.request.get(url + '/api/state').json()
                assert not state['model_busy']
                assert not any(m['kind'] == 'chat' and m['role'] == 'assistant' for m in state['messages'])
                report['checks']['http_tokens_stop_no_partial_commit'] = 'passed'

                page.request.post(url + '/api/settings', data={'api_model': 'normal'}, headers=headers)
                page.locator('#retry-answer').click()
                page.locator('.message.assistant .bubble').filter(has_text='接住你刚说的').wait_for()
                page.wait_for_function('()=>!document.querySelector("#send").disabled')
                assert page.locator('.message.user').count() == 1
                old = page.request.get(url + '/api/state').json()['messages'][-1]['id']
                page.locator('#retry-answer').click()
                page.wait_for_function('(old)=>app.messages.at(-1).id>old', arg=old)
                page.wait_for_function('()=>!document.querySelector("#send").disabled')
                assert page.locator('.message.user').count() == 1
                assert page.locator('.message.assistant').count() == 2
                report['checks']['retry_without_duplicates'] = 'passed'

                page.request.post(url + '/api/settings', data={'api_model': 'malformed'}, headers=headers)
                page.locator('#message-input').fill('测试连接错误')
                page.locator('#send').click()
                page.locator('#error').wait_for(state='visible')
                page.wait_for_function('()=>!document.querySelector("#send").disabled')
                assert page.locator('#retry-answer').is_visible()
                assert page.locator('.message.user').count() == 2
                page.request.post(url + '/api/settings', data={'api_model': 'normal'}, headers=headers)
                page.locator('#retry-answer').click()
                page.wait_for_function('()=>!document.querySelector("#send").disabled&&app.messages.at(-1).role==="assistant"')
                assert page.locator('#error').is_hidden()
                report['checks']['provider_failure_and_recovery'] = 'passed'

                page.route('**/api/chat/stream', lambda route: route.abort(), times=1)
                page.locator('#message-input').fill('网络失败不能丢掉这句')
                page.locator('#send').click()
                page.wait_for_function('()=>!document.querySelector("#send").disabled&&document.querySelector("#message-input").value==="网络失败不能丢掉这句"')
                page.locator('#send').click()
                page.wait_for_function('()=>!document.querySelector("#send").disabled&&app.messages.at(-1).text.includes("接住")')
                assert page.locator('.message.user').count() == 3
                report['checks']['network_failure_preserves_unsent_draft'] = 'passed'

                page.locator('[data-view=memory]').click()
                page.locator('#memory-input').fill('<img src=x onerror=alert(1)>')
                page.locator('#memory-form button').click()
                page.locator('#memory-list').filter(has_text='<img src=x').wait_for()
                assert page.locator('#memory-list img').count() == 0
                report['checks']['xss_text_rendering'] = 'passed'
                page.locator('[data-view=tasks]').click()
                page.locator('#task-title').fill('散步')
                page.locator('#task-form .primary').click()
                page.locator('#task-list').filter(has_text='散步').wait_for()
                page.locator('#task-list .text-button').filter(has_text='5 分钟后').click()
                page.wait_for_function('async()=>{const s=await(await fetch("/api/state")).json();return s.tasks[0].due<Date.now()/1000+310;}')
                page.locator('#task-list .text-button').filter(has_text='做完了').click()
                page.locator('#task-list').filter(has_text='你已完成').wait_for()
                report['checks']['task_delay_and_complete'] = 'passed'
                bad = page.request.post(url + '/api/settings', data={'name': 'bad'}, headers={**headers, 'Origin': 'https://untrusted.invalid'})
                assert bad.status == 403
                fresh_context = browser.new_context()
                assert fresh_context.request.get(url + '/api/state').status == 401
                fresh_context.close()
                report['checks']['origin_and_session_checks'] = 'passed'
                page.locator('[data-view=chat]').click()
                for width in [1440, 390, 360]:
                    page.set_viewport_size({'width': width, 'height': 844})
                    assert not page.evaluate('()=>document.documentElement.scrollWidth>innerWidth+2')
                assert page.locator('#mobile-voice').is_visible()
                page.locator('#mobile-voice').click()
                page.wait_for_function('()=>document.querySelector("#mobile-voice").getAttribute("aria-pressed")==="true"')
                report['checks']['layout_1440_390_360_and_mobile_voice'] = 'passed'
                ARTIFACTS.mkdir(exist_ok=True)
                page.screenshot(path=str(ARTIFACTS / 'phase1-mobile.png'))
                page.set_viewport_size({'width': 1440, 'height': 960})

                # Real browser decoder/audio clock, not a fake Audio object.
                page.locator('.message.assistant .read-button').last.click()
                page.wait_for_function('()=>localAudio&&localAudio.currentTime>0.03')
                page.evaluate('()=>{window.__baselineAudio=localAudio;}')
                page.locator('#stop-voice').click()
                assert page.evaluate('()=>localAudio===null&&window.__baselineAudio.paused&&window.__baselineAudio.getAttribute("src")===""')
                report['checks']['real_wav_audio_clock_and_stop'] = 'passed'

                # The server is intentionally slow; browser aborts and ignores late bytes.
                gate = speech.delay_next()
                plays_before = page.evaluate('()=>__audioEvents.filter(e=>e.type==="play").length')
                page.locator('.message.assistant .read-button').last.click()
                assert gate['started'].wait(3)
                page.wait_for_function('()=>voiceRequest!==null')
                page.locator('#stop-voice').click()
                gate['release'].set()
                assert gate['finished'].wait(3)
                page.wait_for_timeout(150)
                assert page.evaluate('()=>localAudio===null&&__speechCalls.at(-1).aborted')
                assert page.evaluate('()=>__audioEvents.filter(e=>e.type==="play").length') == plays_before
                report['checks']['stopped_delayed_wav_does_not_play'] = 'passed'

                # Replace a completed generation while its automatic audio is delayed.
                gate = speech.delay_next()
                page.locator('#message-input').fill('第一轮声音请慢一点')
                page.locator('#send').click()
                page.wait_for_function('()=>!document.querySelector("#send").disabled&&voiceContext?.generation_id&&voiceRequest!==null')
                assert gate['started'].wait(3)
                stale_generation = page.evaluate('()=>voiceContext.generation_id')
                plays_before = page.evaluate('()=>__audioEvents.filter(e=>e.type==="play").length')
                page.locator('#message-input').fill('改聊第二个话题')
                page.locator('#send').click()
                gate['release'].set()
                assert gate['finished'].wait(3)
                page.wait_for_function('(old)=>!document.querySelector("#send").disabled&&localAudio&&localAudio.currentTime>0.03&&voiceContext.generation_id!==old', arg=stale_generation)
                assert page.evaluate('(old)=>__speechCalls.some(c=>c.payload.generation_id===old&&c.aborted)', stale_generation)
                assert page.evaluate('(old)=>__audioEvents.filter(e=>e.type==="play"&&e.generation===old).length', stale_generation) == 0
                assert page.evaluate('()=>__audioEvents.filter(e=>e.type==="play").length') == plays_before + 1
                with app.db() as connection:
                    discarded = connection.execute("SELECT count(*) FROM audit WHERE event='audio_discarded'").fetchone()[0]
                assert discarded >= 1
                report['checks']['new_chat_aborts_stale_generation_audio_and_server_discards_it'] = 'passed'
                page.locator('#stop-voice').click()
                page.screenshot(path=str(ARTIFACTS / 'phase1-desktop.png'))
                report['javascript_errors'] = errors
                assert not errors, errors
                report['synthetic_synthesis_calls'] = speech.calls
                report['synthetic_wav_bytes'] = len(speech.wav)
                report['audio_discarded_server_audit_count'] = discarded
                report['status'] = 'passed'
                browser.close()
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        for instance in servers:
            instance.shutdown()
            instance.server_close()
        app.synthesize, app.state = original_synthesize, original_state
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
