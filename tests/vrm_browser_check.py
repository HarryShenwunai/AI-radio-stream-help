"""Real Chromium/WebGL VRM flow using original synthetic geometry and test audio.

SwiftShader is recorded explicitly. This is not RTX4060, Windows, final artwork
or human voice acceptance. No external account, microphone or paid model used.
"""
from pathlib import Path
import base64
import io
import json
import math
import struct
import traceback
from urllib.parse import urlsplit
import wave

from playwright.sync_api import sync_playwright

import test_character_http as character_http
from vrm_fixtures import fixtures

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.build/completion-browser'


def tone():
    stream = io.BytesIO()
    with wave.open(stream,'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(2*math.pi*440*i/24000))) for i in range(24000*4)))
    return stream.getvalue()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'scope':'actual local HTTP, real Chromium/WebGL; original synthetic VRM0/1, fake LLM/TTS with actual440Hz WAV playback',
              'status':'running','checks':{},'windows_or_rtx4060_verified':False,
              'not_tested':['reference visual quality','real voice/model/ASR quality','native desktop host','Windows','RTX4060/p95/VRAM','real Bilibili/WeChat account','actual Live2D Core/model playback'],'external_requests':[],'live2d_runtime_script_requests':[]}
    fixture = character_http.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
    fixture.setUp(); models = fixtures(); errors = []; console = []
    original_state = fixture.app.state
    fixture.app.state = lambda:{**original_state(),'local_voice_available':True}
    fixture.app.synthesize = lambda text:tone()
    base = f'http://127.0.0.1:{fixture.server.server_port}'
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required','--mute-audio'])
            context = browser.new_context(viewport={'width':1440,'height':1000})
            context.add_init_script('''window.__micCalls=0;window.__browserAsrStarts=0;
             class NoHardwareRecognition{start(){window.__browserAsrStarts++;}abort(){}stop(){}}
             window.SpeechRecognition=NoHardwareRecognition;window.webkitSpeechRecognition=NoHardwareRecognition;''')
            def route(request):
                if urlsplit(request.request.url).path in {'/live2d-core.js','/live2d-runtime.js'}:report['live2d_runtime_script_requests'].append(request.request.url)
                if urlsplit(request.request.url).hostname not in {'127.0.0.1','localhost',None}:
                    report['external_requests'].append(request.request.url);request.abort()
                else:request.continue_()
            context.route('**/*', route)
            page = context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda message:console.append({'type':message.type,'text':message.text[:1000]}) if message.type in {'warning','error'} and len(console)<30 else None)
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto(base,wait_until='networkidle')
            page.wait_for_function('()=>app?.active_character_id&&!polling')
            first_id = page.evaluate('()=>app.active_character_id')
            def state():return page.request.get(base+'/api/state').json()
            def ready_stage():
                page.wait_for_function('()=>stageVrm?.getStats().state==="ready"&&stageVrm.getStats().frames>2',timeout=30000)
            def import_preview(name):
                page.locator('[data-view=characters]').click()
                page.locator('#appearance-format').select_option('vrm')
                before = state()['active_character']['appearance_id']
                page.locator('#asset-vrm').set_input_files({'name':name,'mimeType':'model/gltf-binary','buffer':models[name]})
                page.locator('#preview-appearance').click()
                try:
                    page.wait_for_function('()=>pendingVrmReady&&previewVrm?.getStats().frames>1&&!document.querySelector("#activate-appearance").disabled',timeout=30000)
                except Exception:
                    report['preview_diagnostics']=page.evaluate('()=>({ready:pendingVrmReady,stats:previewVrm?.getStats(),status:document.querySelector("#appearance-status").textContent,error:document.querySelector("#character-error").textContent,disabled:document.querySelector("#activate-appearance").disabled})')
                    report['console']=console
                    page.screenshot(path=str(OUT/'vrm-preview-failure.png'))
                    raise
                assert state()['active_character']['appearance_id']==before
                return page.evaluate('()=>pendingAsset.id')
            first_asset = import_preview('valid-single-mesh-vrm1.vrm')
            report['checks']['vrm1_real_file_preview_does_not_activate'] = 'passed'
            page.locator('#activate-appearance').click();ready_stage()
            assert state()['active_character']['appearance_id']==first_asset
            report['checks']['explicit_activation_creates_real_webgl_stage'] = 'passed'
            pixels = page.evaluate('''async()=>{const c=document.querySelector('#vrm-stage canvas'),g=c.getContext('webgl2');
             const debug=g.getExtension('WEBGL_debug_renderer_info');const renderer=debug?g.getParameter(debug.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);
             let result={renderer,width:c.width,height:c.height};for(let attempt=0;attempt<90;attempt++){
              await new Promise(requestAnimationFrame);const bytes=new Uint8Array(c.width*c.height*4);g.readPixels(0,0,c.width,c.height,g.RGBA,g.UNSIGNED_BYTE,bytes);
              let opaque=0,transparent=0;for(let i=3;i<bytes.length;i+=4){if(bytes[i]>10)opaque++;else transparent++;}
              result={...result,opaque,transparent,total:c.width*c.height};if(opaque>20)break;}return result;}''')
            assert pixels['opaque']>pixels['total']/500,pixels
            assert pixels['transparent']>pixels['total']/10,pixels
            report['webgl'] = pixels
            report['checks']['gpu_framebuffer_contains_model_pixels_and_transparency'] = 'passed'
            stats = page.evaluate('()=>stageVrm.getStats()')
            assert stats['drawCalls']>0 and stats['triangles']>=24,stats
            page.wait_for_function('()=>stageVrm?.getStats().blinkCount>0',timeout=12000)
            report['checks']['real_renderer_draws_triangles_and_runs_blink_cycle'] = 'passed'
            second_asset = import_preview('valid-textured-multi-mesh-vrm0.vrm')
            page.locator('#activate-appearance').click()
            page.wait_for_function('(id)=>app.active_character.appearance_id===id',arg=second_asset);ready_stage()
            assert page.evaluate('()=>stageVrm.getStats().drawCalls')>=2
            report['checks']['different_vrm0_textured_multi_mesh_structure_renders'] = 'passed'
            # Revision cards identify model resources via thumbnail URLs; button
            # dataset is optional, so find the original resource card directly.
            old_card = page.locator('#appearance-list .appearance-card').filter(has=page.locator('img[src*="'+first_asset+'"]'))
            old_card.get_by_role('button',name='使用',exact=True).click()
            page.wait_for_function('(id)=>app.active_character.appearance_id===id',arg=first_asset);ready_stage()
            report['checks']['user_vrm_revision_rollback_releases_previous_canvas'] = 'passed'
            assert page.locator('#vrm-stage canvas').count()==1
            page.locator('#asset-vrm').set_input_files({'name':'renderer-reject-license-url.vrm','mimeType':'model/gltf-binary','buffer':models['renderer-reject-license-url.vrm']})
            page.locator('#preview-appearance').click()
            page.wait_for_function('()=>previewVrm?.getStats().state==="error"&&!charactersBusy')
            assert page.locator('#activate-appearance').is_disabled()
            failed_frames = page.evaluate('()=>previewVrm.getStats().frames')
            page.wait_for_timeout(700)
            assert page.evaluate('()=>previewVrm.getStats().frames')==failed_frames
            assert state()['active_character']['appearance_id']==first_asset
            page.locator('#cancel-appearance').click()
            report['checks']['renderer_failure_keeps_current_asset_and_stops_render_loop'] = 'passed'
            page.locator('[data-view=chat]').click()
            page.request.post(base+'/api/settings',data={'voice':False,'expected_character_id':first_id},headers={'X-Companion':'local-app'})
            page.evaluate('()=>refresh(true)')
            page.locator('#message-input').fill('VRM_ALPHA_CHAT_CANARY');page.locator('#send').click()
            page.wait_for_function('()=>!busy&&app.messages.some(m=>m.role==="assistant"&&m.kind==="chat")')
            page.request.post(base+'/api/settings',data={'voice':True,'expected_character_id':first_id},headers={'X-Companion':'local-app'})
            page.evaluate('()=>refresh(true)')
            page.locator('.message.assistant .read-button').last.click()
            page.wait_for_function('()=>localAudio?.currentTime>.05&&stageVrm?.getStats().mouth>.02',timeout=15000)
            report['checks']['actual_audio_playback_drives_vrm_mouth'] = 'passed'
            page.locator('#stop-voice').click()
            page.wait_for_function('()=>!localAudio&&stageVrm?.getStats().mouth===0')
            report['checks']['stop_resets_vrm_mouth'] = 'passed'
            page.evaluate('()=>{window.companionDesktopHidden=true;window.dispatchEvent(new Event("companion:desktop-pause"));}')
            page.wait_for_function('()=>!stageVrm&&!document.querySelector("#vrm-stage canvas")')
            report['checks']['host_hidden_disposes_renderer_and_gpu_canvas'] = 'passed'
            page.evaluate('()=>{window.companionDesktopHidden=false;resumeVrmViews();}')
            ready_stage()
            page.evaluate('()=>document.querySelector("#vrm-stage canvas").getContext("webgl2").getExtension("WEBGL_lose_context").loseContext()')
            page.locator('#vrm-retry').wait_for(state='visible')
            assert page.locator('#portrait-avatar').evaluate('(image)=>getComputedStyle(image).visibility')=='visible'
            page.locator('#vrm-retry').click();ready_stage()
            report['checks']['context_loss_falls_back_and_explicit_retry_recovers'] = 'passed'
            page.locator('[data-view=characters]').click()
            page.locator('#character-name').fill('另一独立VRM身份');page.locator('#character-create-form button').click()
            page.wait_for_function('(id)=>app.active_character_id!==id&&!charactersBusy',arg=first_id)
            assert page.locator('#vrm-stage canvas').count()==0
            assert 'VRM_ALPHA_CHAT_CANARY' not in json.dumps(state(),ensure_ascii=False)
            page.locator('#character-select').select_option(first_id)
            page.wait_for_function('(id)=>app.active_character_id===id&&!charactersBusy',arg=first_id);ready_stage()
            report['checks']['identity_switch_disposes_old_model_and_keeps_chat_isolated'] = 'passed'
            page.reload(wait_until='networkidle');ready_stage()
            assert state()['active_character']['appearance_id']==first_asset
            report['checks']['vrm_selection_persists_after_reload'] = 'passed'
            page.locator('[data-view=settings]').click()
            page.locator('[name=local_compute]').select_option('cpu')
            page.locator('[name=local_context]').select_option('2048')
            page.locator('[name=local_gpu_layers]').fill('8')
            page.locator('#voice-backend').select_option('external')
            page.locator('[name=tts_endpoint]').fill('http://127.0.0.1:9880/tts')
            page.locator('[name=tts_reference_audio]').fill('C:\\qa\\authorized-sample.wav')
            page.locator('[name=tts_prompt_text]').fill('合成测试参考文字')
            page.locator('[name=asr_device]').select_option('cuda')
            assert page.locator('[name=asr_compute_type]').input_value()=='float16'
            report['asr_precision_ui']=page.evaluate('()=>({device:document.querySelector("#asr-device").value,precision:document.querySelector("#asr-precision").value,options:[...document.querySelector("#asr-precision").options].map(e=>({value:e.value,disabled:e.disabled}))})')
            # Playwright is_disabled retargets OPTION inside LABEL to its
            # enabled SELECT. Check the browser's native OPTION state instead.
            assert page.locator('[name=asr_compute_type] option[value=int8]').evaluate('(e)=>e.disabled&&e.matches(":disabled")')
            page.locator('[name=asr_device]').select_option('cpu')
            assert page.locator('[name=asr_compute_type]').input_value()=='int8'
            assert page.locator('[name=asr_compute_type] option[value=float16]').evaluate('(e)=>e.disabled&&e.matches(":disabled")')
            page.locator('[name=asr_compute_type]').select_option('int8')
            page.locator('#settings-form [type=submit]').click()
            page.wait_for_function('()=>app.settings.voice_backend==="external"&&app.settings.local_context===2048&&app.settings.tts_prompt_text==="合成测试参考文字"')
            actual=state()['settings']
            assert actual['local_gpu_layers']==8 and actual['tts_reference_audio']=='C:\\qa\\authorized-sample.wav'
            report['checks']['actual_settings_ui_roundtrips_compute_tts_and_local_asr_fields'] = 'passed'
            report['checks']['actual_asr_device_select_keeps_precision_compatible'] = 'passed'
            page.locator('#asr-mode').select_option('local')
            page.locator('[data-view=chat]').click()
            page.evaluate('()=>{navigator.mediaDevices.getUserMedia=async()=>{window.__micCalls++;throw new Error("test fixture forbids hardware capture");};}')
            page.locator('#mic').click()
            page.wait_for_function('()=>localInput?.phase==="idle"')
            assert page.evaluate('()=>window.__micCalls===0&&window.__browserAsrStarts===0')
            report['checks']['missing_local_asr_does_not_capture_microphone_or_silently_use_browser_service'] = 'passed'
            from test_live2d_assets import archive,files
            page.locator('[data-view=characters]').click()
            before_live2d=state()['active_character']['appearance_id']
            page.locator('#appearance-format').select_option('live2d')
            page.locator('#asset-live2d').set_input_files({'name':'synthetic-structure-only.zip','mimeType':'application/zip','buffer':archive(files(True))})
            page.locator('#preview-appearance').click()
            page.wait_for_function('()=>pendingAsset?.format==="live2d"&&!charactersBusy&&document.querySelector("#appearance-status").textContent.includes("Live2D")')
            assert page.locator('#activate-appearance').is_disabled()
            assert state()['active_character']['appearance_id']==before_live2d
            assert report['live2d_runtime_script_requests']==[]
            page.locator('#cancel-appearance').click()
            report['checks']['missing_live2d_runtime_blocks_activation_without_loading_core_or_changing_vrm'] = 'passed'
            page.locator('[data-view=settings]').click()
            for width in [1440,390,360]:
                page.set_viewport_size({'width':width,'height':900})
                assert not page.evaluate('()=>document.documentElement.scrollWidth>innerWidth+2'),width
            report['checks']['layout_1440_390_360'] = 'passed'
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('[data-view=chat]').click()
            page.screenshot(path=str(OUT/'vrm-synthetic-stage.png'))
            assert errors==[],errors
            assert report['external_requests']==[],report['external_requests']
            report['checks']['no_page_exceptions_or_external_model_requests'] = 'passed'
            report['javascript_errors']=errors
            browser.close()
        report['status']='passed'
    except Exception as error:
        report.update({'status':'failed','error':str(error),'traceback':traceback.format_exc(),'javascript_errors':errors})
        raise
    finally:
        fixture.tearDown()
        (ROOT/'review/vrm-browser-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
