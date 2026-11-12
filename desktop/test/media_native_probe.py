"""Real Linux Electron permission flow with a fake camera and real Xvfb capture.

Does not exercise Windows, physical camera/mic, VLM or actual user media.
"""
from __future__ import annotations
import argparse
import ctypes
import ctypes.util
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        body = b'''<!doctype html><html><meta charset="utf-8"><title>Native media permission probe</title>
        <body style="background:#172d29;color:#fff;font:20px sans-serif;padding:50px">
        <h1>Native capture verification</h1><button id="camera">Start synthetic camera</button>
        <button id="screen">Choose actual Xvfb source</button><button id="stop">Stop all tracks</button>
        <button id="output">Use detected display</button><button id="return-output">Return to PC</button>
        <video id="preview" autoplay muted style="display:block;width:500px;margin:20px"></video>
        <pre id="status">Idle</pre><script>
        window.mediaResult={state:'idle'};window.stream=null;window.desktopCaptureId=null;
        async function capture(kind){try{
          if(kind==='screen'&&window.companionDesktop){const r=await companionDesktop.startScreenPreview();desktopCaptureId=r.capture_id;mediaResult={state:r.state,kind:'screen',capture_id:r.capture_id};return}
          const value=await (kind==='camera'?navigator.mediaDevices.getUserMedia({video:true,audio:false}):navigator.mediaDevices.getDisplayMedia({video:true,audio:false}));
          stream=value;document.getElementById('preview').srcObject=value;await document.getElementById('preview').play();const tracks=value.getTracks();
          mediaResult={state:'active',kind,tracks:tracks.map(t=>({kind:t.kind,state:t.readyState})),settings:tracks[0].getSettings()};
        }catch(e){mediaResult={state:'rejected',kind,error:e.name}}document.getElementById('status').textContent=JSON.stringify(mediaResult,null,2)}
        document.getElementById('camera').onclick=()=>capture('camera');document.getElementById('screen').onclick=()=>capture('screen');document.getElementById('stop').onclick=async()=>{if(desktopCaptureId){await companionDesktop.stopScreenPreview(desktopCaptureId);desktopCaptureId=null}for(const t of stream?.getTracks()||[])t.stop();mediaResult={state:'stopped',tracks:(stream?.getTracks()||[]).map(t=>({kind:t.kind,state:t.readyState}))};document.getElementById('status').textContent=JSON.stringify(mediaResult,null,2)};
        document.getElementById('output').onclick=async()=>{const d=await companionDesktop.getDisplays();await companionDesktop.setDisplayOutput(d.displays[0].id);mediaResult={state:'display_output'}};
        document.getElementById('return-output').onclick=async()=>{await companionDesktop.restoreDisplayOutput();mediaResult={state:'returned_pc'}};
        </script>'''
        self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--investigate-display-preflight',action='store_true');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'scope':'Real Linux Electron45/Blink, native dialogs/menus, Xvfb; synthetic camera, real desktop stream',
            'physical_devices_tested':False,'windows_tested':False,'checks':[],'passed':False}
    source_files=[ROOT/'desktop'/name for name in ['main.cjs','preload.cjs','window-policy.cjs','media-policy.cjs',
                  'screen-capture.cjs','screen-capture.html','screen-capture-view.js','screen-capture.css']]
    source_files += [ROOT/'desktop/test/media_native_probe.py',ROOT/'desktop/test/media_native_fixture.cjs']
    source_before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    def check(name, condition):
        if not condition: raise AssertionError(name)
        report['checks'].append({'name':name,'passed':True})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();children=[];connection=None;recorder=None
    try:
        with tempfile.TemporaryDirectory(prefix='native-media-') as directory:
            directory=Path(directory);display=':97';auth=directory/'Xauthority';subprocess.run(['xauth','-f',str(auth),'add',display,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],capture_output=True,check=True);auth.chmod(0o600)
            env={**os.environ,'DISPLAY':display,'XAUTHORITY':str(auth)};xvfb='/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'
            children.append(subprocess.Popen([xvfb,display,'-screen','0','1280x900x24','-nolisten','tcp','-auth',str(auth)],stdout=subprocess.DEVNULL,stderr=(directory/'xvfb.log').open('w')));time.sleep(.5)
            children.append(subprocess.Popen(['xfwm4','--compositor=on','--vblank=off'],env=env,stdout=subprocess.DEVNULL,stderr=(directory/'wm.log').open('w')));time.sleep(.5)
            recorder=subprocess.Popen(['ffmpeg','-y','-f','x11grab','-video_size','1280x900','-framerate','12','-i',display,
                '-an','-c:v','libvpx-vp9','-crf','36','-b:v','0',str(args.output/'native-capture-flow.webm')],env=env,stdout=subprocess.DEVNULL,stderr=(directory/'ffmpeg.log').open('w'))
            x=ctypes.CDLL(ctypes.util.find_library('X11'));xt=ctypes.CDLL(ctypes.util.find_library('Xtst'))
            x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p;x.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x.XKeysymToKeycode.restype=ctypes.c_uint;x.XFlush.argtypes=[ctypes.c_void_p];x.XCloseDisplay.argtypes=[ctypes.c_void_p]
            xt.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
            os.environ['XAUTHORITY']=str(auth);connection=x.XOpenDisplay(display.encode());assert connection
            def key(symbol):
                code=x.XKeysymToKeycode(connection,symbol);xt.XTestFakeKeyEvent(connection,code,1,0);xt.XTestFakeKeyEvent(connection,code,0,0);x.XFlush(connection);time.sleep(.2)
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));debug=sock.getsockname()[1]
            log=(args.output/'electron.log').open('w')
            target=ROOT/'desktop/test/media_native_fixture.cjs' if args.investigate_display_preflight else ROOT/'desktop'
            origin_flag='--fixture-origin=' if args.investigate_display_preflight else '--backend-url='
            command=[str(ROOT/'desktop/node_modules/electron/dist/electron'),str(target),origin_flag+f'http://127.0.0.1:{server.server_port}/','--remote-debugging-port='+str(debug),'--use-fake-device-for-media-stream','--disable-gpu','--user-data-dir='+str(directory/'profile'),'--expanded=true','--smoke-test']
            if args.investigate_display_preflight:command.append('--investigate-display-preflight');report['investigation_only_preflight_override']=True
            children.append(subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT));time.sleep(1)
            with sync_playwright() as playwright:
                browser=playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{debug}');page=browser.contexts[0].pages[0];page.wait_for_selector('#camera')
                page.click('#camera');page.wait_for_timeout(400)
                from PIL import ImageGrab
                ImageGrab.grab(xdisplay=display).save(args.output/'camera-permission.png')
                key(0xff09);key(0xff0d) # Tab and Return select the non-default Allow button.
                page.wait_for_function("mediaResult.state!=='idle'",timeout=8000)
                camera=page.evaluate('mediaResult');report['camera']=camera
                check('real native camera confirmation grants exactly one synthetic video track',camera['state']=='active' and camera['tracks']==[{'kind':'video','state':'live'}])
                page.wait_for_timeout(800)
                report['camera_video']=page.evaluate("(()=>{const v=document.getElementById('preview');return {current_time:v.currentTime,width:v.videoWidth,height:v.videoHeight,ready_state:v.readyState}})()")
                check('synthetic camera delivers video frames to the actual preview',report['camera_video']['current_time']>0 and report['camera_video']['width']>0)
                page.screenshot(path=str(args.output/'camera-active.png'));page.click('#stop');check('camera tracks actually stop',page.evaluate('mediaResult.tracks.every(t=>t.state==="ended")'))
                if not args.investigate_display_preflight:
                    page.click('#camera');page.wait_for_timeout(250);key(0xff0d)
                    page.wait_for_function("()=>mediaResult.state==='rejected'",timeout=8000)
                    check('native cancel rejects subsequent camera capture',page.evaluate('mediaResult.error')=='NotAllowedError')
                page.click('#screen');page.wait_for_timeout(500);ImageGrab.grab(xdisplay=display).save(args.output/'screen-source-picker.png')
                key(0xff54);key(0xff53);key(0xff0d) # Down, Right, Return: explicit source selection.
                page.wait_for_function("mediaResult.kind==='screen'",timeout=8000)
                if not args.investigate_display_preflight:
                    check('source choice opens dedicated preview without starting capture',page.evaluate('mediaResult.state')=='awaiting_user')
                    child=None
                    for _ in range(40):
                        child=next((p for c in browser.contexts for p in c.pages if p.url.endswith('/screen-capture.html')),None)
                        if child:break
                        page.wait_for_timeout(100)
                    assert child,'dedicated capture window not found'
                    child.wait_for_selector('#start');child.screenshot(path=str(args.output/'screen-awaiting-user.png'));child.click('#start')
                    child.wait_for_function("()=>window.captureFrame().state==='active'",timeout=10000)
                    frame=page.evaluate('companionDesktop.getScreenPreviewFrame(desktopCaptureId)')
                    check('isolated dedicated window returns actual local JPEG preview',frame['state']=='active' and frame['mime_type']=='image/jpeg' and frame['width']>0)
                    import base64
                    jpeg=base64.b64decode(frame['image_base64']);(args.output/'screen-preview.jpg').write_bytes(jpeg)
                    report['screen']={key:value for key,value in frame.items() if key!='image_base64'};report['screen']['jpeg_sha256']=hashlib.sha256(jpeg).hexdigest()
                    source_id=child.evaluate('capture.getVideoTracks()[0].getSettings().deviceId')
                    report['screen_track_settings']=child.evaluate("(()=>{const s=capture.getVideoTracks()[0].getSettings();return {width:s.width,height:s.height,frame_rate:s.frameRate}})()")
                    check('screen preview capture stays within requested resolution and frame rate bounds',report['screen_track_settings']['width']<=1600 and report['screen_track_settings']['height']<=900 and report['screen_track_settings']['frame_rate']<=10)
                    report['main_legacy_probe']=page.evaluate('''async source=>{try{const s=await navigator.mediaDevices.getUserMedia({audio:false,video:{mandatory:{chromeMediaSource:'desktop',chromeMediaSourceId:source}}});s.getTracks().forEach(t=>t.stop());return {state:'active'}}catch(e){return {state:'rejected',error:e.name}}}''',source_id)
                    check('main UI cannot use legacy desktop constraints to bypass source selection',report['main_legacy_probe']['state']=='rejected')
                    child.screenshot(path=str(args.output/'screen-isolated-active.png'));page.wait_for_timeout(1800)
                    page.click('#stop');child.wait_for_event('close',timeout=5000) if not child.is_closed() else None
                    check('parent stop destroys capture owner and all its tracks',child.is_closed())
                    displays=page.evaluate('companionDesktop.getDisplays()');report['detected_displays']=displays
                    check('single actual Xvfb display is reported without inventing an external device',len(displays['displays'])==1 and displays['external_display_detected'] is False)
                    original_size=page.evaluate('[innerWidth,innerHeight]');page.click('#output');page.wait_for_function("()=>mediaResult.state==='display_output'")
                    state=page.evaluate('companionDesktop.getState()')
                    check('display output reuses exactly one primary window',state['windowCount']==1 and state['displayOutputId']==displays['displays'][0]['id'])
                    page.screenshot(path=str(args.output/'display-output.png'));page.wait_for_timeout(500)
                    page.click('#return-output');page.wait_for_function("()=>mediaResult.state==='returned_pc'")
                    state=page.evaluate('companionDesktop.getState()')
                    check('return to PC restores the prior window size and expanded mode',state['displayOutputId'] is None and state['expanded'] is True and page.evaluate('[innerWidth,innerHeight]')==original_size)
                    page.wait_for_timeout(500)
                    report['passed']=True
                    return 0
                screen=page.evaluate('mediaResult');report['screen']=screen
                check('real chosen desktop stream contains video and no audio',screen['state']=='active' and screen['tracks']==[{'kind':'video','state':'live'}])
                page.screenshot(path=str(args.output/'screen-active.png'));page.click('#stop');check('desktop capture track actually stops',page.evaluate('mediaResult.tracks.every(t=>t.state==="ended")'))
                if args.investigate_display_preflight:
                    report['legacy_probe']=page.evaluate('''async source=>{try{const s=await navigator.mediaDevices.getUserMedia({audio:false,video:{mandatory:{chromeMediaSource:'desktop',chromeMediaSourceId:source}}});const r={state:'active',tracks:s.getTracks().map(t=>t.kind),source:s.getVideoTracks()[0].getSettings().deviceId};s.getTracks().forEach(t=>t.stop());return r}catch(e){return {state:'rejected',error:e.name}}}''',screen['settings']['deviceId'])
                report['passed']=True
    except Exception as error:report['error']=str(error)
    finally:
        if recorder and recorder.poll() is None:
            recorder.send_signal(signal.SIGINT)
            try:recorder.wait(timeout=8)
            except subprocess.TimeoutExpired:recorder.kill();recorder.wait(timeout=4)
        if connection:x.XCloseDisplay(connection)
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=4)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=4)
        server.shutdown();server.server_close()
        report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
        report['sources_unchanged_during_checks']=source_before==report['source_sha256']
        if not report['sources_unchanged_during_checks']:report['passed']=False
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
