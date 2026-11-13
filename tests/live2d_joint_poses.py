"""Finite, declared-range cloth poses shared by independent Core and GL probes."""
from itertools import product


def joint_combinations(parameters):
    by_id = {item['id']: item for item in parameters}
    required = ['ParamArmL', 'ParamArmR', 'ParamForearmL', 'ParamForearmR']
    for name in required:
        item = by_id[name]
        if not item['min'] < item['default'] < item['max']:
            raise ValueError('Expected a genuine signed authored joint range: ' + name)
    poses = []
    for side in ['L', 'R']:
        for shoulder, elbow in product(['min', 'max'], repeat=2):
            values = {f'ParamArm{side}': by_id[f'ParamArm{side}'][shoulder],
                      f'ParamForearm{side}': by_id[f'ParamForearm{side}'][elbow]}
            poses.append({'name': f'{side}-shoulder-{shoulder}-elbow-{elbow}', 'parameters': values})
    opposite = {'min': 'max', 'max': 'min'}
    for shoulder, elbow in product(['min', 'max'], repeat=2):
        values = {'ParamArmL': by_id['ParamArmL'][shoulder],
                  'ParamArmR': by_id['ParamArmR'][opposite[shoulder]],
                  'ParamForearmL': by_id['ParamForearmL'][elbow],
                  'ParamForearmR': by_id['ParamForearmR'][opposite[elbow]]}
        poses.append({'name': f'opposite-shoulders-{shoulder}-elbows-{elbow}', 'parameters': values})
    return poses


def joint_interiors(parameters):
    """Fourteen off-integer probes; finite interpolation checks, not a proof."""
    by_id = {item['id']: item for item in parameters}
    poses = []
    for name in ['ParamArmL', 'ParamArmR', 'ParamForearmL', 'ParamForearmR']:
        for sign in ['min', 'max']:
            value = by_id[name]['default'] + .37 * (by_id[name][sign] - by_id[name]['default'])
            poses.append({'name': f'interior-{name}-{sign}', 'parameters': {name: value}})
    for side in ['L', 'R']:
        for sign in [-1, 1]:
            values = {}
            for role, fraction in [('ParamArm', .31), ('ParamForearm', -.37)]:
                name = role + side
                item = by_id[name]
                end = item['max'] if fraction * sign > 0 else item['min']
                values[name] = item['default'] + abs(fraction) * (end - item['default'])
            poses.append({'name': f'interior-{side}-opposed-{sign}', 'parameters': values})
    for sign in [-1, 1]:
        values = {}
        for name, fraction in [('ParamArmL', .31), ('ParamArmR', -.31),
                               ('ParamForearmL', -.37), ('ParamForearmR', .37)]:
            item = by_id[name]
            end = item['max'] if fraction * sign > 0 else item['min']
            values[name] = item['default'] + abs(fraction) * (end - item['default'])
        poses.append({'name': f'interior-bilateral-opposed-{sign}', 'parameters': values})
    return poses
