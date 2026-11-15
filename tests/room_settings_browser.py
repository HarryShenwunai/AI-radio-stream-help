"""Same PC script against frozen old and new UI; input is a verbatim user request."""
from pathlib import Path
import argparse,json,os
from playwright.sync_api import sync_playwright
import test_character_http
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--with-character',action='store_true');p.add_argument('--chrome',default=os.environ.get('COMPANION_CHROME','/usr/bin/chromium'));p.add_argument('--model',type=Path);p.add_argument('--runtime-dir',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
if a.with_character and (not a.model or not a.runtime_dir):p.error('--with-character requires --model and --runtime-dir')
old=os.environ.get('COMPANION_DEFAULT_LIVE2D')
if a.with_character:os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve())
f=test_character_http.CharacterHTTPTests();f.setUp()
if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
if a.with_character:
 class Runtime:
  def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js'}
  def read_core(self):return (a.runtime_dir/'live2dcubismcore.min.js').read_bytes()
  def read_bundle(self):return (a.runtime_dir/'build/owner-live2d-runtime.js').read_bytes()
 f.app.live2d_runtime=lambda:Runtime()
r={'checks':{},'errors':[],'input_source':'User conversation, not generated sample','topic':'检查uiux和直播室设置的差异','question':'人物你有了吗','scope':'isolated local PC Chrome / no platform or model generation'}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox']);c=b.new_context(viewport={'width':1440,'height':900},record_video_dir=str(a.out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True);page=c.new_page();page.on('pageerror',lambda e:r['errors'].append(str(e)));base=f'http://127.0.0.1:{f.server.server_port}';page.goto(base);page.wait_for_function('()=>CompanionApp?.core.get().state');page.screenshot(path=str(a.out/'01-main-empty.png'));r['checks']['no_seeded_welcome']=not f.state()['messages'];page.goto(base+'/room.html');page.wait_for_function('()=>window.RoomPreview');page.wait_for_timeout(200)
  if a.with_character:page.wait_for_function('()=>RoomPreview.scene.ready&&RoomPreview.scene.getDiagnostics().available',timeout=60000)
  r['checks']['canvas_empty_fields_hidden']=page.locator('#topic').inner_text()=='' and page.locator('#question').inner_text()==''
  r['checks']['settings_do_not_overlap_canvas']=page.evaluate('()=>{const a=document.querySelector("#room").getBoundingClientRect(),b=document.querySelector("#controls").getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top;}')
  page.screenshot(path=str(a.out/'02-room-empty.png'))
  page.locator('#topic-input').fill(r['topic']);page.locator('button[data-mode=question]').click();r['checks']['selecting_scene_is_draft_only']=page.locator('#room').get_attribute('data-mode')=='focus'
  page.locator('#question-input').fill(r['question'])
  if page.locator('#apply-settings').count():page.locator('#apply-settings').click()
  else:page.locator('#apply-topic').click();page.locator('#apply-question').click()
  r['checks']['apply_uses_user_text']=page.locator('#topic').inner_text()==r['topic'] and page.locator('#question').inner_text()==r['question'];page.screenshot(path=str(a.out/'03-settings-applied.png'))
  page.reload();page.wait_for_function('()=>window.RoomPreview');page.wait_for_timeout(200);r['checks']['reload_keeps_applied_settings']=page.locator('#topic').inner_text()==r['topic'] and page.locator('#question').inner_text()==r['question']
  if page.locator('#apply-settings').count():
   page.locator('button[data-mode=focus]').click();page.locator('#apply-settings').click();page.locator('#timer-toggle').click();page.wait_for_timeout(700);assert page.evaluate('()=>RoomPreview.snapshot().focus.phase')=='running';page.locator('#timer-toggle').click();before=page.evaluate('()=>RoomPreview.snapshot().focus.elapsed');page.wait_for_timeout(700);r['checks']['pause_not_counted']=page.evaluate('()=>RoomPreview.snapshot().focus.elapsed')==before
   page.reload();page.wait_for_function('()=>window.RoomPreview.loaded===true');r['checks']['reload_never_resumes_timer']=page.evaluate('()=>RoomPreview.snapshot().focus.phase')=='paused'
   page.locator('#topic-input').fill('禁止ai文案');page.locator('#apply-settings').click();r['checks']['changed_topic_cannot_keep_old_timer']=page.evaluate('()=>RoomPreview.snapshot().focus.phase')=='idle'
   page.locator('#clear-scene').click();page.reload();page.wait_for_function('()=>RoomPreview.loaded===true');r['checks']['clear_does_not_erase_source']=page.locator('#topic-input').input_value()=='禁止ai文案' and page.locator('#topic').inner_text()==''
   page.locator('#fullscreen-preview').click();page.wait_for_function('()=>document.fullscreenElement?.id==="preview-shell"');r['checks']['fullscreen_contains_no_controls']=page.evaluate('()=>document.fullscreenElement.querySelectorAll("button,input,textarea,select").length===0');ratio=page.locator('#room').bounding_box();r['checks']['preview_keeps_16_9']=abs(ratio['width']/ratio['height']-16/9)<.01;page.screenshot(path=str(a.out/'04-clean-preview.png'));page.evaluate('()=>document.exitFullscreen()');page.wait_for_function('()=>!document.fullscreenElement')
   prior=page.evaluate('()=>RoomPreview.snapshot().config.topic');large='禁止ai文案'*15;page.locator('#topic-input').fill(large);page.locator('#apply-settings').click();r['checks']['overflow_rejected_without_losing_input']=page.evaluate('()=>RoomPreview.snapshot().config.topic')==prior and page.locator('#topic-input').input_value()==large and '超出画面' in page.locator('#issue').inner_text();page.locator('#topic-input').fill('禁止ai文案')
   page.locator('#question-input').fill('<img src=x onerror=alert(1)>');page.locator('button[data-mode=question]').click();page.locator('#apply-settings').click();r['checks']['input_is_never_markup']=page.locator('#question img').count()==0
   sizes=[]
   for width,height in [(1024,768),(1280,720),(1920,1080)]:
    page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100);sizes.append({'width':width,'height':height,'no_horizontal_overflow':page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),'settings_separate':page.evaluate('()=>document.querySelector("#room").getBoundingClientRect().right<=document.querySelector("#controls").getBoundingClientRect().left')})
   r['sizes']=sizes;r['checks']['pc_sizes_keep_controls_separate']=all(s['no_horizontal_overflow'] and s['settings_separate'] for s in sizes)
   old_role=f.initial_id;f.create('第二位角色');page.reload();page.wait_for_function('()=>RoomPreview.loaded===true');r['checks']['other_role_never_loads_previous_scene_text']=page.locator('#topic').inner_text()=='' and page.locator('#question').inner_text()==''
  r['checks']['no_browser_error']=not r['errors'];r['passed']=all(r['checks'].values());r['environment']={'chrome':b.version};c.tracing.stop(path=str(a.out/'trace.zip'));c.close();b.close()
finally:f.tearDown();(a.out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False));assert r['passed']
