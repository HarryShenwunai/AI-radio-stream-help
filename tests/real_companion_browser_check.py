"""Opt-in real app -> local Qwen -> Kokoro -> Chromium/VRM audio/stop check.

No inference function is replaced. Uses existing COMPANION_MODELS/VOICES only,
isolated synthetic user data and a self-authored geometric VRM. SwiftShader is
explicitly not a Windows/RTX4060, artwork, listening or p95 acceptance result.
"""
from datetime import datetime,timezone
import hashlib
import base64
from http.server import ThreadingHTTPServer
import importlib.util
import json
import io
import os
from pathlib import Path
import resource
import sys
import tempfile
import threading
import time
import traceback
from urllib.parse import urlsplit
import wave

from playwright.sync_api import sync_playwright

from vrm_fixtures import synthetic_vrm

ROOT=Path(__file__).resolve().parents[1]
SOURCES=sorted({'app/server.py','frontend/renderer.mjs','frontend/package.json',
    *(str(path.relative_to(ROOT)) for path in (ROOT/'src/companion_runtime').rglob('*.py')),
    *(str(path.relative_to(ROOT)) for path in (ROOT/'app/static').iterdir() if path.suffix in {'.js','.html','.css'})})


def hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def file_sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def main():
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'scope':'actual app HTTP + actual local Qwen/Kokoro + real Chromium WebGL/HTMLAudio; synthetic input and original geometric VRM',
            'status':'running','checks':{},'models_mocked':False,'microphone_used':False,
            'windows_or_rtx4060_verified':False,'human_quality_accepted':False,'p95_measured':False,
            'external_requests':[],'source_sha256_before':hashes()}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output=Path(os.environ.get('COMPANION_EVIDENCE_DIR',str(ROOT.parent/'dist'/('evidence-companion-real-'+stamp))))
    output.mkdir(parents=True,exist_ok=True)
    report['evidence_directory']=str(output)
    report['reproduce_command']='PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright COMPANION_MODELS=/workspace/companion/models COMPANION_VOICES=/workspace/companion/voices /workspace/companion/.venv/bin/python tests/real_companion_browser_check.py'
    report['screen_recording_audio_track']=False
    report['screen_recording_note']='Actual Playwright screen recording; no system audio track. Actual response WAV is preserved separately; no voice-quality acceptance.'
    server=None;worker=None;app=None;errors=[]
    try:
        with tempfile.TemporaryDirectory(prefix='real-companion-browser-') as folder:
            spec=importlib.util.spec_from_file_location('real_browser_app',ROOT/'app/server.py')
            app=importlib.util.module_from_spec(spec);sys.modules[spec.name]=app;spec.loader.exec_module(app)
            app.DATA=Path(folder);app.init()
            app.set_settings({'memory_mode':'off','voice':True,'voice_backend':'kokoro','conversation_mode':'listen','local_compute':'cpu'})
            assert app.MODEL.is_file() and (app.VOICE_DIR/'kokoro-v1.0.onnx').is_file(),'Existing model assets unavailable; no automatic downloads permitted.'
            report['model_filename']=app.MODEL.name
            report['actual_model_assets']=[{'name':path.name,'bytes':path.stat().st_size,'sha256':file_sha256(path)}
                for path in [app.MODEL,app.VOICE_DIR/'kokoro-v1.0.onnx',app.VOICE_DIR/'voices-v1.0.bin']]
            server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.daemon_threads=True
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{server.server_port}'
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=[
                    '--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',
                    '--autoplay-policy=no-user-gesture-required','--mute-audio'])
                context=browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(output/'raw-video'),record_video_size={'width':1440,'height':1000})
                context.add_init_script('''(()=>{window.__evidenceBlobs=new Map();const create=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{const url=create(blob);window.__evidenceBlobs.set(url,blob);return url;};})();''')
                def route(request):
                    if urlsplit(request.request.url).hostname not in {'127.0.0.1','localhost',None}:
                        report['external_requests'].append(request.request.url);request.abort()
                    else:request.continue_()
                context.route('**/*',route)
                page=context.new_page();video=page.video;speech_responses=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('response',lambda response:speech_responses.append(response) if urlsplit(response.url).path=='/api/speech' and response.status==200 else None)
                page.goto(base,wait_until='networkidle');page.wait_for_function('()=>app?.active_character_id&&!polling')
                page.locator('[data-view=characters]').click();page.locator('#appearance-format').select_option('vrm')
                page.locator('#asset-vrm').set_input_files({'name':'original-real-e2e-fixture.vrm','mimeType':'model/gltf-binary','buffer':synthetic_vrm('1')})
                page.locator('#preview-appearance').click()
                page.wait_for_function('()=>pendingVrmReady&&!charactersBusy',timeout=30000)
                page.locator('#activate-appearance').click()
                page.wait_for_function('()=>stageVrm?.getStats().state==="ready"&&stageVrm.getStats().frames>2',timeout=30000)
                report['checks']['actual_self_service_vrm_upload_and_webgl']='passed'
                page.screenshot(path=str(output/'01-self-service-vrm-ready.png'))
                report['renderer']=page.evaluate('()=>{const g=document.querySelector("#vrm-stage canvas").getContext("webgl2"),e=g.getExtension("WEBGL_debug_renderer_info");return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);}')
                page.locator('[data-view=chat]').click()
                page.evaluate('''()=>{window.__realMediaTrace=[];window.__realMediaTimer=setInterval(()=>{
                  const audio=localAudio,stats=stageVrm?.getStats();if(audio&&window.__realMediaTrace.length<1000)
                  window.__realMediaTrace.push({at:performance.now(),time:audio.currentTime,paused:audio.paused,mouth:stats?.mouth||0});},20);}''')
                started=time.monotonic()
                page.locator('#message-input').fill('我今天有点累，陪我聊一句，不要提问。')
                page.locator('#send').click()
                page.wait_for_function('()=>Boolean(streamDraft?.text)||app.messages.some(m=>m.role==="assistant"&&m.kind==="chat")||!document.querySelector("#error").hidden',timeout=120000)
                report['first_text_or_error_seconds']=round(time.monotonic()-started,3)
                page.screenshot(path=str(output/'02-real-chat-stream.png'))
                page.wait_for_function('()=>!busy',timeout=120000)
                if page.locator('#error').is_visible():raise AssertionError(page.locator('#error').inner_text())
                reply=page.evaluate('()=>app.messages.filter(m=>m.role==="assistant"&&m.kind==="chat").at(-1)')
                assert reply and reply['text'],reply
                report['reply_seconds']=round(time.monotonic()-started,3);report['synthetic_reply']=reply['text']
                report['checks']['real_qwen_sse_reply_displayed']='passed'
                page.wait_for_function('()=>localAudio&&localAudio.currentTime>.03&&!localAudio.paused&&stageVrm?.getStats().mouth>.015',timeout=120000)
                report['first_observed_audio_rms_seconds']=round(time.monotonic()-started,3)
                trace=page.evaluate('()=>[...window.__realMediaTrace,{at:performance.now(),time:localAudio.currentTime,paused:localAudio.paused,mouth:stageVrm.getStats().mouth}]')
                report['observed_audio_current_time_max']=max(x['time'] for x in trace)
                report['observed_mouth_max']=max(x['mouth'] for x in trace)
                report['checks']['actual_kokoro_audio_advances_and_drives_vrm_mouth']='passed'
                # Preserve the exact generated Blob before stop aborts the fetch
                # and revokes its URL. Playwright Response.body() may be empty
                # after that cancellation even though HTMLAudio played it.
                encoded=page.evaluate('''async()=>{const blob=window.__evidenceBlobs.get(localAudio.src);if(!blob)throw new Error('Actual playing Blob was not captured');const data=new Uint8Array(await blob.arrayBuffer());let text='';for(let i=0;i<data.length;i++)text+=String.fromCharCode(data[i]);return btoa(text);}''')
                audio=base64.b64decode(encoded,validate=True)
                (output/'actual-kokoro-response.wav').write_bytes(audio)
                with wave.open(io.BytesIO(audio),'rb') as wav:
                    report['actual_response_wav']={'bytes':len(audio),'seconds':wav.getnframes()/wav.getframerate(),'sample_rate':wav.getframerate(),'sha256':hashlib.sha256(audio).hexdigest(),'source':'actual playing HTMLAudio Blob, preserved before stop'}
                page.screenshot(path=str(output/'03-real-audio-playing.png'))
                report['stop_requested_while_audio_active']=page.evaluate('()=>Boolean(localAudio&&!localAudio.paused&&localAudio.currentTime<localAudio.duration)')
                stop_started=time.monotonic();page.locator('#stop-voice').click()
                page.wait_for_function('()=>!localAudio&&stageVrm?.getStats().mouth===0&&!document.body.classList.contains("is-speaking")')
                report['observed_stop_seconds']=round(time.monotonic()-stop_started,3)
                page.wait_for_timeout(600)
                assert page.evaluate('()=>!localAudio&&stageVrm?.getStats().mouth===0')
                report['checks']['stop_silences_real_media_and_no_late_revival']='passed'
                assert report['stop_requested_while_audio_active'],'Real speech ended before the stop action; do not claim a mid-playback interruption.'
                with app.db() as connection:
                    stored=connection.execute('SELECT receipt FROM playback_context WHERE message_id=?',(reply['id'],)).fetchone()
                assert stored,'Actual Audio events did not create a persisted playback receipt.'
                receipt=json.loads(stored['receipt'])
                assert receipt['status']=='stopped' and receipt['confirmed_text']=='',receipt
                prompt=app.build_prompt(app.settings())
                assert not any(message['role']=='assistant' for message in prompt),'Unheard assistant reply remained in generation context.'
                report['actual_audio_receipt']={key:receipt.get(key) for key in ['status','position_seconds','duration_seconds','confirmed_text','evidence','reason']}
                report['checks']['actual_audio_stop_receipt_excludes_unheard_reply_from_next_prompt']='passed'
                assert report['external_requests']==[],report['external_requests']
                assert errors==[],errors
                report['checks']['no_page_exception_or_external_web_request']='passed'
                page.evaluate('()=>clearInterval(window.__realMediaTimer)')
                page.screenshot(path=str(output/'04-real-audio-stopped.png'))
                assert speech_responses,'No actual HTTP speech response observed.'
                report['media_trace']=trace
                context.close()
                video.save_as(str(output/'actual-app-process.webm'))
                report['evidence_paths']=[str(path) for path in sorted(output.iterdir()) if path.is_file()]
                report['evidence_sha256']={str(path):file_sha256(path) for path in sorted(output.iterdir()) if path.is_file()}
                browser.close()
            report['max_rss_kib_linux_process']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc(),javascript_errors=errors)
        raise
    finally:
        if app:app.STOP.set()
        if server:server.shutdown();server.server_close()
        if worker:worker.join(5)
        report['source_sha256_after']=hashes()
        report['source_changed_during_run']=report['source_sha256_before']!=report['source_sha256_after']
        if report['source_changed_during_run']:
            report['status']='source_changed_during_run_not_final_acceptance'
        (ROOT/'review/real-companion-browser-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
