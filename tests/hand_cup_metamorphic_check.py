"""Actual Core + product-adapter hand/cup metamorphic acceptance.

Run only after the final exporter has supplied measured landmarks and a reviewed
functional contract. Missing CupHold, unreviewed anatomy, or missing authored
actions is BLOCKED, never a skipped green check. This does not certify artwork,
Windows/4060, physical hardware, or official Editor re-opening.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import datetime
import hashlib
import io
import itertools
import json
import math
import os
import struct
from pathlib import Path, PurePosixPath
import traceback
import zipfile

from hand_cup_contract import validate
from hand_cup_measurements import (angle_difference, assert_grips, bend_degrees, by_id, changed, distance,
    grip_errors, invariant_except, measure_held_sweep, protected_points_unchanged, semantic_anchors, semantic_ownership, source_point, validate_actual_bindings, assert_hidden_helpers, cup_control_meshes)

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ['frontend/live2d-renderer.mjs', 'app/static/live2d-renderer.js',
           'app/static/scene-controller.js', 'app/static/studio.js', 'app/static/app.js']
OWN = ['tests/hand_cup_metamorphic_check.py', 'tests/hand_cup_browser.mjs',
       'tests/hand_cup_contract.py', 'tests/hand_cup_measurements.py']
HOOK = """(()=>{let runtime;Object.defineProperty(window,'CompanionLive2DRuntime',{
 configurable:true,get(){return runtime;},set(value){runtime=value;
 const init=value.PIXI.Application.prototype.init;
 value.PIXI.Application.prototype.init=async function(options){await init.call(this,options);
 (window.__actualPixiApps??=[]).push(this);};}});})()"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_binding_files(runtime):
    from live2d_original_core_check import installed_script
    result=[]
    for kind in ('core','bundle'):
        script=installed_script(runtime,kind)
        result.extend([runtime/(kind+'.json'),script.parent/'record.json',script])
    return result


def runtime_files(model):
    """Follow actual model references only; never glob PSDs or historical exports."""
    setting = json.loads(model.read_text())
    refs = setting['FileReferences']
    names = [refs['Moc'], *refs['Textures']]
    names += [refs[key] for key in ('Physics', 'Pose', 'DisplayInfo') if refs.get(key)]
    names += [entry['File'] for entry in refs.get('Expressions', [])]
    names += [entry['File'] for rows in refs.get('Motions', {}).values() for entry in rows]
    files = [model]
    for name in names:
        relative = PurePosixPath(name)
        if not isinstance(name, str) or relative.is_absolute() or '..' in relative.parts or ':' in name or '\\' in name:
            raise ValueError('unsafe runtime reference')
        path = model.parent / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(model.parent.resolve()):
            raise ValueError('missing/unsafe actual runtime file: ' + name)
        files.append(path.resolve())
    return list(dict.fromkeys(files))


def archive(model, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as result:
        for path in files:
            result.write(path, path.relative_to(model.parent).as_posix())
    if len(buffer.getvalue()) > 32 * 1024 * 1024:
        raise ValueError('runtime fixture exceeds the actual import budget')
    return buffer.getvalue()


def expect_detected(operation, description):
    """A deliberately wrong *actual measured state* must fail the same guard."""
    try:
        operation()
    except AssertionError as error:
        return {'rejected': True, 'reason': str(error), 'negative_control': description}
    raise AssertionError('detector failed its actual-state negative control: ' + description)


@contextmanager
def recorded_browser(pw, evidence):
    """Flush the real recording and take failure evidence before disconnecting."""
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
        args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    context=browser.new_context(viewport={'width':1440,'height':1000},
        record_video_dir=str(evidence/'video'),record_video_size={'width':1440,'height':1000})
    page=context.new_page()
    try:
        yield browser,context,page
    except BaseException:
        try:
            page.screenshot(path=str(evidence/'FAILED.png'))
        except Exception:
            pass
        raise
    finally:
        try:
            context.close()
        finally:
            browser.close()


def run(args):
    report = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'RUNNING', 'checks': {}, 'negative_controls': {},
              'scope': 'Actual owner-installed Core and production adapter; finite declared hand/cup poses, exact non-target geometry/opacity, real GL visibility, reviewed texture ownership.',
              'artwork_accepted': False, 'windows_executed': False,
              'not_proven': ['human art acceptance', 'all continuous parameter combinations',
                             'official Editor reopening', 'Windows/4060', 'physical hardware']}
    fixture = None
    errors = []
    paths = []
    try:
        model, contract_path, landmark_path, source = [Path(value).resolve() for value in
            (args.model, args.contract, args.landmarks, args.source_manifest)]
        contract, landmarks = json.loads(contract_path.read_text()), json.loads(landmark_path.read_text())
        validate(contract, landmarks)
        files = runtime_files(model)
        binding = contract['model_binding']
        moc = model.parent / json.loads(model.read_text())['FileReferences']['Moc']
        for field, path in [('model3_sha256', model), ('moc3_sha256', moc),
                            ('landmarks_sha256', landmark_path), ('source_manifest_sha256', source)]:
            if binding[field] != sha(path):
                raise ValueError('final actual source binding mismatch: ' + field)
        source_manifest = json.loads(source.read_text())
        art_files = []
        for entry in source_manifest.get('layers', []):
            art_file = (source.parent / entry['file']).resolve()
            if not art_file.is_relative_to(source.parent) or art_file.is_symlink() or sha(art_file)!=entry['sha256']:
                raise ValueError('final reviewed art layer binding mismatch')
            art_files.append(art_file)
        runtime = Path(args.runtime_dir).resolve()
        vendor_files = runtime_binding_files(runtime)
        paths = files + art_files + vendor_files + [contract_path, landmark_path, source] + [ROOT / name for name in PRODUCT + OWN]
        report['sources'] = {str(path): sha(path) for path in dict.fromkeys(paths)}
        report['checks']['reviewed_contract_and_exact_final_export_binding'] = 'passed'
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        report.update(status='BLOCKED', error=str(error), traceback=traceback.format_exc())
        write_report(args.output, report)
        return report

    os.environ['COMPANION_LIVE2D_RUNTIME'] = str(Path(args.runtime_dir).resolve())
    from playwright.sync_api import sync_playwright
    from test_character_http import CharacterHTTPTests
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        fixture = CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
        fixture.setUp()
        with sync_playwright() as pw, recorded_browser(pw,evidence) as (browser,context,page):
            page.add_init_script(HOOK)
            page.on('pageerror', lambda error: errors.append(str(error)))
            base = 'http://127.0.0.1:' + str(fixture.server.server_port)
            page.goto(base)
            page.wait_for_function('()=>CompanionApp.core.get().state!==null')
            role = page.evaluate('()=>CompanionApp.core.scope().character_id')
            data = archive(model, files)
            headers = {'X-Companion':'local-app'}
            response = page.request.post(base + '/api/characters/assets/import', headers=headers,
                data={'character_id':role,'format':'live2d','model':{
                    'filename':'original-hand-cup-acceptance.zip','data_base64':base64.b64encode(data).decode()}})
            assert response.ok, response.text()
            asset = response.json()['asset']
            response = page.request.post(base + '/api/characters/assets/activate', headers=headers,
                data={'character_id':role,'asset_id':asset['id']})
            assert response.ok, response.text()
            page.evaluate('()=>CompanionApp.core.refresh(true)')
            page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2', timeout=60000)
            page.evaluate((ROOT / 'tests/hand_cup_browser.mjs').read_text())
            actual = page.evaluate('asset=>__handCup.init(asset)', asset)
            validate_actual_bindings(actual['rest'], actual['topology'], contract, landmarks)
            page.evaluate('ids=>__handCup.setHiddenHelpers(ids)', contract['meshes'].get('cup_helpers', []))
            assert actual['canvasInfo'] == landmarks['canvasInfo'], 'actual canvas coordinate mapping differs'
            report['actual_model'] = {'core_version':actual['coreVersion'],'moc_version':actual['mocVersion'],
                'consistency':actual['mocConsistency'],'parameters':len(actual['rest']['parameters']),
                'drawables':len(actual['rest']['drawables']),'canvasInfo':actual['canvasInfo']}
            report['checks']['real_core_consistency_actual_ranges_triangles_landmarks'] = 'passed'
            params = {entry['id']: entry for entry in actual['rest']['parameters']}
            cup = set(contract['meshes']['cup'])
            cup_targets = cup_control_meshes(contract)
            helpers = set(contract['meshes'].get('cup_helpers', []))
            torso = set(contract['meshes']['torso'])
            detached = contract['detached_pose']

            def pose(values):
                raw = page.evaluate('v=>__handCup.rawPose(v)', values)
                product = page.evaluate('v=>__handCup.productPose(v)', values)
                assert_hidden_helpers(raw, contract)
                assert_hidden_helpers(product, contract)
                for entry in product['parameters']:
                    requested=values.get(entry['id'], entry['default'])
                    expected=struct.unpack('<f',struct.pack('<f',requested))[0]
                    assert entry['value'] == expected, 'custom actual Core Float32 override did not reach its requested value'
                return {'raw':raw,'product':product}

            def pixels(key=None, compare=None):
                result = page.evaluate('([key,compare])=>__handCup.pixels(key,compare)', [key,compare])
                assert result['error'] == 0 and result['colored'] > 1000, 'real GL error or blank character: ' + str(result)
                return result

            baseline = pose(detached)
            pixels('baseline')
            page.screenshot(path=str(evidence / '01-detached-neutral.png'))
            # Same actual Core states, fresh evaluations, exact control, not hashes.
            repeated = pose(detached)
            for engine in ('raw','product'):
                assert not changed(baseline[engine], repeated[engine]), 'no-operation geometry/opacity is not stable'
            report['checks']['same_pose_repeated_actual_core_exact_geometry_opacity_negative'] = 'passed'

            shown = {**detached, contract['parameters']['cup_visible']:contract['visibility_values']['shown']}
            hidden = {**detached, contract['parameters']['cup_visible']:contract['visibility_values']['hidden']}
            a = pose(shown)
            pixels('visible')
            b = pose(hidden)
            for engine in ('raw','product'):
                changed_ids = invariant_except(a[engine], b[engine], cup)
                assert changed_ids, 'CupVisible changes no actual cup drawable'
                aa, bb = by_id(a[engine]), by_id(b[engine])
                for mesh in cup:
                    assert aa[mesh]['opacity'] > 0 and bb[mesh]['opacity'] == 0, 'CupVisible does not fully hide just the cup'
                    assert aa[mesh]['vertices'] == bb[mesh]['vertices'], 'visibility unexpectedly changes cup geometry'
            delta = pixels(compare='visible')
            assert delta['changed'] > 0, 'hidden cup has no real visible pixel difference'
            report['visibility'] = delta
            report['checks']['detached_cup_visible_only_hides_cup_no_hand_finger_torso_change'] = 'passed'
            page.screenshot(path=str(evidence / '02-empty-cup-hidden.png'))

            transforms = []
            for item in contract['cup_transforms']:
                first = pose({**shown,item['parameter']:item['values'][0]})
                pixels('transform')
                second = pose({**shown,item['parameter']:item['values'][1]})
                for engine in ('raw','product'):
                    changed_ids = invariant_except(first[engine], second[engine], cup_targets)
                    assert changed_ids & cup, 'cup transform has no actual visible-cup geometry effect'
                delta = pixels(compare='transform')
                assert delta['changed'] > 0, 'cup transform affects no visible pixels'
                transforms.append({'parameter':item['parameter'],'values':item['values'],'visible_pixels':delta['changed']})
            report['cup_transforms'] = transforms
            report['checks']['cup_xy_nonaliased_rotation_only_change_actual_cup_and_visible_pixels'] = 'passed'

            fingers = []
            for index,item in enumerate(contract['fingers']):
                first = pose({**hidden,item['parameter']:item['values'][0]})
                pixels('finger')
                second = pose({**hidden,item['parameter']:item['values'][1]})
                measurements = {}
                for engine in ('raw','product'):
                    changed_ids = invariant_except(first[engine],second[engine],set(item['meshes']) | helpers)
                    assert set(item['meshes']) <= changed_ids, 'finger mesh is declared but does not actually deform'
                    root = landmarks['landmarks'][item['root_landmark']]
                    palm_root = landmarks['landmarks'][item['palm_root_landmark']]
                    joint = landmarks['landmarks'][item['joint_landmark']]
                    tip = landmarks['landmarks'][item['tip_landmark']]
                    root_drift = distance(source_point(first[engine],root,actual['canvasInfo']),source_point(second[engine],root,actual['canvasInfo']))
                    tip_movement = distance(source_point(first[engine],tip,actual['canvasInfo']),source_point(second[engine],tip,actual['canvasInfo']))
                    assert root_drift <= item['root_tolerance_px'], 'curl detaches the actual finger root'
                    palm_seam = max(distance(source_point(snapshot,root,actual['canvasInfo']),source_point(snapshot,palm_root,actual['canvasInfo'])) for snapshot in (first[engine],second[engine]))
                    assert palm_seam <= item['root_tolerance_px'], 'fixed root does not remain attached to the actual palm'
                    assert tip_movement >= item['min_tip_movement_px'], 'finger control is too small or moves no real tip'
                    bends = [bend_degrees(*(source_point(snapshot,point,actual['canvasInfo']) for point in (root,joint,tip))) for snapshot in (first[engine],second[engine])]
                    bending = angle_difference(*bends)
                    assert bending >= item['min_bend_degrees'], 'whole-finger rigid rotation does not satisfy actual Curl bending'
                    measurements[engine] = {'root_drift_source_px':root_drift,'palm_seam_source_px':palm_seam,'tip_movement_source_px':tip_movement,'bend_change_degrees':bending,'changed_meshes':sorted(changed_ids)}
                delta = pixels(compare='finger')
                assert delta['changed'] > 0, 'finger deforms but is completely hidden in actual GL'
                fingers.append({'name':item['name'],'parameter':item['parameter'],'geometry':measurements,'visible_pixels':delta['changed']})
                page.screenshot(path=str(evidence / f'finger-{index+1:02d}.png'))
            report['fingers'] = fingers
            report['checks']['ten_actual_fingers_deform_visibly_with_fixed_roots_other_parts_exact'] = 'passed'

            points = [point for item in contract['semantic_probes'] for point in item['source_points']]
            support = page.evaluate('points=>__handCup.alphaSupport(points)', points)
            report['semantic_support'] = support
            report['semantic_owners'] = semantic_ownership(support, contract['semantic_probes'])
            protected_anchors = semantic_anchors(support, contract['semantic_probes'])
            report['checks']['reviewed_torso_points_owned_by_actual_textured_torso_not_arm_or_cuff'] = 'passed'

            limbs = []
            for item in contract['arm_hand_controls']:
                first = pose({**shown,item['parameter']:item['values'][0]})
                pixels('limb')
                second = pose({**shown,item['parameter']:item['values'][1]})
                for engine in ('raw','product'):
                    changed_ids = invariant_except(first[engine],second[engine],set(item['meshes']) | helpers)
                    assert changed_ids, 'actual limb control produces no geometry change'
                    assert not changed_ids & cup, 'detached limb moves the detached cup'
                    protected_points_unchanged(first[engine],second[engine],protected_anchors,actual['canvasInfo'])
                    for finger in contract['fingers']:
                        if finger['side']!=item['side']:
                            continue
                        root=landmarks['landmarks'][finger['root_landmark']]
                        palm=landmarks['landmarks'][finger['palm_root_landmark']]
                        for snapshot in (first[engine],second[engine]):
                            assert distance(source_point(snapshot,root,actual['canvasInfo']),source_point(snapshot,palm,actual['canvasInfo']))<=finger['root_tolerance_px'], 'arm/hand control separates a real finger root from its palm'
                delta = pixels(compare='limb')
                assert delta['changed'] > 0
                limbs.append({'parameter':item['parameter'],'side':item['side'],'kind':item['kind'],'visible_pixels':delta['changed']})
            report['limbs'] = limbs
            report['checks']['detached_arm_hand_motion_leaves_cup_and_semantic_torso_exact'] = 'passed'

            report['held_sweep']={}
            measure_held_sweep(pose,contract,landmarks,params,report['held_sweep'])
            report['checks']['held_body_breath_extreme_combinations_keep_both_actual_grip_contacts'] = 'passed'
            page.screenshot(path=str(evidence / '03-held-body-breath-extreme.png'))

            # Strong negative: preserve the real CupVisible change and additionally
            # curl an actual finger. The exact same invariant guard must detect it.
            item = contract['fingers'][0]
            bad = pose({**hidden,item['parameter']:item['values'][1]})
            report['negative_controls']['non_target_finger_change'] = expect_detected(
                lambda:invariant_except(a['product'],bad['product'],cup),
                'actual CupVisible hide plus actual authored finger curl must not pass cup-only invariant')
            bad_grip = pose({**contract['held_pose'],contract['parameters']['cup_x']:params[contract['parameters']['cup_x']]['max']})
            report['negative_controls']['actual_cup_displaced_from_held_contacts'] = expect_detected(
                lambda:assert_grips(bad_grip['product'],contract,landmarks),
                'actual held CupX extreme separates the grip and must be rejected')
            report['negative_controls']['nonexistent_actual_parameter'] = page.evaluate('''async()=>{
              const before=CompanionApp.scene.getDiagnostics().parameters.length;
              let rejected=false;try{await CompanionApp.scene.applyControls({parameters:[{id:'__NOT_AN_AUTHORED_PARAMETER__',value:0}]});}catch{rejected=true;}
              return {rejected,parameter_count_unchanged:before===CompanionApp.scene.getDiagnostics().parameters.length};}''')
            assert all(report['negative_controls']['nonexistent_actual_parameter'].values())
            report['checks']['strong_actual_geometry_grip_unknown_id_negative_controls'] = 'passed'

            actions = []
            diagnostics = page.evaluate('()=>CompanionApp.scene.getDiagnostics()')
            for item in contract['actions']:
                if item['kind']=='motion':
                    assert 0 <= item['index'] < diagnostics['motions'].get(item['group'],0), 'required action is not in the actual model package'
                else:
                    assert item['name'] in diagnostics['expressions'], 'required expression is not in the actual model package'
                before = page.evaluate('v=>__handCup.productPose(v,true)',item['start_pose'])
                pixels('action')
                after = page.evaluate('item=>__handCup.action(item)', item)
                actual_values = {entry['id']:entry['value'] for entry in after['parameters']}
                for pid,value in item['expect_parameters'].items():
                    assert abs(actual_values[pid]-value) <= item['parameter_tolerance'], 'action terminal Core parameter does not match authored contract: ' + str((item['role'],pid,actual_values[pid],value))
                changed_meshes=changed(before,after)
                assert changed_meshes & set(item['target_meshes']), 'authored action changes no declared target geometry or opacity'
                if item['role']=='wave':
                    assert changed_meshes & set(contract['meshes']['palms']+contract['meshes']['arms']), 'finger-only curl is not a real waving hand/arm action'
                delta = pixels(compare='action')
                assert delta['changed'] > 0, 'authored action is completely invisible'
                if item['role']=='empty_hands':
                    assert all(by_id(after)[mesh]['opacity']==0 for mesh in cup)
                    assert all(by_id(after)[mesh]['opacity']>0 for mesh in contract['meshes']['palms'])
                    assert all(by_id(after)[mesh]['opacity']>0 for finger in contract['fingers'] for mesh in finger['meshes'])
                if item['role']=='hold':
                    assert_grips(after,contract,landmarks)
                page.screenshot(path=str(evidence / ('action-'+item['role']+'.png')))
                actions.append({'role':item['role'],'elapsed_model_seconds':after['elapsed_model_seconds'],'actual_parameters':{pid:actual_values[pid] for pid in item['expect_parameters']},'changed_target_meshes':sorted(changed_meshes & set(item['target_meshes'])),'visible_pixels':delta['changed'],'actual_core_trajectory':after['trajectory']})
            report['actions'] = actions
            report['checks']['authored_hold_detach_wave_empty_hands_actions_real_core_and_gl'] = 'passed'

            # Real current Studio must expose declared actions. The preview is a
            # real separate owner and does not activate itself over this role.
            await_ui_actions(page, contract, data, evidence, report)
            assert not errors, errors
            report['checks']['javascript_runtime'] = 'passed'
            page.evaluate('()=>__handCup.dispose()')
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        if 'page' in locals():
            try:
                page.screenshot(path=str(evidence / 'FAILED.png'))
            except Exception:
                pass
    finally:
        if fixture:
            fixture.tearDown()
        report['page_errors'] = errors
        report['sources_unchanged'] = all(Path(path).is_file() and sha(Path(path))==digest for path,digest in report.get('sources',{}).items())
        if not report['sources_unchanged']:
            report['status'] = 'failed'
            report['source_change_error'] = 'source changed while measuring; rerun the affected gates'
        write_report(args.output,report)
    return report


def await_ui_actions(page, contract, data, evidence, report):
    page.evaluate('''()=>{const original=CompanionScene;window.__handCupPreviews=[];
      window.CompanionScene={...original,create(options){const instance=original.create(options);__handCupPreviews.push(instance);return instance;}};}''')
    old_id = page.evaluate('()=>CompanionApp.core.get().state.active_character.appearance_id')
    page.locator('#open-studio').click()
    page.locator('#studio-format').select_option('live2d')
    page.locator('#studio-model').set_input_files({'name':'original-hand-cup.zip','mimeType':'application/zip','buffer':data})
    page.get_by_role('button',name='上传并检查预览',exact=True).click()
    page.wait_for_function('()=>!document.querySelector("#studio-activate").disabled',timeout=60000)
    assert old_id==page.evaluate('()=>CompanionApp.core.get().state.active_character.appearance_id')
    page.get_by_text('检查模型动作',exact=True).click()
    seen = []
    for item in contract['actions']:
        before=page.evaluate('''async startPose=>{const controller=__handCupPreviews.at(-1);
          await controller.applyControls({reset:true,idleMotion:false,breath:false,autoBlink:false,physics:false,expression:null});
          const defaults=controller.getDiagnostics().parameters.map(p=>({id:p.id,value:p.default}));
          for(let i=0;i<defaults.length;i+=32)await controller.applyControls({parameters:defaults.slice(i,i+32)});
          let marker=controller.getDiagnostics().coreEvaluations;
          while(controller.getDiagnostics().coreEvaluations<marker+4)await new Promise(requestAnimationFrame);
          await controller.applyControls({reset:true});
          const app=__actualPixiApps.findLast(app=>app.canvas?.closest('#studio-preview')&&app.stage?.children?.some(c=>c.internalModel));
          if(!app)throw Error('No actual Studio Core');
          const core=app.stage.children.find(c=>c.internalModel).internalModel.coreModel,info=controller.getDiagnostics().parameters;
          for(const [id,value]of Object.entries(startPose)){
            const entry=info.find(p=>p.id===id);if(!entry)throw Error('Missing actual initial Studio parameter');
            core.setParameterValueByIndex(entry.index,value);
          }
          core.saveParameters();return await __handCup.stable(controller);}''',item['start_pose'])
        if item['kind']=='expression':
            page.locator('#studio-model-expression').select_option(item['name'])
        else:
            option = json.dumps({'group':item['group'],'index':item['index']},ensure_ascii=False,separators=(',',':'))
            page.locator('#studio-model-motion').select_option(option)
            page.get_by_role('button',name='播放所选动作',exact=True).click()
        target = item['expect_parameters']
        page.wait_for_function('''args=>{const d=__handCupPreviews.at(-1).getDiagnostics({drawables:true,includeVertices:true}),p=d.parameters;
          if(d.coreEvaluations<=args.before.evaluations||d.verticesTruncated||d.drawablesTruncated)return false;
          const parameterMatch=Object.entries(args.values).every(([id,value])=>p.some(item=>item.id===id&&Math.abs(item.value-value)<=args.tolerance));
          const geometryChanged=d.drawables.some(item=>args.targets.includes(item.id)&&args.before.drawables.some(old=>old.id===item.id&&(old.opacity!==item.opacity||old.vertices.some((value,i)=>value!==item.vertices[i]))));
          return parameterMatch&&geometryChanged;}''',
          arg={'values':target,'tolerance':item['parameter_tolerance'],'before':before,'targets':item['target_meshes']},timeout=int(item['sample_seconds']*5000+10000))
        assert page.locator('.preview-model-controls .inline-error').is_hidden()
        seen.append(item['role'])
    page.screenshot(path=str(evidence / '04-real-studio-authored-actions.png'))
    page.keyboard.press('Escape')
    assert page.evaluate('()=>__handCupPreviews.at(-1).getDiagnostics().available') is False
    assert page.locator('#open-studio').evaluate('(node)=>node===document.activeElement')
    report['studio_actions'] = seen
    report['checks']['current_studio_real_import_preview_declared_action_controls_dispose_focus'] = 'passed'


def write_report(output, report):
    path = Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','contract','landmarks','source-manifest','runtime-dir','output','evidence-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    report=run(args)
    print(json.dumps({'status':report['status'],'checks':report['checks'],'error':report.get('error')},ensure_ascii=False))
    raise SystemExit(0 if report['status']=='passed' else 2)


if __name__=='__main__':
    main()
