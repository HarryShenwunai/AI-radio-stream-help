"""Real Studio motion -> actual SDK queue completion -> restore default pose.

Uses the original candidate7 as a *runtime regression fixture*. Its rejected
dynamic cloth artwork is not accepted or published as final by this test.
"""
import argparse,datetime,json,os,traceback
from pathlib import Path
from hand_cup_metamorphic_check import ROOT,HOOK,OWN,PRODUCT,archive,recorded_browser,runtime_binding_files,runtime_files,sha,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','contract','runtime-dir','output','evidence-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--expression-only',action='store_true',help='Actual choose -> clear -> reselect expression regression')
    parser.add_argument('--adapter-override',help='Controlled legacy-branch counterfactual compiled adapter; real Core and UI remain genuine')
    args=parser.parse_args();os.environ['COMPANION_LIVE2D_RUNTIME']=str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    model=Path(args.model).resolve();contract_path=Path(args.contract).resolve();contract=json.loads(contract_path.read_text())
    action=next(item for item in contract['actions']if item['role']=='empty_hands')
    files=runtime_files(model);paths=files+[contract_path,Path(__file__).resolve()]+[ROOT/name for name in PRODUCT+OWN]+runtime_binding_files(Path(args.runtime_dir).resolve())
    override=Path(args.adapter_override).resolve()if args.adapter_override else None
    if override:paths.append(override)
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING','checks':{},
        'scope':'actual current Studio authored empty-hands motion completion and reset to real Core defaults; candidate7 artwork remains rejected',
        'artwork_accepted':False,'sources':{str(path):sha(path)for path in paths},'page_errors':[]}
    evidence=Path(args.evidence_dir).resolve();evidence.mkdir(parents=True,exist_ok=True)
    fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
    try:
        with sync_playwright()as pw,recorded_browser(pw,evidence)as(browser,context,page):
            page.add_init_script(HOOK);page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            if override:
                page.route('**/live2d-renderer.js',lambda route:route.fulfill(body=override.read_bytes(),content_type='application/javascript'))
                report['counterfactual']='controlled exact legacy reset branch; not a byte-identical historical full build; genuine Core/motion/Studio'
            page.goto('http://127.0.0.1:'+str(fixture.server.server_port));page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            page.evaluate('''()=>{const original=CompanionScene;window.__resetPreviews=[];
              window.CompanionScene={...original,create(options){const value=original.create(options);__resetPreviews.push(value);return value;}};}''')
            page.locator('#open-studio').click();page.locator('#studio-format').select_option('live2d')
            page.locator('#studio-model').set_input_files({'name':'TEST_ONLY-original-runtime-regression.zip','mimeType':'application/zip','buffer':archive(model,files)})
            page.get_by_role('button',name='上传并检查预览',exact=True).click();page.wait_for_function('()=>!document.querySelector("#studio-activate").disabled',timeout=60000)
            page.get_by_text('检查模型动作',exact=True).click()
            for label in ('自然眨眼','呼吸与轻微动作','播放待机动作','物理摆动'):
                page.get_by_label(label,exact=True).uncheck()
            # Clear natural controls and establish real defaults without leaving
            # custom-map pins that could falsely make the old reset succeed.
            page.evaluate('''async()=>{const controller=__resetPreviews.at(-1);
              await controller.applyControls({reset:true,idleMotion:false,breath:false,autoBlink:false,physics:false,expression:null});
              const app=__actualPixiApps.findLast(app=>app.stage?.children?.some(c=>c.internalModel));
              window.__resetModel=app.stage.children.find(c=>c.internalModel);const core=__resetModel.internalModel.coreModel,raw=core.getModel();
              for(let i=0;i<raw.parameters.count;i++)core.setParameterValueByIndex(i,raw.parameters.defaultValues[i]);core.saveParameters();
              const marker=controller.getDiagnostics().coreEvaluations;while(controller.getDiagnostics().coreEvaluations<marker+4)await new Promise(requestAnimationFrame);}''')
            diagnostic=lambda:page.evaluate('()=>__resetPreviews.at(-1).getDiagnostics({drawables:true,includeVertices:true})')
            baseline=diagnostic();report['baseline_parameters']={p['id']:p['value']for p in baseline['parameters']}
            assert all(p['value']==p['default']for p in baseline['parameters'])
            if args.expression_only:
                name=baseline['expressions'][1]if len(baseline['expressions'])>1 else baseline['expressions'][0]
                page.locator('#studio-model-expression').select_option(name)
                page.wait_for_function('name=>__resetPreviews.at(-1).getDiagnostics().currentExpression===name',arg=name)
                page.locator('#studio-model-expression').select_option('')
                page.wait_for_function('()=>__resetPreviews.at(-1).getDiagnostics().currentExpression===null')
                page.locator('#studio-model-expression').select_option(name)
                try:
                    page.wait_for_function('name=>__resetPreviews.at(-1).getDiagnostics().currentExpression===name',arg=name,timeout=5000)
                except Exception:
                    report['expression_error']=page.locator('.preview-model-controls .inline-error').text_content()
                    raise AssertionError('actual expression cannot be reselected after clearing: '+str(report['expression_error']))
                report['checks']['actual_expression_choose_clear_reselect']='passed'
                page.screenshot(path=str(evidence/'actual-expression-reselected-after-clear.png'))
                assert not report['page_errors'],report['page_errors'];report['status']='passed'
                return
            page.locator('.studio-preview-canvas').scroll_into_view_if_needed();page.screenshot(path=str(evidence/'01-before-actual-motion.png'))
            page.locator('#studio-model-motion').select_option(json.dumps({'group':action['group'],'index':action['index']},ensure_ascii=False,separators=(',',':')))
            page.get_by_role('button',name='播放所选动作',exact=True).click()
            page.locator('.studio-preview-canvas').scroll_into_view_if_needed()
            page.wait_for_function('''()=>{const model=__resetModel,mm=model.internalModel.motionManager;
              if(typeof mm.isFinished!=='function')throw Error('Missing actual SDK completion API');
              return mm.isFinished()&&__resetPreviews.at(-1).getDiagnostics().parameters.some(p=>p.id==='ParamCupVisible'&&p.value===0);}''',timeout=45000)
            after_motion=diagnostic();report['motion_parameters']={p['id']:p['value']for p in after_motion['parameters']}
            assert report['motion_parameters']['ParamCupVisible']==0 and report['baseline_parameters']['ParamCupVisible']==1
            report['checks']['actual_studio_motion_finished_and_saved_empty_hands_parameters']='passed'
            page.screenshot(path=str(evidence/'02-after-completed-empty-hands-motion.png'))
            page.evaluate('''()=>{const controller=__resetPreviews.at(-1),original=controller.applyControls;window.__actualResetInvocations=0;
              controller.applyControls=async values=>{if(values.reset)__actualResetInvocations++;return await original(values);};}''')
            page.get_by_role('button',name='恢复手动姿态',exact=True).focus()
            page.get_by_role('button',name='恢复手动姿态',exact=True).press('Enter')
            assert page.evaluate('()=>__actualResetInvocations')==1,'actual reset button did not invoke the real controller'
            marker=diagnostic()['coreEvaluations'];page.wait_for_function('marker=>__resetPreviews.at(-1).getDiagnostics().coreEvaluations>=marker+4',arg=marker)
            restored=diagnostic();report['after_reset_parameters']={p['id']:p['value']for p in restored['parameters']}
            report['not_restored']=[{'id':p['id'],'value':p['value'],'default':p['default']}for p in restored['parameters']if p['value']!=p['default']]
            page.screenshot(path=str(evidence/'03-after-real-reset-button.png'))
            assert not report['not_restored'],'actual motion-saved parameters survived reset: '+str(report['not_restored'])
            assert __import__('hand_cup_measurements').changed(
                {'drawables':baseline['drawables']},{'drawables':restored['drawables']})==set(),'default geometry/opacity did not restore'
            report['checks']['real_reset_stops_motion_and_restores_all_actual_defaults_and_geometry']='passed'
            page.locator('.studio-preview-canvas').scroll_into_view_if_needed();page.screenshot(path=str(evidence/'04-actual-restored-character-preview.png'))
            assert page.evaluate('()=>CompanionApp.core.get().state.active_character.appearance_id')is None
            page.keyboard.press('Escape');assert page.locator('#open-studio').evaluate('(node)=>node===document.activeElement')
            assert not report['page_errors'],report['page_errors'];report['checks']['preview_never_activates_and_closes_with_focus']='passed';report['status']='passed'
    except Exception as error:report.update(status='failed',error=str(error),traceback=traceback.format_exc())
    finally:
        fixture.tearDown();report['sources_unchanged']=all(Path(path).is_file()and sha(Path(path))==digest for path,digest in report['sources'].items());write_report(args.output,report)
    print(json.dumps({key:value for key,value in report.items()if key not in ('sources','traceback','baseline_parameters','motion_parameters','after_reset_parameters')},ensure_ascii=False))
    raise SystemExit(0 if report['status']=='passed'else 2)


if __name__=='__main__':main()
