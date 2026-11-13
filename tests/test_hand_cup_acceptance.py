"""Detectors/contract unit tests use explicitly synthetic geometry only.

They test the acceptance instrument and cannot pass an actual character. The
full CLI separately requires a SHA-bound genuine Core export and Chrome.
"""
import copy
import math
import tempfile
import unittest
from pathlib import Path

from hand_cup_contract import FORMAT, FORMAT_V2, validate
from hand_cup_measurements import (angle_difference, assert_grips, bend_degrees,
    changed, invariant_except, measure_held_sweep, protected_points_unchanged, semantic_ownership, source_point, validate_actual_bindings, assert_hidden_helpers, cup_control_meshes)
from hand_cup_metamorphic_check import archive, expect_detected, runtime_files


def contracts():
    # No entry below is a claim about actual character anatomy or Core content.
    controls = ['T_Hold','T_Visible','T_X','T_Y','T_Rotation','ParamBodyAngleX','ParamBreath']
    controls += ['T_Finger'+str(i) for i in range(10)]
    controls += ['T_ArmL','T_ArmR','T_HandL','T_HandR']
    params = [{'id':pid,'min':0 if pid in ('T_Hold','T_Visible','ParamBreath') else -45,
               'max':1 if pid in ('T_Hold','T_Visible','ParamBreath') else 45,'default':1 if pid=='T_Visible' else 0} for pid in controls]
    names = ['T_Root'+str(i) for i in range(10)] + ['T_Joint'+str(i) for i in range(10)] + ['T_Tip'+str(i) for i in range(10)]
    names += ['T_CupL','T_CupR','T_PalmL','T_PalmR']
    landmarks = {'format':'actual-live2d-landmark-contract-v1','parameters':params,
        'canvasInfo':{'ppu':1,'originX':0,'originY':0,'width':100,'height':100},
        'landmarks':{name:{'drawable_id':'T_Cup' if 'Cup' in name else 'T_PalmL',
                'vertex_indices':[0,1,2],'weights':[1,0,0],'source_canvas':[0,0]} for name in names}}
    landmarks['landmarks']['T_PalmR']['drawable_id']='T_PalmR'
    for name in ('T_CupR','T_PalmR'):
        landmarks['landmarks'][name].update(weights=[0,1,0],source_canvas=[1,0])
    roles = {'cup_hold':'T_Hold','cup_visible':'T_Visible','cup_x':'T_X','cup_y':'T_Y','cup_rotation':'T_Rotation','held_sweep':['ParamBodyAngleX','ParamBreath'],'held_roles':{'body_x':'ParamBodyAngleX','breath':'ParamBreath'}}
    contract = {'format':FORMAT,'model_binding':{key:'a'*64 for key in ('model3_sha256','moc3_sha256','landmarks_sha256','source_manifest_sha256')},
        'parameters':roles,'detached_pose':{'T_Hold':0},'held_pose':{'T_Hold':1},'visibility_values':{'shown':1,'hidden':0},
        'meshes':{'cup':['T_Cup'],'torso':['T_Torso'],'palms':['T_PalmL','T_PalmR'],'arms':['T_ArmMeshL','T_ArmMeshR']},
        'cup_transforms':[{'parameter':pid,'values':[-45,45]} for pid in ('T_X','T_Y','T_Rotation')],
        'fingers':[{'name':'T_Finger'+str(i),'parameter':'T_Finger'+str(i),'side':'viewer_left' if i<5 else 'viewer_right',
                    'meshes':['T_FingerMesh'+str(i)],'values':[-12,12],'root_landmark':'T_Root'+str(i),
                    'joint_landmark':'T_Joint'+str(i),'palm_root_landmark':'T_PalmL' if i<5 else 'T_PalmR','tip_landmark':'T_Tip'+str(i),'root_tolerance_px':.5,
                    'min_tip_movement_px':1,'min_bend_degrees':1,'tolerance_basis':'explicit detector fixture budget'} for i in range(10)],
        'arm_hand_controls':[{'parameter':'T_'+kind+side,'side':'viewer_left' if side=='L' else 'viewer_right','kind':kind.lower(),
                    'meshes':['T_'+kind+'Mesh'+side],'values':[-1,1]} for kind in ('Arm','Hand') for side in ('L','R')],
        'grips':[{'cup_landmark':'T_Cup'+side,'hand_landmark':'T_Palm'+side,'tolerance_px':1,'tolerance_basis':'explicit detector fixture budget'} for side in ('L','R')],
        'semantic_probes':[{'reviewed':True,'review_basis':'explicit synthetic test only','source_points':[[0,0]],
                    'allowed_meshes':['T_Torso'],'forbidden_meshes':['T_ArmMeshL','T_ArmMeshR']}],
        'actions':[{'role':role,'kind':'expression','name':'T_'+role,'sample_seconds':1,'start_pose':{},
                    'target_meshes':['T_ArmMeshL'] if role=='wave' else ['T_Cup'],
                    'expect_parameters':{'T_Hold':1 if role=='hold' else 0, 'T_Visible':0 if role=='empty_hands' else 1},'parameter_tolerance':.01} for role in ('hold','detach','wave','empty_hands')]}
    return contract,landmarks


def snapshots():
    def mesh(pid):
        return {'id':pid,'vertices':[0,0,1,0,0,1],'opacity':1}
    return {'parameters':[],'drawables':[mesh(pid) for pid in ('T_Cup','T_Finger','T_Torso','T_PalmL','T_PalmR')]}


def helper_contract():
    contract,landmarks=contracts();contract['format']=FORMAT_V2
    contract['meshes']['cup_helpers']=['T_CupHelperL','T_CupHelperR']
    contract['cup_helper_bindings']=[{'mesh_id':mid,'source_object_id':mid,'source_parent_id':'T_Wrist'+side,
        'role':'invisible_cup_attachment','source_manifest_sha256':contract['model_binding']['source_manifest_sha256']}
        for mid,side in zip(contract['meshes']['cup_helpers'],('L','R'))]
    return contract,landmarks


class ContractTests(unittest.TestCase):
    def test_v2_two_source_bound_helpers_explicitly_extend_only_cup_transform_targets(self):
        c,l=helper_contract();validate(c,l)
        self.assertEqual(cup_control_meshes(c),{'T_Cup','T_CupHelperL','T_CupHelperR'})
        c['format']=FORMAT
        with self.assertRaisesRegex(ValueError,'explicit v2'):validate(c,l)

    def test_v2_rejects_extra_helper_and_source_identity_alias(self):
        c,l=helper_contract();c['meshes']['cup_helpers'].append('T_ThirdHelper')
        with self.assertRaisesRegex(ValueError,'exactly two'):validate(c,l)
        c,l=helper_contract();c['cup_helper_bindings'][0]['source_object_id']='T_Cup'
        with self.assertRaisesRegex(ValueError,'not alias'):validate(c,l)

    def test_v2_cannot_exempt_torso_finger_or_limb_as_cup_helper(self):
        c,l=helper_contract();c['meshes']['cup_helpers'][0]='T_Torso';c['cup_helper_bindings'][0].update(mesh_id='T_Torso',source_object_id='T_Torso')
        with self.assertRaisesRegex(ValueError,'disjoint'):validate(c,l)
        c,l=helper_contract();c['fingers'][0]['meshes']=['T_CupHelperL']
        with self.assertRaisesRegex(ValueError,'cannot claim'):validate(c,l)
        c,l=helper_contract();c['arm_hand_controls'][0]['meshes'].append('T_CupHelperL')
        with self.assertRaisesRegex(ValueError,'impersonate physical'):validate(c,l)

    def test_explicit_fixture_contract_is_structurally_complete_not_an_actual_pass(self):
        contract,landmarks=contracts()
        self.assertEqual(validate(contract,landmarks)['finger_count'],10)

    def test_missing_actual_cuphold_is_not_replaced_with_visibility(self):
        contract,landmarks=contracts()
        landmarks['parameters']=[p for p in landmarks['parameters'] if p['id']!='T_Hold']
        with self.assertRaisesRegex(ValueError,'undeclared actual Core parameter'):
            validate(contract,landmarks)

    def test_unbound_export_and_guessed_anatomy_block(self):
        contract,landmarks=contracts()
        contract['model_binding']['moc3_sha256']='pending'
        with self.assertRaisesRegex(ValueError,'SHA-bound'):validate(contract,landmarks)
        contract,landmarks=contracts();contract['semantic_probes'][0]['reviewed']=False
        with self.assertRaisesRegex(ValueError,'not yet reviewed'):validate(contract,landmarks)

    def test_rotational_alias_does_not_count_as_transform(self):
        contract,landmarks=contracts()
        p=next(p for p in landmarks['parameters'] if p['id']=='T_Rotation');p.update(min=-180,max=180)
        contract['cup_transforms'][2]['values']=[-180,180]
        with self.assertRaisesRegex(ValueError,'same pose'):validate(contract,landmarks)

    def test_ten_fingers_cannot_share_mesh_or_excessive_root_budget(self):
        contract,landmarks=contracts();contract['fingers'][1]['meshes']=contract['fingers'][0]['meshes']
        with self.assertRaisesRegex(ValueError,'same mesh'):validate(contract,landmarks)
        contract,landmarks=contracts();contract['fingers'][0]['root_tolerance_px']=10
        with self.assertRaisesRegex(ValueError,'bounded predeclared'):validate(contract,landmarks)

    def test_rigid_rotation_is_not_curl_and_joint_is_required(self):
        contract,landmarks=contracts();contract['fingers'][0]['min_bend_degrees']=0
        with self.assertRaisesRegex(ValueError,'nonrigid'):validate(contract,landmarks)
        contract,landmarks=contracts();contract['fingers'][0]['joint_landmark']='invented'
        with self.assertRaisesRegex(ValueError,'missing measured landmark'):validate(contract,landmarks)

    def test_nonfinite_bools_out_of_range_and_too_many_grip_pixels_rejected(self):
        for value in (True,math.inf,math.nan,999):
            contract,landmarks=contracts();contract['fingers'][0]['values'][1]=value
            with self.assertRaises(ValueError):validate(contract,landmarks)
        contract,landmarks=contracts();contract['grips'][0]['reference_offset_px']=[20,0]
        with self.assertRaisesRegex(ValueError,'separated contacts'):validate(contract,landmarks)

    def test_actions_all_four_unique_and_all_arm_meshes_protected(self):
        contract,landmarks=contracts();contract['actions'][3]['role']='hold'
        with self.assertRaisesRegex(ValueError,'exactly once'):validate(contract,landmarks)
        contract,landmarks=contracts();contract['semantic_probes'][0]['forbidden_meshes']=['T_ArmMeshL']
        with self.assertRaisesRegex(ValueError,'every declared'):validate(contract,landmarks)

    def test_group_overlap_and_finger_only_wave_cannot_empty_satisfy(self):
        contract,landmarks=contracts();contract['meshes']['arms']=['T_Cup']
        with self.assertRaisesRegex(ValueError,'disjoint'):validate(contract,landmarks)
        contract,landmarks=contracts();next(a for a in contract['actions'] if a['role']=='wave')['target_meshes']=['T_FingerMesh0']
        with self.assertRaisesRegex(ValueError,'finger-only'):validate(contract,landmarks)

    def test_eye_or_finger_cannot_impersonate_body_and_breath_sweep(self):
        contract,landmarks=contracts();contract['parameters']['held_sweep']=['T_Finger0','ParamBreath']
        contract['parameters']['held_roles']['body_x']='T_Finger0'
        with self.assertRaisesRegex(ValueError,'impersonate'):validate(contract,landmarks)

    def test_duplicate_grip_labels_cannot_impersonate_two_real_hands(self):
        contract,landmarks=contracts();contract['grips'][1]['hand_landmark']='T_PalmL'
        with self.assertRaisesRegex(ValueError,'both real palm'):validate(contract,landmarks)
        contract,landmarks=contracts();contract['grips'][1]['cup_landmark']='T_CupL'
        with self.assertRaisesRegex(ValueError,'distinct actual source'):validate(contract,landmarks)


class MeasurementTests(unittest.TestCase):
    def test_v2_hidden_helpers_may_transform_but_any_opacity_or_missing_id_rejected(self):
        c,_=helper_contract();s=snapshots()
        for mid in c['meshes']['cup_helpers']:s['drawables'].append({'id':mid,'vertices':[0,0,1,0,0,1],'opacity':0})
        assert_hidden_helpers(s,c);after=copy.deepcopy(s);after['drawables'][-1]['vertices'][0]=100
        self.assertEqual(invariant_except(s,after,cup_control_meshes(c)),{'T_CupHelperR'})
        after['drawables'][-1]['opacity']=1e-20
        with self.assertRaisesRegex(AssertionError,'became visible'):assert_hidden_helpers(after,c)
        s['drawables'].pop()
        with self.assertRaisesRegex(AssertionError,'missing'):assert_hidden_helpers(s,c)

    def test_visibility_only_cup_accepts_exact_non_target_but_detects_finger_change(self):
        baseline=snapshots();hidden=copy.deepcopy(baseline);hidden['drawables'][0]['opacity']=0
        self.assertEqual(invariant_except(baseline,hidden,['T_Cup']),{'T_Cup'})
        hidden['drawables'][1]['vertices'][2]+=.001
        with self.assertRaisesRegex(AssertionError,'T_Finger'):invariant_except(baseline,hidden,['T_Cup'])

    def test_unchanged_digest_is_not_used_and_float_coordinate_difference_counts(self):
        baseline=snapshots();after=copy.deepcopy(baseline)
        after['drawables'][2]['vertices'][0]=1e-12
        self.assertEqual(changed(baseline,after),{'T_Torso'})

    def test_real_barycentric_point_and_source_transform(self):
        baseline=snapshots();definition={'drawable_id':'T_Cup','vertex_indices':[0,1,2],'weights':[.2,.3,.5]}
        self.assertEqual(source_point(baseline,definition,{'ppu':10,'originX':5,'originY':8}),[8,3])
        definition['vertex_indices'][0]=100
        with self.assertRaises(AssertionError):source_point(baseline,definition,{'ppu':10,'originX':5,'originY':8})

    def test_grip_error_detects_actual_geometry_displacement(self):
        contract,landmarks=contracts();baseline=snapshots()
        self.assertEqual(assert_grips(baseline,contract,landmarks)[0]['error_source_px'],0)
        displaced=copy.deepcopy(baseline);displaced['drawables'][0]['vertices'][0]=2
        with self.assertRaisesRegex(AssertionError,'contacts separate'):assert_grips(displaced,contract,landmarks)

    def test_curl_angle_rejects_rigid_rotation_but_sees_joint_bending(self):
        before=bend_degrees([0,0],[1,0],[2,0])
        rigid=bend_degrees([0,0],[0,1],[0,2])
        curled=bend_degrees([0,0],[1,0],[1.5,.5])
        self.assertEqual(angle_difference(before,rigid),0)
        self.assertEqual(angle_difference(before,curled),45)
        self.assertEqual(angle_difference(179,-179),2)

    def test_unchanged_mesh_checks_alone_miss_wrong_arm_ownership(self):
        # Both states are identical: a naive unchanged-body test passes. Actual
        # semantic alpha support still detects a torso-colored forearm polygon.
        baseline=snapshots();self.assertEqual(changed(baseline,baseline),set())
        contract,_=contracts();probes=contract['semantic_probes']
        actual=[{'source_point':[0,0],'supports':[
            {'id':'T_Torso','alpha':255,'opacity':1,'mask_count':0},
            {'id':'T_ArmMeshL','alpha':128,'opacity':1,'mask_count':0}]}]
        with self.assertRaisesRegex(AssertionError,'wrongly owns'):semantic_ownership(actual,probes)
        actual[0]['supports'][1]['alpha']=0
        self.assertEqual(semantic_ownership(actual,probes)[0]['actual_alpha_owners'],['T_Torso'])

    def test_missing_torso_or_unresolved_mask_never_reports_semantic_pass(self):
        contract,_=contracts();probes=contract['semantic_probes']
        support=[{'source_point':[0,0],'supports':[]}]
        with self.assertRaisesRegex(AssertionError,'lacks actual'):semantic_ownership(support,probes)
        support[0]['supports']=[{'id':'T_Torso','alpha':255,'opacity':1,'mask_count':1}]
        with self.assertRaisesRegex(AssertionError,'not yet independently'):semantic_ownership(support,probes)

    def test_explicit_body_backfill_is_legal_but_an_arm_owner_never_is(self):
        contract,_=contracts();probes=contract['semantic_probes'];probes[0]['allowed_meshes'].append('T_BodyBackfill')
        support=[{'source_point':[0,0],'supports':[
            {'id':'T_Torso','alpha':253,'opacity':1,'mask_count':0,'render_order':2},
            {'id':'T_BodyBackfill','alpha':255,'opacity':1,'mask_count':0,'render_order':1}]}]
        self.assertEqual(semantic_ownership(support,probes)[0]['actual_alpha_owners'],['T_BodyBackfill','T_Torso'])
        support[0]['supports'].append({'id':'T_ArmMeshL','alpha':1,'opacity':1,'mask_count':0,'render_order':0})
        with self.assertRaisesRegex(AssertionError,'wrongly owns'):semantic_ownership(support,probes)

    def test_shoulder_glue_can_move_without_moving_protected_abdomen_point(self):
        baseline=snapshots();after=copy.deepcopy(baseline)
        # Source point is vertex0. A shoulder vertex in the same torso mesh may
        # move; this must not require all topwear vertices to remain fixed.
        anchor={'drawable_id':'T_Torso','vertex_indices':[0,1,2],'weights':[1,0,0],'source_canvas':[0,0]}
        canvas={'ppu':1,'originX':0,'originY':0}
        after['drawables'][2]['vertices'][2]=2
        protected_points_unchanged(baseline,after,[anchor],canvas)
        after['drawables'][2]['vertices'][0]=.01
        with self.assertRaisesRegex(AssertionError,'central torso point moves'):
            protected_points_unchanged(baseline,after,[anchor],canvas)

    def test_negative_control_must_fail_or_the_instrument_fails(self):
        self.assertTrue(expect_detected(lambda:self.assertEqual(0,1),'test detector')['rejected'])
        with self.assertRaisesRegex(AssertionError,'failed its'):expect_detected(lambda:None,'broken detector')

    def coupling_fixture(self,breath_moves=True,detached_moves=False,coupled=True):
        contract,landmarks=contracts();parameters={p['id']:p for p in landmarks['parameters']}
        def pose(values):
            movement=values.get('ParamBodyAngleX',0)+values.get('ParamBreath',0)*(10 if breath_moves else 0)
            cup_movement=movement if detached_moves or (values.get('T_Hold',0)==1 and coupled) else 0
            snapshot=snapshots()
            for mesh in snapshot['drawables']:
                delta=cup_movement if mesh['id']=='T_Cup' else movement if mesh['id'].startswith('T_Palm') else 0
                mesh['vertices']=[value+delta if i%2 else value for i,value in enumerate(mesh['vertices'])]
            return {'raw':snapshot,'product':copy.deepcopy(snapshot)}
        return pose,contract,landmarks,parameters

    def test_held_detector_measures_modes_and_off_key_states(self):
        pose,contract,landmarks,parameters=self.coupling_fixture();record={}
        measure_held_sweep(pose,contract,landmarks,parameters,record,interior_count=8)
        self.assertEqual(record['actual_cartesian_states'],6)
        self.assertGreater(record['additional_off_key_states'],0)
        self.assertEqual(record['worst_grip_error_source_px'],{'raw':0,'product':0})
        self.assertGreater(record['detached_worst_grip_error_source_px']['product'],1)

    def test_held_detector_does_not_pass_motionless_breath_or_detached_coupling(self):
        pose,contract,landmarks,parameters=self.coupling_fixture(breath_moves=False)
        with self.assertRaisesRegex(AssertionError,'Breath does not actually'):
            measure_held_sweep(pose,contract,landmarks,parameters,{},interior_count=1)
        pose,contract,landmarks,parameters=self.coupling_fixture(detached_moves=True)
        with self.assertRaisesRegex(AssertionError,'detached cup must remain ROOT'):
            measure_held_sweep(pose,contract,landmarks,parameters,{},interior_count=1)

    def test_held_detector_rejects_no_effect_hold_parameter(self):
        pose,contract,landmarks,parameters=self.coupling_fixture(coupled=False)
        with self.assertRaisesRegex(AssertionError,'held contacts separate'):
            measure_held_sweep(pose,contract,landmarks,parameters,{},interior_count=1)

    def test_explicit_partial_grid_never_changes_actual_limits_or_claims_full(self):
        pose,contract,landmarks,parameters=self.coupling_fixture();before=copy.deepcopy(parameters);record={}
        grid={'ParamBodyAngleX':[0,1],'ParamBreath':[0,.1]}
        measure_held_sweep(pose,contract,landmarks,parameters,record,interior_count=2,sample_grid=grid)
        self.assertFalse(record['complete_authored_axis_grid'])
        self.assertEqual(parameters,before)
        grid['ParamBreath']=[0,2]
        with self.assertRaisesRegex(AssertionError,'cannot redefine'):
            measure_held_sweep(pose,contract,landmarks,parameters,{},interior_count=1,sample_grid=grid)

    def test_runtime_archive_follows_references_excludes_authoring_and_refuses_traversal(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);model=root/'model.model3.json'
            model.write_text(json.dumps({'FileReferences':{'Moc':'model.moc3','Textures':['atlas.png']}}))
            (root/'model.moc3').write_bytes(b'MOC3');(root/'atlas.png').write_bytes(b'PNG')
            (root/'private.psd').write_bytes(b'private')
            files=runtime_files(model)
            self.assertEqual(len(files),3)
            self.assertGreater(len(archive(model,files)),0)
            model.write_text(json.dumps({'FileReferences':{'Moc':'../private.moc3','Textures':[]}}))
            with self.assertRaisesRegex(ValueError,'unsafe'):runtime_files(model)


if __name__=='__main__':
    unittest.main()
