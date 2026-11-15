"""Actual computed-color checks; aesthetic approval remains external."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
import test_character_http
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--css-ref');p.add_argument('--mutant-muted',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=test_character_http.CharacterHTTPTests();f.setUp()
if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
class Runtime:
 def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js'}
 def read_core(self):return (a.runtime_dir/'live2dcubismcore.min.js').read_bytes()
 def read_bundle(self):return (a.runtime_dir/'build/owner-live2d-runtime.js').read_bytes()
f.app.live2d_runtime=lambda:Runtime()
def rgb(value):return [int(x) for x in re.findall(r'\d+',value)[:3]]
def contrast(a,b):
 def lum(c):
  channels=[x/255 for x in rgb(c)];channels=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in channels];return sum(x*w for x,w in zip(channels,[.2126,.7152,.0722]))
 x,y=lum(a),lum(b);return (max(x,y)+.05)/(min(x,y)+.05)
r={'scope':'Linux PC Chrome with original model/Core; no human aesthetic or Windows acceptance','checks':{},'samples':[],'errors':[],'requests':[],'model_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'thresholds':{'all_program_text':4.5,'enabled_control_text':4.5,'input_boundary':3},'input_source':'verbatim user text, not generated content'}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader']);c=b.new_context(viewport={'width':1440,'height':900},record_video_dir=str(a.out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True)
  if a.css_ref or a.mutant_muted:
   css=subprocess.check_output(['git','show',a.css_ref+':app/static/room.css']) if a.css_ref else (test_character_http.ROOT/'app/static/room.css').read_bytes()+b'\n.widget-label{color:var(--room-background)!important}'
   c.route('**/room.css',lambda route:route.fulfill(body=css,content_type='text/css'))
  page=c.new_page();page.on('pageerror',lambda e:r['errors'].append(str(e)));page.on('request',lambda req:r['requests'].append({'method':req.method,'url':req.url}));base=f'http://127.0.0.1:{f.server.server_port}';page.goto(base);page.goto(base+'/room.html');page.wait_for_function('()=>RoomPreview?.loaded&&RoomPreview.scene.ready&&RoomPreview.scene.getDiagnostics().available',timeout=60000)
  page.locator('#topic-input').fill('直播间设置更多样');page.locator('#question-input').fill('人物更多样')
  for theme in ['carbon','midnight','daylight']:
   page.locator('#theme-select').select_option(theme)
   for layout in ['right','left','small']:
    page.locator('#layout-select').select_option(layout)
    for mode in ['focus','question','break']:
     page.locator('button[data-mode='+mode+']').click();page.locator('#apply-settings').click()
     if mode=='focus':page.locator('#timer-toggle').click();page.locator('#timer-toggle').click()
     if mode=='break':page.locator('#break-toggle').click();page.locator('#break-toggle').click()
     data=page.evaluate('''()=>{const room=document.querySelector('#room'),s=getComputedStyle(room),ids=['topic','question','caption','clock','timer-state','break-status','room-state'];return {theme:room.dataset.theme,layout:room.dataset.layout,mode:room.dataset.mode,background:s.backgroundImage,mainColor:s.color,palette:RoomDesign.palette(room.dataset.theme),text:[...ids.map(id=>document.getElementById(id)),...room.querySelectorAll('.widget-label')].filter(n=>n.getClientRects().length).map(n=>({id:n.id||n.className,color:getComputedStyle(n).color})),model:{filter:getComputedStyle(document.querySelector('#character-canvas canvas')).filter,opacity:getComputedStyle(document.querySelector('#character-canvas canvas')).opacity}}}''')
     colors=re.findall(r'rgba?\([^)]+\)',data['background']);ratios=[{'id':t['id'],'ratio':min(contrast(t['color'],bg) for bg in colors)} for t in data['text']];data['ratios']=ratios;r['samples'].append(data)
     assert colors and ratios
     if not all(x['ratio']>=4.5 for x in ratios):r['checks']['program_text_contrast']=False;raise AssertionError('Computed program text contrast below predeclared 4.5: '+json.dumps(ratios))
     expected={tuple(bytes.fromhex(data['palette'][k][1:])) for k in ['background','ambient']};assert {tuple(rgb(color)) for color in colors}==expected;assert tuple(rgb(data['mainColor']))==tuple(bytes.fromhex(data['palette']['foreground'][1:]));
     assert data['model']=={'filter':'none','opacity':'1'}
     if layout=='right' and mode=='question':
      page.locator('#controls').evaluate('(n)=>n.scrollTop=0');page.screenshot(path=str(a.out/(theme+'-workspace.png')));page.locator('#hide-controls').click();page.locator('#fullscreen-preview').click();page.wait_for_function('()=>document.fullscreenElement');page.screenshot(path=str(a.out/(theme+'-preview.png')));page.evaluate('()=>document.exitFullscreen()');page.wait_for_function('()=>!document.fullscreenElement');page.locator('#show-controls').click()
  r['checks']['program_text_contrast']=True;r['checks']['theme_persists_across_modes_layouts']=all(s['theme']==r['samples'][i//9*9]['theme'] for i,s in enumerate(r['samples']));r['checks']['no_filter_or_opacity_change_to_character']=True
  pairs=[('#apply-settings','#apply-settings'),('#theme-select','#theme-select'),('#controls summary','#controls'),('#settings-state','body'),('.workspace-header>span','body')]
  r['operator_samples']=[]
  for fg,bg in pairs:
   for hover in [False,True]:
    if hover:page.locator(fg).hover()
    colors=page.evaluate('([fg,bg])=>{let node=document.querySelector(bg),color=getComputedStyle(node).backgroundColor;while(node.parentElement&&color==="rgba(0, 0, 0, 0)"){node=node.parentElement;color=getComputedStyle(node).backgroundColor;}return {foreground:getComputedStyle(document.querySelector(fg)).color,background:color,border:getComputedStyle(document.querySelector(fg)).borderTopColor};}',[fg,bg]);ratio=contrast(colors['foreground'],colors['background']);r['operator_samples'].append({'selector':fg,'hover':hover,'ratio':ratio,**colors});assert ratio>=4.5,(fg,hover,colors,ratio)
  r['checks']['operator_default_and_hover_contrast']=True
  colors=next(s for s in r['operator_samples'] if s['selector']=='#theme-select');assert contrast(colors['border'],colors['background'])>=3;r['checks']['input_boundary_contrast']=True
  key='room-settings:'+f.initial_id;page.add_init_script('(key=>{const p=JSON.parse(localStorage.getItem(key));if(p){p.config.theme="forest";p.draft.theme="slate";localStorage.setItem(key,JSON.stringify(p));}})('+json.dumps(key)+');');page.reload();page.wait_for_function('()=>RoomPreview.loaded');r['migration_observed']={'applied':page.locator('#room').get_attribute('data-theme'),'draft':page.locator('#theme-select').input_value()};r['checks']['old_saved_palette_and_draft_migrate_separately']=page.locator('#room').get_attribute('data-theme')=='midnight' and page.locator('#theme-select').input_value()=='daylight' and page.locator('#topic-input').input_value()=='直播间设置更多样'
  r['checks']['no_extra_model_or_platform_requests']=not any(q['method']=='POST' or '/connectors/' in q['url'] for q in r['requests']);r['checks']['no_browser_errors']=not r['errors'];r['passed']=all(r['checks'].values());r['video']=str(page.video.path());r['chrome']=b.version;c.tracing.stop(path=str(a.out/'trace.zip'));c.close();b.close()
except Exception as e:r['failure']=str(e);raise
finally:f.tearDown();(a.out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps({'passed':r.get('passed'),'checks':r['checks']},ensure_ascii=False));raise SystemExit(0 if r['passed'] else 1)
