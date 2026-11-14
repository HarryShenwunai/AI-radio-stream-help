"""Real Chrome adverse-path review. Synthetic input/provider; never connects Bili."""
import argparse,json,time
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
from live_output_browser_smoke import MATERIAL,ANSWER,QUESTION,tone
from companion_runtime.live import LiveBinding,LiveIngress

p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
f=CharacterHTTPTests();f.setUp();service=f.app.integrations()
ingress=LiveIngress(LiveBinding('bilibili-open-live','123'),ttl_seconds=30,dedupe_seconds=60)
service.bili=SimpleNamespace(ingress=ingress,status=lambda:{'state':'local-test-fixture'})
service.output.set_material(MATERIAL,True);f.app.generate_once=lambda *a,**k:ANSWER;f.app.synthesize=lambda text:tone()
report={'scope':'isolated real HTTP and Chrome; synthetic events and test tone','cases':{},'errors':[]};base=f'http://127.0.0.1:{f.server.server_port}'
def record(name,ok,**evidence):report['cases'][name]={'passed':bool(ok),**evidence}
def job(event_id,answer=ANSWER):
 ingress.submit({'room_id':'123','event_id':event_id,'text':QUESTION})
 f.app.generate_once=lambda *a,**k:answer
 return f.post('connectors/bili/reply',{'event_id':event_id})
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=a.chrome,headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader'])
  ctx=browser.new_context(viewport={'width':1280,'height':960},record_video_dir=str(out/'video'));ctx.tracing.start(screenshots=True,snapshots=True,sources=True)
  host=ctx.new_page();host.on('pageerror',lambda e:report['errors'].append(str(e)))
  host.goto(base);host.wait_for_function('()=>window.CompanionApp?.core.get().state')
  host.locator('#open-companion-controls').click();host.get_by_role('button',name='微信与直播连接').click();host.get_by_role('button',name='哔哩哔哩直播预览',exact=True).click()
  host.get_by_text('本节教材',exact=True).click();draft='尚未保存的教材 Δx/Δt，不能被刷新覆盖。'
  host.get_by_label('本场公开教材',exact=True).fill(draft);host.get_by_role('button',name='刷新',exact=True).click();host.wait_for_timeout(150)
  actual=host.get_by_label('本场公开教材',exact=True).input_value();record('refresh_preserves_material',actual==draft,expected=draft,actual=actual)
  # Open the material disclosure if refresh collapsed it, and expose the actual field.
  host.locator('.live-material').evaluate('(el)=>el.open=true');host.screenshot(path=str(out/'01-material-refresh.png'))
  host.get_by_label('允许在直播中使用这份教材',exact=True).check();host.get_by_label('本场公开教材',exact=True).fill('修改后的教材')
  record('editing_revokes_previous_material_consent',not host.get_by_label('允许在直播中使用这份教材',exact=True).is_checked())
  host.locator('.live-material').evaluate('(el)=>el.open=false')
  host.locator('.close-layer').focus();focus=[]
  for _ in range(12):
   host.keyboard.press('Tab');focus.append(host.evaluate('()=>({tag:document.activeElement.tagName,text:document.activeElement.textContent.slice(0,40)})'))
  record('keyboard_can_reach_settings',any(x['tag']=='SUMMARY' for x in focus),focus=focus)
  review=job('keyboard-review');host.get_by_role('button',name='刷新',exact=True).click();host.wait_for_timeout(100)
  host.locator('.close-layer').focus();review_focus=[]
  for _ in range(14):
   host.keyboard.press('Tab');review_focus.append(host.evaluate('()=>document.activeElement.tagName'))
  record('keyboard_review_can_reach_settings','SUMMARY' in review_focus,focus=review_focus)
  # Burst/long host-side input: valid events, no network or synthetic online counts.
  for i in range(15):ingress.submit({'room_id':'123','event_id':'burst-'+str(i),'text':('较长数学问题 Δx/Δt '+str(i)+' ') * 12})
  host.get_by_role('button',name='刷新',exact=True).click();host.wait_for_timeout(100)
  host.get_by_role('button',name='播放这条回答',exact=True).scroll_into_view_if_needed()
  first=host.locator('.live-workspace > *').first
  record('review_stays_before_burst_questions',first.get_attribute('class')=='live-answer')
  host.locator('.experience-body').evaluate('(el)=>el.scrollTop=0');host.screenshot(path=str(out/'02-review-priority.png'))
  for width in [390,1280]:
   host.set_viewport_size({'width':width,'height':720});host.locator('.live-question').last.scroll_into_view_if_needed()
   b=host.get_by_role('button',name='停止播放',exact=True).bounding_box()
   ok=host.evaluate('()=>document.documentElement.scrollWidth<=innerWidth') and b and 0<=b['y'] and b['y']+b['height']<=720
   record('burst_layout_'+str(width),ok);host.screenshot(path=str(out/f'02-burst-{width}.png'))
  # Deliberately reject browser playback, exercising the production error branch.
  denied=browser.new_context(viewport={'width':800,'height':600},record_video_dir=str(out/'denied-video'));denied.tracing.start(screenshots=True,snapshots=True,sources=True)
  denied.add_init_script("HTMLMediaElement.prototype.play=function(){return Promise.reject(new DOMException('Injected autoplay denial','NotAllowedError'));}")
  stage=denied.new_page();path=f.post('connectors/bili/output/open',{})['path'];stage.goto(base+path);stage.get_by_role('button',name='启用本页音频').click()
  item=job('denied');f.post('connectors/bili/approve',{'id':item['id'],'confirm_output':True})
  for _ in range(20):
   stage.wait_for_timeout(150)
   if service.output.jobs[item['id']]['state']=='failed':break
  record('audio_denial_visible_and_stopped',stage.locator('#status').is_visible() and stage.locator('#enable').is_visible() and stage.evaluate('()=>active===null'),status_text=stage.locator('#status').inner_text(),state=service.output.jobs[item['id']]['state'])
  stage.screenshot(path=str(out/'03-audio-denied.png'));denied.tracing.stop(path=str(out/'denied-trace.zip'));denied.close()
  # Narrow output must not silently play an answer clipped outside the viewport.
  normal=browser.new_context(viewport={'width':390,'height':720},record_video_dir=str(out/'output-video'));normal.tracing.start(screenshots=True,snapshots=True,sources=True)
  stage=normal.new_page();stage.goto(base+path);stage.get_by_role('button',name='启用本页音频').click()
  long='这是用于检查字幕容纳能力的长回答，不是模型质量验收。'*25
  item=job('long',long[:690]);f.post('connectors/bili/approve',{'id':item['id'],'confirm_output':True});stage.wait_for_timeout(800)
  info=stage.evaluate("()=>({overflow:document.documentElement.scrollHeight>innerHeight||document.documentElement.scrollWidth>innerWidth,active:Boolean(active),statusVisible:!status.hidden,text:status.textContent})")
  record('long_output_not_silently_clipped',not info['overflow'] and (info['active'] or info['statusVisible']),**info)
  stage.screenshot(path=str(out/'04-long-output.png'),full_page=True)
  # Return to a normal output size; corrupt WAV must be visibly refused.
  stage.close();stage=normal.new_page();stage.set_viewport_size({'width':1280,'height':720});stage.goto(base+path);stage.get_by_role('button',name='启用本页音频').click()
  f.app.synthesize=lambda text:b'not-a-wave-file'
  item=job('corrupt');f.post('connectors/bili/approve',{'id':item['id'],'confirm_output':True});stage.wait_for_timeout(700)
  record('corrupt_audio_is_visible_failure',stage.locator('#status').is_visible() and service.output.jobs[item['id']]['state']=='failed')
  stage.screenshot(path=str(out/'05-corrupt-audio.png'))
  stage.close();stage=normal.new_page();stage.set_viewport_size({'width':1280,'height':720});stage.goto(base+path);stage.get_by_role('button',name='启用本页音频').click()
  f.app.synthesize=lambda text:tone()
  item=job('network');f.post('connectors/bili/approve',{'id':item['id'],'confirm_output':True})
  stage.wait_for_function('()=>active&&!active.audio.paused')
  began=time.monotonic();stage.route('**/api/live-output',lambda route:route.abort())
  stage.wait_for_function('()=>active===null&&!status.hidden',timeout=2000)
  elapsed=(time.monotonic()-began)*1000
  stage.wait_for_timeout(2200);snapshot=service.output.status()
  record('disconnect_stops_and_reaps_consumer',elapsed<1500 and service.output.jobs[item['id']]['state']=='failed',stop_ms=elapsed)
  stage.screenshot(path=str(out/'06-disconnected.png'))
  normal.tracing.stop(path=str(out/'output-trace.zip'));normal.close()
  record('no_uncaught_browser_errors',not report['errors'])
  ctx.tracing.stop(path=str(out/'host-trace.zip'));ctx.close();browser.close()
finally:
 f.app.STOP.set()
 for svc in f.app.INTEGRATIONS.values():svc.close()
 f.tearDown();(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({name:item['passed'] for name,item in report['cases'].items()}))
