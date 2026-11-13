"""Partial actual-Core held/detached interpolation probe, no action/art pass.

Rebinds reviewed source grip guides to the new MOC's real default triangles;
never assumes pre-CupHold indices or parameter lists still apply. Uses the
owner-helper-built runtime, no SDK copied into the app or published output.
"""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import sys
import traceback

from hand_cup_metamorphic_check import (ROOT,HOOK,OWN,PRODUCT,archive,expect_detected,
    recorded_browser,runtime_binding_files,runtime_files,sha,write_report)
from hand_cup_measurements import assert_grips,by_id,invariant_except,measure_held_sweep,validate_actual_bindings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','grip-guides','runtime-dir','output','evidence-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--axes',nargs='+',default=['ParamBodyAngleX','ParamBodyAngleY','ParamBodyAngleZ','ParamBreath'])
    parser.add_argument('--interior-count',type=int,default=16)
    parser.add_argument('--sample-grid',help='Optional explicitly partial preflight grid JSON; never changes actual Core min/max')
    args=parser.parse_args()
    if not 1<=args.interior_count<=256:raise ValueError('bounded off-key samples required')
    roles={'ParamBodyAngleX':'body_x','ParamBodyAngleY':'body_y','ParamBodyAngleZ':'body_z',
        'ParamBodyLean':'body_lean','ParamProportion':'body_proportion','ParamBreath':'breath'}
    if not 2<=len(args.axes)<=6 or len(set(args.axes))!=len(args.axes) or not set(args.axes)<=roles.keys() or 'ParamBreath' not in args.axes:
        raise ValueError('real Body and Breath axes required')
    os.environ['COMPANION_LIVE2D_RUNTIME']=str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    sys.path.insert(0,str(ROOT/'scripts'))
    from avatar_live2d_contract import build
    model,guide=Path(args.model).resolve(),Path(args.grip_guides).resolve()
    files=runtime_files(model);guides=json.loads(guide.read_text())
    evidence=Path(args.evidence_dir).resolve();evidence.mkdir(parents=True,exist_ok=True)
    paths=files+[guide,Path(__file__).resolve(),ROOT/'scripts/avatar_live2d_contract.py']+[ROOT/name for name in OWN+PRODUCT]
    paths+=runtime_binding_files(Path(args.runtime_dir).resolve())
    sample_grid=None
    if args.sample_grid:
        sample_path=Path(args.sample_grid).resolve();sample_grid=json.loads(sample_path.read_text());paths.append(sample_path)
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING','checks':{},
        'scope':'partial real raw-Core and product held/detached finite Cartesian plus off-key interpolation test',
        'full_acceptance':'BLOCKED','artwork_accepted':False,'windows_executed':False,
        'sources':{str(path):sha(path)for path in paths},'page_errors':[],
        'pending':['final unified artist-reviewed body/wrist/source','four complete authored hand/cup actions','actual final Studio action flow','human art acceptance, Windows/4060, official Editor reopening']}
    fixture=None
    try:
        fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
        with sync_playwright()as pw,recorded_browser(pw,evidence)as(browser,context,page):
            page.add_init_script(HOOK);page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            base='http://127.0.0.1:'+str(fixture.server.server_port);page.goto(base)
            page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'}
            response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'original-real-hold.zip','data_base64':base64.b64encode(archive(model,files)).decode()}})
            assert response.ok,response.text();asset=response.json()['asset']
            response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':asset['id']});assert response.ok,response.text()
            page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2',timeout=60000)
            page.evaluate((ROOT/'tests/hand_cup_browser.mjs').read_text());actual=page.evaluate('asset=>__handCup.init(asset)',asset)
            parameters={p['id']:p for p in actual['rest']['parameters']}
            assert all(pid in parameters for pid in args.axes+['ParamCupHold','ParamCupVisible','ParamCupX'])
            assert parameters['ParamCupHold']['min']==0 and parameters['ParamCupHold']['max']==1 and parameters['ParamCupHold']['default']==1
            # Preserve truthful raw/default diagnostics *before* a stale or
            # displaced source guide fails rebinding. Do not silently bind a
            # Hold0 pose and call it the actual default Hold1 rest.
            cup_ids={value['drawable_id']for name,value in guides['landmarks'].items()if name.endswith('_cup')}
            palm_ids={value['drawable_id']for name,value in guides['landmarks'].items()if name.endswith('_palm')}
            modes={}
            for hold in (0,1):
                state=page.evaluate('v=>__handCup.rawPose(v)',{'ParamCupHold':hold})
                canvas=actual['canvasInfo'];summary={}
                for mid in cup_ids|palm_ids:
                    mesh=by_id(state)[mid];vertices=mesh['vertices']
                    points=[[canvas['originX']+vertices[i]*canvas['ppu'],canvas['originY']-vertices[i+1]*canvas['ppu']]for i in range(0,len(vertices),2)]
                    summary[mid]={'bbox_source_px':[min(p[0]for p in points),min(p[1]for p in points),max(p[0]for p in points),max(p[1]for p in points)],
                        'centroid_source_px':[sum(p[axis]for p in points)/len(points)for axis in (0,1)],'opacity':mesh['opacity']}
                modes[str(hold)]=summary
                page.evaluate('v=>__handCup.productPose(v)',{'ParamCupHold':hold})
                page.screenshot(path=str(evidence/('default-body-hold-'+str(hold)+'.png')))
            report['default_body_hold_mode_diagnostics']=modes
            report['actual_default_parameters']={p['id']:p['value']for p in actual['rest']['parameters']}
            rest={'format':'actual-live2d-core-rest-v1','parameters':actual['rest']['parameters'],'canvasInfo':actual['canvasInfo'],
                'drawables':[{**d,'vertexPositions':d['vertices'],'indices':actual['topology'][d['id']]['indices']}for d in actual['rest']['drawables']]}
            requests={name:{'drawable_id':value['drawable_id'],'source_canvas':value['source_canvas']}for name,value in guides['landmarks'].items()}
            try:
                landmarks=build(rest,requests)
            except ValueError as error:
                failures=[]
                for name,value in requests.items():
                    try:build(rest,{name:value})
                    except ValueError:failures.append(name)
                raise ValueError('actual default Hold1 source grip rebinding failed for '+str(failures)+': '+str(error))from error
            landmarks['source_sha256']={str(guide):sha(guide),str(model):sha(model)}
            write_report(evidence/'actual-rebound-grip-contract.json',landmarks)
            grips=[{'cup_landmark':'grip_'+side+'_cup','hand_landmark':'grip_'+side+'_palm','tolerance_px':1,
                    'tolerance_basis':'parent-authorized predeclared one source pixel maximum contact error'}for side in ('r','l')]
            cup=list({landmarks['landmarks'][grip['cup_landmark']]['drawable_id']for grip in grips})
            contract={'parameters':{'cup_hold':'ParamCupHold','cup_visible':'ParamCupVisible','cup_x':'ParamCupX',
                'held_sweep':args.axes,'held_roles':{roles[pid]:pid for pid in args.axes}},
                'held_pose':{'ParamCupHold':1,'ParamCupVisible':1},'visibility_values':{'shown':1,'hidden':0},
                'meshes':{'cup':cup},'grips':grips,'fingers':[],'arm_hand_controls':[],'semantic_probes':[]}
            validate_actual_bindings(actual['rest'],actual['topology'],contract,landmarks)
            support=page.evaluate('points=>__handCup.alphaSupport(points)',[requests['grip_'+side+'_cup']['source_canvas']for side in ('r','l')])
            for item,side in zip(support,('r','l')):
                expected={landmarks['landmarks']['grip_'+side+'_cup']['drawable_id'],landmarks['landmarks']['grip_'+side+'_palm']['drawable_id']}
                owners={d['id']for d in item['supports']if d['alpha']>=32 and d['opacity']>0 and d['mask_count']==0}
                assert expected<=owners,'actual contact guide has no opaque cup/palm texture support: '+str((item,expected))
            report['actual_default']={'core_version':actual['coreVersion'],'moc_version':actual['mocVersion'],'consistency':actual['mocConsistency'],
                'parameters':len(parameters),'drawables':len(actual['rest']['drawables']),'cup_hold':parameters['ParamCupHold'],'source_grip_support':support}
            report['checks']['real_new_core_cuphold_default_ranges_and_fresh_alpha_supported_grip_triangles']='passed'
            calls=0
            def pose(values):
                nonlocal calls
                raw=page.evaluate('v=>__handCup.rawPose(v)',values)
                product=page.evaluate('v=>__handCup.productPose(v)',values)
                calls+=1
                if calls%10==0:
                    gl=page.evaluate('()=>__handCup.pixels(null)');assert gl['error']==0 and gl['colored']>1000,gl
                return {'raw':raw,'product':product}
            report['held_sweep']={}
            measure_held_sweep(pose,contract,landmarks,parameters,report['held_sweep'],args.interior_count,sample_grid=sample_grid)
            report['checks']['actual_body_breath_detached_root_and_visible_held_grips_with_off_key_interpolation']='passed'
            extreme={pid:parameters[pid]['max']for pid in args.axes}
            pose({**extreme,'ParamCupHold':0});page.screenshot(path=str(evidence/'01-detached-body-breath-extreme.png'))
            pose({**extreme,'ParamCupHold':1});page.screenshot(path=str(evidence/'02-held-same-body-breath-extreme.png'))
            wrong=pose({**extreme,'ParamCupHold':1,'ParamCupX':parameters['ParamCupX']['max']})
            report['negative_control']=expect_detected(lambda:assert_grips(wrong['product'],contract,landmarks),
                'actual CupX extreme while held must separate and fail the same one-pixel grip guard')
            report['checks']['actual_displaced_cup_negative_control_rejected']='passed'
            pose({'ParamCupHold':1});page.screenshot(path=str(evidence/'03-default-held.png'))
            assert not report['page_errors'],report['page_errors'];page.evaluate('()=>__handCup.dispose()')
            report['checks']['javascript_runtime']='passed';report['status']='partial_checks_passed_full_acceptance_blocked'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
    finally:
        if fixture:fixture.tearDown()
        report['sources_unchanged']=all(Path(path).is_file()and sha(Path(path))==digest for path,digest in report['sources'].items())
        if not report['sources_unchanged']:report.update(status='failed',source_change_error='source changed while evaluating')
        write_report(args.output,report)
    print(json.dumps({'status':report['status'],'checks':report['checks'],'error':report.get('error'),'held_sweep':report.get('held_sweep')},ensure_ascii=False))
    raise SystemExit(0 if report['status']=='partial_checks_passed_full_acceptance_blocked'else 2)


if __name__=='__main__':main()
