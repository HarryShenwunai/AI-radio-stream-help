from pathlib import Path
import sys,json,argparse,numpy as np
from scipy.interpolate import PchipInterpolator
DEFAULT=Path(__file__).resolve().parents[2]/'.build/r3-both-eyes'
parser=argparse.ArgumentParser(description='Bind and export the existing R3 dual-eye rig in a selected workspace.')
parser.add_argument('--work-dir',type=Path,default=DEFAULT)
parser.add_argument('--client-dir',type=Path,default=DEFAULT.parent/'r3-upper-authoring')
args=parser.parse_args();P=args.work_dir.resolve();sys.path.insert(0,str(args.client_dir.resolve()))
from local_client import session
m=json.loads((P/'mesh-map.json').read_text());configs=json.loads((P/'eyes.json').read_text())
with session() as c:
 c.edit('project_open',path=str(P/'eye-base.psd2live'),discard_unsaved=True)
 for side,config in configs.items():
  name=side+'Lid';pid='ParamEye'+side+'Open';topo=json.loads((P/(name+'-topology.json')).read_text());b=topo['bounds'];height=b[3]-b[1];u=np.array(config['upper']);curve=PchipInterpolator(u[:,0],u[:,1])
  c.edit('keyform_apply',changes=[{'op':'seed','target':m[name],'key':{pid:v}} for v in [0,1]])
  ops=[]
  for i,x,y in topo['items']:
   cx=x+540-config['box'][0];cy=y+800-config['box'][1]
   top=float(curve(np.clip(cx,u[0,0],u[-1,0])))-7
   target=top+(cy-top)*.06
   ops.append({'type':'translate','delta':[0,(target-cy)/height],'selection':{'indices':[i]}})
  for start in range(0,len(ops),16):c.edit('rig_deform',changes=[{'target':m[name],'key':{pid:1},'operations':ops[start:start+16]}])
  c.edit('keyform_apply',changes=[{'op':'set','target':m[name],'key':{pid:v},'channels':{'opacity':alpha}} for v,alpha in [(0,1),(.98,1),(1,0)]])
  # Close the actual iris aperture together with the lid; feathered lid edges
  # must not leave a strip of the iris visible during the last closing frames.
  aperture=side+'Sclera';at=json.loads((P/(aperture+'-topology.json')).read_text())
  ah=at['bounds'][3]-at['bounds'][1];lo=np.array(config['lower']);lower=PchipInterpolator(lo[:,0],lo[:,1])
  c.edit('keyform_apply',changes=[{'op':'seed','target':m[aperture],'key':{pid:v}} for v in [0,1]])
  aops=[]
  for i,x,y in at['items']:
   cx=x+540-config['box'][0];cy=y+800-config['box'][1]
   destination=float(lower(np.clip(cx,lo[0,0],lo[-1,0])))-.6
   aops.append({'type':'translate','delta':[0,(destination-cy)/ah],'selection':{'indices':[i]}})
  for start in range(0,len(aops),16):c.edit('rig_deform',changes=[{'target':m[aperture],'key':{pid:0},'operations':aops[start:start+16]}])
  name=side+'Iris';topo=json.loads((P/(name+'-topology.json')).read_text());b=topo['bounds'];w=b[2]-b[0];h=b[3]-b[1]
  keys=[{'ParamEyeBallX':x,'ParamEyeBallY':y} for x in [-1,0,1] for y in [-1,0,1]]
  c.edit('keyform_apply',changes=[{'op':'seed','target':m[name],'key':k} for k in keys])
  c.edit('rig_deform',changes=[{'target':m[name],'key':k,'operations':[{'type':'translate','delta':[k['ParamEyeBallX']*config['gaze'][0]/w,-k['ParamEyeBallY']*config['gaze'][1]/h]}]} for k in keys])
  print('bound',side,flush=True)
 c.edit('project_save_as',path=str(P/'character-both-eyes.psd2live'))
 for name,params in [('open',{}),('half',{'ParamEyeROpen':.5,'ParamEyeLOpen':.5}),('closed',{'ParamEyeROpen':0,'ParamEyeLOpen':0}),('left-only',{'ParamEyeLOpen':0}),('right-only',{'ParamEyeROpen':0}),('gaze-left',{'ParamEyeBallX':-1}),('gaze-right',{'ParamEyeBallX':1})]:
  meta,imgs=c.call('view_render_model',{'viewport':{'mode':'canvas_rect','left':0,'top':0,'width':1137,'height':1383},'target_long_edge':1383,'parameters':params,'background':'transparent'})
  for i,img in enumerate(imgs):(P/(name+'-'+str(i)+'.png')).write_bytes(img)
  print('rendered',name,flush=True)
 c.edit('project_export_model',output_directory=str(P/'runtime'));print('exported',flush=True)
