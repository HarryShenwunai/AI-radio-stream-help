"""Actual Audio/HTTP/SQLite/context acknowledgement; synthetic tone and fake LLM.
Records product interaction without injecting engineering details into the UI.
"""
from pathlib import Path
import json
import time
import traceback
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
from character_browser_check import tone
ROOT=Path(__file__).resolve().parents[1]

def main():
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp()
 original=f.app.state;f.app.state=lambda:{**original(),'local_voice_available':True};f.app.synthesize=lambda text:tone()
 text='我先说第一件事：今天我们可以慢慢聊。接下来这段尾部还没有播放完成：海盐风铃的完整计划。'
 with f.app.db() as connection:
  connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('voice','false')")
  connection.execute("INSERT INTO messages(role,text,created,kind) VALUES('user',?,?,'chat')",('先和我说完整的计划。',f.app.now()))
  message=connection.execute("INSERT INTO messages(role,text,created,kind) VALUES('assistant',?,?,'chat')",(text,f.app.now())).lastrowid
 report={'date':'2026-11-12','status':'RUNNING','scope':'real Chromium HTMLAudio and actual playback routes/SQLite/prompt filtering; synthetic 4s tone, fake LLM; not proof of human hearing','checks':{},'external_connections':0}
 out=Path('/workspace/.live2d/evaluation/playback');out.mkdir(parents=True,exist_ok=True);receipts=[];errors=[]
 def capture(request):
  if request.method=='POST' and request.url.endswith('/api/playback/receipt'):
   body=request.post_data_json;receipts.append({key:body.get(key) for key in ['status','position_seconds','duration_seconds','character_id','appearance_id','message_id']})
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio'])
   context=browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(out/'video'),record_video_size={'width':1440,'height':1000});page=context.new_page();page.set_default_timeout(20000);page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',capture)
   try:
    assert any(row.get('role')=='assistant' and text in row['content'] for row in f.app.build_prompt(f.app.settings()));report['checks']['baseline_message_is_eligible_before_audio']='passed'
    page.goto(f'http://127.0.0.1:{f.server.server_port}');button=page.locator(f'[data-message-id="{message}"] .read-button');button.wait_for();button.click()
    page.wait_for_function('()=>localAudio&&!localAudio.paused&&activePlayback!==null');page.wait_for_timeout(1300);page.screenshot(path=str(out/'playing.png'))
    with page.expect_response(lambda response:response.url.endswith('/api/playback/receipt') and response.request.post_data_json.get('status')=='stopped') as pending:
     page.locator('#stop-voice').click()
    result=pending.value.json();assert result['accepted'] and result['confirmed_characters']==0,result
    stopped=next(item for item in reversed(receipts) if item['status']=='stopped');assert 0<stopped['position_seconds']<stopped['duration_seconds'],stopped
    report['checks']['real_stop_acknowledges_position_without_inventing_heard_text']='passed';page.screenshot(path=str(out/'stopped.png'))
    page.locator('#message-input').fill('现在接着和我聊吧。');page.locator('#send').click()
    deadline=time.monotonic()+15
    while not f.model_calls and time.monotonic()<deadline:page.wait_for_timeout(100)
    assert f.model_calls
    prompt=f.model_calls[-1];assert not any('海盐风铃' in item['content'] for item in prompt);assert not any(item.get('role')=='assistant' and item['content']==text for item in prompt)
    report['checks']['next_model_prompt_excludes_unconfirmed_assistant_tail']='passed'
    page.wait_for_function('()=>!busy');assert page.locator(f'[data-message-id="{message}"] .bubble').inner_text()==text
    report['checks']['full_text_stays_visible_in_chat']='passed';page.screenshot(path=str(out/'next-turn.png'))
    button.click()
    with page.expect_response(lambda response:response.url.endswith('/api/playback/receipt') and response.request.post_data_json.get('status')=='completed',timeout=12000) as completed:
     page.wait_for_timeout(4500)
    final=completed.value.json();assert final['accepted'] and final['confirmed_characters']==len(text),final
    report['checks']['actual_audio_end_confirms_the_whole_synthesized_message']='passed'
    assert page.locator(f'[data-message-id="{message}"] .playback-status').inner_text()=='播放完成';page.screenshot(path=str(out/'completed.png'))
    page.locator('#message-input').fill('这次继续刚才的计划。');page.locator('#send').click()
    deadline=time.monotonic()+15
    while len(f.model_calls)<2 and time.monotonic()<deadline:page.wait_for_timeout(100)
    assert any(item.get('role')=='assistant' and text in item['content'] for item in f.model_calls[-1]);report['checks']['completed_message_is_available_to_next_model_turn']='passed'
    assert not errors;report['checks']['javascript_runtime']='passed';report['status']='passed'
   except Exception as error:
    report.update(status='failed',error=str(error),traceback=traceback.format_exc());page.screenshot(path=str(out/'failure.png'));raise
   finally:
    video=page.video;context.close();video.save_as(str(out/'receipt-flow.webm'));report['video']=str(out/'receipt-flow.webm');browser.close()
 finally:
  report['receipts_without_credentials']=receipts;report['javascript_errors']=errors;f.tearDown();(ROOT/'review/playback-browser-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
