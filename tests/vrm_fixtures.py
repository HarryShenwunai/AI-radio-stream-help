"""Original synthetic VRM test geometry; no downloaded character artwork.

Generated fixture geometry/texture is dedicated to CC0-1.0 for testing. The
coarse shapes exercise format/animation plumbing, not accepted visual quality.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct

from PIL import Image


class Binary:
    def __init__(self, document):
        self.document, self.data = document, bytearray()

    def view(self, data, target=None):
        while len(self.data) % 4:
            self.data.append(0)
        item = {'buffer': 0, 'byteOffset': len(self.data), 'byteLength': len(data)}
        if target:
            item['target'] = target
        self.data.extend(data)
        self.document['bufferViews'].append(item)
        return len(self.document['bufferViews']) - 1

    def accessor(self, rows, kind, component=5126, target=None, bounds=False):
        widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
        rows = [(row,) if kind == 'SCALAR' else tuple(row) for row in rows]
        values = [value for row in rows for value in row]
        assert all(len(row) == widths[kind] for row in rows)
        blob = struct.pack('<' + ('f' if component == 5126 else 'H') * len(values), *values)
        item = {'bufferView': self.view(blob, target), 'componentType': component, 'count': len(rows), 'type': kind}
        if bounds:
            item.update({'min': [min(row[i] for row in rows) for i in range(widths[kind])],
                         'max': [max(row[i] for row in rows) for i in range(widths[kind])]})
        self.document['accessors'].append(item)
        return len(self.document['accessors']) - 1


def glb(document, data):
    document = copy.deepcopy(document)
    document['buffers'] = [{'byteLength': len(data)}]
    encoded = json.dumps(document, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    encoded += b' ' * (-len(encoded) % 4)
    data = bytes(data) + b'\0' * (-len(data) % 4)
    return (struct.pack('<III', 0x46546c67, 2, 12 + 8 + len(encoded) + 8 + len(data))
            + struct.pack('<II', len(encoded), 0x4e4f534a) + encoded
            + struct.pack('<II', len(data), 0x004e4942) + data)


def unpack(payload):
    length, kind = struct.unpack_from('<II', payload, 12)
    assert kind == 0x4e4f534a
    document = json.loads(payload[20:20+length])
    binary_length, kind = struct.unpack_from('<II', payload, 20+length)
    assert kind == 0x004e4942
    return document, payload[28+length:28+length+binary_length][:document['buffers'][0]['byteLength']]


def cube(center, half, joint):
    positions, normals, uv = [], [], []
    for x, y, z in [(-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1),
                    (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1)]:
        positions.append(tuple(center[i] + half[i]*value for i, value in enumerate((x,y,z))))
        normals.append((x/math.sqrt(3), y/math.sqrt(3), z/math.sqrt(3)))
        uv.append(((x+1)/2, (y+1)/2))
    indices = [0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,2,3,7,2,7,6,1,2,6,1,6,5,3,0,4,3,4,7]
    return {'positions': positions, 'normals': normals, 'uv': uv,
            'joints': [(joint,0,0,0)]*8, 'weights': [(1,0,0,0)]*8, 'indices': indices}


def synthetic_vrm(version='1'):
    """A VRM1 single skinned mesh, or VRM0 multiple meshes/materials/PNG."""
    assert version in {'0', '1'}
    document = {'asset': {'version': '2.0', 'generator': 'Original synthetic QA fixture'},
                'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [], 'meshes': [],
                'skins': [], 'materials': [{'name': 'plain-blue', 'pbrMetallicRoughness':
                  {'baseColorFactor': [.3,.5,.85,1], 'metallicFactor': 0, 'roughnessFactor': .8}}],
                'bufferViews': [], 'accessors': [], 'extensions': {}, 'extensionsUsed': []}
    specifications = [
        ('hips', None, [0,.9,0]), ('spine', 'hips', [0,.14,0]), ('chest', 'spine', [0,.16,0]),
        ('neck', 'chest', [0,.17,0]), ('head', 'neck', [0,.10,0]),
        ('leftUpperLeg', 'hips', [.11,-.05,0]), ('leftLowerLeg','leftUpperLeg',[0,-.4,0]), ('leftFoot','leftLowerLeg',[0,-.4,.08]),
        ('rightUpperLeg','hips',[-.11,-.05,0]), ('rightLowerLeg','rightUpperLeg',[0,-.4,0]), ('rightFoot','rightLowerLeg',[0,-.4,.08]),
        ('leftUpperArm','chest',[.18,.1,0]), ('leftLowerArm','leftUpperArm',[.25,0,0]), ('leftHand','leftLowerArm',[.22,0,0]),
        ('rightUpperArm','chest',[-.18,.1,0]), ('rightLowerArm','rightUpperArm',[-.25,0,0]), ('rightHand','rightLowerArm',[-.22,0,0]),
        ('leftEye','head',[.045,.035,.10]), ('rightEye','head',[-.045,.035,.10])]
    bone_index, world = {}, []
    for name, parent, translation in specifications:
        index = len(document['nodes'])
        bone_index[name] = index
        document['nodes'].append({'name': name, 'translation': translation})
        if parent:
            parent_index = bone_index[parent]
            document['nodes'][parent_index].setdefault('children', []).append(index)
            world.append([world[parent_index][axis]+translation[axis] for axis in range(3)])
        else:
            world.append(translation)
    binary = Binary(document)
    inverse = []
    for x,y,z in world:
        inverse.append([1,0,0,0,0,1,0,0,0,0,1,0,-x,-y,-z,1])
    document['skins'] = [{'name': 'humanoid-skin', 'skeleton': 0, 'joints': list(range(len(world))),
                          'inverseBindMatrices': binary.accessor(inverse, 'MAT4')}]
    body = cube((0,1.08,0), (.17,.22,.1), bone_index['chest'])
    head = cube((0,1.50,0), (.14,.14,.13), bone_index['head'])

    if version == '0':
        image = Image.new('RGBA', (16,16), (210,100,155,255))
        for x in range(8):
            for y in range(16): image.putpixel((x,y), (110,175,210,255))
        stream = io.BytesIO(); image.save(stream, format='PNG')
        document['images'] = [{'bufferView': binary.view(stream.getvalue()), 'mimeType': 'image/png'}]
        document['samplers'] = [{'magFilter': 9729, 'minFilter': 9729}]
        document['textures'] = [{'source': 0, 'sampler': 0}]
        document['materials'].append({'name': 'embedded-texture', 'pbrMetallicRoughness':
                                      {'baseColorTexture': {'index': 0}, 'metallicFactor': 0, 'roughnessFactor': .65}})
        groups = [body, head]
    else:
        joined = {key: body[key] + head[key] for key in ['positions','normals','uv','joints','weights']}
        joined['indices'] = body['indices'] + [value+8 for value in head['indices']]
        groups = [joined]

    mesh_nodes = []
    for number, geometry in enumerate(groups):
        attributes = {
            'POSITION': binary.accessor(geometry['positions'], 'VEC3', target=34962, bounds=True),
            'NORMAL': binary.accessor(geometry['normals'], 'VEC3', target=34962),
            'TEXCOORD_0': binary.accessor(geometry['uv'], 'VEC2', target=34962),
            'JOINTS_0': binary.accessor(geometry['joints'], 'VEC4', component=5123, target=34962),
            'WEIGHTS_0': binary.accessor(geometry['weights'], 'VEC4', target=34962)}
        deltas = []
        for mode in ['blink','aa','happy']:
            values = []
            for x,y,z in geometry['positions']:
                is_head = y > 1.3
                values.append((0, (-.025 if mode == 'aa' else .015 if mode == 'happy' else -.008) if is_head else 0, 0))
            deltas.append({'POSITION': binary.accessor(values, 'VEC3', target=34962, bounds=True)})
        primitive = {'attributes': attributes, 'indices': binary.accessor(geometry['indices'], 'SCALAR', component=5123, target=34963),
                     'material': min(number,len(document['materials'])-1), 'targets': deltas}
        mesh = {'name': 'fixture-part-'+str(number), 'primitives': [primitive], 'weights': [0,0,0],
                'extras': {'targetNames': ['blink','aa','happy']}}
        document['meshes'].append(mesh)
        mesh_nodes.append(len(document['nodes']))
        document['nodes'].append({'name': mesh['name'], 'mesh': number, 'skin': 0})
        document['scenes'][0]['nodes'].append(mesh_nodes[-1])
    if version == '1':
        expressions = {name: {'isBinary': False, 'morphTargetBinds': [{'node': mesh_nodes[0], 'index': index, 'weight': 1}]}
                       for index,name in enumerate(['blink','aa','happy'])}
        look_range = {'inputMaxValue': 90, 'outputScale': 10}
        document['extensions']['VRMC_vrm'] = {
            'specVersion': '1.0',
            'meta': {'name': 'QA synthetic A - single mesh', 'version': '1', 'authors': ['Project QA'],
                     'licenseUrl': 'https://vrm.dev/licenses/1.0/',
                     'otherLicenseUrl': 'https://creativecommons.org/publicdomain/zero/1.0/',
                     'copyrightInformation': 'Original synthetic QA geometry; CC0-1.0; no third-party artwork.'},
            'humanoid': {'humanBones': {name:{'node': index} for name,index in bone_index.items()}},
            'expressions': {'preset': expressions},
            'lookAt': {'type': 'bone', 'offsetFromHeadBone': [0,.035,.1],
                       **{name: look_range for name in ['rangeMapHorizontalInner','rangeMapHorizontalOuter','rangeMapVerticalDown','rangeMapVerticalUp']}}}
        document['extensionsUsed'] = ['VRMC_vrm']
    else:
        document['extensions']['VRM'] = {
            'specVersion': '0.0', 'exporterVersion': 'Original QA fixture',
            'meta': {'title': 'QA synthetic B - textured multiple meshes', 'version': '1', 'author': 'Project QA',
                     'allowedUserName': 'Everyone', 'violentUssageName': 'Allow', 'sexualUssageName': 'Allow',
                     'commercialUssageName': 'Allow', 'licenseName': 'CC0', 'otherLicenseUrl': 'https://creativecommons.org/publicdomain/zero/1.0/'},
            'humanoid': {'humanBones': [{'bone': name,'node': index,'useDefaultValues': True} for name,index in bone_index.items()]},
            'firstPerson': {'firstPersonBone': bone_index['head'], 'firstPersonBoneOffset': {'x':0,'y':.035,'z':.1},
                            'lookAtTypeName':'Bone', 'meshAnnotations':[{'mesh': i,'firstPersonFlag':'Both'} for i in range(2)]},
            'blendShapeMaster': {'blendShapeGroups': [{'name': name,'presetName': preset,'binds':[{'mesh':1,'index': index,'weight':100}], 'materialValues':[], 'isBinary':False}
                                                      for index,(name,preset) in enumerate([('blink','blink'),('aa','a'),('happy','joy')])]},
            'secondaryAnimation': {'boneGroups': [], 'colliderGroups': []},
            'materialProperties': [{'name': material['name'],'shader':'VRM_USE_GLTFSHADER','renderQueue':2000,
                                    'floatProperties':{},'vectorProperties':{},'textureProperties':{},'keywordMap':{},'tagMap':{}}
                                   for material in document['materials']]}
        document['extensionsUsed'] = ['VRM']
    return glb(document, binary.data)


def fixtures():
    first, second = synthetic_vrm('1'), synthetic_vrm('0')
    document, binary = unpack(first)
    result = {'valid-single-mesh-vrm1.vrm': first, 'valid-textured-multi-mesh-vrm0.vrm': second,
              'bad-truncated.vrm': first[:-7], 'bad-fake.vrm': b'not a GLB or VRM'}
    render_reject = copy.deepcopy(document)
    render_reject['extensions']['VRMC_vrm']['meta']['licenseUrl'] = 'https://creativecommons.org/publicdomain/zero/1.0/'
    result['renderer-reject-license-url.vrm'] = glb(render_reject, binary)
    for label in ['external-uri','data-uri','accessor-range','node-cycle','vrm-version']:
        bad = copy.deepcopy(document)
        if label == 'external-uri': bad['buffers'][0]['uri'] = 'https://untrusted.invalid/model.bin'
        if label == 'data-uri': bad['images'] = [{'uri':'data:image/png;base64,AAAA'}]
        if label == 'accessor-range': bad['accessors'][1]['count'] = 999999999
        if label == 'node-cycle': bad['nodes'][0].setdefault('children', []).append(0)
        if label == 'vrm-version': bad['extensions']['VRMC_vrm']['specVersion'] = '9.9'
        # Preserve mutated buffer declaration after container construction.
        payload = glb(bad, binary)
        if label == 'external-uri':
            bad, _ = unpack(payload); bad['buffers'][0]['uri'] = 'https://untrusted.invalid/model.bin'
            encoded = json.dumps(bad, separators=(',', ':')).encode();encoded += b' '*(-len(encoded)%4)
            padded = binary+b'\0'*(-len(binary)%4)
            payload = struct.pack('<III',0x46546c67,2,28+len(encoded)+len(padded))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(padded),0x004e4942)+padded
        result['bad-'+label+'.vrm'] = payload
    damaged = bytearray(binary)
    position_view = document['bufferViews'][document['accessors'][1]['bufferView']]
    struct.pack_into('<f', damaged, position_view.get('byteOffset',0), float('nan'))
    result['bad-nonfinite-position.vrm'] = glb(document, damaged)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.build/vrm-fixtures'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'license':'CC0-1.0 for generated fixture geometry/texture','not_art_quality_acceptance':True,'files':[]}
    for name,data in fixtures().items():
        (args.output/name).write_bytes(data)
        expected = 'valid' if name.startswith('valid-') else 'backend_accept_renderer_reject' if name.startswith('renderer-') else 'backend_reject'
        manifest['files'].append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'expected':expected})
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
