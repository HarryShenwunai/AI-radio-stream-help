"""Partial actual-Core probe before a full functional hand/cup contract exists.

Never reports full acceptance. Actual CupHold, curl joints and authored actions
must separately pass hand_cup_metamorphic_check.py. This early probe exercises
the real browser measurement code and catches bad anatomy assignments early.
"""
import argparse
import datetime
import json
import base64
import os
from pathlib import Path
import traceback

from hand_cup_measurements import (angle_difference,bend_degrees,distance,invariant_except,
    semantic_ownership,source_point,validate_actual_bindings)
from hand_cup_metamorphic_check import ROOT, HOOK, PRODUCT, OWN, archive, recorded_browser, runtime_binding_files, runtime_files, sha, write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','rig-contract','runtime-dir','output','evidence-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--landmarks')
    parser.add_argument('--joint-landmarks')
    parser.add_argument('--additional-body-owner',action='append',default=[],help='Explicitly reviewed extra body-only alpha owner, such as a backfill')
    args=parser.parse_args()
    os.environ['COMPANION_LIVE2D_RUNTIME']=str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    model=Path(args.model).resolve();contract_path=Path(args.rig_contract).resolve()
    contract=json.loads(contract_path.read_text())
    files=runtime_files(model)
    measured=None
    if bool(args.landmarks)!=bool(args.joint_landmarks):
        raise ValueError('root/tip and joint contracts must be supplied together')
    if args.landmarks:
        landmark_paths=[Path(args.landmarks).resolve(),Path(args.joint_landmarks).resolve()]
        measured=json.loads(landmark_paths[0].read_text());joints=json.loads(landmark_paths[1].read_text())
        if measured['parameters']!=joints['parameters'] or measured['canvasInfo']!=joints['canvasInfo']:
            raise ValueError('root/tip and joint measurements belong to different real Core rests')
        if set(measured['landmarks'])&set(joints['landmarks']):
            raise ValueError('joint mapping must not replace root/tip points')
        measured['landmarks'].update(joints['landmarks'])
    output=Path(args.evidence_dir).resolve();output.mkdir(parents=True,exist_ok=True)
    paths=files+[contract_path,Path(__file__).resolve()]+[ROOT/name for name in PRODUCT+OWN]
    paths+=runtime_binding_files(Path(args.runtime_dir).resolve())
    if measured:paths+=landmark_paths
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING',
        'scope':'Partial real-Core and product-adapter probe of intermediate candidate; not final full character acceptance',
        'checks':{},'full_acceptance':'BLOCKED','artwork_accepted':False,'windows_executed':False,
        'sources':{str(path):sha(path) for path in paths},'blocked_items':[]}
    errors=[];fixture=None
    try:
        fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');fixture.setUp()
        with sync_playwright()as pw,recorded_browser(pw,output)as(browser,context,page):
            page.add_init_script(HOOK);page.on('pageerror',lambda error:errors.append(str(error)))
            base='http://127.0.0.1:'+str(fixture.server.server_port);page.goto(base);page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            role=page.evaluate('()=>CompanionApp.core.scope().character_id');headers={'X-Companion':'local-app'}
            response=page.request.post(base+'/api/characters/assets/import',headers=headers,data={'character_id':role,'format':'live2d','model':{'filename':'actual-intermediate-hand-cup.zip','data_base64':base64.b64encode(archive(model,files)).decode()}})
            assert response.ok,response.text();asset=response.json()['asset']
            response=page.request.post(base+'/api/characters/assets/activate',headers=headers,data={'character_id':role,'asset_id':asset['id']});assert response.ok,response.text()
            page.evaluate('()=>CompanionApp.core.refresh(true)');page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2',timeout=60000)
            page.evaluate((ROOT/'tests/hand_cup_browser.mjs').read_text());actual=page.evaluate('asset=>__handCup.init(asset)',asset)
            params={p['id']:p for p in actual['rest']['parameters']};cup=contract['meshes']['cup']
            report['actual_core']={'version':actual['coreVersion'],'consistency':actual['mocConsistency'],'parameters':len(params),'drawables':len(actual['rest']['drawables']),'canvasInfo':actual['canvasInfo']}
            report['checks']['actual_product_import_runtime_and_independent_consistent_core']='passed'
            for parameter in ('ParamCupVisible','ParamCupX','ParamCupY','ParamCupRotation'):
                assert parameter in params,'candidate does not actually author '+parameter
            def pose(values):
                return {'raw':page.evaluate('v=>__handCup.rawPose(v)',values),'product':page.evaluate('v=>__handCup.productPose(v)',values)}
            pose({});page.evaluate('()=>__handCup.pixels("neutral")');page.screenshot(path=str(output/'01-neutral.png'))
            a=pose({'ParamCupVisible':1});page.evaluate('()=>__handCup.pixels("shown")')
            b=pose({'ParamCupVisible':0})
            for engine in ('raw','product'):
                assert invariant_except(a[engine],b[engine],cup)
                before={d['id']:d for d in a[engine]['drawables']};after={d['id']:d for d in b[engine]['drawables']}
                assert all(after[mid]['opacity']==0 and before[mid]['opacity']>0 and before[mid]['vertices']==after[mid]['vertices'] for mid in cup)
            delta=page.evaluate('()=>__handCup.pixels(null,"shown")');assert delta['error']==0 and delta['changed']>0,delta
            report['visibility_pixels']=delta;report['checks']['cup_visibility_only_cup_changes_actual_raw_product_geometry_opacity_and_pixels']='passed'
            page.screenshot(path=str(output/'02-cup-hidden.png'))
            results=[]
            for pid in ('ParamCupX','ParamCupY','ParamCupRotation'):
                values=[params[pid]['min'],params[pid]['max']]
                assert pid!='ParamCupRotation' or abs((values[1]-values[0])%360)>1e-7
                a=pose({pid:values[0]});page.evaluate('()=>__handCup.pixels("transform")')
                b=pose({pid:values[1]})
                for engine in ('raw','product'):assert invariant_except(a[engine],b[engine],cup)
                delta=page.evaluate('()=>__handCup.pixels(null,"transform")');assert delta['error']==0 and delta['changed']>0,delta
                results.append({'parameter':pid,'values':values,'pixels':delta['changed']})
            report['transforms']=results;report['checks']['cup_xy_rotation_change_only_real_cup_and_actual_pixels']='passed'
            actual_ids={d['id']for d in actual['rest']['drawables']}
            assert set(args.additional_body_owner)<=actual_ids,'reviewed body backfill is not an actual Core drawable'
            probes=[{**entry,'source_points':[entry['source_canvas']],
                'allowed_meshes':list(dict.fromkeys(entry['allowed_meshes']+args.additional_body_owner))} for entry in contract['semantic_probes']]
            report['explicit_additional_reviewed_body_owners']=args.additional_body_owner
            supports=page.evaluate('points=>__handCup.alphaSupport(points)',[point for probe in probes for point in probe['source_points']])
            report['semantic_supports']=supports;report['semantic_owners']=semantic_ownership(supports,probes)
            report['checks']['reviewed_torso_points_actual_triangles_texture_alpha_exclude_arms']='passed'
            if measured:
                validate_actual_bindings(actual['rest'],actual['topology'],
                    {'meshes':{'cup':cup},'fingers':[],'arm_hand_controls':[],'semantic_probes':probes},measured)
                assert actual['canvasInfo']==measured['canvasInfo']
                results=[];failed=[]
                for name,mesh in contract['meshes']['fingers'].items():
                    # These explicit IDs exist in the exporter recipe and are
                    # checked against genuine Core, never created by lookup.
                    _,digit,side=name.split('-');pid='ParamFinger'+digit.title()+side.upper()
                    assert pid in params,'authored finger mapping not present in actual Core: '+pid
                    points=[measured['landmarks'][name+'_'+kind] for kind in ('root','joint','tip')]
                    palm_root=measured['landmarks'][name+'_palm_root']
                    assert all(point['drawable_id']==mesh for point in points)
                    first=pose({pid:params[pid]['min'],'ParamCupVisible':0});page.evaluate('()=>__handCup.pixels("finger")')
                    second=pose({pid:params[pid]['max'],'ParamCupVisible':0})
                    metrics={}
                    for engine in ('raw','product'):
                        changed=invariant_except(first[engine],second[engine],[mesh]);assert changed,'finger control changes no real mesh'
                        a=[source_point(first[engine],point,actual['canvasInfo']) for point in points]
                        b=[source_point(second[engine],point,actual['canvasInfo']) for point in points]
                        metrics[engine]={'root_drift_source_px':distance(a[0],b[0]),'tip_movement_source_px':distance(a[2],b[2]),
                            'palm_seam_source_px':max(distance(source_point(snapshot,points[0],actual['canvasInfo']),source_point(snapshot,palm_root,actual['canvasInfo'])) for snapshot in (first[engine],second[engine])),
                            'bend_change_degrees':angle_difference(bend_degrees(*a),bend_degrees(*b))}
                    delta=page.evaluate('()=>__handCup.pixels(null,"finger")');assert delta['error']==0
                    result={'name':name,'parameter':pid,'mesh':mesh,'metrics':metrics,'visible_pixels':delta['changed']}
                    result['passes_root_tip_nonrigid_visible']=all(value['root_drift_source_px']<=.5 and value['palm_seam_source_px']<=.5 and value['tip_movement_source_px']>=1 and value['bend_change_degrees']>=1 for value in metrics.values()) and delta['changed']>0
                    if not result['passes_root_tip_nonrigid_visible']:failed.append(name)
                    results.append(result)
                    page.screenshot(path=str(output/(name+'-curl-max.png')))
                report['curl']={'root_budget_source_px':.5,'minimum_tip_source_px':1,'minimum_bend_degrees':1,
                    'budget_basis':'predeclared instrument thresholds before r3b evaluation; exact non-target meshes and actual visible GL required',
                    'fingers':results,'failed':failed}
                assert not failed,'actual root/tip/nonrigid/visible curl checks failed: '+str(failed)
                report['checks']['ten_real_fingers_nonrigid_joint_curl_fixed_roots_non_target_exact_visible']='passed'
            pose({});page.screenshot(path=str(output/'03-neutral-after-probes.png'))
            if 'ParamCupHold' not in params:report['blocked_items'].append('Actual Core has no CupHold=0/1; held Body/Breath compensation not implemented')
            if not measured:report['blocked_items'].append('Final root/joint/tip curl contract not yet evaluated')
            report['blocked_items']+=['Both final held grip contracts and Body/Breath compensation not yet accepted','Full held/detach/wave/empty_hands authored actions not yet accepted','Human artwork acceptance and Windows execution not tested']
            assert not errors,errors;report['checks']['javascript_runtime']='passed';page.evaluate('()=>__handCup.dispose()')
            report['status']='partial_checks_passed_full_acceptance_blocked'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if 'page'in locals():
            try:page.screenshot(path=str(output/'FAILED.png'))
            except Exception:pass
    finally:
        if fixture:fixture.tearDown()
        report['page_errors']=errors;report['sources_unchanged']=all(sha(Path(path))==digest for path,digest in report['sources'].items())
        if not report['sources_unchanged']:report.update(status='failed',source_change_error='sources changed during probe')
        write_report(args.output,report)
    print(json.dumps({'status':report['status'],'checks':report['checks'],'error':report.get('error'),'blocked_items':report['blocked_items']},ensure_ascii=False))
    raise SystemExit(0 if report['status']=='partial_checks_passed_full_acceptance_blocked' else 2)


if __name__=='__main__':main()
