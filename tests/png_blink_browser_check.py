"""Real browser PNG blink/talk_blink lifecycle using synthetic colors/tone only."""
from pathlib import Path
import json
import tempfile
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests,png_fixture
from character_browser_check import tone
ROOT=Path(__file__).resolve().parents[1]
def main():
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp();report={'date':'2026-11-12','status':'RUNNING','checks':{},'scope':'real Chromium, decoded synthetic PNG and test tone; no artwork, microphone or model quality claim'}
 original=f.app.state;f.app.state=lambda:{**original(),'local_voice_available':True};f.app.synthesize=lambda text:tone()
 try:
  with tempfile.TemporaryDirectory(prefix='png-blink-') as folder:
   files={}
   for i,key in enumerate(['idle','talk','blink','talk_blink']):
    p=Path(folder)/(key+'.png');p.write_bytes(png_fixture((50+i*45,80+i*20,160-i*15,220)));files[key]=str(p)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio']);page=browser.new_page(viewport={'width':1440,'height':1000});page.add_init_script('Math.random=()=>0;');errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
    page.goto(f'http://127.0.0.1:{f.server.server_port}');page.locator('#character-select option').first.wait_for(state='attached');page.locator('#manage-characters').click()
    for key,selector in [('idle','#asset-idle'),('talk','#asset-talk'),('blink','#asset-blink'),('talk_blink','#asset-talk-blink')]:page.locator(selector).set_input_files(files[key])
    page.locator('#preview-appearance').click();page.get_by_text('已检查 · 96 × 160 · 尚未启用',exact=True).wait_for();page.locator('#activate-appearance').click()
    page.wait_for_function("()=>document.querySelector('#portrait-avatar').src.includes('/blink.png')",timeout=7000);report['checks']['optional_idle_blink_is_used']='passed'
    page.wait_for_function("()=>document.querySelector('#portrait-avatar').src.includes('/idle.png')");report['checks']['short_blink_restores_idle']='passed'
    page.evaluate("()=>speak('合成测试音')")
    page.wait_for_function("()=>document.querySelector('#portrait-avatar').src.includes('/talk_blink.png')",timeout=7000);report['checks']['actual_playback_selects_talk_blink']='passed'
    page.evaluate("()=>{stopVoice();window.companionDesktopHidden=true;window.dispatchEvent(new Event('companion:desktop-pause'));}")
    assert page.evaluate("()=>pngBlinkTimer===0&&pngBlinkEndTimer===0&&!pngBlinkActive");report['checks']['hidden_stage_releases_blink_timers']='passed'
    assert not errors;report['checks']['javascript_runtime']='passed';report['javascript_errors']=errors;browser.close()
  report['status']='passed'
 finally:f.tearDown();(ROOT/'review/png-blink-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
