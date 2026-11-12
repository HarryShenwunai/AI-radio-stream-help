"""Native Electron window/IPC check on an authenticated local Xvfb display.

A synthetic local page is used. This is not the complete product or target-OS
focus/compositor/fullscreen verification. Does not access microphones/accounts.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import datetime,json,os,secrets,shutil,socket,subprocess,tempfile,threading,time,urllib.request
import psutil
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
DESKTOP=ROOT/'desktop';OUT=DESKTOP/'test-results';OUT.mkdir(exist_ok=True)
XVFB=Path(os.environ.get('COMPANION_XVFB',shutil.which('Xvfb') or '/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'))
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/':
   body=b'''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/desktop.css"><script defer src="/fixture.js"></script><script defer src="/desktop.js"></script></head><body><main class="shell"><section class="portrait"><div class="illustration"><img alt="synthetic fixture" src="/figure.svg"></div></section><section class="workspace"><h1>Offline desktop test fixture</h1><input id="input"></section></main><div id="toast" hidden></div></body></html>''';typ='text/html; charset=utf-8'
  elif self.path=='/fixture.js':body=b'window.stopVoice=()=>{window.paused=(window.paused||0)+1}; window.toast=(text)=>{window.lastToast=text};';typ='text/javascript'
  elif self.path=='/figure.svg':body=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 400"><circle cx="125" cy="90" r="60" fill="#d2a6bf"/><rect x="65" y="155" width="120" height="220" rx="50" fill="#9578b3"/></svg>';typ='image/svg+xml'
  elif self.path in ('/desktop.css','/desktop.js'):body=(ROOT/'app/static'/self.path[1:]).read_bytes();typ='text/css' if self.path.endswith('.css') else 'text/javascript'
  else:self.send_response(404);self.end_headers();return
  self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(body)
def port():
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'native Electron window and renderer bridge against local synthetic page on Xvfb','checks':[],'actual_microphone_or_model_tests':0,'limitations':['No compositor/window-manager user-desktop verification','No target Windows/macOS or fullscreen game coverage','No actual underlying-window pointer hit-test','No model/voice quality test']}
def check(name,ok):
 assert ok,name
 report['checks'].append({'name':name,'result':'passed'})
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
process=None;xserver=None
try:
 with tempfile.TemporaryDirectory(prefix='desktop-host-check-') as temp:
  temp=Path(temp);display=':92';auth=temp/'Xauthority';cookie=secrets.token_hex(16)
  subprocess.run(['xauth','-f',str(auth),'add',display,'MIT-MAGIC-COOKIE-1',cookie],capture_output=True,check=True)
  auth.chmod(0o600)
  xserver=subprocess.Popen([str(XVFB),display,'-screen','0','1440x1000x24','-nolisten','tcp','-auth',str(auth)],stdout=subprocess.DEVNULL,stderr=(temp/'xvfb.log').open('w'))
  time.sleep(.5);assert xserver.poll() is None
  debugging=port();env={**os.environ,'DISPLAY':display,'XAUTHORITY':str(auth),'COMPANION_DATA':str(temp/'data')}
  binary=os.environ.get('COMPANION_DESKTOP_BINARY')
  command=([binary] if binary else [str(DESKTOP/'node_modules/electron/dist/electron'),str(DESKTOP)])+['--backend-url='+f'http://127.0.0.1:{server.server_port}','--remote-debugging-port='+str(debugging),'--disable-gpu','--smoke-test','--user-data-dir='+str(temp/'electron-data')]
  report['binary_kind']='packaged host' if binary else 'development Electron host'
  started=time.monotonic()
  if os.environ.get('COMPANION_DESKTOP_TEST_NO_SANDBOX')=='1':command.append('--no-sandbox');report['cloud_test_no_sandbox']=True
  process=subprocess.Popen(command,env=env,stdout=(temp/'electron.stdout').open('w'),stderr=(temp/'electron.stderr').open('w'))
  end=time.monotonic()+20
  while time.monotonic()<end:
   if process.poll() is not None:raise RuntimeError((temp/'electron.stderr').read_text()[-1600:])
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{debugging}/json/version',timeout=.3) as response:json.load(response)
    break
   except Exception:time.sleep(.1)
  else:raise RuntimeError('Electron CDP did not start')
  with sync_playwright() as p:
   browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{debugging}');page=browser.contexts[0].pages[0];page.wait_for_selector('.desktop-tools')
   state=page.evaluate('()=>window.companionDesktop.getState()');report['initial_state']=state
   report['compact_ready_seconds_with_cdp']=round(time.monotonic()-started,3)
   procs=[psutil.Process(process.pid)]+psutil.Process(process.pid).children(recursive=True)
   rss=sum(proc.memory_info().rss for proc in procs if proc.is_running())
   report['single_process_tree_rss_sum_kib']=round(rss/1024)
   try:
    report['single_process_tree_pss_sum_kib']=round(sum(proc.memory_full_info().pss for proc in procs if proc.is_running())/1024)
   except (psutil.AccessDenied,psutil.NoSuchProcess,AttributeError):
    report['single_process_tree_pss_sum_kib']=None
   baseline_cpu=sum(sum(proc.cpu_times()[:2]) for proc in procs if proc.is_running());idle_started=time.monotonic();page.wait_for_timeout(5000)
   current_procs=[psutil.Process(process.pid)]+psutil.Process(process.pid).children(recursive=True)
   current_cpu=sum(sum(proc.cpu_times()[:2]) for proc in current_procs if proc.is_running())
   elapsed=time.monotonic()-idle_started
   report['idle_observation_seconds']=round(elapsed,3);report['idle_cpu_percent_one_core']=round(max(0,current_cpu-baseline_cpu)/elapsed*100,2)
   report['resource_scope']='Single Electron parent/descendant RSS/PSS snapshot and five-second idle CPU interval; RSS can count shared pages repeatedly. Fixture Python/Xvfb excluded, GPU disabled, no LLM/TTS. Not p95, steady workload or target-device budget.'
   check('one native window and compact renderer',state['windowCount']==1 and not state['expanded'] and page.locator('body').evaluate('(e)=>e.classList.contains("desktop-collapsed")'))
   check('renderer has no Node integration',page.evaluate('()=>typeof require==="undefined" && typeof process==="undefined"'))
   check('preload exposes only limited host operations',set(page.evaluate('()=>Object.keys(window.companionDesktop)'))=={'getState','setExpanded','setClickThrough','hide','restore','quit','onState'})
   rejected=page.evaluate('async()=>{try{await window.companionDesktop.setExpanded("true");return false}catch{return true}}');check('native IPC rejects malformed argument',rejected)
   page.screenshot(path='/workspace/dist/desktop-shell-compact.png')
   page.locator('[data-desktop-action=stop]').click();check('compact stop control pauses local media',page.evaluate('()=>window.paused')>=1)
   state=page.evaluate('()=>window.companionDesktop.setExpanded(true)');page.wait_for_function('()=>!document.body.classList.contains("desktop-collapsed")')
   check('expand reuses one native window',state['expanded'] and state['windowCount']==1 and page.evaluate('()=>innerWidth')>=1000)
   page.screenshot(path='/workspace/dist/desktop-shell-expanded.png')
   state=page.evaluate('()=>window.companionDesktop.setExpanded(false)');page.wait_for_function('()=>document.body.classList.contains("desktop-collapsed")')
   check('collapse restores compact bounds',not state['expanded'] and page.evaluate('()=>innerWidth')<=330)
   state=page.evaluate('()=>window.companionDesktop.setClickThrough(true)');check('click-through state accepted with timed recovery',state['clickThrough'] and state['clickThroughTimeoutSeconds']==60)
   state=page.evaluate('()=>window.companionDesktop.restore()');check('restore clears click-through',not state['clickThrough'] and state['visible'])
   if state['recoveryShortcut']:
    hidden=page.evaluate('()=>window.companionDesktop.hide()');check('explicit hide stops local media',not hidden['visible'] and page.evaluate('()=>window.paused')>=1)
    state=page.evaluate('()=>window.companionDesktop.restore()');check('hidden native window can recover',state['visible'] and state['windowCount']==1)
   else:
    check('hide disabled without registered recovery shortcut',page.locator('[data-desktop-action=hide]').is_disabled())
   previous=page.url;page.evaluate('()=>{window.location.href="https://example.invalid/"}');page.wait_for_timeout(200);check('off-origin navigation prevented',page.url==previous)
   popup=page.evaluate('()=>window.open("https://example.invalid/")===null');check('new windows denied',popup and len(browser.contexts[0].pages)==1)
   report['runtime_version']=page.evaluate('()=>navigator.userAgent')
   report['passed']=True
   page.evaluate('()=>window.companionDesktop.quit()')
  process.wait(timeout=5)
except Exception as error:
 report.update({'passed':False,'error':str(error)})
finally:
 if process and process.poll() is None:process.terminate();process.wait(timeout=5)
 if xserver:xserver.terminate();xserver.wait(timeout=5)
 server.shutdown();server.server_close()
 (OUT/('packaged-smoke.json' if os.environ.get('COMPANION_DESKTOP_BINARY') else 'smoke.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['passed']:raise SystemExit(1)
