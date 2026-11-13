"""Real page integration/layout only. Never configure/approve a real connector."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
ROOT=Path(__file__).resolve().parents[1]
def main():
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp();report={'date':'2026-11-12','status':'RUNNING','checks':{},'real_platform_connections':0,'real_messages_sent':0};errors=[];writes=[]
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda x:errors.append(str(x)));page.on('request',lambda r:writes.append(r.url) if r.method=='POST' and '/api/connectors/' in r.url else None)
   page.goto(f'http://127.0.0.1:{f.server.server_port}');page.locator('#character-select option').first.wait_for(state='attached');page.locator('.nav[data-view=connectors]').click();page.locator('#view-connectors').wait_for()
   assert page.locator('#view-title').inner_text()=='平台连接';page.get_by_text('未绑定',exact=True).wait_for();report['checks']['real_navigation_and_local_status']='passed'
   page.evaluate("()=>{CompanionConnectorsUI.fields.pairing_token.value='synthetic-token';CompanionConnectorsUI.fields.access_key_secret.value='synthetic-secret';window.companionDesktopHidden=true;window.dispatchEvent(new Event('companion:desktop-pause'));}")
   assert page.locator('[name=pairing_token]').input_value()=='' and page.locator('[name=access_key_secret]').input_value()=='';report['checks']['native_hidden_clears_secrets_immediately']='passed';page.evaluate('()=>window.companionDesktopHidden=false')
   page.evaluate("async()=>{CompanionConnectorsUI.fields.pairing_token.value='synthetic-old-role';await api('characters/create',{name:'独立角色乙'});await refresh(true);}")
   assert page.locator('[name=pairing_token]').input_value()=='';assert page.locator('#character-select').input_value()!=f.initial_id;report['checks']['identity_adoption_resets_old_approval_secrets']='passed'
   for width in [1440,390,360]:
    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(80)
    assert page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),width
   report['checks']['layout_1440_390_360']='passed';page.screenshot(path='/workspace/dist/connectors-mobile.png')
   assert not writes;report['checks']['no_connector_configuration_approval_or_send']='passed';assert not errors;report['checks']['javascript_runtime']='passed';report['javascript_errors']=errors;report['connector_posts']=writes;browser.close()
  report['status']='passed'
 finally:f.tearDown();(ROOT/'review/connectors-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
