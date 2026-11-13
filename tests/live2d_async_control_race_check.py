"""Actual SDK expression resource delay and adapter load/reset cancellation.

The SDK and Core are real; Playwright holds one authenticated expression HTTP
response. A second actual asset load or reset must cancel the old control
without writing its expression cache, stopping the new model, or surfacing a
false loading failure. This direct adapter contract probe is not art approval.
"""
import argparse,base64,datetime,json,os,traceback
from pathlib import Path
from urllib.parse import urljoin
from hand_cup_metamorphic_check import ROOT,HOOK,OWN,PRODUCT,archive,recorded_browser,runtime_binding_files,runtime_files,sha,write_report

ADAPTER_HOOK="""(()=>{let library;Object.defineProperty(window,'CompanionLive2D',{configurable:true,get(){return library;},set(value){library={...value,create(options){const instance=value.create(options);(window.__actualControlAdapters??=[]).push(instance);return instance;}};}});})()"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','runtime-dir','output','evidence-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--mode',choices=['load','reset'],default='load');args=parser.parse_args()
    os.environ['COMPANION_LIVE2D_RUNTIME']=str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    model=Path(args.model).resolve();files=runtime_files(model);paths=files+[Path(__file__).resolve()]+[ROOT/name for name in OWN+PRODUCT]+runtime_binding_files(Path(args.runtime_dir).resolve())
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING','mode':args.mode,'checks':{},
        'scope':'direct actual adapter API with real delayed authenticated expression bytes, not fake SDK, not art acceptance',
        'sources':{str(path):sha(path)for path in paths},'page_errors':[]};evidence=Path(args.evidence_dir).resolve();evidence.mkdir(parents=True,exist_ok=True)
    fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    try:
        with sync_playwright()as pw,recorded_browser(pw,evidence)as(browser,context,page):
            page.add_init_script(HOOK+";\n"+ADAPTER_HOOK);page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            base='http://127.0.0.1:'+str(fixture.server.server_port);page.goto(base);page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'};zipbytes=archive(model,files)
            def import_asset():
                response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'original-async-race.zip','data_base64':base64.b64encode(zipbytes).decode()}})
                assert response.ok,response.text();return response.json()['asset']
            a,b=import_asset(),import_asset()
            response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':a['id']});assert response.ok,response.text()
            page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready&&window.__actualControlAdapters?.length>0',timeout=60000)
            page.evaluate('()=>__actualControlAdapters[0].applyControls({reset:true,idleMotion:false,breath:false,autoBlink:false,physics:false})')
            setting=page.request.get(urljoin(base,a['model']['url'])).json();expression=setting['FileReferences']['Expressions'][1]
            group=next(group for group in setting['FileReferences']['Motions']if group=='招手')
            resource=urljoin(base,a['resources'][expression['File']]['url']);routes=[]
            page.route(resource,lambda route:routes.append(route))
            page.evaluate('''input=>{window.__asyncControlOutcome=null;__actualControlAdapters[0].applyControls({expression:input.name,motion:{group:input.group,index:0}})
              .then(value=>window.__asyncControlOutcome={value}).catch(error=>window.__asyncControlOutcome={error:error.message});}''',{'name':expression['Name'],'group':group})
            for _ in range(100):
                page.wait_for_timeout(20)
                if routes:break
            assert len(routes)==1,'actual expression HTTP request was not held'
            if args.mode=='load':
                assert page.evaluate('asset=>__actualControlAdapters[0].load(asset)',b)
            else:
                assert page.evaluate('()=>__actualControlAdapters[0].applyControls({reset:true})')
            page.evaluate('''()=>{const adapter=__actualControlAdapters[0];window.__stopNewModelCalls=0;
              const app=__actualPixiApps.find(app=>app.stage?.children?.some(c=>c.internalModel)),model=app.stage.children.find(c=>c.internalModel),mm=model.internalModel.motionManager;
              window.__raceCurrentModel=model;const stop=mm.stopAllMotions.bind(mm);mm.stopAllMotions=function(){__stopNewModelCalls++;return stop();};}''')
            before=page.evaluate('()=>__actualControlAdapters[0].getDiagnostics()');assert before['currentExpression']is None
            routes[0].continue_();page.wait_for_function('()=>__asyncControlOutcome!==null',timeout=15000)
            page.wait_for_timeout(200)
            report['outcome']=page.evaluate('()=>__asyncControlOutcome');report['new_model_stop_calls']=page.evaluate('()=>__stopNewModelCalls')
            after=page.evaluate('()=>__actualControlAdapters[0].getDiagnostics()');report['current_expression_after_old_result']=after['currentExpression']
            report['actual_parameters_after_old_result']={p['id']:p['value']for p in after['parameters']}
            page.screenshot(path=str(evidence/'after-real-delayed-expression.png'))
            assert report['outcome']=={'value':False},'stale real expression did not cancel cleanly: '+str(report['outcome'])
            assert report['new_model_stop_calls']==0 and after['currentExpression']is None,'late old control mutated the current model'
            assert not report['page_errors'],report['page_errors'];report['checks']['actual_delayed_expression_cancels_without_cache_motion_or_error']='passed';report['status']='passed'
    except Exception as error:report.update(status='failed',error=str(error),traceback=traceback.format_exc())
    finally:
        fixture.tearDown();report['sources_unchanged']=all(Path(path).is_file()and sha(Path(path))==digest for path,digest in report['sources'].items());write_report(args.output,report)
    print(json.dumps({key:value for key,value in report.items()if key not in('sources','traceback','actual_parameters_after_old_result')},ensure_ascii=False))
    raise SystemExit(0 if report['status']=='passed'else 2)


if __name__=='__main__':main()
