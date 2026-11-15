"""Real owner-provided Live2D Core/model + native Kokoro, isolated PC app."""
import argparse,hashlib,json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright
import test_character_http

def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--voices',type=Path,required=True);p.add_argument('--chrome',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve())
 f=test_character_http.CharacterHTTPTests();f.setUp();f.app.VOICE_DIR=a.voices.resolve();f.app.synthesize=f.real_synthesize
 if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
 else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
 class Runtime:
  def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js'}
  def read_core(self):return (a.runtime_dir/'live2dcubismcore.min.js').read_bytes()
  def read_bundle(self):return (a.runtime_dir/'build/owner-live2d-runtime.js').read_bytes()
 f.app.live2d_runtime=lambda:Runtime()
 f.post('settings',{'local_voice':'zf_xiaoyi','voice_rate':1.06,'expected_character_id':f.initial_id})
 r={'scope':'Linux PC Chrome; owner-provided original candidate; real Core and Kokoro; no target Windows or human aesthetic acceptance','checks':{},'errors':[],'model_package_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest()}
 try:
  with sync_playwright() as pw:
   b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader']);c=b.new_context(viewport={'width':1440,'height':900},record_video_dir=str(a.out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True);page=c.new_page();page.on('pageerror',lambda e:r['errors'].append(str(e)));base=f'http://127.0.0.1:{f.server.server_port}'
   page.goto(base);page.wait_for_function('()=>CompanionApp?.scene.ready && CompanionApp.scene.getDiagnostics().available===true',timeout=60000)
   r['startup']=page.evaluate('()=>({stats:CompanionApp.scene.getStats(),model:CompanionApp.scene.getDiagnostics()})');assert r['startup']['model']['mocConsistencyChecked'];assert r['startup']['model']['coreEvaluations']>0;r['checks']['default_live2d_draws_without_import_click']=True
   page.screenshot(path=str(a.out/'01-default-character.png'))
   page.evaluate("()=>{window.voiceObservations=[];window.voiceProbe=setInterval(()=>voiceObservations.push({time:performance.now(),stats:CompanionApp.scene.getStats(),model:CompanionApp.scene.getDiagnostics()}),100);CompanionApp.speech.speak('人物你有了吗');}")
   page.wait_for_function('()=>CompanionApp.speech.state==="playing"',timeout=30000);page.wait_for_function('()=>voiceObservations.some(x=>x.model.lipSyncValue>0.01)',timeout=10000);page.screenshot(path=str(a.out/'02-character-speaking.png'));page.evaluate('()=>CompanionApp.speech.stop()');page.wait_for_function('()=>CompanionApp.speech.state==="idle" && CompanionApp.scene.getDiagnostics().lipSyncValue<0.001');r['voice_observations']=page.evaluate('()=>{clearInterval(voiceProbe);return voiceObservations;}');r['checks']['actual_speech_drives_mouth_and_stop_resets']=True
   role=f.state()['active_character']['appearance_id'];page.reload();page.wait_for_function('()=>CompanionApp?.scene.ready && CompanionApp.scene.getDiagnostics().available===true',timeout=60000);assert f.state()['active_character']['appearance_id']==role;r['checks']['reload_keeps_same_default']=True
   page.goto(base+'/room.html');page.wait_for_function('()=>RoomPreview?.scene.ready && RoomPreview.scene.getDiagnostics().available===true',timeout=60000)
   page.locator('#topic-input').fill('检查uiux和直播室设置的差异');page.locator('#apply-settings').click();page.locator('#timer-toggle').click();page.wait_for_timeout(1250);state=page.evaluate('()=>RoomPreview.snapshot()');assert state['focus']['phase']=='running' and state['focus']['elapsed']>500
   page.locator('#timer-toggle').click();before=page.evaluate('()=>RoomPreview.snapshot().focus.elapsed');page.wait_for_timeout(1100);after=page.evaluate('()=>RoomPreview.snapshot().focus.elapsed');assert before==after;r['checks']['timer_runs_and_pause_does_not_count']=True
   page.locator('#hide-controls').click();page.screenshot(path=str(a.out/'03-focus-room.png'));r['room_idle_stats']=page.evaluate('()=>RoomPreview.scene.getStats()')
   page.locator('#show-controls').click();page.locator('#question-input').fill('人物你有了吗');page.locator('button[data-mode=question]').click();page.locator('#apply-settings').click();assert page.locator('#question-widget').is_visible();assert page.locator('button[data-mode=question]').get_attribute('aria-pressed')=='true';assert page.locator('#caption').is_hidden();page.locator('#hide-controls').click();page.screenshot(path=str(a.out/'04-question-room.png'))
   page.locator('#show-controls').click();page.locator('button[data-mode=break]').click();page.locator('#apply-settings').click();assert page.evaluate('()=>RoomPreview.snapshot().focus.phase')=='paused';page.locator('#break-toggle').click();page.wait_for_timeout(600);assert page.evaluate('()=>RoomPreview.snapshot().breakRemaining')<300000;page.locator('#break-toggle').click();before=page.evaluate('()=>RoomPreview.snapshot().breakRemaining');page.wait_for_timeout(600);assert before==page.evaluate('()=>RoomPreview.snapshot().breakRemaining');page.locator('#hide-controls').click();page.screenshot(path=str(a.out/'05-break-room.png'));r['checks']['scene_switch_and_break_pause_are_explicit']=True
   # Input is text, never markup or a model request.
   page.locator('#show-controls').click();page.locator('#question-input').fill('<img src=x onerror=alert(1)>');page.locator('button[data-mode=question]').click();page.locator('#apply-settings').click();assert page.locator('#question img').count()==0;r['checks']['manual_text_cannot_execute_markup']=True
   assert not r['errors'],r['errors'];r['environment']={'chrome':b.version};r['passed']=True;c.tracing.stop(path=str(a.out/'trace.zip'));c.close();b.close()
 except Exception as e:r['failure']=str(e);raise
 finally:
  f.tearDown();(a.out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 print(json.dumps({'passed':r.get('passed'),'checks':r['checks']},ensure_ascii=False))
if __name__=='__main__':main()
