"""Original final-candidate main-stage scene/action evidence; no art/Windows claim.

Uses real Studio scene selection, actual current application model/action API,
real installed SDK/Core/GL. Never produces a synthetic product screenshot.
"""
import argparse,base64,datetime,json,os,struct,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from hand_cup_metamorphic_check import HOOK,OWN,PRODUCT,archive,runtime_files,runtime_binding_files,recorded_browser,sha,write_report
from hand_cup_contract import validate
from hand_cup_measurements import assert_hidden_helpers,assert_grips,by_id
from test_character_http import CharacterHTTPTests
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser()
for key in ('model','contract','landmarks','source-manifest','runtime-dir','output','evidence-dir'):p.add_argument('--'+key,required=True)
a=p.parse_args();model=Path(a.model).resolve();cp=Path(a.contract).resolve();lp=Path(a.landmarks).resolve();source=Path(a.source_manifest).resolve();rt=Path(a.runtime_dir).resolve();evidence=Path(a.evidence_dir).resolve();evidence.mkdir(parents=True,exist_ok=True)
c=json.loads(cp.read_text());landmarks=json.loads(lp.read_text());validate(c,landmarks);moc=model.parent/json.loads(model.read_text())['FileReferences']['Moc'];bindings={'model3_sha256':model,'moc3_sha256':moc,'landmarks_sha256':lp,'source_manifest_sha256':source}
for key,path in bindings.items():assert sha(path)==c['model_binding'][key],('Actual final source binding mismatch',key)
files=runtime_files(model);paths=files+[cp,lp,source,Path(__file__).resolve()]+[ROOT/x for x in OWN+PRODUCT]+[ROOT/'app/static/studio.js',ROOT/'app/static/style.css',ROOT/'app/static/stage-actions.js',ROOT/'app/static/index.html']+runtime_binding_files(rt);os.environ['COMPANION_LIVE2D_RUNTIME']=str(rt)
r={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running','sources':{str(p):sha(p)for p in paths},'checks':{},'scenes':[],'page_errors':[],'artwork_accepted':False,'scope':'Actual application main stage, actual Studio environment choices and real authored motion/Core/GL. Actual main-stage model-derived buttons trigger each motion; programmatic parameter writes only establish declared starting poses. No automatic-chat hand-motion/Windows/real audio claim.'};f=None
try:
 f=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp()
 with sync_playwright()as pw,recorded_browser(pw,evidence)as(_,context,page):
  page.add_init_script(HOOK);page.on('pageerror',lambda e:r['page_errors'].append(str(e)));base='http://127.0.0.1:'+str(f.server.server_port);module=page.request.get(base+'/stage-actions.js');assert module.ok;assert 'javascript'in module.headers.get('content-type','');r['module_http']={'status':module.status,'content_type':module.headers['content-type'],'sha256':__import__('hashlib').sha256(module.body()).hexdigest()};assert r['module_http']['sha256']==sha(ROOT/'app/static/stage-actions.js');page.goto(base);page.wait_for_function('()=>CompanionApp.core.get().state!==null');role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'}
  response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'original-final-candidate.zip','data_base64':base64.b64encode(archive(model,files)).decode()}});assert response.ok,response.text();asset=response.json()['asset'];response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':asset['id']});assert response.ok,response.text();page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2',timeout=60000);page.evaluate((ROOT/'tests/hand_cup_browser.mjs').read_text());actual=page.evaluate('a=>__handCup.init(a)',asset);page.evaluate('ids=>__handCup.setHiddenHelpers(ids)',c['meshes'].get('cup_helpers',[]));r['actual']={'moc_consistency':actual['mocConsistency'],'core_version':actual['coreVersion'],'drawables':len(actual['rest']['drawables']),'parameters':len(actual['rest']['parameters'])}
  actions={x['role']:x for x in c['actions']}
  item=actions['wave'];setting=page.request.get(base+asset['model']['url']).json();reference=setting['FileReferences']['Motions'][item['group']][item['index']]['File'];url=base+asset['resources'][reference]['url'];outage=[True];hits=[0]
  def fault(route):
   hits[0]+=1
   if outage[0]:route.fulfill(status=503,content_type='application/json',body='{"error":"controlled_local_transient"}')
   else:route.continue_()
  page.route(url,fault);page.evaluate('value=>__handCup.productPose(value,true)',item['start_pose']);page.locator('#open-stage-actions').click();page.locator('[data-flow=stage-actions]').get_by_role('button',name=item['group'],exact=True).click();page.locator('[data-flow=stage-actions] .inline-error').wait_for(state='visible',timeout=15000);page.screenshot(path=str(evidence/'01-actual-transient-motion-error.png'));r['first_error']=page.locator('[data-flow=stage-actions] .inline-error').inner_text();r['requests_after_error']=hits[0];outage[0]=False
  page.locator('[data-flow=stage-actions]').get_by_role('button',name=item['group'],exact=True).click();page.locator('[data-flow=stage-actions] .inline-error').wait_for(state='visible',timeout=15000);r['requests_after_normal_retry']=hits[0];r['sdk_cached_failed_motion']=page.evaluate('group=>{const app=__actualPixiApps.findLast(a=>a.stage?.children?.some(x=>x.internalModel));const m=app.stage.children.find(x=>x.internalModel);return m.internalModel.motionManager.motionGroups[group][0]===null;}',item['group']);page.screenshot(path=str(evidence/'02-normal-retry-still-cached-error.png'))
  recover=page.locator('#stage-reload-model')
  if recover.count():
   previous=page.evaluate('()=>__actualPixiApps.length');recover.click();page.wait_for_function('old=>__actualPixiApps.length>old&&CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2',arg=previous,timeout=60000);page.evaluate('value=>__handCup.productPose(value,true)',item['start_pose']);page.locator('#open-stage-actions').click();page.locator('[data-flow=stage-actions]').get_by_role('button',name=item['group'],exact=True).click();page.wait_for_function('args=>{const d=CompanionApp.scene.getDiagnostics();return Object.entries(args.values).every(([id,value])=>d.parameters.some(p=>p.id===id&&Math.abs(p.value-value)<=args.tolerance));}',arg={'values':item['expect_parameters'],'tolerance':item['parameter_tolerance']},timeout=20000);assert page.locator('[data-flow=stage-actions]').count()==0;gl=page.evaluate('()=>__handCup.pixels(null)');assert gl['error']==0 and gl['colored']>1000;r['real_reload_recovery']={'requests_after_recovery':hits[0],'new_pixi_model':True,'actual_core_target_values_reached':True,'gl':gl};page.screenshot(path=str(evidence/'03-actual-recovered-wave.png'));r['status']='passed_real_reload_recovery'
  else:r['status']='failed_real_transient_motion_not_recoverable_by_retry'
  assert not r['page_errors'];r['checks']={'actual_http503_into_motion_loader':'passed','ordinary_retry_does_not_reload_failed_sdk_cache':'observed','explicit_model_reload_recovery':'passed'if 'real_reload_recovery'in r else'failed'};page.evaluate('()=>__handCup.dispose()')
except Exception as e:r.update(status='failed',error=str(e),traceback=traceback.format_exc())
finally:
 if f:f.tearDown()
 r['sources_unchanged']=all(Path(p).exists()and sha(Path(p))==v for p,v in r['sources'].items());write_report(a.output,r)
print(json.dumps({'status':r['status'],'scenes':len(r['scenes']),'source_stable':r['sources_unchanged'],'error':r.get('error')}))
