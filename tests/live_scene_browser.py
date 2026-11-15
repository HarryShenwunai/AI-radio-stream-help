"""PC scene controls against real HTTP; synthetic ingress and deterministic answers."""
import argparse,json,platform
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
from companion_runtime.live import LiveBinding,LiveIngress

def main():
 p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 f=CharacterHTTPTests();f.setUp();s=f.app.integrations();ingress=LiveIngress(LiveBinding('bilibili-open-live','123'),ttl_seconds=30)
 s.bili=SimpleNamespace(ingress=ingress,status=lambda:{'state':'local-test-fixture'});inputs=[]
 f.app.generate_once=lambda settings,messages,**kw:(inputs.append(messages) or '晚上好，欢迎进来聊聊。')
 r={'scope':'Linux PC Chrome / synthetic events / deterministic model','checks':{},'errors':[]}
 def event(ident,text):ingress.submit({'room_id':'123','event_id':ident,'text':text})
 try:
  with sync_playwright() as pw:
   b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox']);c=b.new_context(viewport={'width':1280,'height':960},record_video_dir=str(a.out/'video'));c.tracing.start(screenshots=True,snapshots=True,sources=True)
   page=c.new_page();page.on('pageerror',lambda e:r['errors'].append(str(e)));page.goto(f'http://127.0.0.1:{f.server.server_port}');page.wait_for_function('()=>window.CompanionApp?.core.get().state')
   page.locator('#open-companion-controls').click();page.get_by_role('button',name='微信与直播连接').click();page.get_by_role('button',name='哔哩哔哩直播预览',exact=True).click()
   page.locator('.live-context > summary').click();topic=page.get_by_label('本场公开背景',exact=True);topic.fill('今天聊音乐，主播喜欢民谣。')
   held=[];page.route('**/api/connectors/status',lambda route:held.append(route));page.get_by_role('button',name='刷新',exact=True).click();page.wait_for_timeout(100);assert held
   topic.fill('今天聊音乐，观众可以分享喜欢的歌。');topic.evaluate('(el)=>el.setSelectionRange(3,7)');before=topic.evaluate('(el)=>[el.value,el.selectionStart,el.selectionEnd,document.activeElement===el,el.closest("details").open]')
   held[0].continue_();page.wait_for_timeout(200);after=topic.evaluate('(el)=>[el.value,el.selectionStart,el.selectionEnd,document.activeElement===el,el.closest("details").open]');assert before==after;(r['checks']).update(context_draft_focus_preserved=True)
   page.unroute('**/api/connectors/status');page.get_by_label('允许将背景用于公开回复',exact=True).check();page.get_by_role('button',name='应用现场设置').click();page.wait_for_function('()=>document.querySelector(".live-context summary")?.textContent==="现场互动"');assert s.output.topic=='今天聊音乐，观众可以分享喜欢的歌。'
   event('greeting','晚上好！');page.get_by_role('button',name='刷新',exact=True).click();page.get_by_role('button',name='准备回答',exact=True).click();page.get_by_role('button',name='播放这条回答',exact=True).wait_for();assert not s.output.material;assert len(inputs)==1
   page.screenshot(path=str(a.out/'01-no-material-review.png'));r['checks']['no_material_manual_review']=True
   page.get_by_role('button',name='主播讲解中',exact=True).click();page.get_by_role('button',name='结束讲解',exact=True).wait_for();assert not page.get_by_role('button',name='播放这条回答',exact=True).count();assert all(j['state']=='cancelled' for j in s.output.jobs.values());r['checks']['host_takeover_cancels_review']=True
   event('during','讲解期间的问题');page.get_by_role('button',name='刷新',exact=True).click();page.get_by_text('讲解期间的问题',exact=True).wait_for();assert not page.get_by_role('button',name='准备回答',exact=True).count()
   page.screenshot(path=str(a.out/'02-host-speaking.png'));page.get_by_role('button',name='结束讲解',exact=True).click();page.get_by_role('button',name='主播讲解中',exact=True).wait_for();assert not page.get_by_text('讲解期间的问题',exact=True).count();r['checks']['no_stale_backlog_after_resume']=True
   page.locator('.live-context > summary').click();page.get_by_label('严格按教材答疑',exact=True).check();page.get_by_role('button',name='应用现场设置').click();page.wait_for_function('()=>document.querySelector(".live-context summary")?.textContent==="严格教材答疑"')
   event('strict','这一题如何证明？');page.get_by_role('button',name='刷新',exact=True).click();page.get_by_role('button',name='准备回答',exact=True).click();page.get_by_text('严格答疑需要允许公开的教材。',exact=True).wait_for();assert len(inputs)==1;r['checks']['strict_requires_material']=True
   page.locator('.live-context > summary').click();page.get_by_label('严格按教材答疑',exact=True).uncheck();topic.fill('现在聊烹饪');page.get_by_label('允许将背景用于公开回复',exact=True).check();page.get_by_role('button',name='应用现场设置').click();page.wait_for_function('()=>document.querySelector(".live-context summary")?.textContent==="现场互动"');assert not page.get_by_text('这一题如何证明？',exact=True).count()
   event('new','番茄炒蛋怎么做？');page.get_by_role('button',name='刷新',exact=True).click();page.get_by_role('button',name='准备回答',exact=True).click();page.get_by_role('button',name='播放这条回答',exact=True).wait_for();assert '这一题如何证明' not in str(inputs[-1]);assert '今天聊音乐' not in str(inputs[-1]);r['checks']['topic_isolation']=True
   page.screenshot(path=str(a.out/'03-topic-switched.png'));assert not r['errors'];r['environment']={'platform':platform.platform(),'chrome':b.version};r['model_inputs']=inputs;r['passed']=True
   c.tracing.stop(path=str(a.out/'trace.zip'));c.close();b.close()
 finally:
  f.tearDown();(a.out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 print(json.dumps(r['checks']))
if __name__=='__main__':main()
