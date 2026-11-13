"""Independent, exact geometry assertions for real Core snapshots.

This module does not synthesize a rig or infer anatomical IDs from names. All
anatomy comes from the reviewed, SHA-bound test contract. Coordinates are Core
units until explicitly converted to the measured source-canvas pixels.
"""
from __future__ import annotations

import math
import itertools
import random


def by_id(snapshot):
    result = {entry['id']: entry for entry in snapshot['drawables']}
    assert len(result) == len(snapshot['drawables']), 'duplicate actual drawable ID'
    for entry in result.values():
        values = entry['vertices']
        assert len(values) >= 6 and len(values) % 2 == 0
        assert all(math.isfinite(value) for value in values), 'nonfinite actual vertices'
        assert math.isfinite(entry['opacity']), 'nonfinite actual opacity'
    return result


def changed(before, after):
    a, b = by_id(before), by_id(after)
    assert a.keys() == b.keys(), 'actual drawable set changed'
    return {key for key in a if a[key]['vertices'] != b[key]['vertices'] or a[key]['opacity'] != b[key]['opacity']}


def invariant_except(before, after, allowed):
    actual = changed(before, after)
    forbidden = actual - set(allowed)
    assert not forbidden, 'unrelated actual geometry/opacity changed: ' + ', '.join(sorted(forbidden))
    return actual


def cup_control_meshes(contract):
    """v2 explicitly adds only the two invisible, source-bound attachment meshes."""
    return set(contract['meshes']['cup'] + contract['meshes'].get('cup_helpers', []))


def assert_hidden_helpers(snapshot, contract):
    meshes = by_id(snapshot)
    for mid in contract['meshes'].get('cup_helpers', []):
        assert mid in meshes and meshes[mid]['opacity'] == 0, 'technical cup helper became visible or is missing: ' + mid


def source_point(snapshot, definition, canvas):
    drawable = by_id(snapshot)[definition['drawable_id']]
    values = drawable['vertices']
    ids, weights = definition['vertex_indices'], definition['weights']
    assert len(ids) == len(weights) == 3
    assert all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(values) // 2 for i in ids)
    assert all(math.isfinite(w) and 0 <= w <= 1 for w in weights) and abs(sum(weights) - 1) < 1e-7
    x = sum(values[2*i] * w for i, w in zip(ids, weights))
    y = sum(values[2*i+1] * w for i, w in zip(ids, weights))
    return [canvas['originX'] + x * canvas['ppu'], canvas['originY'] - y * canvas['ppu']]


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bend_degrees(root, joint, tip):
    proximal = [joint[0]-root[0], joint[1]-root[1]]
    distal = [tip[0]-joint[0], tip[1]-joint[1]]
    assert math.hypot(*proximal) > 1e-5 and math.hypot(*distal) > 1e-5, 'degenerate finger landmarks'
    return math.degrees(math.atan2(proximal[0]*distal[1]-proximal[1]*distal[0], proximal[0]*distal[0]+proximal[1]*distal[1]))


def angle_difference(a, b):
    return abs((a-b+180) % 360 - 180)


def validate_actual_bindings(snapshot, topology, contract, landmarks):
    meshes = by_id(snapshot)
    assert_hidden_helpers(snapshot, contract)
    parameter_ids = {p['id'] for p in snapshot['parameters']}
    expected = {p['id']: p for p in landmarks['parameters']}
    assert parameter_ids == expected.keys(), 'measured landmark contract belongs to a different actual Core parameter set'
    for item in snapshot['parameters']:
        assert all(item[key] == expected[item['id']][key] for key in ('min', 'default', 'max')), 'Core authored range changed'
    groups = list(contract['meshes'].values())
    groups += [entry['meshes'] for entry in contract['fingers'] + contract['arm_hand_controls']]
    groups += [entry[key] for entry in contract['semantic_probes'] for key in ('allowed_meshes', 'forbidden_meshes')]
    for group in groups:
        assert set(group) <= meshes.keys(), 'contract claims missing actual Core meshes: ' + str(set(group) - meshes.keys())
    for name, entry in landmarks['landmarks'].items():
        assert entry['drawable_id'] in meshes, 'landmark claims nonexistent Core mesh: ' + name
        indices = entry['vertex_indices']
        actual_triangles = topology[entry['drawable_id']]['indices']
        assert any(set(indices) == set(actual_triangles[i:i+3]) for i in range(0, len(actual_triangles), 3)), 'landmark is not an actual Core triangle: ' + name
        assert distance(source_point(snapshot, entry, landmarks['canvasInfo']), entry['source_canvas']) <= .01, 'rest triangle does not reproduce the measured source point: ' + name


def grip_errors(snapshot, contract, landmarks):
    result = []
    for entry in contract['grips']:
        cup = source_point(snapshot, landmarks['landmarks'][entry['cup_landmark']], landmarks['canvasInfo'])
        hand = source_point(snapshot, landmarks['landmarks'][entry['hand_landmark']], landmarks['canvasInfo'])
        offset = entry.get('reference_offset_px', [0, 0])
        error = distance(cup, [hand[0] + offset[0], hand[1] + offset[1]])
        result.append({'cup_landmark': entry['cup_landmark'], 'hand_landmark': entry['hand_landmark'],
                       'error_source_px': error, 'tolerance_source_px': entry['tolerance_px']})
    return result


def assert_grips(snapshot, contract, landmarks):
    result = grip_errors(snapshot, contract, landmarks)
    assert all(item['error_source_px'] <= item['tolerance_source_px'] for item in result), 'actual cup-to-hand contacts separate: ' + str(result)
    return result


def semantic_ownership(supports, probes):
    """Consume actual Core triangle+texture-alpha evidence from the browser.

    No tolerance hides a wrong part assignment. Masked positive supports are
    deliberately not accepted until their final clip alpha is independently
    resolved. This is more conservative than a neutral screenshot.
    """
    assert len(supports) == sum(len(probe['source_points']) for probe in probes)
    summaries = []
    offset = 0
    for probe in probes:
        for point in probe['source_points']:
            item = supports[offset]
            offset += 1
            assert item['source_point'] == point
            positive = [support for support in item['supports'] if support['alpha'] > 0 and support['opacity'] > 0]
            assert not any(support['mask_count'] for support in positive), 'masked semantic texture support is not yet independently resolved'
            owners = {support['id'] for support in positive}
            assert owners & set(probe['allowed_meshes']), 'reviewed torso point lacks actual visible torso texture support: ' + str(point)
            forbidden = owners & set(probe['forbidden_meshes'])
            assert not forbidden, 'arm/cuff texture wrongly owns reviewed torso point: ' + str((point, forbidden))
            assert owners <= set(probe['allowed_meshes']), 'undeclared non-body texture supports the reviewed torso point: ' + str((point,owners-set(probe['allowed_meshes'])))
            summaries.append({'source_point': point, 'actual_alpha_owners': sorted(owners)})
    return summaries


def semantic_anchors(supports, probes):
    semantic_ownership(supports, probes)
    result = []
    offset = 0
    for probe in probes:
        for point in probe['source_points']:
            for support in supports[offset]['supports']:
                if support['id'] in probe['allowed_meshes'] and support['alpha'] > 0 and support['opacity'] > 0:
                    result.append({'drawable_id':support['id'],'vertex_indices':support['triangle'],
                                   'weights':support['weights'],'source_canvas':point})
            offset += 1
    return result


def protected_points_unchanged(before, after, anchors, canvas):
    for anchor in anchors:
        a, b = source_point(before,anchor,canvas), source_point(after,anchor,canvas)
        assert a == b, 'reviewed central torso point moves under arm/hand control: ' + str((anchor['source_canvas'],a,b))


def measure_held_sweep(pose, contract, landmarks, parameters, record, interior_count=64, seed=9426, sample_grid=None):
    """Finite actual-pose test, also reusable with detector unit fixtures.

    ``pose`` must produce independently evaluated raw/product snapshots. The
    production CLI uses real Core and real adapter; unit fixtures explicitly
    label themselves synthetic. Additional off-key samples prevent evaluating
    only the exporter's own fitting table. No continuous-domain proof is made.
    """
    ids=contract['parameters']['held_sweep']
    levels=[sorted(set(parameters[pid][key] for key in ('min','default','max'))) for pid in ids]
    if sample_grid is not None:
        assert isinstance(sample_grid,dict) and set(sample_grid)==set(ids), 'explicit partial grid must name every selected actual axis'
        for pid,values in sample_grid.items():
            assert isinstance(values,list) and 2<=len(values)<=5 and len(set(values))==len(values), 'partial grid needs distinct explicit test values'
            assert all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and parameters[pid]['min']<=v<=parameters[pid]['max'] for v in values), 'partial grid cannot redefine the actual authored range'
            assert parameters[pid]['default'] in values, 'partial grid must include the actual default for independent control probes'
        levels=[sorted(sample_grid[pid]) for pid in ids]
    common={**contract['held_pose'],contract['parameters']['cup_visible']:contract['visibility_values']['shown']}
    hold=contract['parameters']['cup_hold']
    cup=set(contract['meshes']['cup'])
    canvas=landmarks['canvasInfo']
    root=pose({**common,hold:0,**{pid:parameters[pid]['default'] for pid in ids}})
    states=[dict(zip(ids,values)) for values in itertools.product(*levels)]
    count=len(states)
    rng=random.Random(seed)
    interiors=[]
    for _ in range(interior_count):
        state={pid:values[0]+rng.choice((.25,.5,.75))*(values[-1]-values[0]) for pid,values in zip(ids,levels)}
        if state not in states and state not in interiors:interiors.append(state)
    states+=interiors
    worst={'raw':0.0,'product':0.0};detached_worst={'raw':0.0,'product':0.0}
    effect={'raw':False,'product':False};moved={'raw':set(),'product':set()}
    movement={'raw':{},'product':{}}
    record.update(actual_cartesian_states=count,additional_off_key_states=len(interiors),seed=seed,
        complete_authored_axis_grid=sample_grid is None,
        levels=dict(zip(ids,levels)),off_key_parameters=interiors,completed_states=0,
        worst_grip_error_source_px=worst,detached_worst_grip_error_source_px=detached_worst,
        measured_hand_grip_displacement_source_px=movement,
        scope=('full selected authored min/default/max grid' if sample_grid is None else 'explicit PARTIAL preflight grid, not the full authored range')+' plus fixed-seed off-key samples; not a continuous proof')
    for values in states:
        record['last_parameters']=values
        detached=pose({**common,**values,hold:0})
        held=pose({**common,**values,hold:1})
        record['last_grip_errors']={engine:grip_errors(held[engine],contract,landmarks)for engine in ('raw','product')}
        record['last_detached_grip_errors']={engine:grip_errors(detached[engine],contract,landmarks)for engine in ('raw','product')}
        for engine in ('raw','product'):
            for snapshot in (root[engine], detached[engine], held[engine]):
                assert_hidden_helpers(snapshot, contract)
            a,b,c=by_id(root[engine]),by_id(detached[engine]),by_id(held[engine])
            assert all(a[mid]['vertices']==b[mid]['vertices'] and a[mid]['opacity']==b[mid]['opacity'] for mid in cup), 'CupHold0 is not independent of Body/Breath; detached cup must remain ROOT'
            invariant_except(detached[engine],held[engine],cup)
            assert all(c[mid]['opacity']==b[mid]['opacity'] and c[mid]['opacity']>0 for mid in cup), 'CupHold changes visibility instead of preserving the held cup'
            effect[engine] |= any(c[mid]['vertices']!=b[mid]['vertices'] for mid in cup)
            det_errors=record['last_detached_grip_errors'][engine]
            detached_worst[engine]=max(detached_worst[engine],*(item['error_source_px'] for item in det_errors))
            errors=record['last_grip_errors'][engine]
            assert all(item['error_source_px']<=item['tolerance_source_px'] for item in errors), 'actual held contacts separate: '+str((engine,values,errors))
            worst[engine]=max(worst[engine],*(item['error_source_px'] for item in errors))
            nondefault=[pid for pid,value in values.items() if value!=parameters[pid]['default']]
            if len(nondefault)==1:
                delta=max(distance(source_point(root[engine],landmarks['landmarks'][grip['hand_landmark']],canvas),
                    source_point(detached[engine],landmarks['landmarks'][grip['hand_landmark']],canvas)) for grip in contract['grips'])
                movement[engine][nondefault[0]]=max(movement[engine].get(nondefault[0],0),delta)
                if delta>1e-4:moved[engine].add(nondefault[0])
        record['completed_states']+=1
    breath=contract['parameters']['held_roles']['breath']
    for engine in ('raw','product'):
        assert breath in moved[engine], 'Breath does not actually move a hand; meaningful coupling was not tested'
        assert moved[engine]-{breath}, 'Body does not actually move a hand; meaningful coupling was not tested'
        assert detached_worst[engine]>1 and effect[engine], 'Hold0/Hold1 have no meaningful actual cup/hand coupling contrast'
    record['parameters_actually_moving_palms']={engine:sorted(values) for engine,values in moved.items()}
    return record
