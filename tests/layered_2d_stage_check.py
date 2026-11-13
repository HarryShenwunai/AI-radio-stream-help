"""Real Chrome independent geometric layers; explicitly not finished character art."""
import json,traceback
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
ROOT=Path(__file__).resolve().parents[1];OUT=Path('/workspace/dist/layered-2d-stage');OUT.mkdir(exist_ok=True,parents=True)
def main():
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp();report={'date':'2026-11-12','status':'RUNNING','fixture':'TEST_ONLY_INDEPENDENT_LAYERS.zip','artwork_quality_proven':False,'checks':{}};errors=[]
 try:
  with sync_playwright()as pw:
   b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=b.new_page(viewport={'width':1200,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(f.server.server_port));page.wait_for_function('()=>CompanionApp.core.get().state!==null');page.locator('#open-studio').click();page.locator('#studio-format').select_option('layered-2d');page.locator('#studio-model').set_input_files(str(ROOT/'.build/layered-2d-smoke/TEST_ONLY_INDEPENDENT_LAYERS.zip'));page.get_by_role('button',name='上传并检查预览',exact=True).click();page.wait_for_function('()=>!document.querySelector("#studio-activate").disabled');assert page.locator('.studio-preview canvas.layered-canvas').count()==1;report['checks']['real_package_file_upload_and_first_canvas_draw_before_activation']='passed';page.screenshot(path=str(OUT/'preview-test-geometry.png'));page.locator('#studio-activate').click();page.wait_for_function('()=>CompanionApp.scene.getStats().format!=="png-states"&&CompanionApp.scene.getStats().layerCount>0');page.wait_for_timeout(400);stats=page.evaluate('()=>CompanionApp.scene.getStats()');assert stats['frames']>3;report['checks']['single_stage_renderer_animates_real_separate_layers']='passed';assert page.locator('#character-canvas canvas').count()==1;report['checks']['single_active_stage_canvas']='passed';page.evaluate('()=>CompanionApp.pause()');assert page.locator('#character-canvas canvas').count()==0;report['checks']['pause_disposes_canvas']='passed';assert not errors,errors;report['checks']['no_page_errors']='passed';b.close();report['status']='passed'
 except Exception as e:report['status']='failed';report['error']=str(e);report['traceback']=traceback.format_exc();raise
 finally:report['page_errors']=errors;(ROOT/'review/layered-2d-stage-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));f.tearDown()
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
