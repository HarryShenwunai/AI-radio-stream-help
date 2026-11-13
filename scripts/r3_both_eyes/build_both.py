from pathlib import Path
import sys,json,argparse
DEFAULT=Path(__file__).resolve().parents[2]/'.build/r3-both-eyes'
parser=argparse.ArgumentParser(description='Build the existing R3 both-eye rig from explicit local source layers.')
parser.add_argument('--work-dir',type=Path,default=DEFAULT)
parser.add_argument('--source-dir',type=Path,default=DEFAULT.parent/'r3-motion-revision/source')
parser.add_argument('--client-dir',type=Path,default=DEFAULT.parent/'r3-upper-authoring')
parser.add_argument('--transparent-stage',action='store_true')
args=parser.parse_args();P=args.work_dir.resolve();P.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(args.client_dir.resolve()))
from local_client import session
source=args.source_dir.resolve()
with session() as c:
 man=json.loads((source/'layers.json').read_text())
 layers=[]
 for row in man['layers']:
  if row['name']=='Eye_closed':continue
  layers.append({'path':str(source/row['file']),'name':row['name'],'role':'unknown','x':row['x'],'y':row['y']})
  if row['name']=='Neck_face':
   for side,box in [('R',(700,410)),('L',(565,380))]:
    for part in ['Sclera','Iris','Lid','Foreground']:
     name=side+part
     layers.append({'path':str(P/(name+'.png')),'name':name,'role':'unknown','x':box[0],'y':box[1]})
 c.edit('project_create_artwork',width=1137,height=1383,layers=layers)
 c.edit('settings_update',changes={'atlasSize':4096,'meshOnly':True,'generateDeformers':False,'generatePhysics':False,'meshSpacing':20,'meshOuterMargin':1,'meshEdgeWidth':1,'alphaThreshold':1,'headStrength':0,'bodyStrength':0,'exportCmo3':True,'exportMoc3':True,'exportJson':True,'exportCan3':True})
 c.edit('rig_generate');print('generated',flush=True)
 objects=c.call('workspace_inspect',{'scope':'objects','limit':64})[0]['items'];meshes={r['name']:r['target'] for r in objects if r['target'].startswith('mesh:')}
 (P/'mesh-map.json').write_text(json.dumps(meshes,indent=2))
 c.edit('rig_edit_structure',edits=[{'action':'static','kind':'mesh','id':meshes[n].split(':')[1],'opacity':0} for n in ['Empty_pose_cleanplate','Mouth_open']])
 if args.transparent_stage:
  c.edit('rig_edit_structure',edits=[{'action':'static','kind':'mesh','id':meshes['Background_and_hidden_body'].split(':')[1],'opacity':0},{'action':'static','kind':'mesh','id':meshes['Steam'].split(':')[1],'opacity':.12}])
 for side in ['L','R']:
  c.edit('rig_edit_structure',edits=[{'action':'static','kind':'mesh','id':meshes[side+'Iris'].split(':')[1],'masked_by':[meshes[side+'Sclera'].split(':')[1]]}])
 head=['Neck_face','Hair_shell','Mouth_open']+[side+part for side in ['L','R'] for part in ['Sclera','Iris','Lid','Foreground']]
 c.edit('canvas_rotation',id='R3Head',name='R3 head group',meshes=[meshes[n].split(':',1)[1] for n in head],add_to='parent_of_selected',origin=[540,800],angle=0,preservePose=True)
 c.edit('keyform_apply',changes=[{'op':'set','target':'rotation:R3Head','key':{'ParamAngleZ':k},'geometry':{'angle':v}} for k,v in [(-10,-.7),(0,0),(10,.7)]])
 for pid,default in [('ParamCupLower',0),('ParamCupVisible',1)]:c.edit('parameter_create',parameter_id=pid,name=pid,min=0,max=1,default=default)
 target=meshes['Torso'];c.edit('keyform_apply',changes=[{'op':'seed','target':target,'key':{'ParamBreath':v}} for v in [0,1]])
 c.edit('rig_deform',changes=[{'target':target,'key':{'ParamBreath':1},'operations':[{'type':'translate','delta':[0,-.004],'selection':{'center':[.353,.328],'radius':.20,'feather':.16}},{'type':'translate','delta':[0,-.0015],'selection':{'center':[.22,.20],'radius':.12,'feather':.10}}]}])
 for name in ['LLid','RLid','LIris','RIris','LSclera','RSclera']:
  r=c.call('mesh_get_topology',{'target':meshes[name]})[0];(P/(name+'-topology.json')).write_text(json.dumps(r,indent=2));print(name,str(r)[:180],flush=True)
 c.edit('project_save_as',path=str(P/'eye-base.psd2live'));print('saved',flush=True)
