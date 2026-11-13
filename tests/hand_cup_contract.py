"""Strict test-only contract for a measured hand/cup rig; no guessed anatomy IDs."""
from __future__ import annotations
import math
import re

FORMAT = 'live2d-hand-cup-metamorphic-v1'
FORMAT_V2 = 'live2d-hand-cup-metamorphic-v2'
ROLES = {'hold', 'detach', 'wave', 'empty_hands'}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(contract, landmarks):
    if contract.get('format') not in (FORMAT, FORMAT_V2):
        raise ValueError('requires an explicit hand/cup metamorphic contract')
    if landmarks.get('format') != 'actual-live2d-landmark-contract-v1':
        raise ValueError('requires actual rest-Core landmark contract')
    binding = contract.get('model_binding', {})
    for field in ('model3_sha256', 'moc3_sha256', 'landmarks_sha256', 'source_manifest_sha256'):
        if not isinstance(binding.get(field), str) or not re.fullmatch('[a-f0-9]{64}', binding[field]):
            raise ValueError('actual exported model, measured landmarks and reviewed source must be SHA-bound')
    source = landmarks.get('parameters', [])
    params = {entry['id']: entry for entry in source}
    if not source or len(params) != len(source):
        raise ValueError('actual Core parameter IDs must be nonempty and unique')
    for entry in params.values():
        if not all(finite(entry.get(key)) for key in ('min', 'default', 'max')) or not entry['min'] <= entry['default'] <= entry['max']:
            raise ValueError('invalid actual parameter range')
    def parameter(pid):
        if not isinstance(pid, str) or pid not in params:
            raise ValueError('undeclared actual Core parameter: ' + str(pid))
        return params[pid]
    def value(pid, v):
        p = parameter(pid)
        if not finite(v) or not p['min'] <= v <= p['max']:
            raise ValueError('test value outside authored range: ' + pid)
    def mesh_list(values):
        if not isinstance(values, list) or not values or len(values) != len(set(values)) or not all(isinstance(x, str) and x for x in values):
            raise ValueError('nonempty distinct mesh IDs required')
    def landmark(name):
        if name not in landmarks.get('landmarks', {}):
            raise ValueError('missing measured landmark: ' + str(name))
    def tolerance(entry, key, limit):
        if not finite(entry.get(key)) or not 0 <= entry[key] <= limit or not entry.get('tolerance_basis'):
            raise ValueError('anchor tolerance requires a bounded predeclared source-pixel budget and basis')
    roles = contract.get('parameters', {})
    for key in ('cup_hold', 'cup_visible', 'cup_x', 'cup_y', 'cup_rotation'):
        parameter(roles.get(key))
    hold_parameter = parameter(roles['cup_hold'])
    if hold_parameter['min'] != 0 or hold_parameter['max'] != 1:
        raise ValueError('actual CupHold must author the explicit 0..1 detached/held range')
    if len(set(roles[key] for key in ('cup_hold', 'cup_visible', 'cup_x', 'cup_y', 'cup_rotation'))) != 5:
        raise ValueError('cup controls must be distinct actual parameters')
    for mode in ('detached_pose', 'held_pose'):
        if not isinstance(contract.get(mode), dict):raise ValueError('explicit authored pose is required')
        for pid, v in contract[mode].items():value(pid, v)
    if contract['detached_pose'].get(roles['cup_hold']) != 0 or contract['held_pose'].get(roles['cup_hold']) != 1:
        raise ValueError('CupHold detached=0 and held=1 must be explicit')
    shown, hidden = contract.get('visibility_values', {}).get('shown'), contract.get('visibility_values', {}).get('hidden')
    value(roles['cup_visible'], shown);value(roles['cup_visible'], hidden)
    if shown == hidden:raise ValueError('visibility needs distinct states')
    for kind in ('cup', 'torso', 'palms', 'arms'):
        mesh_list(contract.get('meshes', {}).get(kind))
    helpers = contract['meshes'].get('cup_helpers', [])
    if contract['format'] == FORMAT:
        if helpers or contract.get('cup_helper_bindings'):
            raise ValueError('invisible cup helpers require the explicit v2 contract')
    else:
        mesh_list(helpers)
        bindings = contract.get('cup_helper_bindings', [])
        if len(helpers) != 2 or len(bindings) != 2 or {item.get('mesh_id') for item in bindings} != set(helpers):
            raise ValueError('v2 requires exactly two SHA-bound invisible cup helpers')
        for item in bindings:
            if (item.get('role') != 'invisible_cup_attachment' or item.get('source_object_id') != item['mesh_id']
                    or not isinstance(item.get('source_parent_id'), str) or not item['source_parent_id']
                    or item.get('source_manifest_sha256') != binding['source_manifest_sha256']):
                raise ValueError('helper identity must bind the actual source object and parent, not alias a body mesh')
    group_ids = [pid for group in contract['meshes'].values() for pid in group]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError('cup/torso/palms/arms must be disjoint actual mesh groups')
    transforms = contract.get('cup_transforms', [])
    if {item.get('parameter') for item in transforms} != {roles['cup_x'], roles['cup_y'], roles['cup_rotation']} or len(transforms) != 3:
        raise ValueError('requires all three actual cup transform probes')
    for entry in transforms:
        values = entry.get('values', [])
        if len(values) != 2 or values[0] == values[1]:raise ValueError('transform needs two distinct interior states')
        for v in values:value(entry['parameter'], v)
        if entry['parameter'] == roles['cup_rotation'] and abs((values[1]-values[0]) % 360) < 1e-8:
            raise ValueError('rotational endpoints are the same pose; use nonaliased angles such as ±45')
    fingers = contract.get('fingers', [])
    if len(fingers) != 10 or len({finger.get('name') for finger in fingers}) != 10 or len({finger.get('parameter') for finger in fingers}) != 10:
        raise ValueError('requires ten distinct real finger controls')
    if {finger.get('side') for finger in fingers} != {'viewer_left', 'viewer_right'} or any(sum(f['side'] == side for f in fingers) != 5 for side in ('viewer_left', 'viewer_right')):
        raise ValueError('requires five fingers on each explicitly named viewer side')
    finger_meshes = []
    for entry in fingers:
        parameter(entry['parameter']);mesh_list(entry['meshes']);finger_meshes.extend(entry['meshes'])
        for v in entry.get('values', []):value(entry['parameter'], v)
        if len(entry.get('values', [])) != 2 or entry['values'][0] == entry['values'][1]:raise ValueError('finger needs distinct curl states')
        landmark(entry['root_landmark']);landmark(entry['palm_root_landmark']);landmark(entry['joint_landmark']);landmark(entry['tip_landmark']);tolerance(entry, 'root_tolerance_px', .5)
        if not finite(entry.get('min_tip_movement_px')) or entry['min_tip_movement_px'] < 1:
            raise ValueError('finger visible tip movement budget must be at least one source pixel')
        if not finite(entry.get('min_bend_degrees')) or entry['min_bend_degrees'] < 1:
            raise ValueError('curl requires actual nonrigid joint bending, not whole-finger rigid rotation')
    if len(finger_meshes) != len(set(finger_meshes)):
        raise ValueError('different finger controls cannot claim the same mesh')
    if set(finger_meshes) & set(group_ids):
        raise ValueError('finger meshes cannot claim cup, torso, palm or arm meshes')
    limbs = contract.get('arm_hand_controls', [])
    if not {('viewer_left', 'arm'), ('viewer_right', 'arm'), ('viewer_left', 'hand'), ('viewer_right', 'hand')} <= {(item.get('side'), item.get('kind')) for item in limbs}:
        raise ValueError('both actual arms and hands need detached probes')
    for entry in limbs:
        parameter(entry['parameter']);mesh_list(entry['meshes'])
        if set(entry['meshes']) & set(helpers):
            raise ValueError('technical cup helpers cannot impersonate physical limb meshes')
        if len(entry.get('values', [])) != 2:raise ValueError('limb needs two test states')
        if entry['values'][0] == entry['values'][1]:raise ValueError('limb states must differ')
        for v in entry['values']:value(entry['parameter'], v)
    held = roles.get('held_sweep', [])
    if not isinstance(held, list) or not 2 <= len(held) <= 6 or len(set(held)) != len(held):raise ValueError('explicit Body/Breath sweep parameters required')
    for pid in held:parameter(pid)
    held_roles=roles.get('held_roles', {})
    allowed_held={'body_x':'ParamBodyAngleX','body_y':'ParamBodyAngleY','body_z':'ParamBodyAngleZ','body_lean':'ParamBodyLean','body_proportion':'ParamProportion','breath':'ParamBreath'}
    if not isinstance(held_roles,dict) or not 2 <= len(held_roles) <= 6 or 'breath' not in held_roles:
        raise ValueError('held sweep needs explicit actual Body and Breath roles')
    if any(role not in allowed_held or pid!=allowed_held[role] for role,pid in held_roles.items()) or set(held_roles.values()) != set(held):
        raise ValueError('finger/eye parameters cannot impersonate standard Body/Breath sweep roles')
    grips = contract.get('grips', [])
    if len(grips) < 2:raise ValueError('both real holding contacts need measured anchors')
    hands = [landmarks['landmarks'].get(entry.get('hand_landmark'), {}).get('drawable_id') for entry in grips]
    if len(set(hands)) < 2 or not set(hands) <= set(contract['meshes']['palms']):
        raise ValueError('two grip labels cannot impersonate both real palm meshes')
    cup_points=[]
    for entry in grips:
        landmark(entry['cup_landmark']);landmark(entry['hand_landmark']);tolerance(entry, 'tolerance_px', 1)
        cup_point=landmarks['landmarks'][entry['cup_landmark']]
        if cup_point['drawable_id'] not in contract['meshes']['cup']:
            raise ValueError('grip cup anchor must belong to an actual cup mesh')
        cup_points.append(cup_point['source_canvas'])
        offset = entry.get('reference_offset_px', [0, 0])
        if len(offset) != 2 or not all(finite(v) for v in offset) or math.hypot(*offset) > 5:
            raise ValueError('grip offset must be small and explicit, not hide separated contacts')
    if not any(math.dist(a,b)>=1 for a in cup_points for b in cup_points):
        raise ValueError('two holding contacts must be distinct actual source-canvas locations')
    semantic = contract.get('semantic_probes', [])
    if not semantic:raise ValueError('reviewed torso ownership probes are required')
    for entry in semantic:
        if entry.get('reviewed') is not True or not entry.get('review_basis'):raise ValueError('source semantic point is not yet reviewed')
        points = entry.get('source_points', [])
        if not points or any(len(point) != 2 or not all(finite(v) for v in point) for point in points):raise ValueError('actual reviewed source points required')
        mesh_list(entry['allowed_meshes']);mesh_list(entry['forbidden_meshes'])
        if not set(contract['meshes']['arms']) <= set(entry['forbidden_meshes']):
            raise ValueError('torso semantic probe must exclude every declared upper/forearm mesh')
        if not set(entry['allowed_meshes']) <= set(contract['meshes']['torso']):
            raise ValueError('semantic probe allowed owners must be declared torso meshes')
    actions = contract.get('actions', [])
    if len(actions) != 4 or {entry.get('role') for entry in actions} != ROLES:raise ValueError('hold/detach/wave/empty_hands actions must all be authored exactly once')
    for entry in actions:
        if entry.get('kind') not in {'motion', 'expression'}:raise ValueError('action must be a declared motion or expression')
        if not finite(entry.get('sample_seconds')) or not 0 < entry['sample_seconds'] <= 15:raise ValueError('action sampling time must be explicit and bounded')
        if entry['kind'] == 'motion' and (not isinstance(entry.get('group'), str) or not isinstance(entry.get('index'), int) or isinstance(entry.get('index'), bool) or entry['index'] < 0):raise ValueError('actual motion group/index required')
        if entry['kind'] == 'expression' and not isinstance(entry.get('name'), str):raise ValueError('actual expression name required')
        if not entry.get('expect_parameters'):raise ValueError('actual terminal parameter expectations are required')
        for pid, v in entry['expect_parameters'].items():value(pid, v)
        if not isinstance(entry.get('start_pose'), dict):raise ValueError('authored action needs an explicit initial pose')
        for pid, v in entry['start_pose'].items():value(pid, v)
        mesh_list(entry.get('target_meshes'))
        if entry['role'] == 'hold' and entry['expect_parameters'].get(roles['cup_hold']) != 1:
            raise ValueError('hold action must actually enter CupHold=1')
        if entry['role'] == 'detach' and entry['expect_parameters'].get(roles['cup_hold']) != 0:
            raise ValueError('detach action must actually enter CupHold=0')
        if entry['role'] == 'empty_hands' and entry['expect_parameters'].get(roles['cup_visible']) != hidden:
            raise ValueError('empty_hands must actually hide the cup')
        if entry['role'] == 'wave':
            limb_meshes = set(contract['meshes']['arms'] + contract['meshes']['palms'] + finger_meshes)
            if not set(entry['target_meshes']) <= limb_meshes or not set(entry['target_meshes']) & set(contract['meshes']['arms'] + contract['meshes']['palms']):
                raise ValueError('wave must target a real palm or arm; finger-only curl is not waving')
        elif not set(contract['meshes']['cup']) & set(entry['target_meshes']):
            raise ValueError('hold/detach/empty_hands action must target the actual cup')
        if not finite(entry.get('parameter_tolerance')) or not 0 <= entry['parameter_tolerance'] <= .01:
            raise ValueError('action parameter comparison needs an explicit tolerance no greater than .01 authored units')
    return {'parameter_ids': sorted(params), 'finger_count': len(fingers), 'action_roles': sorted(ROLES)}
