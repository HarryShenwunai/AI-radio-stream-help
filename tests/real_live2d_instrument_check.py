"""Check the final real-voice harness's detector with actual Core, without AI/audio.

Uses an explicitly intermediate original model. Manual mouth-positive/default-
negative controls prove moving body/physics cannot create a false mouth effect.
No generate/synthesize replacements, no model loading, no final acceptance claim.
"""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
from hand_cup_metamorphic_check import archive, runtime_files, runtime_binding_files
from real_live2d_companion_browser_check import ROOT, MOUTH_PROOF, AUDIO_OBSERVATION, sha

parser=argparse.ArgumentParser(description=__doc__)
for name in ['model','runtime-dir','output','evidence-dir']:parser.add_argument('--'+name,required=True)
args=parser.parse_args();model=Path(args.model).resolve();runtime=Path(args.runtime_dir).resolve();out=Path(args.evidence_dir);out.mkdir(parents=True,exist_ok=True);os.environ['COMPANION_LIVE2D_RUNTIME']=str(runtime)
setting=json.loads(model.read_text());lips=[pid for group in setting.get('Groups',[]) if group.get('Name')=='LipSync' for pid in group['Ids']]
paths=runtime_files(model)+runtime_binding_files(runtime)+[Path(__file__).resolve(),ROOT/'tests/real_live2d_companion_browser_check.py',ROOT/'app/server.py',*(ROOT/'src/companion_runtime').rglob('*.py'),*filter(lambda p:p.suffix in {'.js','.html','.css'},(ROOT/'app/static').iterdir())];sources={str(p):sha(p) for p in paths}
report={'status':'running','scope':'Measurement-instrument selfcheck only: actual Core/product with manually controlled mouth and moving body/physics; no AI/audio/provider, no final rig acceptance','sources':sources,'actual_provider_invoked':False};server=worker=app=None
try:
 with tempfile.TemporaryDirectory(prefix='mouth-instrument-') as data:
  spec=importlib.util.spec_from_file_location('mouth_detector_instrument_app',ROOT/'app/server.py');app=importlib.util.module_from_spec(spec);sys.modules[spec.name]=app;spec.loader.exec_module(app);app.DATA=Path(data);app.init()
  server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.daemon_threads=True;worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader']);context=browser.new_context(viewport={'width':1440,'height':1000});context.add_init_script(AUDIO_OBSERVATION);page=context.new_page();base='http://127.0.0.1:'+str(server.server_port);page.goto(base);page.wait_for_function('()=>CompanionApp?.core.get().state?.active_character_id');role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'}
   response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'instrument-only-original.zip','data_base64':base64.b64encode(archive(model,runtime_files(model))).decode()}});assert response.ok,response.text();asset=response.json()['asset'];response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':asset['id']});assert response.ok;page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>=3',timeout=60000)
   moc_url=next(v['url'] for k,v in asset['resources'].items() if k.endswith('.moc3'));report['detector']=page.evaluate(MOUTH_PROOF,{'mocURL':moc_url,'lipSyncIds':lips,'expectedMocSha256':sha(model.parent/setting['FileReferences']['Moc'])})
   page.evaluate('()=>CompanionApp.scene.applyControls({idleMotion:false,expression:null,headX:.25,bodyX:.25})')
   parameters=page.evaluate('()=>CompanionApp.scene.getDiagnostics().parameters');defs={p['id']:p for p in parameters};positive=[{'id':pid,'value':defs[pid]['default']+.45*(defs[pid]['max']-defs[pid]['default'])} for pid in lips]
   page.evaluate('p=>CompanionApp.scene.applyControls({parameters:p})',positive);marker=page.evaluate('()=>CompanionApp.scene.getDiagnostics().coreEvaluations');page.wait_for_function('n=>CompanionApp.scene.getDiagnostics().coreEvaluations>=n+3',arg=marker)
   report['manual_positive']=page.evaluate('()=>__realLive2DMouth.evaluate(CompanionApp.scene.getDiagnostics({drawables:true,includeVertices:true}))');assert report['manual_positive']['actualMouthEqualsIndependentCoreAtAllActualInputs'];assert report['manual_positive']['changedByMouthOnlyCounterfactual'];page.screenshot(path=str(out/'manual-mouth-positive-instrument-only.png'))
   page.evaluate('p=>CompanionApp.scene.applyControls({parameters:p})',[{'id':pid,'value':defs[pid]['default']} for pid in lips]);marker=page.evaluate('()=>CompanionApp.scene.getDiagnostics().coreEvaluations');page.wait_for_function('n=>CompanionApp.scene.getDiagnostics().coreEvaluations>=n+3',arg=marker)
   report['default_negative_with_body_active']=page.evaluate('()=>__realLive2DMouth.evaluate(CompanionApp.scene.getDiagnostics({drawables:true,includeVertices:true}))');assert report['default_negative_with_body_active']['actualMouthEqualsIndependentCoreAtAllActualInputs'];assert not report['default_negative_with_body_active']['changedByMouthOnlyCounterfactual'];report['body_conditions']=page.evaluate('()=>{const d=CompanionApp.scene.getDiagnostics();return {automatic:d.automatic,physics:d.physics,actualNonMouthInputs:d.parameters.filter(p=>!__realLive2DMouth.lipSyncIds.includes(p.id)&&p.value!==p.default).map(p=>({id:p.id,value:p.value}))};}');assert report['body_conditions']['actualNonMouthInputs'];assert app.LOCAL_LLM is None and app.LOCAL_VOICE is None
   page.evaluate('()=>{clearInterval(__realLiveTraceTimer);__realLive2DMouth.dispose();}');context.close();browser.close()
  app.STOP.set();server.shutdown();server.server_close();worker.join(5);server=None;report['status']='instrument_selfcheck_passed_not_real_provider_or_final_rig'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 if app:app.STOP.set()
 if server:server.shutdown();server.server_close()
 if worker:worker.join(5)
 report['sources_unchanged']=all(p.is_file() and sha(p)==digest for p,digest in [(Path(k),v) for k,v in sources.items()]);Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'source_stable':report['sources_unchanged'],'actual_provider_invoked':False,'error':report.get('error')}))
