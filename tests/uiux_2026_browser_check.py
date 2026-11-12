"""Reproducible UI baseline/acceptance: real Chrome/HTTP, fake AI and test tone.

The desktop bridge is a controlled browser stub; native Electron, Windows DPI,
artwork quality, actual accounts, microphone and model quality are not tested.
Zoom scenarios emulate browser layout with viewport/DPR, not native UI zoom.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import io
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import struct
import time
import traceback
import wave

from playwright.sync_api import sync_playwright
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
HOST_STUB = """(()=>{let state={expanded:EXPANDED,visible:true,clickThrough:false,recoveryShortcut:true};let listener=()=>{};window.companionDesktop={getState:async()=>state,onState:cb=>{listener=cb;},setExpanded:async expanded=>{state={...state,expanded};listener(state);return state;},setClickThrough:async clickThrough=>{state={...state,clickThrough};listener(state);return state;},hide:async()=>{state={...state,visible:false};listener(state);return state;},quit:async()=>state};})();"""
INSTRUMENT = """(()=>{
 const observed=window.__uiux={audioContexts:0,rafs:0,streams:[],captureCalls:[],cores:[],scenes:[],speakers:[],uis:[]};
 for(const [name,list]of [['CompanionCore','cores'],['CompanionScene','scenes'],['CompanionSpeech','speakers'],['CompanionUI','uis']]){
  let exposed;
  Object.defineProperty(window,name,{configurable:true,get:()=>exposed,set:library=>{
   exposed={...library,create(...args){const instance=Reflect.apply(library.create,library,args);observed[list].push(instance);return instance;}};
  }});
 }
 for(const key of ['AudioContext','webkitAudioContext']){
  const Original=window[key];if(Original)window[key]=new Proxy(Original,{construct(target,args){observed.audioContexts++;return Reflect.construct(target,args);}});
 }
 const raf=window.requestAnimationFrame.bind(window);
 window.requestAnimationFrame=callback=>{observed.rafs++;return raf(callback);};
 for(const kind of ['getUserMedia','getDisplayMedia']){
  const media=navigator.mediaDevices;if(!media?.[kind])continue;
  const acquire=media[kind].bind(media);
  media[kind]=async constraints=>{observed.captureCalls.push({kind,audio:Boolean(constraints?.audio),video:Boolean(constraints?.video)});const stream=await acquire(constraints);observed.streams.push(stream);return stream;};
 }
})();"""


def test_tone():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000)
        wav.writeframes(b''.join(struct.pack('<h',int(3500*math.sin(2*math.pi*440*i/24000))) for i in range(24000*4)))
    return stream.getvalue()


def contrast_sample(page, selector, target):
    """Sample one known padding pixel, not all gradient states or WCAG conformance."""
    element=page.locator(selector).first;element.scroll_into_view_if_needed()
    rect=element.bounding_box();color=element.evaluate('(e)=>getComputedStyle(e).color')
    image=Image.open(io.BytesIO(page.screenshot())).convert('RGB')
    x=min(image.width-1,max(0,round(rect['x']+rect['width']/2)))
    y=min(image.height-1,max(0,round(rect['y']+min(6,rect['height']/4))))
    background=image.getpixel((x,y));values=[float(x) for x in re.findall(r'[\d.]+',color)]
    if len(values) not in {3,4}:return {'selector':selector,'status':'unknown_css_color','color':color}
    alpha=values[3] if len(values)==4 else 1
    foreground=[values[i]*alpha+background[i]*(1-alpha) for i in range(3)]
    def luminance(rgb):
        channels=[v/255 for v in rgb]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return .2126*linear[0]+.7152*linear[1]+.0722*linear[2]
    lights=sorted([luminance(foreground),luminance(background)])
    ratio=(lights[1]+.05)/(lights[0]+.05)
    return {'selector':selector,'css_foreground':color,'actual_background_pixel_rgb':background,
            'background_sample_css_position':{'x':x,'y':y},'ratio':round(ratio,3),'candidate_target':target,
            'status':'meets_sample_target' if ratio>=target else 'below_sample_target',
            'scope':'single real composite-background padding pixel, not all gradients/states or WCAG certification'}


def exercise_after(page, fixture, report, out, browser, base):
    checks=report['checks'];page.set_viewport_size({'width':1440,'height':1000})
    page.locator('button[data-view=chat]').first.click()
    count=page.evaluate('()=>app.messages.length')
    page.locator('#message-input').fill('KEYBOARD_QA_LINE')
    page.keyboard.press('Shift+Enter')
    assert '\n' in page.locator('#message-input').input_value()
    assert page.evaluate('()=>app.messages.length')==count
    page.keyboard.press('Enter')
    page.wait_for_function('()=>!busy&&app.messages.some(m=>m.role==="user"&&m.text.includes("KEYBOARD_QA_LINE"))')
    checks['shift_enter_newline_and_enter_real_form_submit']='passed'
    page.locator('#message-input').focus();page.keyboard.press('Tab')
    focus=page.evaluate('()=>{const e=document.activeElement,r=e.getBoundingClientRect(),s=getComputedStyle(e);return {id:e.id,tag:e.tagName,width:r.width,height:r.height,outline:s.outline,boxShadow:s.boxShadow};}')
    assert focus['tag']=='BUTTON' and focus['width']>0 and focus['height']>0,focus
    report['keyboard_focus_observation']=focus
    page.screenshot(path=str(out/'23-keyboard-focus.png'))
    checks['tab_reaches_visible_composer_control']='passed'
    # Display preference must not create media or ask a server/provider.
    before=page.evaluate('()=>({audio:__uiux.audioContexts,canvas:document.querySelectorAll("canvas").length,raf:__uiux.rafs})')
    theme_requests=[]
    listener=lambda request:theme_requests.append({'method':request.method,'url':request.url})
    page.on('request',listener)
    page.locator('#theme-toggle').click();page.wait_for_timeout(300)
    assert page.locator('html').get_attribute('data-theme')=='night'
    after=page.evaluate('()=>({audio:__uiux.audioContexts,canvas:document.querySelectorAll("canvas").length,raf:__uiux.rafs,theme:localStorage.getItem("companion-theme")})')
    page.remove_listener('request',listener)
    assert after['audio']==before['audio'] and after['canvas']==before['canvas'] and after['raf']==before['raf'],(before,after)
    assert not [r for r in theme_requests if r['method']!='GET' or '/api/state' not in r['url']],theme_requests
    assert after['theme']=='night'
    report['theme_png_resource_observation']={'before':before,'after':after,'requests':theme_requests}
    checks['theme_png_no_new_canvas_audio_context_raf_or_provider_request']='passed'
    page.screenshot(path=str(out/'20-night-chat.png'))
    samples=[contrast_sample(page,'.message.assistant .bubble',4.5),contrast_sample(page,'#theme-toggle',3)]
    page.reload(wait_until='networkidle');page.wait_for_function('()=>app?.active_character_id&&!polling')
    assert page.locator('html').get_attribute('data-theme')=='night'
    checks['night_preference_persists_locally_after_reload']='passed'
    page.locator('button[data-view=settings]').first.click()
    page.locator('#settings-model').evaluate('(e)=>e.open=true')
    samples.append(contrast_sample(page,'#local-model-note',4.5))
    page.screenshot(path=str(out/'21-night-settings-warning.png'))
    report['night_contrast_samples']=samples
    for sample in samples:
        if sample['status']!='meets_sample_target':report['findings'].append({'issue':'night_contrast_sample_needs_review',**sample})
    checks['night_normal_warning_icon_contrast_samples']='passed' if all(s['status']=='meets_sample_target' for s in samples) else 'findings'
    page.keyboard.press('Escape')
    page.locator('#theme-toggle').click()
    # Escape returns focus to the exact opening control.
    opener=page.locator('button[data-view=settings]').first;opener.click()
    page.keyboard.press('Escape')
    assert page.locator('#view-chat').is_visible()
    assert opener.evaluate('(el)=>el===document.activeElement')
    checks['escape_closes_panel_and_restores_opener_focus']='passed'
    opener.click();details=page.locator('#settings-model')
    details.evaluate('(el)=>el.open=true')
    field=page.locator('[name=local_gpu_layers]');field.fill('999')
    details.evaluate('(el)=>el.open=false')
    page.locator('#save-settings').click()
    assert details.evaluate('(el)=>el.open') and field.evaluate('(el)=>el===document.activeElement')
    assert field.evaluate('(el)=>!el.validity.valid')
    checks['invalid_folded_setting_opens_and_focuses_exact_control']='passed'
    field.fill('20')
    # Unsaved private settings must never enter a newly selected identity.
    page.locator('#settings-character').evaluate('(el)=>el.open=true')
    page.locator('[name=personality]').fill('UNSAVED_PRIVATE_PERSONA_QA')
    details.evaluate('(el)=>el.open=true')
    page.locator('[name=api_key]').evaluate('(el)=>el.value="UNSAVED_SECRET_QA"')
    first=page.locator('#character-select').input_value()
    page.locator('button[data-view=characters]').first.click()
    page.locator('#character-name').fill('独立测试角色乙')
    page.locator('#character-create-form').evaluate('(form)=>form.requestSubmit()')
    page.wait_for_function('(id)=>app.active_character_id!==id&&!charactersBusy',arg=first)
    assert page.locator('[name=api_key]').input_value()==''
    assert 'UNSAVED_PRIVATE_PERSONA_QA' not in page.locator('[name=personality]').input_value()
    assert 'UNSAVED_PRIVATE_PERSONA_QA' not in str(fixture.state())
    checks['role_switch_clears_unsaved_private_settings_and_secret']='passed'
    page.locator('#character-select').select_option(first)
    page.wait_for_function('(id)=>app.active_character_id===id&&!charactersBusy',arg=first)
    # Actual synthetic PNG upload, preview and explicit activation.
    page.locator('button[data-view=characters]').first.click()
    page.locator('#appearance-format').select_option('png')
    page.locator('#asset-idle').set_input_files({'name':'original-geometric-idle.png','mimeType':'image/png','buffer':fixture_module_png(fixture)})
    old=fixture.state()['active_character'].get('appearance_id')
    page.locator('#preview-appearance').click()
    page.wait_for_function('()=>pendingAsset&&!document.querySelector("#activate-appearance").disabled')
    assert fixture.state()['active_character'].get('appearance_id')==old
    page.locator('#activate-appearance').click()
    page.wait_for_function('()=>Boolean(app.active_character.appearance_id)&&!charactersBusy')
    checks['actual_file_png_preview_and_explicit_activation']='passed'
    page.locator('button[data-view=chat]').first.click()
    fixture.app.set_settings({'voice':True});page.evaluate('()=>refresh(true)')
    page.wait_for_function('()=>!polling&&app.settings.voice===true')
    page.locator('.message.assistant .read-button').last.click()
    page.wait_for_function('()=>localAudio&&!localAudio.paused&&localAudio.currentTime>.05')
    page.locator('#stop-voice').click();page.wait_for_function('()=>!localAudio&&!document.body.classList.contains("is-speaking")')
    checks['actual_test_tone_playback_and_visible_stop']='passed'
    # Browser captures a fixed test WAV through real MediaRecorder/decoder. ASR
    # inference is explicitly fake; no physical microphone is used.
    page.locator('#message-input').fill('')
    page.locator('#mic').click();page.wait_for_function('()=>localInput.phase==="recording"')
    page.wait_for_timeout(350)
    page.locator('button[data-view=characters]').first.click()
    page.wait_for_timeout(150)
    capture=page.evaluate('()=>({phase:localInput.phase,live:__uiux.streams.flatMap(s=>s.getTracks()).filter(t=>t.readyState==="live").length})')
    assert capture['live']==0 and capture['phase']=='idle',capture
    checks['leaving_chat_ends_synthetic_microphone_tracks']='passed'
    report['navigation_recording_observation']=capture
    page.locator('button[data-view=chat]').first.click();page.locator('#mic').click()
    page.wait_for_function('()=>localInput.phase==="recording"');page.wait_for_timeout(700);page.locator('#mic').click()
    page.wait_for_function('()=>document.querySelector("#message-input").value.includes("合成音源录音测试")&&localInput.phase==="idle"')
    assert fixture._uiux_recordings and fixture._uiux_recordings[-1]['nonzero_samples']>0
    report['actual_recording_pcm']=fixture._uiux_recordings
    checks['actual_media_recorder_decode_resample_wav_to_fake_asr_draft']='passed'
    # One real VRM renderer, no heavyweight inference/downloads.
    from vrm_fixtures import synthetic_vrm
    page.locator('button[data-view=characters]').first.click();page.locator('#appearance-format').select_option('vrm')
    page.locator('#asset-vrm').set_input_files({'name':'original-ui-resource-test.vrm','mimeType':'model/gltf-binary','buffer':synthetic_vrm('1')})
    page.locator('#preview-appearance').click();page.wait_for_function('()=>pendingVrmReady&&!charactersBusy',timeout=30000)
    page.locator('#activate-appearance').click();page.wait_for_function('()=>stageVrm?.getStats().state==="ready"',timeout=30000)
    page.evaluate('()=>{window.__themeStage=stageVrm;window.__themeCanvases=[...document.querySelectorAll("canvas")];}')
    before=page.evaluate('()=>({audio:__uiux.audioContexts,canvas:document.querySelectorAll("canvas").length})')
    page.locator('#theme-toggle').click();page.wait_for_timeout(150);page.locator('#theme-toggle').click()
    assert page.evaluate('()=>stageVrm===window.__themeStage&&window.__themeCanvases.every(c=>c.isConnected)')
    after=page.evaluate('()=>({audio:__uiux.audioContexts,canvas:document.querySelectorAll("canvas").length})')
    assert before==after,(before,after)
    report['theme_vrm_resource_observation']={'before':before,'after':after,'same_renderer_and_canvas_nodes':True}
    assert page.locator('#vrm-stage canvas').is_visible()
    pixels=page.evaluate('''()=>new Promise(resolve=>requestAnimationFrame(()=>{const canvas=document.querySelector('#vrm-stage canvas'),gl=canvas.getContext('webgl2'),rgba=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);let visible=0;for(let i=3;i<rgba.length;i+=4)if(rgba[i]>16)visible++;resolve({width:canvas.width,height:canvas.height,nontransparent_pixels:visible,error:gl.getError()});}))''')
    assert pixels['nontransparent_pixels']>100 and pixels['error']==0,pixels
    report['theme_vrm_resource_observation']['actual_framebuffer']=pixels
    page.screenshot(path=str(out/'22-original-geometric-vrm-resource-check.png'))
    checks['theme_vrm_preserves_one_renderer_canvas_and_audio_context_count']='passed'
    reduced=browser.new_context(viewport={'width':1120,'height':850},reduced_motion='reduce')
    rp=reduced.new_page();rp.goto(base,wait_until='networkidle')
    styles=rp.evaluate('()=>[".workspace",".portrait",".rail"].map(s=>{const e=document.querySelector(s),c=getComputedStyle(e);return {selector:s,transition:c.transitionDuration,animation:c.animationDuration};})')
    for item in styles:
        for prop in ['transition','animation']:
            assert all(float(x.strip().removesuffix('s'))<=.001 for x in item[prop].split(',')),item
    reduced.close();report['reduced_motion_ui_css_only']=styles
    checks['reduced_motion_shell_css_only_not_vrm_or_live2d_animation']='passed'


def fixture_module_png(fixture):
    stream=io.BytesIO();Image.new('RGBA',(96,160),(90,110,190,220)).save(stream,format='PNG');return stream.getvalue()


def native_main(args):
    """Current source Electron on private X11, with an attached fixture backend."""
    root=args.source_root.resolve();out=args.output_dir or Path('/workspace/dist/uiux-2026/native')
    out.mkdir(parents=True,exist_ok=True)
    report_path=args.report or REPO/'review/uiux-2026-native.json'
    source=lambda:{**source_hashes(root),**{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'desktop').iterdir() if p.is_file() and p.suffix in {'.cjs','.json'}}}
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'scope':'actual current-source Linux Electron/X11 and current app HTTP, externally attached isolated fixture backend',
            'status':'running','models_mocked':True,'native_linux_host_verified':False,'bundled_backend_spawn_verified':False,
            'windows_or_rtx4060_verified':False,'microphone_used':False,'source_sha256_before':source(),'checks':{},
            'limitations':['source Electron developer run, not a rebuilt release package','attached backend is externally owned and must remain alive on host quit','private Xvfb+xfwm software compositor, not physical Windows/GPU/multi-DPI','synthetic test tone and fixed dialogue, no inference/accounts','screen recording has no audio track']}
    spec=importlib.util.spec_from_file_location('native_uiux_fixture',root/'tests/test_character_http.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fixture=module.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    fixture.app.set_settings({'voice':False});original=fixture.app.state
    fixture.app.state=lambda:{**original(),'local_voice_available':True};fixture.app.synthesize=lambda text:test_tone()
    fixture.chat('本机窗口测试的合成输入')
    package=json.loads(Path('/workspace/dist/character-2d.companion.json').read_text())
    imported=fixture.post('characters/assets/import',{'character_id':fixture.initial_id,'states':package['states'],'animation_regions':package['animation_regions']})
    fixture.post('characters/assets/activate',{'character_id':fixture.initial_id,'asset_id':imported['asset']['id']})
    children=[];recorder=None;desktop=None
    try:
        td=Path(fixture.tmp.name);display=':97';authority=td/'Xauthority'
        assert not Path('/tmp/.X11-unix/X97').exists(),'Private :97 display already in use; do not attach or terminate it.'
        subprocess.run(['xauth','-f',str(authority),'add',display,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],check=True,capture_output=True)
        authority.chmod(0o600);env={**os.environ,'DISPLAY':display,'XAUTHORITY':str(authority)}
        xvfb=shutil.which('Xvfb') or '/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'
        children.append(subprocess.Popen([xvfb,display,'-screen','0','1440x1000x24','-nolisten','tcp','-auth',str(authority)],env=env,stdout=(out/'xvfb.log').open('w'),stderr=subprocess.STDOUT))
        time.sleep(.4)
        children.append(subprocess.Popen(['xfwm4','--compositor=on','--vblank=off'],env=env,stdout=(out/'xfwm.log').open('w'),stderr=subprocess.STDOUT))
        time.sleep(.6)
        ffmpeg=shutil.which('ffmpeg')
        assert ffmpeg,'Actual X11 screen recording requires ffmpeg; do not substitute a static animation.'
        recorder=subprocess.Popen([ffmpeg,'-y','-f','x11grab','-draw_mouse','0','-video_size','1440x1000','-framerate','15','-i',display+'.0','-an','-c:v','libvpx','-deadline','realtime','-cpu-used','8','-b:v','700k',str(out/'actual-linux-electron-x11.webm')],env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=(out/'recording.log').open('w'))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));debug=sock.getsockname()[1]
        base='http://127.0.0.1:'+str(fixture.server.server_port)
        binary=root/'desktop/node_modules/electron/dist/electron'
        desktop=subprocess.Popen([str(binary),str(root/'desktop'),'--smoke-test','--backend-url='+base,'--remote-debugging-port='+str(debug),'--disable-gpu','--user-data-dir='+str(td/'electron-data')],env=env,stdout=(out/'electron.stdout').open('w'),stderr=(out/'electron.stderr').open('w'));children.append(desktop)
        import urllib.request
        for _ in range(160):
            if desktop.poll() is not None:raise RuntimeError('Electron exited early: '+(out/'electron.stderr').read_text()[-1500:])
            try:urllib.request.urlopen('http://127.0.0.1:'+str(debug)+'/json/version',timeout=.2).close();break
            except (OSError,ValueError):time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp('http://127.0.0.1:'+str(debug));page=browser.contexts[0].pages[0]
            report['browser_version']=browser.version
            report['actual_user_agent']=page.evaluate('()=>navigator.userAgent')
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.locator('.desktop-tools').wait_for();page.wait_for_function('()=>window.CompanionApp?.scene.ready&&Boolean(CompanionApp.core.get().state?.active_character_id)')
            state=page.evaluate('()=>companionDesktop.getState()');report['initial_host_state']=state
            assert state['windowCount']==1 and not state['expanded'] and state['platform']=='linux'
            assert page.evaluate('()=>[document.body,document.documentElement].every(e=>getComputedStyle(e).backgroundColor==="rgba(0, 0, 0, 0)")')
            report['checks']['actual_native_one_compact_window_and_transparent_css']='passed'
            page.screenshot(path=str(out/'01-actual-native-compact.png'),omit_background=True)
            page.locator('[data-desktop-action=expand]').click();page.wait_for_function('()=>!document.body.classList.contains("desktop-collapsed")')
            assert page.evaluate('async()=>{const s=await companionDesktop.getState();return s.expanded&&s.windowCount===1;}')
            report['expanded_viewport']=observation(page)
            page.locator('#theme-switch').click();assert page.locator('html').get_attribute('data-theme')=='night'
            page.screenshot(path=str(out/'02-actual-native-expanded-night.png'))
            report['checks']['native_expand_and_current_ui_night_theme']='passed'
            fixture.app.set_settings({'voice':True});page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.core.get().state.settings.voice===true')
            page.locator('#reply-read').click();page.wait_for_function('()=>CompanionApp.speech.audio&&!CompanionApp.speech.audio.paused&&CompanionApp.speech.audio.currentTime>.05')
            state=page.evaluate('()=>companionDesktop.getState()')
            assert state['recoveryShortcut'],'Private X11 recovery shortcut unavailable; hide test must not silently pass.'
            page.evaluate('()=>companionDesktop.hide()');page.wait_for_function('()=>window.companionDesktopHidden&&!CompanionApp.speech.audio')
            assert not page.evaluate('async()=>(await companionDesktop.getState()).visible')
            report['checks']['actual_native_hide_stops_real_htmlaudio_and_sets_guard']='passed'
            page.evaluate('()=>companionDesktop.restore()');page.wait_for_function('()=>!window.companionDesktopHidden&&document.body.classList.contains("desktop-collapsed")')
            assert page.evaluate('async()=>(await companionDesktop.getState()).visible')
            page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getStats().cacheSize===4&&document.querySelector("#character-canvas .regional-png-canvas")')
            assert page.locator('#character-canvas .regional-png-canvas').is_visible()
            report['checks']['actual_restore_reloads_and_displays_same_regional_png']='passed'
            page.screenshot(path=str(out/'03-actual-native-restored.png'),omit_background=True)
            report['checks']['actual_native_restore_returns_visible_compact_window']='passed'
            assert not errors,errors;report['javascript_errors']=errors
            page.evaluate('()=>companionDesktop.quit()');desktop.wait(timeout=8)
            assert fixture.request('GET','/api/state')[0]==200,'Host must not terminate its externally attached backend.'
            report['checks']['native_quit_exits_host_and_preserves_externally_owned_backend']='passed'
        report['native_linux_host_verified']=True;report['status']='captured'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        raise
    finally:
        if recorder and recorder.poll() is None:
            try:recorder.communicate(b'q',timeout=8)
            except subprocess.TimeoutExpired:recorder.terminate();recorder.wait(timeout=3)
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=4)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)
        fixture.tearDown();report['source_sha256_after']=source()
        report['source_changed_during_run']=report['source_sha256_after']!=report['source_sha256_before']
        if report['source_changed_during_run']:report['status']='source_changed_not_final'
        report['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file()]
        report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['status','checks','error','source_changed_during_run']},ensure_ascii=False,indent=2))
    if report['status']!='captured':raise SystemExit(1)


def source_hashes(root):
    paths = sorted([root/'app/server.py', *(root/'app/static').rglob('*'), *(root/'src').rglob('*.py')])
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file() and p.suffix in {'.py', '.js', '.html', '.css', '.svg'}}


def observation(page):
    return page.evaluate('''()=>{const r=e=>{if(!e)return null;const b=e.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};};return {innerWidth,innerHeight,dpr:devicePixelRatio,visualViewport:{width:visualViewport.width,height:visualViewport.height,scale:visualViewport.scale},scrollWidth:document.documentElement.scrollWidth,horizontalOverflow:document.documentElement.scrollWidth>innerWidth+2,chatCollapsed:document.body.classList.contains('chat-collapsed'),desktopCollapsed:document.body.classList.contains('desktop-collapsed'),workspace:r(document.querySelector('.workspace')),composer:r(document.querySelector('#message-input')),portrait:r(document.querySelector('.portrait')),visibleUnlabelledButtons:[...document.querySelectorAll('button')].filter(b=>b.getClientRects().length&&!b.textContent.trim()&&!b.getAttribute('aria-label')&&!b.title).map(b=>b.id||b.className),smallVisibleTargets:[...document.querySelectorAll('button')].filter(b=>b.getClientRects().length).map(b=>({id:b.id,text:b.innerText.slice(0,30),width:b.getBoundingClientRect().width,height:b.getBoundingClientRect().height})).filter(b=>b.width<24||b.height<24)}}''')


def rebuilt_main(args):
    """New single-scene IA only; the old baseline runner is retained separately below."""
    root=args.source_root.resolve();out=args.output_dir or Path('/workspace/dist/uiux-2026/after')
    out.mkdir(parents=True,exist_ok=True);report_path=args.report or REPO/'review/uiux-2026-after.json'
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'status':'running',
      'scope':'new IA actual Chromium/HTTP/SQLite/PNG/Audio/MediaRecorder; fake LLM/TTS/ASR and optional synthetic screen/VLM protocol',
      'models_mocked':True,'physical_microphone_or_camera_used':False,'windows_or_rtx4060_verified':False,
      'native_desktop_verified':False,'human_visual_quality_accepted':False,'source_sha256_before':source_hashes(root),
      'checks':{},'findings':[],'scenarios':[],'javascript_errors':[],'external_requests':[],
      'zoom_method':'Registered CSS viewport+DPR equivalent, not native Chrome zoom or physical Windows DPI.'}
    spec=importlib.util.spec_from_file_location('rebuilt_ui_fixture',root/'tests/test_character_http.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fixture=module.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    fixture.app.set_settings({'voice':False,'memory_mode':'off'})
    def generate(settings,messages,on_delta=None,cancel=None,on_status=None):
        text='好，先歇一会儿。我在这里陪你。'
        if on_delta:on_delta(text)
        fixture.app.check_cancel(cancel);return text
    fixture.app.generate=generate
    audio=test_tone();(out/'synthetic-microphone-source.wav').write_bytes(audio)
    fixture.app.synthesize=lambda text:audio;original=fixture.app.state
    fixture.app.state=lambda:{**original(),'local_voice_available':True}
    recordings=[]
    @dataclass
    class Transcript:
        text:str='合成音源录音测试'
        segments:tuple=()
        duration_seconds:float=1
        language:str='zh'
        elapsed_seconds:float=.001
    class FakeASR:
        def __init__(self,*args,**kwargs):pass
        def diagnostics(self):return {'ready':True,'local_only':True,'recording_uploaded_to_cloud':False}
        def transcribe_wav(self,data,cancel=None):
            with wave.open(io.BytesIO(data),'rb') as wav:
                assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())==(1,2,16000)
                pcm=wav.readframes(wav.getnframes())
            nonzero=sum(sample!=0 for sample, in struct.iter_unpack('<h',pcm))
            recordings.append({'bytes':len(data),'duration_seconds':len(pcm)/32000,'nonzero_samples':nonzero,'asr_inference_mocked':True})
            return Transcript(duration_seconds=len(pcm)/32000)
    fixture.app.LocalASR=FakeASR
    base='http://127.0.0.1:'+str(fixture.server.server_port);context=None
    requested=set()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=[
                '--autoplay-policy=no-user-gesture-required','--mute-audio','--use-fake-device-for-media-stream',
                '--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str((out/'synthetic-microphone-source.wav').resolve())])
            context=browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(out/'raw-video'),record_video_size={'width':1440,'height':1000})
            context.add_init_script(INSTRUMENT);context.grant_permissions(['microphone'],origin=base)
            def route(request):
                from urllib.parse import urlsplit
                url=urlsplit(request.request.url);requested.add(url.path)
                if url.hostname not in {'localhost','127.0.0.1',None}:report['external_requests'].append(request.request.url);request.abort()
                else:request.continue_()
            context.route('**/*',route)
            page=context.new_page();page.on('pageerror',lambda e:report['javascript_errors'].append(str(e)))
            page.goto(base,wait_until='networkidle');page.wait_for_function('()=>window.CompanionApp?.core.get().state?.active_character_id')
            assert page.locator('#settings-form,#view-tasks,.rail').count()==0
            assert page.evaluate('()=>__uiux.captureCalls.length')==0
            devices=page.request.get(base+'/api/devices').json()
            assert all(devices[k]['declared_available'] and devices[k]['detection']=='not_checked' and devices[k]['permission']=='not_requested' for k in ['display','camera','microphone'])
            report['initial_devices']=devices;report['checks']['new_ia_no_old_forms_default_declarations_do_not_acquire_media']='passed'
            report['initial_resource_paths']=sorted(requested)
            assert not requested.intersection({'/vrm-renderer.js','/live2d-renderer.js','/live2d-core.js'})
            page.locator('#compose-text').fill('今天有点累，想休息一会儿。');page.locator('#send-message').click()
            page.wait_for_function('()=>!CompanionApp.core.get().chat&&CompanionApp.core.get().state.messages.some(m=>m.kind==="chat"&&m.role==="assistant")')
            report['checks']['new_composer_real_http_to_fake_dialogue']='passed'
            # Actual user-facing one-file import, with package-provided explicit regions.
            package=Path('/workspace/dist/character-2d.companion.json');assert package.is_file()
            report['character_package']={'path':str(package),'bytes':package.stat().st_size,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
            page.locator('#open-studio').click();page.locator('#studio-format').select_option('png-package')
            page.locator('#studio-model').set_input_files(package);page.locator('.import-form button[type=submit]').click()
            page.locator('#studio-activate:not([disabled])').wait_for(timeout=30000)
            assert not fixture.state()['active_character'].get('appearance_id')
            page.locator('#studio-activate').click()
            page.wait_for_function('()=>CompanionApp.scene.ready&&Boolean(CompanionApp.core.get().state.active_character.appearance_id)&&!CompanionApp.ui.active',timeout=30000)
            assert page.locator('#character-canvas .regional-png-canvas').is_visible()
            report['checks']['real_single_file_package_preview_explicit_enable_and_regions']='passed'
            # Same source role/assets, real fresh-context viewport/DPR scenarios.
            def capture(name,width,height,zoom=1,view='scene'):
                c=browser.new_context(viewport={'width':round(width/zoom),'height':round(height/zoom)},device_scale_factor=zoom)
                c.add_init_script(INSTRUMENT);c.route('**/*',route);p=c.new_page();p.on('pageerror',lambda e:report['javascript_errors'].append(str(e)))
                p.goto(base,wait_until='networkidle');p.wait_for_function('()=>window.CompanionApp?.scene.ready&&CompanionApp.core.get().state?.active_character_id')
                if view=='studio':p.locator('#open-studio').click();p.locator('#studio-format').wait_for()
                elif view=='history':p.locator('#open-history').click();p.locator('#conversation-log').wait_for()
                p.wait_for_timeout(120);path=out/(name+'.png');p.screenshot(path=str(path))
                item={'name':name,'requested_physical_size':[width,height],'zoom_equivalent':zoom,'view':view,'screenshot':str(path),'screenshot_pixels':list(Image.open(path).size),**observation(p)}
                assert item['innerWidth']==round(width/zoom) and abs(item['dpr']-zoom)<.001
                if item['horizontalOverflow']:report['findings'].append({'scenario':name,'issue':'horizontal_overflow'})
                if zoom>=2:
                    target=p.locator('#compose-text' if view=='scene' else '.import-form button[type=submit]')
                    target.focus();target.scroll_into_view_if_needed();box=target.bounding_box()
                    reachable=box and box['x']>=-2 and box['y']>=-2 and box['x']+box['width']<=item['innerWidth']+2 and box['y']+box['height']<=item['innerHeight']+2
                    item['keyboard_target_after_focus_scroll']={'box':box,'reachable':bool(reachable)}
                    if not reachable:report['findings'].append({'scenario':name,'issue':'zoom_keyboard_target_unreachable','box':box})
                report['scenarios'].append(item);c.close()
            for number,(width,height,zoom,view) in enumerate([
                (1440,1000,1,'scene'),(1440,1000,1,'studio'),(1120,850,1,'scene'),
                (1440,1000,1.1,'scene'),(1440,1000,1.1,'studio'),(1440,1000,1.25,'scene'),(1440,1000,1.25,'studio'),
                (390,844,1,'scene'),(390,844,1,'studio'),(390,844,1.25,'scene'),
                (1440,1000,2,'scene'),(1440,1000,2,'studio'),(1440,1000,1,'history')],1):
                capture(f'{number:02d}-{view}-{width}-{zoom}',width,height,zoom,view)
            report['checks']['actual_viewports_and_110_125_200_percent_layout']='passed' if not report['findings'] else 'findings'
            # Theme does not duplicate a regional canvas, scene or audio context.
            page.evaluate('()=>{window.__sceneBefore=CompanionApp.scene;window.__canvasBefore=document.querySelector("#character-canvas canvas");}')
            before=page.evaluate('()=>({contexts:__uiux.audioContexts,canvas:document.querySelectorAll("#character-canvas canvas").length,raf:__uiux.rafs})')
            page.locator('#theme-switch').click();page.wait_for_timeout(250)
            after=page.evaluate('()=>({contexts:__uiux.audioContexts,canvas:document.querySelectorAll("#character-canvas canvas").length,raf:__uiux.rafs})')
            assert before==after and page.evaluate('()=>__sceneBefore===CompanionApp.scene&&__canvasBefore.isConnected')
            assert page.locator('html').get_attribute('data-theme')=='night'
            report['theme_resource_counts']={'before':before,'after':after}
            report['checks']['regional_png_theme_reuses_canvas_scene_audio_and_no_new_raf']='passed'
            page.screenshot(path=str(out/'20-night-scene.png'))
            samples=[contrast_sample(page,'#current-reply',4.5),contrast_sample(page,'#theme-switch',3)]
            page.reload(wait_until='networkidle');page.wait_for_function('()=>window.CompanionApp?.scene.ready')
            assert page.locator('html').get_attribute('data-theme')=='night'
            report['checks']['theme_local_persistence']='passed'
            opener=page.locator('#conversation-connection');opener.click();page.get_by_role('button',name='使用本机模型',exact=True).click()
            samples.append(contrast_sample(page,'.readiness-card',4.5));page.screenshot(path=str(out/'21-night-connection-warning.png'))
            report['night_contrast_samples']=samples
            for sample in samples:
                if sample['status']!='meets_sample_target':report['findings'].append({'issue':'contrast_sample_below_candidate_target',**sample})
            layers=page.get_by_label('显卡卸载层数',exact=True);advanced=page.locator('details').filter(has=layers)
            advanced.evaluate('(e)=>e.open=true');layers.fill('999');advanced.evaluate('(e)=>e.open=false')
            page.get_by_role('button',name='使用本机方式',exact=True).click()
            assert advanced.evaluate('(e)=>e.open') and layers.evaluate('(e)=>e===document.activeElement&&!e.validity.valid')
            layers.fill('20');page.keyboard.press('Escape')
            assert not page.locator('#experience-root').is_visible() and opener.evaluate('(e)=>e===document.activeElement')
            report['checks']['purpose_local_flow_invalid_disclosure_and_escape_focus']='passed'
            page.locator('#theme-switch').click()
            # Keyboard and per-identity unsent draft.
            text=page.locator('#compose-text');text.fill('KEYBOARD_NEW_IA_QA');page.keyboard.press('Shift+Enter');assert '\n' in text.input_value()
            page.keyboard.press('Enter');page.wait_for_function('()=>!CompanionApp.core.get().chat&&CompanionApp.core.get().state.messages.some(m=>m.text.includes("KEYBOARD_NEW_IA_QA"))')
            text.fill('UNSENT_ALPHA_PRIVATE_QA');first=page.evaluate('()=>CompanionApp.core.scope().character_id');first_name=fixture.state()['settings']['name']
            page.locator('#identity-picker').click();page.locator('#studio-new-name').fill('独立测试角色乙')
            page.get_by_role('button',name='创建空白身份',exact=True).click()
            page.wait_for_function('(id)=>CompanionApp.core.scope().character_id!==id&&!CompanionApp.core.get().mutating',arg=first)
            assert text.input_value()=='' and 'UNSENT_ALPHA_PRIVATE_QA' not in str(fixture.state())
            page.locator('#identity-picker').click();card=page.locator('.identity-item').filter(has=page.get_by_role('heading',name=first_name,exact=True))
            card.get_by_role('button',name='切换',exact=True).click();page.wait_for_function('(id)=>CompanionApp.core.scope().character_id===id&&!CompanionApp.core.get().mutating',arg=first)
            assert text.input_value()=='UNSENT_ALPHA_PRIVATE_QA';text.fill('')
            report['checks']['keyboard_linebreak_submit_identity_and_private_draft_isolation']='passed'
            # Device declarations are independent and never OS permissions.
            def open_devices():
                page.locator('#open-companion-controls').click();page.get_by_role('button',name='陪伴使用的设备',exact=True).click();page.locator('#device-microphone').wait_for()
            open_devices()
            for kind in ['display','camera','microphone']:
                page.locator('#device-'+kind).select_option('absent');page.wait_for_function('(id)=>!document.getElementById(id).disabled',arg='device-'+kind)
            assert page.evaluate('()=>__uiux.captureCalls.length')==0
            page.keyboard.press('Escape');page.wait_for_function('()=>document.querySelector("#record-input").disabled')
            assert page.locator('#compose-text').is_enabled()
            fixture.app.set_settings({'voice':True});page.evaluate('()=>CompanionApp.core.refresh(true)')
            page.locator('#reply-read').click();page.wait_for_function('()=>CompanionApp.speech.audio?.currentTime>.05')
            page.locator('#stop-speaking').click();page.wait_for_function('()=>!CompanionApp.speech.audio')
            report['checks']['absent_mic_camera_aux_display_keep_pc_text_and_actual_tts']='passed'
            open_devices();page.locator('#device-microphone').select_option('present');page.wait_for_function('()=>!document.querySelector("#device-microphone").disabled')
            page.keyboard.press('Escape');page.wait_for_function('()=>!document.querySelector("#record-input").disabled')
            assert page.evaluate('()=>__uiux.captureCalls.length')==0
            report['checks']['declare_present_again_does_not_resume_or_acquire_media']='passed'
            page.locator('#record-input').click();page.wait_for_function('()=>CompanionApp.inputPhase==="recording"')
            page.wait_for_timeout(350);page.locator('#open-studio').click();page.wait_for_timeout(100)
            assert page.evaluate('()=>CompanionApp.inputPhase==="idle"&&__uiux.streams.every(s=>s.getTracks().every(t=>t.readyState==="ended"))')
            report['checks']['modal_navigation_stops_real_synthetic_media_recorder_tracks']='passed'
            page.keyboard.press('Escape');page.locator('#record-input').click();page.wait_for_function('()=>CompanionApp.inputPhase==="recording"')
            page.wait_for_timeout(700);page.locator('#record-input').click()
            page.wait_for_function('()=>CompanionApp.inputPhase==="idle"&&document.querySelector("#compose-text").value.includes("合成音源录音测试")')
            assert recordings and recordings[-1]['nonzero_samples']>0
            report['real_recording_to_fake_asr']=recordings;report['checks']['real_media_recorder_wav_resample_to_fake_asr_draft_no_auto_send']='passed'
            # Read-only scene and privacy readiness never silently start camera/screen.
            before_media=page.evaluate('()=>__uiux.captureCalls.length')
            page.locator('#open-companion-controls').click();page.get_by_role('button',name='分享与记忆边界',exact=True).click()
            page.get_by_role('button',name='一起看看屏幕或相机',exact=True).click()
            page.wait_for_timeout(200)
            assert page.evaluate('()=>__uiux.captureCalls.length')==before_media
            assert page.get_by_role('button',name='预览相机',exact=True).count()==0
            report['checks']['unconfigured_vision_is_explicit_and_never_acquires_media']='passed'
            page.keyboard.press('Escape')
            # Real local schedule lifecycle, no scheduler thread/external delivery.
            page.locator('#open-possibilities').click();page.get_by_role('button',name='一起安排时间',exact=True).click()
            page.get_by_label('想提醒什么',exact=True).fill('仅本机独立QA提醒')
            from datetime import timedelta
            page.get_by_label('什么时候',exact=True).fill((datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'))
            page.get_by_role('button',name='先看看提案',exact=True).click()
            page.get_by_role('button',name='确认本机提醒',exact=True).click()
            page.get_by_role('button',name='取消这次提醒',exact=True).click()
            page.locator('.proposal-card').filter(has_text='已取消').wait_for()
            assert fixture.state()['assistance']['proposals'][0]['status']=='cancelled'
            report['checks']['real_schedule_proposal_confirm_cancel_same_flow']='passed'
            page.keyboard.press('Escape')
            # UI-only motion preference, not all model/head/eye animation.
            reduce=browser.new_context(viewport={'width':1120,'height':850},reduced_motion='reduce');rp=reduce.new_page();rp.goto(base,wait_until='networkidle')
            styles=rp.evaluate('()=>["#scene-screen",".interaction-area"].map(s=>{const c=getComputedStyle(document.querySelector(s));return {selector:s,transition:c.transitionDuration,animation:c.animationDuration};})')
            for value in styles:
                assert all(float(v.strip().removesuffix('s'))<=.001 for key in ['transition','animation'] for v in value[key].split(',')),value
            reduce.close();report['reduced_motion_ui_css_only']=styles
            report['checks']['reduced_motion_shell_css_only']='passed'
            assert not report['javascript_errors'] and not report['external_requests'],(report['javascript_errors'],report['external_requests'])
            report['checks']['no_page_exception_or_external_cdn_request']='passed'
            video=page.video;context.close();context=None;video.save_as(str(out/'actual-new-ia-functional-flow.webm'));browser.close()
        report['status']='captured_with_findings' if report['findings'] else 'captured'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if context:
            try:page.screenshot(path=str(out/'failure.png'));context.close()
            except Exception:pass
        raise
    finally:
        fixture.tearDown();report['source_sha256_after']=source_hashes(root)
        report['source_changed_during_run']=report['source_sha256_before']!=report['source_sha256_after']
        if report['source_changed_during_run']:report['status']='source_changed_not_final'
        report['all_requested_paths']=sorted(requested);report['automated_ui_checks_passed']=report['status']=='captured'
        report['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file()]
        report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['status','checks','findings','error','source_changed_during_run']},ensure_ascii=False,indent=2))
    if report['status'] not in {'captured','captured_with_findings'}:raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['before', 'after'], default='before')
    parser.add_argument('--source-root', type=Path, default=REPO)
    parser.add_argument('--source-commit', default=None)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--native',action='store_true',help='Actual current-source Linux Electron + private X11 + attached fixture backend, no model.')
    args = parser.parse_args()
    if args.native:return native_main(args)
    if args.phase=='after':return rebuilt_main(args)
    root = args.source_root.resolve()
    out = args.output_dir or Path('/workspace/dist/uiux-2026')/args.phase
    out.mkdir(parents=True, exist_ok=True)
    report_path = args.report or REPO/'review'/('uiux-2026-'+args.phase+'.json')
    commit = args.source_commit or subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    report = {'observed_at':datetime.now(timezone.utc).isoformat(), 'phase':args.phase,
              'source_commit':commit, 'source_root':str(root), 'source_sha256_before':source_hashes(root),
              'status':'running', 'scope':'actual Chromium/HTTP/SQLite UI; fake LLM/TTS and controlled desktop bridge',
              'models_mocked':True, 'real_microphone':False, 'real_accounts_connected':False,
              'native_desktop_verified':False, 'windows_or_rtx4060_verified':False,
              'zoom_method':'CSS viewport + DPR device-metrics equivalent. Not Chrome-native zoom or Windows physical DPI.',
              'artwork':'existing repository placeholder only; not final anime artwork acceptance',
              'scenarios':[], 'findings':[], 'checks':{}, 'javascript_errors':[], 'external_requests':[]}
    spec = importlib.util.spec_from_file_location('uiux_fixture', root/'tests/test_character_http.py')
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture = fixture_module.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
    fixture.setUp()
    # Inference remains deliberately synthetic; actual HTTP/UI persistence stays real.
    def fake_generate(settings, messages, on_delta=None, cancel=None, on_status=None):
        text = '好，先歇一会儿。我在这里陪你。'
        if on_delta:on_delta(text)
        fixture.app.check_cancel(cancel)
        return text
    fixture.app.generate = fake_generate
    fixture.app.set_settings({'voice':False, 'memory_mode':'off'})
    if args.phase=='after':
        tone=test_tone();(out/'synthetic-microphone-source.wav').write_bytes(tone)
        fixture.app.synthesize=lambda text:tone
        original_state=fixture.app.state
        fixture.app.state=lambda:{**original_state(),'local_voice_available':True}
        fixture._uiux_recordings=[]
        @dataclass
        class SyntheticTranscription:
            text:str='合成音源录音测试'
            segments:tuple=()
            duration_seconds:float=1
            language:str='zh'
            elapsed_seconds:float=.001
        class FakeASR:
            def __init__(self,*args,**kwargs):pass
            def diagnostics(self):return {'ready':True,'local_only':True,'recording_uploaded_to_cloud':False}
            def transcribe_wav(self,audio,cancel=None):
                with wave.open(io.BytesIO(audio),'rb') as wav:
                    assert wav.getnchannels()==1 and wav.getsampwidth()==2 and wav.getframerate()==16000
                    frames=wav.readframes(wav.getnframes());duration=len(frames)/32000
                nonzero=sum(1 for (sample,) in struct.iter_unpack('<h',frames) if sample)
                fixture._uiux_recordings.append({'bytes':len(audio),'duration_seconds':duration,'sample_rate':16000,'nonzero_samples':nonzero,'asr_inference_mocked':True})
                return SyntheticTranscription(duration_seconds=duration)
        fixture.app.LocalASR=FakeASR
    base = 'http://127.0.0.1:'+str(fixture.server.server_port)
    context = None;requested_paths=set()
    try:
        with sync_playwright() as pw:
            flags=['--autoplay-policy=no-user-gesture-required','--mute-audio','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']
            if args.phase=='after':flags+=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str((out/'synthetic-microphone-source.wav').resolve())]
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,args=flags)
            context = browser.new_context(viewport={'width':1440,'height':1000},
                record_video_dir=str(out/'raw-video'),record_video_size={'width':1440,'height':1000})
            if args.phase=='after':
                context.add_init_script(INSTRUMENT)
                context.grant_permissions(['microphone'],origin=base)
            page = context.new_page()
            page.on('pageerror',lambda error:report['javascript_errors'].append(str(error)))
            def route(request):
                from urllib.parse import urlsplit
                requested_paths.add(urlsplit(request.request.url).path)
                if urlsplit(request.request.url).hostname not in {'127.0.0.1','localhost',None}:
                    report['external_requests'].append(request.request.url);request.abort()
                else:request.continue_()
            context.route('**/*',route)
            page.goto(base,wait_until='networkidle')
            page.wait_for_function('()=>app?.active_character_id&&!polling')
            page.locator('#message-input').fill('今天有点累，想休息一会儿。')
            page.locator('#send').click()
            page.wait_for_function('()=>!busy&&app.messages.some(m=>m.role==="assistant"&&m.kind==="chat")')
            report['checks']['actual_text_form_to_fake_provider_reply']='passed'
            report['startup_png_resource_paths']=sorted(requested_paths)
            assert not requested_paths.intersection({'/vrm-renderer.js','/live2d-renderer.js','/live2d-core.js'}),requested_paths
            report['checks']['png_startup_does_not_download_optional_3d_or_core_bundle']='passed'
            def capture(name, width, height, zoom=1, view='chat'):
                # New contexts keep Playwright's registered viewport/DPR aligned
                # with Chromium. Raw CDP overrides are reset by some actions.
                scenario_context=browser.new_context(viewport={'width':round(width/zoom),'height':round(height/zoom)},device_scale_factor=zoom)
                scenario_context.route('**/*',route)
                scenario_page=scenario_context.new_page()
                scenario_page.on('pageerror',lambda error:report['javascript_errors'].append(str(error)))
                scenario_page.goto(base,wait_until='networkidle')
                scenario_page.wait_for_function('()=>app?.active_character_id&&!polling')
                scenario_page.locator('button[data-view='+view+']').first.click()
                scenario_page.wait_for_timeout(180)
                item={'name':name,'nominal_physical_pixels':{'width':width,'height':height},'layout_zoom_equivalent':zoom,'view':view,**observation(scenario_page)}
                path=out/(name+'.png');scenario_page.screenshot(path=str(path));item['screenshot']=str(path)
                item['after_screenshot_viewport']=scenario_page.evaluate('()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})')
                item['screenshot_pixels']=list(Image.open(path).size)
                assert item['innerWidth']==round(width/zoom) and abs(item['dpr']-zoom)<.001,item
                assert item['after_screenshot_viewport']['width']==item['innerWidth'],item
                if args.phase=='after' and zoom>=2:
                    target=scenario_page.locator('#message-input' if view=='chat' else '#preview-appearance')
                    target.focus();target.scroll_into_view_if_needed()
                    box=target.bounding_box()
                    item['zoom_keyboard_target']={'selector':'#message-input' if view=='chat' else '#preview-appearance','bounds':box,'focused':target.evaluate('(el)=>el===document.activeElement')}
                    reachable=box and box['x']>=-2 and box['y']>=-2 and box['x']+box['width']<=item['innerWidth']+2 and box['y']+box['height']<=item['innerHeight']+2
                    item['zoom_keyboard_target']['within_viewport_after_scroll']=bool(reachable)
                    if not reachable:report['findings'].append({'scenario':name,'issue':'zoom_target_unreachable_after_focus_and_scroll','target':item['zoom_keyboard_target']})
                scenario_context.close()
                report['scenarios'].append(item)
                if item['horizontalOverflow']:report['findings'].append({'scenario':name,'issue':'horizontal_overflow','observed_scroll_width':item['scrollWidth'],'viewport':item['innerWidth']})
                if item['visibleUnlabelledButtons']:report['findings'].append({'scenario':name,'issue':'unlabelled_visible_button','elements':item['visibleUnlabelledButtons']})
            capture('01-expanded-chat-1440',1440,1000)
            capture('02-characters-1440',1440,1000,view='characters')
            capture('03-expanded-chat-1120',1120,850)
            capture('04-expanded-chat-110-percent',1440,1000,1.10)
            capture('05-characters-110-percent',1440,1000,1.10,view='characters')
            capture('06-expanded-chat-125-percent',1440,1000,1.25)
            capture('07-characters-125-percent',1440,1000,1.25,view='characters')
            capture('08-chat-390',390,844)
            capture('09-characters-390',390,844,view='characters')
            capture('10-chat-390-125-percent',390,844,1.25)
            if args.phase=='after':
                capture('14-chat-200-percent',1440,1000,2)
                capture('15-characters-200-percent',1440,1000,2,view='characters')
            page.set_viewport_size({'width':390,'height':740})
            page.locator('#show-stage').click();page.wait_for_timeout(150)
            path=out/'11-browser-collapsed-390.png';page.screenshot(path=str(path));report['scenarios'].append({'name':'browser-collapsed-390','screenshot':str(path),**observation(page)})
            page.locator('#toggle-chat').click()
            # A controlled bridge exercises real desktop.js/CSS. Window resizing
            # and OS drag/click-through are explicitly not real native checks.
            host_page = context.new_page();host_page.on('pageerror',lambda e:report['javascript_errors'].append(str(e)))
            host_page.add_init_script(HOST_STUB.replace('EXPANDED','false'))
            host_page.set_viewport_size({'width':330,'height':470})
            host_page.goto(base,wait_until='networkidle');host_page.wait_for_function('()=>app?.active_character_id')
            path=out/'12-desktop-compact-330x470.png';host_page.screenshot(path=str(path),omit_background=True)
            report['scenarios'].append({'name':'desktop-compact-330x470','host_bridge':'controlled_stub','screenshot':str(path),**observation(host_page)})
            host_page.get_by_role('button',name='展开聊天',exact=True).click()
            host_page.set_viewport_size({'width':1120,'height':850});host_page.wait_for_timeout(150)
            path=out/'13-desktop-expanded-1120x850.png';host_page.screenshot(path=str(path))
            report['scenarios'].append({'name':'desktop-expanded-1120x850','host_bridge':'controlled_stub','screenshot':str(path),**observation(host_page)})
            report['checks']['controlled_bridge_compact_to_expanded']='passed'
            if args.phase=='after':exercise_after(page,fixture,report,out,browser,base)
            videos=[(page.video,out/'actual-browser-flow.webm'),(host_page.video,out/'controlled-host-flow.webm')]
            context.close();context=None
            for video,target in videos:video.save_as(str(target))
            browser.close()
        assert not report['javascript_errors'],report['javascript_errors']
        assert not report['external_requests'],report['external_requests']
        report['checks']['javascript_runtime']='passed'
        report['checks']['no_external_cdn_or_web_request']='passed'
        report['status']='captured_with_findings' if report['findings'] else 'captured'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if context:
            try:page.screenshot(path=str(out/'failure.png'));context.close()
            except Exception:pass
        raise
    finally:
        fixture.tearDown()
        report['source_sha256_after']=source_hashes(root)
        report['all_requested_paths']=sorted(requested_paths)
        report['source_changed_during_run']=report['source_sha256_before']!=report['source_sha256_after']
        if report['source_changed_during_run']:report['status']='source_changed_not_final'
        report['automated_ui_checks_passed']=report['status']=='captured' and not report['findings'] and not report['javascript_errors']
        report['human_visual_quality_accepted']=False
        report['reproduce_command']='PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright python tests/uiux_2026_browser_check.py --phase '+args.phase+' --source-root '+str(root)
        report['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()]
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['status','source_changed_during_run','checks','findings','error']},ensure_ascii=False,indent=2))
    if report['status'] not in {'captured','captured_with_findings'}:raise SystemExit(1)


if __name__=='__main__':main()
