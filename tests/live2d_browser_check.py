"""Actual owner-installed Core/framework + licensed model acceptance.

Requires explicit paths; downloads nothing and never substitutes fake Core/MOC.
The model and vendor runtime remain outside the repository/default package.
"""
from pathlib import Path
import argparse
import json
import os
import time
import traceback
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
from character_browser_check import tone
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model-zip',required=True);parser.add_argument('--runtime-dir',required=True);parser.add_argument('--output',default='review/live2d-browser-check.json');parser.add_argument('--label',default='haru');parser.add_argument('--before-worker-bundle');args=parser.parse_args()
    package=Path(args.model_zip).resolve();runtime=Path(args.runtime_dir).resolve()
    if not package.is_file() or not runtime.is_dir():raise SystemExit('Provide the separately licensed local model ZIP and installed runtime directory.')
    os.environ['COMPANION_LIVE2D_RUNTIME']=str(runtime)
    fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    original=fixture.app.state;fixture.app.state=lambda:{**original(),'local_voice_available':True};fixture.app.synthesize=lambda text:tone()
    report={'date':'2026-11-12','status':'RUNNING','scope':'actual owner-installed Core/framework, official licensed local evaluation model, Chromium software WebGL; synthetic test audio','checks':{},'vendor_code_bundled':False,'real_microphone':False,'public_platform_connections':0,'not_tested':['Windows/RTX4060 performance','arbitrary Cubism exports','reference artwork acceptance','real voice/model quality','SDK or model publication permission']}
    errors=[];console=[];out=Path('/workspace/.live2d/evaluation')/args.label;out.mkdir(exist_ok=True,parents=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader','--autoplay-policy=no-user-gesture-required','--mute-audio'])
            context=browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(out/'video'),record_video_size={'width':1440,'height':1000});page=context.new_page();page.set_default_timeout(60000)
            if args.before_worker_bundle:
                page.route('**/live2d-renderer.js',lambda route:route.fulfill(body=Path(args.before_worker_bundle).read_bytes(),content_type='application/javascript'))
                page.add_init_script("window.__policyViolations=[];document.addEventListener('securitypolicyviolation',e=>window.__policyViolations.push({directive:e.effectiveDirective,blockedURI:e.blockedURI,originalPolicy:e.originalPolicy}));")
            page.on('pageerror',lambda x:errors.append(str(x)));page.on('console',lambda x:console.append({'type':x.type,'text':x.text}) if x.type in ['error','warning'] else None)
            try:
                page.goto(f'http://127.0.0.1:{fixture.server.server_port}');page.locator('#character-select option').first.wait_for(state='attached')
                state=page.evaluate('()=>api("live2d/runtime")');assert state['available'] and state['core_available'] and state['renderer_available'];report['installed_runtime_status']=state
                page.locator('#manage-characters').click();page.locator('#appearance-format').select_option('live2d');page.locator('#asset-live2d').set_input_files(str(package));page.locator('#preview-appearance').click()
                if args.before_worker_bundle:
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline and not any('Creating a worker' in item['text'] and 'Content Security Policy' in item['text'] for item in console):page.wait_for_timeout(100)
                    assert any('Creating a worker' in item['text'] and 'Content Security Policy' in item['text'] for item in console),console
                    page.wait_for_timeout(1000);page.screenshot(path=str(out/'failure-worker.png'))
                    report['status']='expected_failure_reproduced';report['source_variant']='controlled reproduction of observed pre-fix worker bug: the local original adapter with Pixi worker preferences removed; product source unchanged'
                    report['csp_violations']=page.evaluate('()=>window.__policyViolations');report['checks']['csp_worker_failure_observed']='passed';return
                page.wait_for_function("()=>document.querySelector('#vrm-preview').dataset.state==='ready'||document.querySelector('#vrm-preview').dataset.state==='error'||!document.querySelector('#character-error').hidden||!document.querySelector('#vrm-preview-retry').hidden")
                page.screenshot(path=str(out/'preview-checkpoint.png'));report['preview_status']=page.locator('#appearance-status').inner_text();report['preview_error']=page.locator('#character-error').inner_text()
                assert page.locator('#vrm-preview').get_attribute('data-state')=='ready',(report['preview_status'],report['preview_error'])
                assert page.evaluate('()=>!app.active_character.appearance_id')
                report['core_observation']=page.evaluate('()=>({coreVersion:Live2DCubismCore.Version.csmGetVersion(),latestMocVersion:Live2DCubismCore.Version.csmGetLatestMocVersion(),wrapper:CompanionLive2DRuntime.versions})')
                report['checks']['actual_core_model_preview_without_activation']='passed';page.screenshot(path=str(out/'preview.png'))
                page.locator('#activate-appearance').click();page.locator('#vrm-stage[data-state=ready]').wait_for();page.wait_for_timeout(1500)
                report['checks']['explicit_activation_creates_live2d_webgl_stage']='passed';report['model_observation']=page.evaluate('()=>({id:app.active_character.appearance.id,moc:app.active_character.appearance.moc3_version,stats:stageVrm.getStats()})')
                pixels=page.evaluate('''()=>new Promise(resolve=>requestAnimationFrame(()=>{const canvas=document.querySelector('#vrm-stage canvas'),gl=canvas.getContext('webgl2')||canvas.getContext('webgl'),width=gl.drawingBufferWidth,height=gl.drawingBufferHeight,rgba=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);let colored=0,transparent=0,transparentRgbNonzero=0;for(let i=0;i<rgba.length;i+=4){if(rgba[i+3]>16&&(rgba[i]||rgba[i+1]||rgba[i+2]))colored++;if(rgba[i+3]===0){transparent++;if(rgba[i]||rgba[i+1]||rgba[i+2])transparentRgbNonzero++;}}resolve({width,height,colored,transparent,transparentRgbNonzero,premultiplied:gl.getContextAttributes().premultipliedAlpha,corner:Array.from(rgba.slice(0,4)),cssBackground:getComputedStyle(canvas).backgroundColor,error:gl.getError()});}))''')
                report['framebuffer_observation']=pixels;page.screenshot(path=str(out/'stage-checkpoint.png'))
                assert pixels['colored']>1000 and pixels['transparent']>1000 and pixels['error']==0,pixels
                report['framebuffer_observation']=pixels;report['checks']['real_framebuffer_contains_model_pixels_and_alpha']='passed';assert not pixels['premultiplied'] or pixels['transparentRgbNonzero']==0,pixels;report['checks']['premultiplied_transparent_background_is_valid']='passed';page.screenshot(path=str(out/'stage.png'))
                page.evaluate("()=>speak('本机合成测试音')");page.wait_for_function('()=>stageVrm&&stageVrm.getStats().mouth>0.002',timeout=10000);report['checks']['actual_audio_activity_drives_live2d_mouth']='passed'
                page.evaluate('()=>stopVoice()');assert page.evaluate('()=>stageVrm.getStats().mouth===0');report['checks']['stop_resets_mouth']='passed'
                page.evaluate("()=>{window.companionDesktopHidden=true;window.dispatchEvent(new Event('companion:desktop-pause'));}")
                assert page.locator('#vrm-stage canvas').count()==0 and page.evaluate('()=>stageVrm===null');report['checks']['native_hidden_releases_canvas_and_renderer']='passed'
                page.evaluate('()=>{window.companionDesktopHidden=false;resumeVrmViews();}');page.locator('#vrm-stage[data-state=ready]').wait_for();report['checks']['restore_reloads_model']='passed'
                page.evaluate('()=>{const canvas=document.querySelector("#vrm-stage canvas"),gl=canvas.getContext("webgl2")||canvas.getContext("webgl");gl.getExtension("WEBGL_lose_context").loseContext();}')
                page.locator('#vrm-retry').wait_for();page.locator('#vrm-retry').click();page.locator('#vrm-stage[data-state=ready]').wait_for();report['checks']['webgl_loss_retry_recovers']='passed'
                previous=page.locator('#character-select').input_value();page.evaluate("async()=>{await api('characters/create',{name:'另一位独立角色'});await refresh(true);}")
                assert page.locator('#character-select').input_value()!=previous and page.locator('#vrm-stage canvas').count()==0;report['checks']['identity_switch_releases_old_live2d']='passed'
                page.locator('#character-select').select_option(previous);page.locator('#vrm-stage[data-state=ready]').wait_for();page.reload();page.locator('#vrm-stage[data-state=ready]').wait_for();report['checks']['identity_asset_selection_survives_reload']='passed'
                assert not errors,errors;report['checks']['javascript_runtime']='passed'
            except Exception:
                try:
                    report['visible_status']=page.locator('#appearance-status').inner_text();report['visible_error']=page.locator('#character-error').inner_text();page.screenshot(path=str(out/'failure.png'))
                except Exception:pass
                raise
            finally:
                video=page.video;context.close();video.save_as(str(out/'acceptance.webm'));report['video']=str(out/'acceptance.webm');browser.close()
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error']=str(error);report['traceback']=traceback.format_exc()
        try:
            report['visible_status']=page.locator('#appearance-status').inner_text();report['visible_error']=page.locator('#character-error').inner_text();page.screenshot(path=str(out/'failure.png'))
        except Exception:pass
        raise
    finally:
        report['javascript_errors']=errors;report['browser_warnings']=console;fixture.tearDown();Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
