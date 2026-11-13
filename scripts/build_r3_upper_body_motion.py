"""Replace R3 review/lowering playback with a restrained, held-cup idle clip.

The existing MOC3 still contains legacy parameters; constant tracks hold those
at their neutral values. This does not claim to remove compiled rig geometry.
"""
import argparse
import math
import json
from pathlib import Path


def build(runtime: Path, *, bound_breath: bool = False, bound_gaze: bool = False, bound_both_eyes: bool = False) -> None:
    model_path = runtime / 'model.model3.json'
    model = json.loads(model_path.read_text())
    tracks = {
        'ParamCupLower': [(0, 0), (12, 0)],
        'ParamCupVisible': [(0, 1), (12, 1)],
        'ParamMouthOpenY': [(0, 0), (12, 0)],
        'ParamEyeROpen': [(0, 1), (2.1, 1), (2.2, 0), (2.36, 1),
                          (7.3, 1), (7.4, 0), (7.58, 1), (12, 1)],
        # R3 maps +/-10 parameter units to +/-0.7 degrees of head rotation.
        'ParamAngleZ': [(0, 0), (2, 0), (4, 2), (6, 0), (8, -2), (10, 0), (12, 0)],
    }
    if bound_both_eyes:
        tracks['ParamEyeLOpen'] = list(tracks['ParamEyeROpen'])
    if bound_breath:
        # Only enable for a model with verified local chest/shoulder geometry.
        tracks['ParamBreath'] = [(i / 10, round((1 - math.cos(2 * math.pi * i / 40)) / 2, 6)) for i in range(121)]
    if bound_gaze:
        tracks['ParamEyeBallX'] = [(0, 0), (1, 0), (2, -.6), (3, -.6), (4, 0), (6, .7), (7, .7), (8, 0), (12, 0)]
        tracks['ParamEyeBallY'] = [(0, 0), (3, 0), (4, .3), (5, 0), (9, -.3), (10, 0), (12, 0)]
    # Ease starts/stops while keeping the short close and slower reopen timing.
    # Sampling at 60 Hz also makes the existing linear motion format portable.
    for parameter in ['ParamEyeROpen', 'ParamEyeLOpen', 'ParamEyeBallX', 'ParamEyeBallY', 'ParamAngleZ']:
        if parameter not in tracks:
            continue
        keys = tracks[parameter]
        eased = [keys[0]]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if v0 == v1:
                eased.append((t1, v1))
                continue
            count = max(2, math.ceil((t1 - t0) * 60))
            for step in range(1, count + 1):
                u = step / count
                weight = u * u * (3 - 2 * u)
                eased.append((round(t0 + (t1 - t0) * u, 6), round(v0 + (v1 - v0) * weight, 6)))
        tracks[parameter] = eased
    curves = []
    for parameter, keys in tracks.items():
        segments = list(keys[0])
        for time, value in keys[1:]:
            segments.extend([0, time, value])
        curves.append({'Target': 'Parameter', 'Id': parameter, 'Segments': segments})
    motion = {'Version': 3, 'Meta': {
        'Duration': 12, 'Fps': 30, 'Loop': True, 'AreBeziersRestricted': True,
        'CurveCount': len(curves),
        'TotalSegmentCount': sum(len(keys) - 1 for keys in tracks.values()),
        'TotalPointCount': sum(len(keys) for keys in tracks.values()),
        'UserDataCount': 0, 'TotalUserDataSize': 0,
    }, 'Curves': curves, 'UserData': []}
    motions = model['FileReferences'].setdefault('Motions', {})
    # Remove only the two R3 actions explicitly retired by the user.
    for group, filename in [('Review', 'R3_review.motion3.json'),
                            ('GentleLower', 'R3_lower_eased.motion3.json')]:
        if group in motions:
            remaining = [row for row in motions[group] if row.get('File') != 'motions/' + filename]
            if remaining:
                motions[group] = remaining
            else:
                del motions[group]
    folder = runtime / 'motions'
    folder.mkdir(exist_ok=True)
    (folder / 'R3_upper_body.motion3.json').write_text(json.dumps(motion, indent=2) + '\n')
    motions['Idle'] = [{'File': 'motions/R3_upper_body.motion3.json', 'FadeInTime': 0, 'FadeOutTime': 0}]
    model_path.write_text(json.dumps(model, indent=2) + '\n')
    referenced = {row.get('File') for rows in motions.values() for row in rows}
    for filename in ['R3_review.motion3.json', 'R3_lower_eased.motion3.json']:
        if 'motions/' + filename not in referenced:
            (folder / filename).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--bound-breath', action='store_true', help='Enable only after verifying an actual local breath binding')
    parser.add_argument('--bound-gaze', action='store_true', help='Enable only for a model with independent masked iris binding')
    parser.add_argument('--bound-both-eyes', action='store_true', help='Enable for independently bound left and right eyelids')
    args = parser.parse_args()
    build(args.runtime, bound_breath=args.bound_breath, bound_gaze=args.bound_gaze, bound_both_eyes=args.bound_both_eyes)
