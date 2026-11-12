"""Linux X11/xfwm4 probe for real pointer routing and initial focus.

Uses local synthetic content and XTest on an authenticated private display.
This verifies this Linux stack only, not other compositors or fullscreen games.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import ctypes as C,ctypes.util,datetime,json,os,re,secrets,shutil,socket,subprocess,tempfile,threading,time,urllib.request
from PIL import ImageGrab
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];DESKTOP=ROOT/'desktop';OUT=DESKTOP/'test-results';OUT.mkdir(exist_ok=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/':data=b'''<!doctype html><html><head><meta charset="utf-8"><title>Native desktop probe</title><link rel="stylesheet" href="/desktop.css"><script defer src="/fixture.js"></script><script defer src="/desktop.js"></script></head><body><main class="shell"><section class="portrait"><div class="illustration"><img src="/figure.svg" alt="synthetic shape"></div></section><section class="workspace"><input></section></main></body></html>''';typ='text/html'
  elif self.path=='/fixture.js':data=b'window.clickCount=0;window.stopVoice=()=>{};window.toast=()=>{};document.addEventListener("click",()=>window.clickCount++);';typ='text/javascript'
  elif self.path=='/figure.svg':data=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 400"><circle cx="125" cy="90" r="60" fill="#d2a6bf"/><rect x="65" y="155" width="120" height="220" rx="50" fill="#9578b3"/></svg>';typ='image/svg+xml'
  elif self.path in ['/desktop.js','/desktop.css']:data=(ROOT/'app/static'/self.path[1:]).read_bytes();typ='text/javascript' if self.path.endswith('.js') else 'text/css'
  else:self.send_response(404);self.end_headers();return
  self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
def freeport():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
X=C.CDLL(ctypes.util.find_library('X11'));T=C.CDLL(ctypes.util.find_library('Xtst'))
D=C.c_void_p;W=C.c_ulong;I=C.c_int;U=C.c_uint;L=C.c_long
for name,argtypes,restype in [
 ('XOpenDisplay',[C.c_char_p],D),('XDefaultRootWindow',[D],W),('XCreateSimpleWindow',[D,W,I,I,U,U,U,W,W],W),
 ('XMapWindow',[D,W],I),('XStoreName',[D,W,C.c_char_p],I),('XSelectInput',[D,W,L],I),('XMoveResizeWindow',[D,W,I,I,U,U],I),
 ('XSetInputFocus',[D,W,I,W],I),('XGetInputFocus',[D,C.POINTER(W),C.POINTER(I)],I),('XSync',[D,I],I),
 ('XPending',[D],I),('XNextEvent',[D,D],I),('XDestroyWindow',[D,W],I),('XCloseDisplay',[D],I),
 ('XTranslateCoordinates',[D,W,W,I,I,C.POINTER(I),C.POINTER(I),C.POINTER(W)],I),
 ('XInternAtom',[D,C.c_char_p,I],W),('XGetSelectionOwner',[D,W],W),
]:
 fn=getattr(X,name);fn.argtypes=argtypes;fn.restype=restype
T.XTestFakeMotionEvent.argtypes=[D,I,I,I,W];T.XTestFakeMotionEvent.restype=I
T.XTestFakeButtonEvent.argtypes=[D,U,I,W];T.XTestFakeButtonEvent.restype=I
class WMHints(C.Structure):
 _fields_=[('flags',L),('input',I),('initial_state',I),('icon_pixmap',W),('icon_window',W),('icon_x',I),('icon_y',I),('icon_mask',W),('window_group',W)]
class ClientData(C.Union):
 _fields_=[('l',L*5),('b',C.c_char*20)]
class ClientMessage(C.Structure):
 _fields_=[('type',I),('serial',W),('send_event',I),('display',D),('window',W),('message_type',W),('format',I),('data',ClientData)]
X.XSetWMHints.argtypes=[D,W,C.POINTER(WMHints)];X.XSetWMHints.restype=I
X.XSendEvent.argtypes=[D,W,I,L,D];X.XSendEvent.restype=I
report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'packaged Electron host on private Xvfb plus xfwm4 compositor and XTest; synthetic local page','checks':[],'model_or_microphone_tests':0,'limitations':['Only this Linux X11/xfwm4 configuration','No Windows/macOS, Wayland or fullscreen game validation','No user character art or actual backend/model in this probe']}
def check(name,passed):
 assert passed,name
 report['checks'].append({'name':name,'result':'passed'})
def focus(display):
 window=W();revert=I();X.XGetInputFocus(display,C.byref(window),C.byref(revert));return window.value
def clear_events(display):
 hits=0;event=(C.c_long*24)()
 while X.XPending(display):
  X.XNextEvent(display,C.byref(event));hits+=int(C.cast(C.byref(event),C.POINTER(I))[0]==4)
 return hits
def click(display,x,y):
 T.XTestFakeMotionEvent(display,-1,x,y,0);T.XTestFakeButtonEvent(display,1,1,0);T.XTestFakeButtonEvent(display,1,0,0);X.XSync(display,0);time.sleep(.15)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
children=[];display=None;background=None
try:
 with tempfile.TemporaryDirectory(prefix='desktop-native-probe-') as td:
  td=Path(td);display_name=':93';auth=td/'Xauthority';subprocess.run(['xauth','-f',str(auth),'add',display_name,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],capture_output=True,check=True);auth.chmod(0o600)
  env={**os.environ,'DISPLAY':display_name,'XAUTHORITY':str(auth)}
  xvfb=os.environ.get('COMPANION_XVFB') or shutil.which('Xvfb') or '/workspace/.desktop-tools/xvfb/usr/bin/Xvfb'
  children.append(subprocess.Popen([xvfb,display_name,'-screen','0','1440x1000x24','-nolisten','tcp','-auth',str(auth)],stdout=subprocess.DEVNULL,stderr=(td/'xvfb.log').open('w')));time.sleep(.4)
  children.append(subprocess.Popen(['xfwm4','--compositor=on','--vblank=off'],env=env,stdout=subprocess.DEVNULL,stderr=(td/'wm.log').open('w')));time.sleep(.8)
  os.environ['XAUTHORITY']=str(auth)
  display=X.XOpenDisplay(display_name.encode());assert display
  root=X.XDefaultRootWindow(display);owner=X.XGetSelectionOwner(display,X.XInternAtom(display,b'_NET_WM_CM_S0',0));check('xfwm4 compositor owns X11 selection',owner!=0)
  background=X.XCreateSimpleWindow(display,root,0,0,1440,1000,0,0,0x336633);X.XStoreName(display,background,b'Probe background');hints=WMHints();hints.flags=3;hints.input=1;hints.initial_state=1;X.XSetWMHints(display,background,C.byref(hints));X.XSelectInput(display,background,1<<2);X.XMapWindow(display,background);X.XSync(display,0);time.sleep(.25)
  X.XMoveResizeWindow(display,background,0,0,1440,1000);message=ClientMessage();message.type=33;message.send_event=1;message.display=display;message.window=background;message.message_type=X.XInternAtom(display,b'_NET_ACTIVE_WINDOW',0);message.format=32;message.data.l[0]=1;X.XSendEvent(display,root,0,(1<<19)|(1<<20),C.byref(message));X.XSync(display,0);time.sleep(.25);before=focus(display);check('background test window receives initial focus',before==background)
  debug=freeport();binary=os.environ.get('COMPANION_DESKTOP_BINARY',str(ROOT/'.build/desktop/linux-unpacked/companion-desktop'))
  child=subprocess.Popen([binary,'--backend-url='+f'http://127.0.0.1:{server.server_port}','--remote-debugging-port='+str(debug),'--disable-gpu','--user-data-dir='+str(td/'electron-data')],env=env,stdout=subprocess.DEVNULL,stderr=(td/'electron.log').open('w'));children.append(child)
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   if child.poll() is not None:raise RuntimeError((td/'electron.log').read_text()[-1000:])
   try:
    urllib.request.urlopen(f'http://127.0.0.1:{debug}/json/version',timeout=.2).close();break
   except Exception:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{debug}');page=browser.contexts[0].pages[0];page.wait_for_selector('.desktop-tools');page.wait_for_timeout(500)
   check('passive compact startup preserves external keyboard focus',focus(display)==background)
   tree=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True);match=re.search(r'(0x[0-9a-f]+) "Native desktop probe"',tree);assert match,tree
   wid=int(match.group(1),16);x=I();y=I();childwin=W();X.XTranslateCoordinates(display,wid,root,0,0,C.byref(x),C.byref(y),C.byref(childwin));px=x.value+165;py=y.value+330
   img=ImageGrab.grab(xdisplay=display_name);img.save('/workspace/dist/desktop-shell-composited.png');pixel=img.getpixel((x.value+5,y.value+190))[:3];report['transparent_area_observed_rgb']=pixel
   check('transparent window reveals underlying test background',all(abs(a-b)<8 for a,b in zip(pixel,(51,102,51))))
   clear_events(display);old=page.evaluate('()=>clickCount');click(display,px,py);check('normal pointer hit reaches character window',page.evaluate('()=>clickCount')==old+1 and clear_events(display)==0)
   page.evaluate('()=>window.companionDesktop.setClickThrough(true)');page.wait_for_timeout(150);clear_events(display);old=page.evaluate('()=>clickCount');click(display,px,py);hits=clear_events(display)
   check('actual XTest pointer click passes to underlying window',hits==1 and page.evaluate('()=>clickCount')==old)
   page.evaluate('()=>window.companionDesktop.restore()');page.wait_for_timeout(150);clear_events(display);old=page.evaluate('()=>clickCount');click(display,px,py);check('pointer input recovers after explicit restore',page.evaluate('()=>clickCount')==old+1 and clear_events(display)==0)
   page.evaluate('()=>window.companionDesktop.setExpanded(true)');page.wait_for_timeout(150);check('explicit expand can take input focus',focus(display)!=background)
   page.evaluate('()=>window.companionDesktop.setExpanded(false)');page.wait_for_timeout(150);report['focus_after_collapse']=focus(display);report['background_window_id']=background;report['electron_window_id']=wid;check('collapse releases input focus to background',focus(display)==background)
   page.evaluate('()=>window.companionDesktop.quit()');child.wait(timeout=5);time.sleep(.2);report['passed']=True
except Exception as error:report.update({'passed':False,'error':str(error)})
finally:
 if display:
  if background:X.XDestroyWindow(display,background)
  X.XCloseDisplay(display)
 for child in reversed(children):
  if child.poll() is None:
   child.terminate()
   try:child.wait(timeout=3)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
 server.shutdown();server.server_close();(OUT/'native-window-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['passed']:raise SystemExit(1)
