"""Desktop-only delayed refresh regression; isolated server, no real Bili/model.
Run with --ui-source pointing to the frozen old source for a negative control.
"""
from pathlib import Path
import argparse,json,platform
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--chrome',required=True);parser.add_argument('--ui-source',type=Path);args=parser.parse_args()
out=args.out;out.mkdir(parents=True,exist_ok=True)
f=CharacterHTTPTests();f.setUp();f.app.integrations().output.set_material('M1: f(x)=x²，f′(x)=2x。',True)
r={'scope':'desktop Chrome, isolated HTTP; no Windows/real Bili acceptance'}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=args.chrome,args=['--no-sandbox'])
  c=b.new_context(viewport={'width':1280,'height':900},record_video_dir=str(out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True)
  p=c.new_page();requests=[];errors=[];p.on('request',lambda request:requests.append({'method':request.method,'path':request.url.split('/api/')[-1]}));p.on('pageerror',lambda error:errors.append(str(error)))
  if args.ui_source:p.route('**/connectors-ui.js',lambda route:route.fulfill(body=args.ui_source.read_text(),content_type='application/javascript'))
  p.goto(f'http://127.0.0.1:{f.server.server_port}');p.wait_for_function('()=>window.CompanionApp?.core.get().state')
  p.locator('#open-companion-controls').click();p.get_by_role('button',name='微信与直播连接').click();p.get_by_role('button',name='哔哩哔哩直播预览',exact=True).click()
  p.get_by_text('本节教材',exact=True).click();field=p.get_by_label('本场公开教材',exact=True);field.fill('草稿 A')
  requests.clear()
  held=[];p.route('**/api/connectors/status',lambda route:held.append(route));p.get_by_role('button',name='刷新',exact=True).click();p.wait_for_timeout(100);assert held
  text='草稿 B：由导数定义计算 f′(3)，保留尚未提交的材料。';field.fill(text);field.evaluate('(el)=>el.setSelectionRange(5,12)')
  r['before']=field.evaluate('(el)=>({value:el.value,focused:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd,open:el.closest("details").open})')
  p.screenshot(path=str(out/'before-response.png'));held[0].continue_();p.wait_for_timeout(300)
  r['after']=field.evaluate('(el)=>({value:el.value,focused:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd,open:el.closest("details").open})')
  r['server_material']=f.app.integrations().output.material['text'];p.screenshot(path=str(out/'after-response.png'))
  r['requests']=list(requests);r['errors']=errors;r['environment']={'platform':platform.platform(),'chrome':b.version}
  r['checks']={'draft_unchanged':r['before']['value']==r['after']['value'],'editing_context_unchanged':r['before']==r['after'],'no_browser_write':all(x['method']=='GET' for x in requests),'server_material_unchanged':r['server_material']=='M1: f(x)=x²，f′(x)=2x。','no_browser_error':not errors}
  # A refresh must not steal focus from an unrelated control.
  p.unroute('**/api/connectors/status');held.clear();p.route('**/api/connectors/status',lambda route:held.append(route))
  p.get_by_role('button',name='刷新',exact=True).click();p.wait_for_timeout(100)
  p.locator('.close-layer').focus();assert p.locator('.close-layer').evaluate('(el)=>document.activeElement===el');held[0].continue_();p.wait_for_timeout(200)
  r['checks']['no_focus_theft']=p.locator('.close-layer').evaluate('(el)=>document.activeElement===el')
  c.tracing.stop(path=str(out/'trace.zip'));c.close();b.close()
finally:
 f.tearDown();(out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False))

assert all(r['checks'].values()),r['checks']
