"""PC viewport layout checks. CSS mode simulation is not native Windows acceptance."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--chrome',required=True);parser.add_argument('--css-source',type=Path);args=parser.parse_args()
out=args.out;out.mkdir(parents=True,exist_ok=True)
f=CharacterHTTPTests();f.setUp();r={'scope':'isolated Chrome layout; no native desktop or character acceptance','cases':{},'errors':[]}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=args.chrome,args=['--no-sandbox'])
  c=b.new_context(viewport={'width':1280,'height':900});c.tracing.start(screenshots=True,snapshots=True,sources=True);p=c.new_page();p.on('pageerror',lambda e:r['errors'].append(str(e)))
  if args.css_source:p.route('**/study-room.css',lambda route:route.fulfill(body=args.css_source.read_text(),content_type='text/css'))
  p.goto(f'http://127.0.0.1:{f.server.server_port}');p.wait_for_function('()=>window.CompanionStudy')
  def measure(name):
   a=p.locator('.study-desk').bounding_box();d=p.locator('.interaction-area').bounding_box();send=p.locator('#send-message').bounding_box()
   gap=round(d['y']-a['y']-a['height'],2)
   r['cases'][name]={'gap_px':gap,'adjacent':abs(gap)<=1,'input_in_view':send['y']>=0 and send['y']+send['height']<=p.viewport_size['height']}
   p.screenshot(path=str(out/(name+'.png')))
  measure('idle')
  p.locator('#study-goal').fill('求导并检查答案');p.locator('#study-main').click();p.locator('#study-main').click();measure('paused')
  # Inject text only to exercise the maximum reply-summary layout, not model quality.
  p.evaluate("()=>{document.querySelector('#current-reply').hidden=false;document.querySelector('#current-reply-text').textContent='根据教材逐步核对计算。'.repeat(40)}");measure('reply')
  p.set_viewport_size({'width':1024,'height':600});measure('short-window')
  p.locator('#study-view').click();r['cases']['immersive']=not p.locator('.study-desk').is_visible() and not p.locator('.interaction-area').is_visible();p.locator('#study-view').click()
  for cls in ['desktop-collapsed','desktop-display-output']:
   p.evaluate('(cls)=>document.body.classList.add(cls)',cls);r['cases'][cls]=not p.locator('.study-desk').is_visible() and not p.locator('.interaction-area').is_visible();p.evaluate('(cls)=>document.body.classList.remove(cls)',cls)
  c.tracing.stop(path=str(out/'trace.zip'));b.close()
finally:
 f.tearDown();(out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False))

assert not r['errors'],r['errors']
assert all(all(case[k] for k in ['adjacent','input_in_view']) if isinstance(case,dict) else case for case in r['cases'].values()),r['cases']
