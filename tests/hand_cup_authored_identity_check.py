"""Read the frozen authored rig's PRIO v6 tables without opening the editor.

Interoperability reader based on the pinned v3.6.7 RigIrObjects/RigIrBinary
format source supplied in .build/live2d-toolchain-research. Does not execute
vendor code, alter the project, infer native Core internals, or accept a rig.
"""
import argparse,datetime,hashlib,itertools,json,math,re,struct,zipfile
from pathlib import Path
from hand_cup_metamorphic_check import sha,write_report


class Reader:
    def __init__(self,data):self.data=memoryview(data);self.pos=0
    def take(self,n):
        if n<0 or self.pos+n>len(self.data):raise ValueError('truncated PRIO')
        result=self.data[self.pos:self.pos+n];self.pos+=n;return result
    def integer(self):return struct.unpack('>i',self.take(4))[0]
    def scalar(self):
        value=struct.unpack('>f',self.take(4))[0]
        if not math.isfinite(value):raise ValueError('nonfinite authored float')
        return value
    def boolean(self):
        value=bytes(self.take(1))[0]
        if value not in (0,1):raise ValueError('bad PRIO boolean')
        return bool(value)
    def count(self):
        value=self.integer()
        if not 0<=value<=len(self.data)-self.pos:raise ValueError('bad PRIO length')
        return value
    def string(self):return bytes(self.take(self.count())).decode('utf-8',errors='strict')
    def nullable(self,read):return read()if self.boolean()else None
    def array(self,read):return [read()for _ in range(self.count())]
    def integers(self):return self.array(self.integer)
    def floats(self):
        n=self.count();data=self.take(4*n)
        values=[struct.unpack('>f',bytes(data[plane*n+i]for plane in range(4)))[0]for i in range(n)]
        if not all(math.isfinite(value)for value in values):raise ValueError('nonfinite planar authored float')
        return values
    def rgb(self):return [self.scalar()for _ in range(3)]
    def grid(self,form):
        return {'axes':self.array(lambda:{'parameter':self.string(),'keys':self.floats()}),
                'cells':self.array(lambda:{'coordinate':self.integers(),'form':form()})}
    def channels(self):
        def value():
            tag=self.integer()
            if tag==0:return self.scalar()
            if tag==1:return self.rgb()
            if tag==2:return self.boolean()
            raise ValueError('unknown channel tag')
        return self.array(lambda:{'channel':self.integer(),'grid':self.grid(value)})
    def binding(self,form):
        return {'parameter':self.string(),'keys':self.floats(),'neutral_index':self.integer(),
            'shapes':self.array(lambda:self.nullable(form)),
            'limits':self.array(lambda:{'parameter':self.string(),'points':self.array(lambda:[self.scalar(),self.scalar()])})}
    def color_state(self):return {'opacity':self.scalar(),'multiply':self.rgb(),'screen':self.rgb()}
    def deformer(self):
        kind=self.integer()
        if kind not in (0,1):raise ValueError('unknown deformer kind')
        result={'kind':'warp'if kind==0 else'rotation','id':self.string(),'name':self.string(),
            'parent':self.nullable(self.string),'part':self.nullable(self.string)}
        if kind==0:
            result.update(rows=self.integer(),columns=self.integer(),bilinear=self.boolean(),grid=self.nullable(lambda:self.grid(self.floats)))
        else:
            result.update(base_angle=self.scalar(),grid=self.nullable(lambda:self.grid(lambda:[self.scalar()for _ in range(4)])))
        result['channels']=self.channels();result.update(self.color_state())
        if kind==1:result.update(flip_x=self.boolean(),flip_y=self.boolean())
        result.update(selectable=self.boolean(),visible=self.boolean(),enabled=self.boolean())
        def form():
            shape={'points':self.floats()}if kind==0 else{'pivot':[self.scalar()for _ in range(4)],'flip_x':self.boolean(),'flip_y':self.boolean()}
            shape.update(self.color_state());return shape
        result['shapes']=self.array(lambda:self.binding(form))
        if kind==1:result['handle_length']=self.nullable(self.scalar)
        return result
    def mesh(self):
        result={'id':self.string(),'name':self.string(),'parent':self.nullable(self.string),'blend':self.integer(),'alpha_blend':self.integer(),
            'masked_by':self.array(self.string),'invert_mask':self.boolean()}
        result['geometry']=self.nullable(lambda:{'positions':self.floats(),'uvs':self.floats(),'indices':self.integers()})
        result['grid']=self.nullable(lambda:self.grid(self.floats));result['channels']=self.channels()
        result['draw_order']=self.scalar();result.update(self.color_state())
        result.update(culling=self.boolean(),visible=self.boolean(),selectable=self.boolean(),texture_source=self.nullable(self.string),page=self.integer(),tile=self.nullable(self.string))
        def form():
            entry={'deltas':self.floats(),'draw_order':self.scalar()};entry.update(self.color_state());return entry
        result['shapes']=self.array(lambda:self.binding(form));result['user_data']=self.string();return result


def decode(data,kind):
    reader=Reader(data)
    if reader.integer()!=0x5052494F or reader.integer()!=6 or reader.integer()!=kind:raise ValueError('requires exact PRIO v6 and expected kind')
    result=reader.deformer()if kind==1 else reader.mesh()if kind==2 else None
    if result is None or reader.pos!=len(data):raise ValueError('foreign/trailing PRIO data')
    return result


def grid_summary(node):
    grid=node.get('grid')
    if not grid:raise ValueError('target has no actual authored grid')
    hold=next(i for i,a in enumerate(grid['axes'])if a['parameter']=='ParamCupHold')
    actual_coordinates=[tuple(cell['coordinate'])for cell in grid['cells']]
    expected_coordinates=set(itertools.product(*(range(len(a['keys']))for a in grid['axes'])))
    if len(actual_coordinates)!=len(set(actual_coordinates))or set(actual_coordinates)!=expected_coordinates:
        raise ValueError('incomplete or duplicate authored key grid')
    zero=grid['axes'][hold]['keys'].index(0.0)
    forms=[cell['form']for cell in grid['cells']if cell['coordinate'][hold]==zero]
    if not forms:raise ValueError('no actual Hold0 cells')
    signatures={b''.join(struct.pack('>f',v)for v in form)for form in forms}
    return {'id':node['id'],'kind':node.get('kind','mesh'),'axis_keys':{a['parameter']:a['keys']for a in grid['axes']},
        'all_cells':len(grid['cells']),'hold0_cells':len(forms),'hold0_unique_bit_forms':len(signatures),
        'hold0_form_floats':len(forms[0]),'hold0_first_form_sha256':hashlib.sha256(next(iter(signatures))).hexdigest(),
        'hold0_all_form_values_zero':all(v==0 for form in forms for v in form),
        'constant_opacity':node['opacity'],'additional_channels':len(node['channels']),'additional_blend_bindings':len(node['shapes'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();project=Path(args.project).resolve();root=Path(__file__).resolve().parents[1]
    source=[root/'.build/live2d-toolchain-research'/name for name in ('RigIrObjects.kt','RigIrBinary.kt','MaterializedRigCodec.kt')]
    sources={str(path):sha(path)for path in [project,Path(__file__).resolve(),*source]}
    with zipfile.ZipFile(project)as z:
        revisions=[name for name in z.namelist()if name.startswith('rig/revisions/')and name.endswith('.json')]
        if len(revisions)!=1:raise ValueError('must resolve exactly one active authored rig revision; do not scan history')
        rig=json.loads(z.read(revisions[0]));found={}
        for field,kind in (('deformers',1),('meshes',2)):
            for digest in rig[field]:
                if not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('bad content hash')
                path='rig/objects/'+digest+'.bin'
                if z.getinfo(path).file_size>64*1024*1024:raise ValueError('object budget exceeded')
                data=z.read(path)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('authored object hash mismatch')
                node=decode(data,kind)
                if node['id']in ('OriginalCupHoldFollow','ArtMeshLayer'):
                    found[node['id']]=grid_summary(node)
    if set(found)!={'OriginalCupHoldFollow','ArtMeshLayer'}:raise ValueError('missing actual cup/follow nodes')
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'measured_authored_hold0_tables',
        'scope':'independent exact-bit serialized key-table audit, not an inference about native Core interpolation internals',
        'sources':sources,'sources_unchanged':all(sha(Path(path))==digest for path,digest in sources.items()),'nodes':found}
    write_report(args.output,report);print(json.dumps(found,ensure_ascii=False))


if __name__=='__main__':main()
