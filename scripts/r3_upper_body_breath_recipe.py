"""Apply the verified R3 local torso binding through an existing PSD2Live client.

Requires the R3 master mesh layout (Torso = ArtMeshLayer21). Does not author
an eye/gaze effect or move the head, sleeves, hands or mug. Work on a copy.
"""


def apply_breath(client):
    objects = client.call('workspace_inspect', {'scope': 'objects', 'limit': 64})[0]['items']
    torso = next((row for row in objects if row.get('name') == 'Torso'), None)
    if not torso or torso['target'] != 'mesh:ArtMeshLayer21':
        raise ValueError('Requires the inspected R3 Torso mesh; do not apply to another character')
    target = torso['target']
    client.edit('keyform_apply', changes=[
        {'op': 'seed', 'target': target, 'key': {'ParamBreath': value}}
        for value in [0, 1]
    ])
    # Reset first so reapplying the recipe does not accumulate displacement.
    client.edit('keyform_apply', changes=[
        {'op': 'reset', 'target': target, 'key': {'ParamBreath': 1}, 'to': 'rest'}
    ])
    return client.edit('rig_deform', changes=[{
        'target': target, 'key': {'ParamBreath': 1}, 'operations': [
            {'type': 'translate', 'delta': [0, -.004],
             'selection': {'center': [.353, .328], 'radius': .20, 'feather': .16}},
            {'type': 'translate', 'delta': [0, -.0015],
             'selection': {'center': [.22, .20], 'radius': .12, 'feather': .10}},
        ],
    }])
