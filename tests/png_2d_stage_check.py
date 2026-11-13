"""Initial actual new app PNG upload/cache/RMS/stop check, not final UI freeze.

Uses only the authorized four generated 2D states. No rejected 3D, real model,
microphone or platform account. Read-only source PNGs; actual app normalization.
"""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import traceback

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

import test_character_http as fixtures
from png_2d_asset_browser_check import FILES, cadence_wav, digest
from uiux_2026_browser_check import source_hashes

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('COMPANION_2D_STAGE_EVIDENCE','/workspace/dist/uiux-2026/2d-actual-stage'))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'status':'running',
      'scope':'actual app HTTP/SQLite/PNG normalization + real Chromium 4-state cache and actual HTMLAudio/RMS, fake text/TTS provider returning fixed9sec4Hz test WAV',
      'final_ui_freeze':False,'artwork_modified':False,'real_model_or_microphone':False,'human_visual_acceptance':False,
      'layered_rig_or_live2d_verified':False,'source_sha_before':source_hashes(ROOT),'asset_sha_before':{n:digest(p) for n,p in FILES.items()},
      'checks':{},'javascript_errors':[],'limits':['UI source is still being changed by its owner; source changes invalidate final acceptance','PNG whole-frame changes can alter hair/clothes even if DOM bounds remain fixed','UI CSS reduced-motion used to isolate frame geometry; source blink/RMS continue','Actual screen video has no audio track; synthetic test WAV separately supplied']}
    fixture=fixtures.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    wave=cadence_wav();(OUT/'synthetic-cadence.wav').write_bytes(wave)
    fixture.app.synthesize=lambda text:wave;original=fixture.app.state
    fixture.app.state=lambda:{**original(),'local_voice_available':True}
    fixture.app.set_settings({'voice':False});fixture.chat('这是一条二维角色声音测试输入')
    context=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio'])
            context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce',record_video_dir=str(OUT/'raw-video'),record_video_size={'width':1440,'height':1000})
            context.add_init_script('Math.random=()=>0.1;') # Repeatable natural blink interval, no forced face state.
            page=context.new_page();page.on('pageerror',lambda e:report['javascript_errors'].append(str(e)))
            requests=[];page.on('request',lambda request:requests.append(request.url) if '/api/assets/' in request.url else None)
            base='http://127.0.0.1:'+str(fixture.server.server_port)
            page.goto(base,wait_until='networkidle');page.wait_for_function('()=>window.CompanionApp?.core.get().state?.active_character_id')
            page.locator('#open-studio').click();page.locator('#studio-format').select_option('png')
            for name,path in FILES.items():page.locator('#studio-'+name).set_input_files(path)
            page.locator('.import-form button[type=submit]').click()
            page.locator('#studio-activate:not([disabled])').wait_for(timeout=30000)
            assert not fixture.state()['active_character'].get('appearance_id')
            report['checks']['actual_four_file_upload_and_preview_not_active']='passed'
            page.screenshot(path=str(OUT/'01-actual-four-state-preview.png'))
            page.locator('#studio-activate').click()
            page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getStats().cacheSize===4&&Boolean(CompanionApp.core.get().state.active_character.appearance_id)',timeout=30000)
            report['checks']['explicit_enable_preloads_and_decodes_four_actual_states']='passed'
            report['initial_scene_stats']=page.evaluate('()=>CompanionApp.scene.getStats()')
            assert report['initial_scene_stats']['requestCount']==4,report['initial_scene_stats']
            report['normalized_pixel_equality']={}
            for state,descriptor in fixture.state()['active_character']['appearance']['states'].items():
                normalized=page.request.get(base+descriptor['url']).body()
                with Image.open(io.BytesIO(normalized)) as image:actual=np.asarray(image.convert('RGBA'))
                with Image.open(FILES[state]) as image:expected=np.asarray(image)
                equal=bool(np.array_equal(actual,expected));assert equal,state
                report['normalized_pixel_equality'][state]=equal
            report['checks']['server_normalization_preserves_all_source_rgba_pixels']='passed'
            initial=page.locator('#character-image').get_attribute('src')
            page.screenshot(path=str(OUT/'02-actual-2d-idle-stage.png'))
            baseline=len(requests)
            page.evaluate('''()=>{window.__pngTrace=[];window.__pngTimer=setInterval(()=>{const image=document.querySelector('#character-image'),r=image.getBoundingClientRect(),audio=CompanionApp.speech.audio;window.__pngTrace.push({at:performance.now(),src:image.src,mouth:CompanionApp.scene.getStats().mouth,audio:audio?.currentTime??null,playing:Boolean(audio&&!audio.paused),box:{x:r.x,y:r.y,width:r.width,height:r.height}});},20);}''')
            page.locator('#reply-read').click()
            page.wait_for_function('()=>CompanionApp.speech.audio?.currentTime>.05&&CompanionApp.scene.getStats().mouth===1')
            page.wait_for_timeout(5600)
            report['playing_scene_stats']=page.evaluate('()=>CompanionApp.scene.getStats()')
            page.screenshot(path=str(OUT/'03-actual-audio-rms-2d-stage.png'))
            assert page.evaluate('()=>CompanionApp.speech.audio&&!CompanionApp.speech.audio.paused')
            page.locator('#stop-speaking').click();page.wait_for_function('()=>!CompanionApp.speech.audio&&CompanionApp.scene.getStats().mouth===0&&!CompanionApp.scene.getStats().audioAnalysis')
            page.wait_for_timeout(250)
            page.wait_for_function('(src)=>document.querySelector("#character-image").src===src',arg=initial,timeout=1000)
            report['checks']['actual_htmlaudio_rms_switches_and_stop_returns_closed_mouth_idle']='passed'
            trace=page.evaluate('()=>{clearInterval(__pngTimer);return __pngTrace;}');report['actual_media_trace']=trace
            report['unique_state_blob_urls_observed']=len({t['src'] for t in trace})
            interior=[t for t in trace if t['playing'] and t['audio'] is not None and .5<=t['audio']<=5]
            report['mouth_states_in_internal_cadence_window']=sorted({t['mouth'] for t in interior})
            assert {t['mouth'] for t in interior}=={0,1},'Only cold-start/stop closed the mouth; repeated125ms internal silence did not.'
            assert report['unique_state_blob_urls_observed']>=3,'No actual natural blink URL observed in deterministic interval.'
            report['checks']['actual_audio_contains_closed_and_open_mouth_plus_natural_blink']='passed'
            report['asset_requests_during_actual_playback_and_stop']=len(requests)-baseline
            assert len(requests)==baseline,requests[baseline:]
            report['checks']['no_png_refetch_during_audio_blink_or_stop']='passed'
            for key in ['x','y','width','height']:
                values=[t['box'][key] for t in trace];report.setdefault('dom_geometry_ranges',{})[key]={'min':min(values),'max':max(values),'range':max(values)-min(values)}
            report['checks']['same_dimensions_no_dom_frame_jump']='passed' if max(v['range'] for v in report['dom_geometry_ranges'].values())<.1 else 'geometry_change_observed'
            report['final_scene_stats']=page.evaluate('()=>CompanionApp.scene.getStats()')
            page.screenshot(path=str(OUT/'04-actual-stopped-idle-stage.png'))
            assert report['javascript_errors']==[],report['javascript_errors']
            video=page.video;context.close();context=None;video.save_as(str(OUT/'actual-app-2d-rms-cache-stop.webm'));browser.close()
        report['status']='initial_functional_checks_passed_not_final_ui_acceptance'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if context:
            try:page.screenshot(path=str(OUT/'failure.png'));context.close()
            except Exception:pass
        raise
    finally:
        fixture.tearDown();report['source_sha_after']=source_hashes(ROOT)
        report['source_changed_during_run']=report['source_sha_before']!=report['source_sha_after']
        report['asset_sha_after']={n:digest(p) for n,p in FILES.items()};report['asset_sources_unchanged']=report['asset_sha_before']==report['asset_sha_after']
        report['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)} for p in OUT.rglob('*') if p.is_file()]
        report['reproduce_command']='PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright python tests/png_2d_stage_check.py'
        (ROOT/'review/png-2d-stage-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['status','checks','error','source_changed_during_run','asset_sources_unchanged']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
