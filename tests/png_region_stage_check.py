"""Real Chrome scope-cached PNG, actual Audio RMS, optional fixed-base regions.
Synthetic alternating tone is a test source, not a human voice/phoneme benchmark.
"""
import sys,base64,json,io,math,struct,wave,time,traceback
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/workspace/dist/png-region-stage');OUT.mkdir(parents=True,exist_ok=True)
def tone():
 out=io.BytesIO()
 with wave.open(out,'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*220*i/24000)) if (i//3000)%2==0 else 0) for i in range(24000*5)))
 return out.getvalue()
def main():
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp();app=f.app;old=app.state;app.state=lambda:{**old(),'local_voice_available':True};app.synthesize=lambda text:tone();report={'status':'RUNNING','date':'2026-11-12','scope':'real Chrome/HTTP/PNG/Audio RMS; generated licensed project artwork + synthetic alternating 125ms tone/silence','checks':{},'not_proven':['phoneme alignment','human voice quality','independent anatomical layers','Live2D','Windows hardware']};errors=[]
 try:
  with sync_playwright()as pw:
   browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio']);context=browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(OUT/'video'),record_video_size={'width':1440,'height':1000});page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));base='http://127.0.0.1:'+str(f.server.server_port);page.goto(base);page.wait_for_function('()=>CompanionApp.core.get().state!==null');role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'};other=page.request.post(base+'/api/characters/create',data={'name':'隔离身份'},headers=headers).json()['active_character_id'];assert page.request.post(base+'/api/characters/select',data={'id':role},headers=headers).ok;page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('(role)=>CompanionApp.core.scope().character_id===role',arg=role)
   source=json.loads(Path('/workspace/dist/character-2d.companion.json').read_text());source.update({'character_id':other,'expected_character_id':other,'role':'system','owner':'forged','permissions':'all'});requests=[]
   def inspect_request(request):
    if request.url.endswith('/api/characters/assets/import'):requests.append(request.post_data_json)
   page.on('request',inspect_request);page.locator('#open-studio').click();page.locator('#studio-format').select_option('png-package');page.locator('#studio-model').set_input_files({'name':'character-2d.companion.json','mimeType':'application/json','buffer':json.dumps(source,ensure_ascii=False).encode()});page.get_by_role('button',name='上传并检查预览',exact=True).click();page.wait_for_function('()=>!document.querySelector("#studio-activate").disabled');assert requests and requests[-1]['character_id']==role;assert not any(key in requests[-1] for key in ['expected_character_id','role','owner','permissions']);assert page.request.get(base+'/api/state').json()['active_character'].get('appearance_id') is None;report['checks']['single_file_package_whitelists_scope_and_previews_without_activation']='passed';page.screenshot(path=str(OUT/'package-preview.png'));page.locator('#studio-activate').click();page.wait_for_function('()=>CompanionApp.core.get().state.active_character.appearance_id!==null');report['checks']['explicit_package_activation']='passed';
   page.wait_for_selector('.regional-png-canvas');page.wait_for_function('()=>CompanionApp.scene.ready');page.screenshot(path=str(OUT/'idle.png'))
   # Capture a real runtime body ROI. It is outside both optional face rectangles.
   body=lambda:page.evaluate('()=>{const c=document.querySelector(".regional-png-canvas");return Array.from(c.getContext("2d").getImageData(100,650,850,750).data)}')
   before=body();page.evaluate('()=>CompanionApp.speech.speak("这是自动化测试的交替有声与静音波形。")');page.wait_for_function('()=>CompanionApp.speech.audio?.paused===false');trace=[]
   for _ in range(80):
    trace.append(page.evaluate('()=>({t:CompanionApp.speech.audio?.currentTime??0,mouth:CompanionApp.scene.getStats().mouth})'));page.wait_for_timeout(45)
   middle=[p for p in trace if .5<p['t']<3.5];assert any(p['mouth']==0 for p in middle),middle;assert any(p['mouth']==1 for p in middle),middle;report['checks']['actual_audio_interior_voiced_and_silent_windows_both_observed']='passed';report['trace']=trace
   after=body();changed=sum(a!=b for a,b in zip(before,after));assert changed==0,changed;report['body_rgba_changed_components']=changed;report['checks']['body_pixels_identical_during_real_speech_and_blinks']='passed';page.screenshot(path=str(OUT/'speaking.png'));page.evaluate('()=>CompanionApp.speech.stop()');assert page.evaluate('()=>CompanionApp.scene.getStats().mouth')==0;assert page.evaluate('()=>CompanionApp.scene.getStats().audioAnalysis')is False;report['checks']['stop_closes_mouth_and_analysis']='passed';assert page.evaluate('()=>CompanionApp.scene.getStats().requestCount')==4;report['checks']['only_four_state_requests_per_scope']='passed';page.evaluate('()=>CompanionApp.pause()');assert page.evaluate('()=>CompanionApp.scene.getStats().cacheSize')==0;report['checks']['pause_releases_cached_state_resources']='passed';assert errors==[],errors;report['checks']['no_page_errors']='passed';context.close();browser.close();report['status']='passed'
 except Exception as e:report['status']='failed';report['error']=str(e);report['traceback']=traceback.format_exc();raise
 finally:
  report['page_errors']=errors;(ROOT/'review/png-region-stage-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));f.tearDown()
 print(json.dumps({'status':report['status'],'checks':report['checks'],'body_rgba_changed_components':report.get('body_rgba_changed_components')},ensure_ascii=False))
if __name__=='__main__':main()
