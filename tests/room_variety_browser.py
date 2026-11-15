"""Actual PC interaction; original art only, blank second identity is a switch fixture."""
import argparse,json,os,subprocess,time
from pathlib import Path
from playwright.sync_api import sync_playwright
import test_character_http
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--baseline-ref');p.add_argument('--mutant-static-design',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=test_character_http.CharacterHTTPTests();f.setUp()
if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
second=f.create('切换检查');f.select(f.initial_id)
class Runtime:
 def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js'}
 def read_core(self):return (a.runtime_dir/'live2dcubismcore.min.js').read_bytes()
 def read_bundle(self):return (a.runtime_dir/'build/owner-live2d-runtime.js').read_bytes()
f.app.live2d_runtime=lambda:Runtime()
r={'scope':'Local Linux PC Chrome, original model and Core, no platform/Windows/independent acceptance','checks':{},'errors':[],'requests':[],'timings_ms':[],'fixture':'Second blank identity is a switching fault fixture, not new artwork','input_source':'verbatim user: 人物更多样 / 直播间设置更多样'}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader']);c=b.new_context(viewport={'width':1440,'height':900},record_video_dir=str(a.out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True)
  if a.baseline_ref:
   def content_handler(body,content_type):
    def handle(route):route.fulfill(body=body,content_type=content_type)
    return handle
   for name in ['room.js','room.html','room.css']:
    data=subprocess.check_output(['git','show',a.baseline_ref+':app/static/'+name]);c.route('**/'+name,content_handler(data,'text/html' if name.endswith('html') else 'text/css' if name.endswith('css') else 'application/javascript'))
  if a.mutant_static_design:
   source=(test_character_http.ROOT/'app/static/room.js').read_text().replace("node.dataset.layout=value.layout;node.dataset.theme=value.theme;","node.dataset.layout='right';node.dataset.theme='paper';");c.route('**/room.js',lambda route:route.fulfill(body=source,content_type='application/javascript'))
  page=c.new_page();page.on('pageerror',lambda e:r['errors'].append(str(e)));page.on('request',lambda q:r['requests'].append({'method':q.method,'path':q.url.split(str(f.server.server_port))[-1]}));base=f'http://127.0.0.1:{f.server.server_port}';page.goto(base);page.goto(base+'/room.html');page.wait_for_function('()=>window.RoomPreview?.loaded===true');page.wait_for_function('()=>RoomPreview.scene.ready&&RoomPreview.scene.getDiagnostics().available',timeout=60000)
  r['checks']['variety_controls_exist']=all(page.locator('#'+id).count()==1 for id in ['character-select','layout-select','theme-select','save-design','show-topic'])
  if r['checks']['variety_controls_exist']:
   with page.expect_popup() as opened:page.locator('#manage-characters').click()
   library=opened.value;library.wait_for_function('()=>window.CompanionApp?.ui.active==="studio"');r['checks']['manage_link_opens_real_identity_library']=library.locator('.identity-list .identity-item').count()==2;library.close()
   page.locator('#topic-input').fill('直播间设置更多样');page.locator('#question-input').fill('人物更多样');page.locator('button[data-mode=question]').click();page.locator('#apply-settings').click()
   page.locator('#layout-select').select_option('left');page.locator('#theme-select').select_option('forest');r['checks']['design_selection_is_draft']=page.evaluate('()=>RoomPreview.snapshot().config.layout')=='right';page.locator('#apply-settings').click();r['checks']['design_apply_is_explicit']=page.locator('#room').get_attribute('data-layout')=='left' and page.locator('#room').get_attribute('data-theme')=='forest'
   page.locator('#design-name').fill('直播间设置更多样');page.locator('#save-design').click();page.locator('#layout-select').select_option('small');page.locator('#theme-select').select_option('slate');page.locator('#apply-settings').click();page.locator('#load-design').click();r['checks']['load_does_not_apply']=page.locator('#room').get_attribute('data-layout')=='small';page.locator('#apply-settings').click();r['checks']['load_preserves_content']=page.locator('#topic-input').input_value()=='直播间设置更多样' and page.locator('#question-input').input_value()=='人物更多样' and page.locator('#room').get_attribute('data-layout')=='left'
   stored=page.evaluate('()=>JSON.parse(localStorage.getItem("room-settings:"+RoomPreview.snapshot().config.characterId+":designs"))');r['checks']['saved_design_has_no_dialogue_or_timer']=not any(key in stored[0]['design'] for key in ['topic','question','caption','focus','minutes'])
   page.reload();page.wait_for_function('()=>RoomPreview.loaded===true&&RoomPreview.scene.ready');r['checks']['designs_and_selection_survive_reload']=page.locator('#design-select option').count()==2 and page.locator('#room').get_attribute('data-layout')=='left' and page.locator('#room').get_attribute('data-theme')=='forest'
   page.locator('#show-topic').uncheck();page.locator('#show-question').uncheck();page.locator('#apply-settings').click();r['checks']['widget_visibility_keeps_source']=page.locator('#topic').is_hidden() and page.locator('#question-widget').is_hidden() and page.locator('#topic-input').input_value()=='直播间设置更多样';page.locator('#show-topic').check();page.locator('#show-question').check();page.locator('#apply-settings').click()
   for width,height in [(1024,768),(1440,900),(1920,1080)]:
    page.set_viewport_size({'width':width,'height':height})
    for layout in ['right','left','small']:
     for theme in ['paper','forest','slate']:
      page.locator('#layout-select').select_option(layout);page.locator('#theme-select').select_option(theme);start=time.monotonic();page.locator('#apply-settings').click();r['timings_ms'].append(round((time.monotonic()-start)*1000,2))
      assert page.locator('#room').get_attribute('data-layout')==layout and page.locator('#room').get_attribute('data-theme')==theme
      assert page.locator('#room').get_attribute('data-overflow')=='false',page.locator('#issue').inner_text()
      assert page.locator('#topic').is_visible() and page.locator('#question-widget').is_visible()
      assert page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth&&document.querySelector("#room").getBoundingClientRect().right<=document.querySelector("#controls").getBoundingClientRect().left')
      if width==1440 and (layout,theme) in [('right','paper'),('left','forest'),('small','slate')]:
       page.locator('#controls').evaluate('(n)=>n.scrollTop=0');page.screenshot(path=str(a.out/(layout+'-'+theme+'.png')))
   r['checks']['all_layout_theme_pc_combinations_fit']=True
   page.locator('#character-select').select_option(second);r['checks']['character_choice_is_draft']=page.evaluate('()=>RoomPreview.snapshot().config.characterId')==f.initial_id;page.locator('#apply-settings').click();page.wait_for_function('()=>RoomPreview.scene.ready&&RoomPreview.scene.getStats().state==="ready"');r['checks']['blank_role_clears_old_renderer']=page.locator('#character-canvas canvas').count()==0 and page.locator('#character-image').is_hidden() and page.locator('#character-status').inner_text()=='未启用角色';r['checks']['preview_does_not_switch_conversation_identity']=f.state()['active_character_id']==f.initial_id
   page.reload();page.wait_for_function('()=>RoomPreview.loaded===true&&RoomPreview.scene.ready');r['checks']['preview_character_persists']=page.locator('#character-select').input_value()==second and page.locator('#character-canvas canvas').count()==0
   page.locator('#character-select').select_option(f.initial_id);page.locator('#apply-settings').click();page.wait_for_function('()=>RoomPreview.scene.ready&&RoomPreview.scene.getDiagnostics().coreEvaluations>0',timeout=60000);r['checks']['return_to_original_draws_actual_core']=True
   f.post('characters/archive',{'id':second});page.locator('#topic-input').fill('禁止ai文案');page.locator('#refresh-characters').click();page.wait_for_function('()=>!document.querySelector("#refresh-characters").disabled');r['checks']['manual_refresh_excludes_archived_and_keeps_draft']=page.locator('#character-select option').count()==1 and page.locator('#topic-input').input_value()=='禁止ai文案';page.locator('#topic-input').fill('直播间设置更多样')
   page.locator('#fullscreen-preview').click();page.wait_for_function('()=>document.fullscreenElement');r['checks']['fullscreen_has_no_controls']=page.evaluate('()=>document.fullscreenElement.querySelectorAll("button,input,textarea,select,a").length===0');page.evaluate('()=>document.exitFullscreen()')
   page.locator('#design-select').select_option('直播间设置更多样');page.once('dialog',lambda d:d.dismiss());page.locator('#delete-design').click();r['checks']['delete_cancel_preserves_design']=page.locator('#design-select option').count()==2;page.once('dialog',lambda d:d.accept());page.locator('#delete-design').click();page.reload();page.wait_for_function('()=>RoomPreview.loaded');r['checks']['delete_confirm_persists']=page.locator('#design-select option').count()==1
   r['checks']['no_model_or_platform_requests']=not any(q['method']=='POST' or '/connectors/' in q['path'] for q in r['requests'])
  r['checks']['no_browser_errors']=not r['errors'];r['passed']=all(r['checks'].values());r['chrome']=b.version;r['video']=str(page.video.path());c.tracing.stop(path=str(a.out/'trace.zip'));c.close();b.close()
except Exception as e:r['failure']=str(e);raise
finally:f.tearDown();(a.out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps({'passed':r.get('passed'),'checks':r['checks']},ensure_ascii=False));raise SystemExit(0 if r['passed'] else 1)
