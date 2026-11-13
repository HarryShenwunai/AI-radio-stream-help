"""Real app -> local Qwen -> Kokoro -> regional 2D PNG -> Audio -> stop/context.

No generate/synthesize replacement. Uses existing local weights and authorized
repository PNGs with explicit animation_regions; not a layered art/Live2D claim.
Linux/Chromium evidence is not Windows/4060 or human artwork/voice acceptance.
The older VRM report is retained separately; this writes a new 2D-only report.
"""
import base64
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
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

ROOT=Path(__file__).resolve().parents[1]
ASSET_DIR=ROOT/'assets/character-2d'
REPORT=ROOT/'review/real-2d-companion-browser-check.json'


def file_sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def hashes():
    paths=[ROOT/'app/server.py',Path(__file__).resolve(),
           *(ROOT/'src/companion_runtime').rglob('*.py'),
           *(p for p in (ROOT/'app/static').iterdir() if p.suffix in {'.js','.html','.css','.png','.jpg','.webp','.svg'}),
           ASSET_DIR/'import-selection.json',*(ASSET_DIR.glob('*.png'))]
    return {str(p.relative_to(ROOT)):file_sha256(p) for p in sorted(paths) if p.is_file()}


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output=Path(os.environ.get('COMPANION_EVIDENCE_DIR',str(ROOT.parent/'dist'/('evidence-real-2d-'+stamp))))
    output.mkdir(parents=True,exist_ok=True)
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'status':'running',
            'scope':'actual local app HTTP/Qwen/Kokoro + regional PNG Canvas2D + real HTMLAudio/RMS, stop and persisted conservative next-prompt context',
            'models_mocked':False,'microphone_used':False,'external_requests':[],'checks':{},
            'windows_or_rtx4060_verified':False,'human_visual_voice_dialogue_accepted':False,'p95_measured':False,
            'layered_psd_live2d_or_physical_relighting_verified':False,'source_sha256_before':hashes(),
            'evidence_directory':str(output),'screen_recording_audio_track':False,
            'recording_note':'Actual Playwright screen video has no system audio track. Actual response WAV is preserved separately before cancellation.',
            'reproduce_command':'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright COMPANION_MODELS=/workspace/companion/models COMPANION_VOICES=/workspace/companion/voices /workspace/companion/.venv/bin/python tests/real_companion_browser_check.py'}
    server=None;worker=None;app=None;context=None;browser=None;page=None;video=None;errors=[]
    try:
        selection=json.loads((ASSET_DIR/'import-selection.json').read_text())
        regions=selection.get('animation_regions')
        if regions is None:
            package_path=Path(os.environ.get('COMPANION_PNG_PACKAGE','/workspace/dist/character-2d.companion.json'))
            package=json.loads(package_path.read_text())
            assert package.get('format')=='companion-png-package' and package.get('version')==1
            regions=package.get('animation_regions')
            report['region_metadata_source']={'path':str(package_path),'sha256':file_sha256(package_path),
                                              'note':'Explicit reviewed metadata from the delivered one-file package; source PNGs remain the repository assets.'}
        assert isinstance(regions,dict) and {'eyes','mouth'}<=regions.keys(),'Explicit reviewed eye/mouth region metadata is not ready; do not silently test whole-frame replacement.'
        files={state:ASSET_DIR/name for state,name in selection['files'].items()}
        assert set(files)=={'idle','talk','blink','talk_blink'}
        for state,path in files.items():
            assert file_sha256(path)==selection['sha256'][state],state
        report['animation_regions']=regions
        report['original_asset_sha256']={state:file_sha256(path) for state,path in files.items()}
        with tempfile.TemporaryDirectory(prefix='real-2d-companion-') as data:
            spec=importlib.util.spec_from_file_location('real_2d_browser_app',ROOT/'app/server.py')
            app=importlib.util.module_from_spec(spec);sys.modules[spec.name]=app;spec.loader.exec_module(app)
            app.DATA=Path(data);app.init()
            app.set_settings({'memory_mode':'off','voice':True,'voice_backend':'kokoro',
                              'conversation_mode':'listen','local_compute':'cpu'})
            assert app.MODEL.is_file() and (app.VOICE_DIR/'kokoro-v1.0.onnx').is_file(),'Existing local model/voice assets are required; downloads are not part of this check.'
            report['actual_model_assets']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':file_sha256(p)}
                for p in [app.MODEL,app.VOICE_DIR/'kokoro-v1.0.onnx',app.VOICE_DIR/'voices-v1.0.bin']]
            server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.daemon_threads=True
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            base='http://127.0.0.1:'+str(server.server_port)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                    args=['--autoplay-policy=no-user-gesture-required','--mute-audio',
                          '--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
                context=browser.new_context(viewport={'width':1440,'height':1000},
                    record_video_dir=str(output/'raw-video'),record_video_size={'width':1440,'height':1000})
                context.add_init_script("""(()=>{window.__evidenceBlobs=new Map();const create=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{const url=create(blob);__evidenceBlobs.set(url,blob);return url;};})();""")
                def route(request):
                    if urlsplit(request.request.url).hostname not in {'127.0.0.1','localhost',None}:
                        report['external_requests'].append(request.request.url);request.abort()
                    else:request.continue_()
                context.route('**/*',route)
                page=context.new_page();video=page.video
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base,wait_until='networkidle')
                page.wait_for_function('()=>window.CompanionApp?.core.get().state?.active_character_id')
                assert page.locator('#settings-form,#view-tasks,.rail button[data-view]').count()==0,'Old UI bridge is not the rebuilt app.'
                character=page.evaluate('()=>CompanionApp.core.scope().character_id')
                payload={'character_id':character,'animation_regions':regions,'states':{
                    state:{'filename':path.name,'data_base64':base64.b64encode(path.read_bytes()).decode()}
                    for state,path in files.items()}}
                response=page.request.post(base+'/api/characters/assets/import',data=payload,
                    headers={'X-Companion':'local-app'},timeout=45000)
                assert response.status==200,(response.status,response.text()[:500])
                imported=response.json()['asset'];assert imported['animation_regions']==regions
                assert not page.request.get(base+'/api/state').json()['active_character'].get('appearance_id')
                response=page.request.post(base+'/api/characters/assets/activate',
                    data={'character_id':character,'asset_id':imported['id']},
                    headers={'X-Companion':'local-app'})
                assert response.status==200,(response.status,response.text()[:500])
                page.evaluate('()=>CompanionApp.core.refresh(true)')
                page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getStats().cacheSize===4&&document.querySelector("#character-canvas .regional-png-canvas")',timeout=30000)
                assert page.locator('#character-canvas .regional-png-canvas').is_visible()
                assert page.locator('#character-canvas canvas').count()==1
                report['initial_scene_stats']=page.evaluate('()=>CompanionApp.scene.getStats()')
                assert page.evaluate('()=>CompanionApp.core.get().state.settings.memory_mode')=='off'
                report['checks']['actual_png_api_import_explicit_regions_and_canvas_ready']='passed'
                page.screenshot(path=str(output/'01-real-regional-2d-ready.png'))
                # First readback can differ by one channel unit even with no
                # drawing. Measure that control; require read2/read3 exact and
                # retain read3 as the strict regional comparison baseline.
                report['canvas_readback_controls']=page.evaluate("""()=>{const c=document.querySelector('#character-canvas .regional-png-canvas'),ctx=c.getContext('2d');const read=()=>ctx.getImageData(0,0,c.width,c.height).data,first=read(),second=read(),third=read();function diff(a,b){let pixels=0,max=0;for(let i=0;i<a.length;i+=4){let d=0;for(let k=0;k<4;k++)d=Math.max(d,Math.abs(a[i+k]-b[i+k]));if(d)pixels++;max=Math.max(max,d);}return {changed_pixels:pixels,max_channel_delta:max};}window.__idleComposite=third;window.__realTrace=[];window.__realTimer=setInterval(()=>{const audio=CompanionApp.speech.audio;if(audio&&__realTrace.length<1000)__realTrace.push({at:performance.now(),time:audio.currentTime,paused:audio.paused,...CompanionApp.scene.getStats()});},20);return {first_to_second:diff(first,second),second_to_third:diff(second,third),cause:'unknown; rendering-backend conversion is an inference, no drawing occurred between reads'};}""")
                assert report['canvas_readback_controls']['second_to_third']['changed_pixels']==0,report['canvas_readback_controls']
                started=time.monotonic()
                page.locator('#compose-text').fill('我今天有点累，陪我聊一句，不要提问。')
                page.locator('#send-message').click()
                page.wait_for_function("""()=>{const s=CompanionApp.core.get();return Boolean(s.chat?.text)||s.failed||s.state.messages.some(m=>m.role==='assistant'&&m.kind==='chat');}""",timeout=120000)
                report['first_text_or_error_seconds']=round(time.monotonic()-started,3)
                page.screenshot(path=str(output/'02-real-qwen-stream.png'))
                page.wait_for_function('()=>!CompanionApp.core.get().chat',timeout=120000)
                failed=page.evaluate('()=>CompanionApp.core.get().failed')
                assert not failed,failed
                reply=page.evaluate("()=>CompanionApp.core.get().state.messages.filter(m=>m.role==='assistant'&&m.kind==='chat').at(-1)")
                assert reply and reply['text'],reply
                report['actual_reply']=reply['text'];report['reply_seconds']=round(time.monotonic()-started,3)
                report['checks']['real_qwen_reply_with_memory_off']='passed'
                page.wait_for_function('()=>CompanionApp.speech.audio?.currentTime>.03&&!CompanionApp.speech.audio.paused&&CompanionApp.scene.getStats().mouth===1',timeout=120000)
                report['first_observed_audio_rms_seconds']=round(time.monotonic()-started,3)
                encoded=page.evaluate("""async()=>{const blob=__evidenceBlobs.get(CompanionApp.speech.audio.src);if(!blob)throw new Error('Playing original audio Blob is missing');const bytes=new Uint8Array(await blob.arrayBuffer());let text='';for(const value of bytes)text+=String.fromCharCode(value);return btoa(text);}""")
                audio=base64.b64decode(encoded,validate=True);(output/'actual-kokoro-response.wav').write_bytes(audio)
                with wave.open(io.BytesIO(audio),'rb') as wav:
                    report['actual_response_wav']={'bytes':len(audio),'seconds':wav.getnframes()/wav.getframerate(),
                        'sample_rate':wav.getframerate(),'channels':wav.getnchannels(),'sha256':hashlib.sha256(audio).hexdigest()}
                region_pixels=page.evaluate("""regions=>{const canvas=document.querySelector('#character-canvas .regional-png-canvas'),now=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data,base=__idleComposite;let outside=0,inside=0;for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){const allowed=Object.values(regions).some(r=>x>=r.x&&x<r.x+r.width&&y>=r.y&&y<r.y+r.height),i=(y*canvas.width+x)*4;let changed=false;for(let k=0;k<4;k++)if(now[i+k]!==base[i+k])changed=true;if(changed){if(allowed)inside++;else outside++;}}return {changed_outside_reviewed_regions:outside,changed_inside_reviewed_regions:inside,width:canvas.width,height:canvas.height};}""",regions)
                assert region_pixels['changed_outside_reviewed_regions']==0,region_pixels
                assert region_pixels['changed_inside_reviewed_regions']>0,region_pixels
                report['actual_regional_composite_pixels']=region_pixels
                report['checks']['real_kokoro_audio_drives_png_mouth_and_fixed_idle_outside_regions']='passed'
                page.screenshot(path=str(output/'03-real-kokoro-mouth-playing.png'))
                report['stop_requested_while_audio_active']=page.evaluate('()=>Boolean(CompanionApp.speech.audio&&!CompanionApp.speech.audio.paused&&CompanionApp.speech.audio.currentTime<CompanionApp.speech.audio.duration)')
                stop_started=time.monotonic();page.locator('#stop-speaking').click()
                page.wait_for_function('()=>!CompanionApp.speech.audio&&CompanionApp.scene.getStats().mouth===0&&!CompanionApp.scene.getStats().audioAnalysis')
                report['observed_stop_seconds']=round(time.monotonic()-stop_started,3)
                page.wait_for_timeout(500)
                assert page.evaluate('()=>!CompanionApp.speech.audio&&CompanionApp.scene.getStats().mouth===0')
                assert report['stop_requested_while_audio_active'],'Audio ended before stop; no mid-playback interruption claim is valid.'
                report['checks']['actual_stop_closes_mouth_and_no_late_audio_revival']='passed'
                with app.db() as connection:
                    stored=connection.execute('SELECT receipt FROM playback_context WHERE message_id=?',(reply['id'],)).fetchone()
                    memories=connection.execute('SELECT count(*) FROM memories').fetchone()[0]
                assert stored,'Actual Audio did not yield a persisted playback receipt.'
                receipt=json.loads(stored['receipt'])
                assert receipt['status']=='stopped' and receipt['confirmed_text']=='',receipt
                assert memories==0 and app.settings()['memory_mode']=='off'
                assert not any(m['role']=='assistant' for m in app.build_prompt(app.settings())),'Unheard assistant tail stayed in next prompt.'
                assert page.locator('#current-reply-text').inner_text()==reply['text']
                report['actual_audio_receipt']={k:receipt.get(k) for k in ['status','position_seconds','duration_seconds','confirmed_text','evidence','reason']}
                report['checks']['unheard_tail_excluded_from_prompt_visible_reply_preserved']='passed'
                report['media_trace']=page.evaluate('()=>{clearInterval(__realTimer);return __realTrace;}')
                assert report['external_requests']==[] and errors==[],(report['external_requests'],errors)
                report['checks']['no_page_exception_or_external_web_request']='passed'
                page.screenshot(path=str(output/'04-real-stopped-context-safe.png'))
                context.close();context=None;video.save_as(str(output/'actual-app-real-2d-qwen-kokoro-stop.webm'));browser.close();browser=None
            report['max_rss_kib_linux_inference_process']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if page:
            try:page.screenshot(path=str(output/'failure.png'))
            except Exception:pass
        raise
    finally:
        if context:
            try:
                context.close()
                if video:video.save_as(str(output/'actual-app-real-2d-partial-failure.webm'))
            except Exception:pass
        if browser:
            try:browser.close()
            except Exception:pass
        if app:app.STOP.set()
        if server:server.shutdown();server.server_close()
        if worker:worker.join(5)
        report['javascript_errors']=errors;report['source_sha256_after']=hashes()
        report['source_changed_during_run']=report['source_sha256_before']!=report['source_sha256_after']
        if report['source_changed_during_run']:report['status']='source_changed_during_run_not_final_acceptance'
        report['evidence_paths']=[str(p) for p in sorted(output.iterdir()) if p.is_file()]
        report['evidence_sha256']={str(p):file_sha256(p) for p in sorted(output.iterdir()) if p.is_file()}
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
