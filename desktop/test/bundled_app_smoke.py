"""Actual packaged UI + embedded Python backend; isolated data, no inference/accounts."""
from pathlib import Path
import datetime,json,os,secrets,shutil,socket,subprocess,tempfile,time,urllib.request
import psutil
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ.get('COMPANION_DESKTOP_TEST_RESULTS',str(ROOT/'desktop/test-results')));OUT.mkdir(parents=True,exist_ok=True)
WINDOWS=os.name=='nt'
binary=Path(os.environ.get('COMPANION_DESKTOP_BINARY',ROOT/('.build/desktop/character-windows-x64/companion-desktop.exe' if WINDOWS else '.build/desktop/character-linux-unpacked/companion-desktop')))
def port():
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'actual '+('Windows' if WINDOWS else 'Linux')+' Electron bundle spawning its embedded native backend and actual app page','checks':[],'inference_or_microphone_tests':0,'limitations':['Only the executing OS/CI display; physical Windows 10/11, multi-DPI/multi-monitor/fullscreen not covered','Synthetic PNG tests import mechanics, not anime artwork quality','No model/voice quality evaluation in this check']}
def check(name,value):
 assert value,name
 report['checks'].append({'name':name,'result':'passed'})
children=[]
try:
 with tempfile.TemporaryDirectory(prefix='desktop-bundled-app-') as temp:
  td=Path(temp);env={**os.environ,'COMPANION_DATA':str(td/'data')}
  if not WINDOWS:
   display=':94';auth=td/'Xauthority'
   subprocess.run(['xauth','-f',str(auth),'add',display,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],capture_output=True,check=True);auth.chmod(0o600)
   env.update({'DISPLAY':display,'XAUTHORITY':str(auth)})
   xvfb=os.environ.get('COMPANION_XVFB') or shutil.which('Xvfb') or '/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'
   children.append(subprocess.Popen([xvfb,display,'-screen','0','1440x1000x24','-nolisten','tcp','-auth',str(auth)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL));time.sleep(.4)
   children.append(subprocess.Popen(['xfwm4','--compositor=on','--vblank=off'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL));time.sleep(.5)
  debug=port();started=time.monotonic();desktop=subprocess.Popen([str(binary),'--smoke-test','--remote-debugging-port='+str(debug),'--disable-gpu','--user-data-dir='+str(td/'electron-data')],env=env,stdout=(td/'desktop.stdout').open('w'),stderr=(td/'desktop.stderr').open('w'));children.append(desktop)
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   if desktop.poll() is not None:raise RuntimeError((td/'desktop.stderr').read_text()[-2000:])
   try:urllib.request.urlopen(f'http://127.0.0.1:{debug}/json/version',timeout=.2).close();break
   except Exception:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{debug}');page=browser.contexts[0].pages[0];errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
   page.wait_for_selector('.desktop-tools');page.wait_for_function('()=>document.querySelector("#character-select").options.length>0')
   report['page_ready_seconds_with_cdp']=round(time.monotonic()-started,3);report['page_origin']=page.url
   def is_backend(proc):
    exe=proc.exe().replace('\\','/').lower()
    return '/resources/backend/' in exe and (proc.name().lower() in {'companion-backend','companion-backend.exe'} or exe.endswith('/python/python.exe'))
   descendant=psutil.Process(desktop.pid).children(recursive=True);backend=[proc for proc in descendant if is_backend(proc)]
   check('bundle spawned embedded backend without attached URL',len(backend)>=1 and '/resources/backend/' in backend[0].exe().replace('\\','/').lower())
   check('actual app page has one compact native window',page.locator('#manage-characters').count()==1 and page.evaluate('async()=>(await companionDesktop.getState()).windowCount===1 && document.body.classList.contains("desktop-collapsed")'))
   check('actual app compact root and body backgrounds are transparent',page.evaluate('()=>[document.documentElement,document.body].every(e=>getComputedStyle(e).backgroundColor==="rgba(0, 0, 0, 0)")'))
   page.locator('[data-desktop-action=expand]').click();page.wait_for_function('()=>!document.body.classList.contains("desktop-collapsed")')
   page.locator('#manage-characters').click();page.locator('#character-name').fill('本机验证角色');page.locator('#character-create-form button').click()
   page.wait_for_function('()=>document.querySelector("#character-select").selectedOptions[0]?.textContent==="本机验证角色"')
   check('create self-service character in real UI',page.locator('#character-error').is_hidden())
   fixture=td/'own-fixture.png';image=Image.new('RGBA',(160,240),(0,0,0,0));draw=ImageDraw.Draw(image);draw.ellipse((45,10,115,80),fill=(190,125,180,255));draw.polygon([(80,85),(30,225),(130,225)],fill=(130,110,180,255));image.save(fixture)
   page.locator('#asset-idle').set_input_files(fixture);page.locator('#preview-appearance').click();page.wait_for_function('()=>document.querySelector("#appearance-status").textContent.includes("已检查")')
   check('real backend validates PNG and returns isolated preview',page.locator('#appearance-preview').is_visible() and page.locator('#appearance-preview-image').evaluate('(e)=>e.complete && e.naturalWidth===160'))
   page.locator('#activate-appearance').click();page.wait_for_function('()=>document.querySelector("#appearance-preview").hidden && document.querySelector("#portrait-avatar").naturalWidth===160')
   check('activate uploaded PNG in actual character stage',page.locator('#portrait-avatar').evaluate('(e)=>e.src.includes("/api/")'))
   artifacts=Path(os.environ.get('COMPANION_DESKTOP_SCREENSHOTS',str(OUT)));artifacts.mkdir(parents=True,exist_ok=True)
   page.screenshot(path=str(artifacts/'desktop-app-character-manager.png'))
   page.locator('[data-desktop-action=collapse]').click();page.wait_for_function('()=>document.body.classList.contains("desktop-collapsed")')
   check('collapse preserves uploaded character in same page',page.locator('#portrait-avatar').evaluate('(e)=>e.naturalWidth===160') and page.evaluate('async()=>(await companionDesktop.getState()).windowCount===1'))
   page.screenshot(path=str(artifacts/'desktop-app-compact.png'))
   state=page.evaluate('()=>companionDesktop.setClickThrough(true)');check('actual app can enable timed click-through',state['clickThrough'])
   page.evaluate('()=>companionDesktop.restore()');check('restore recovers actual app pointer state',not page.evaluate('async()=>(await companionDesktop.getState()).clickThrough'))
   state=page.evaluate('()=>companionDesktop.getState()')
   if state['recoveryShortcut']:
    page.evaluate('()=>companionDesktop.hide()');page.wait_for_timeout(100);check('real hide sets explicit host media guard',page.evaluate('async()=>window.companionDesktopHidden && !(await companionDesktop.getState()).visible'))
    hidden_audio=page.evaluate('''async()=>{
     const descriptor=Object.getOwnPropertyDescriptor(document,'hidden'), originalFetch=window.fetch, OriginalAudio=window.Audio;
     const originalSpeak=window.speechSynthesis?.speak,oldLocal=app.local_voice_available,oldSelected=selectedVoice;
     const counts={speechRequests:0,audioObjects:0,synthesisCalls:0};
     try{
      Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});
      app.local_voice_available=true;selectedVoice='';
      window.fetch=(input,...options)=>{if(String(typeof input==='string'?input:input.url).includes('/api/speech')){counts.speechRequests++;return Promise.reject(new Error('Unexpected hidden speech'));}return originalFetch(input,...options);};
      window.Audio=function(...args){counts.audioObjects++;return new OriginalAudio(...args);};
      if(window.speechSynthesis)window.speechSynthesis.speak=()=>{counts.synthesisCalls++;};
      await speak('隐藏窗口不应开始这次朗读');
      return {documentHidden:document.hidden,hostHidden:window.companionDesktopHidden,...counts};
     }finally{
      window.fetch=originalFetch;window.Audio=OriginalAudio;app.local_voice_available=oldLocal;selectedVoice=oldSelected;
      if(window.speechSynthesis)window.speechSynthesis.speak=originalSpeak;
      if(descriptor)Object.defineProperty(document,'hidden',descriptor);else delete document.hidden;
     }
    }''');report['hidden_audio_probe']=hidden_audio
    check('native hidden flag blocks new speech when document.hidden is false',hidden_audio=={'documentHidden':False,'hostHidden':True,'speechRequests':0,'audioObjects':0,'synthesisCalls':0})
    page.evaluate('()=>companionDesktop.restore()');page.wait_for_timeout(100);check('real app restores after hide',page.evaluate('async()=>!window.companionDesktopHidden && (await companionDesktop.getState()).visible'))
   check('actual app has no JavaScript page exceptions',not errors);report['page_errors']=errors
   owned=[proc for proc in psutil.Process(desktop.pid).children(recursive=True) if is_backend(proc) or proc.name().lower()=='focus-x11'];page.evaluate('()=>companionDesktop.quit()');desktop.wait(timeout=8)
   deadline=time.monotonic()+4
   while time.monotonic()<deadline and any(proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE for proc in owned):time.sleep(.1)
   check('desktop quit stops owned backend and focus helper',all(not proc.is_running() or proc.status()==psutil.STATUS_ZOMBIE for proc in owned))
   report['passed']=True
except Exception as error:report.update({'passed':False,'error':str(error)})
finally:
 for child in reversed(children):
  if child.poll() is None:
   child.terminate()
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
 (OUT/('windows-bundled-app-smoke.json' if WINDOWS else 'bundled-app-smoke.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['passed']:raise SystemExit(1)
