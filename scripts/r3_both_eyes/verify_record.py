from pathlib import Path
import json,threading,http.server,functools,base64,argparse
from playwright.sync_api import sync_playwright
DEFAULT=Path(__file__).resolve().parents[2]/'.build/r3-both-eyes'
parser=argparse.ArgumentParser(description='Verify actual Core poses and record the held-cup dual-eye model.')
parser.add_argument('--work-dir',type=Path,default=DEFAULT)
parser.add_argument('--transparent-stage',action='store_true')
args=parser.parse_args();P=args.work_dir.resolve()
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
http=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(P)));threading.Thread(target=http.serve_forever,daemon=True).start()
mesh_map={name:target.split(':',1)[1] for name,target in json.loads((P/'mesh-map.json').read_text()).items()}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=str(P/'owner-local/chrome-headless-shell-linux64/chrome-headless-shell'),headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':720,'height':876},device_scale_factor=1);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:'+str(http.server_port)+'/preview.html');page.wait_for_function('window.state?.ready || window.error',timeout=90000);assert not page.evaluate('window.error')
 report=page.evaluate('''(names)=>{
 const core=window.reviewModel.internalModel.coreModel;
 const snap=()=>Object.fromEntries(Array.from({length:core.getModel().drawables.count},(_,i)=>[core.getDrawableId(i),Array.from(core.getDrawableVertexPositions(i))]));
 window.drawPose({});const neutral=snap(),checks=[];
 const poses=[];for(let i=0;i<=10;i++)poses.push({ParamEyeROpen:i/10,ParamEyeLOpen:i/10},{ParamEyeROpen:i/10},{ParamEyeLOpen:i/10});
 for(const x of [-1,0,1])for(const y of [-1,0,1])poses.push({ParamEyeBallX:x,ParamEyeBallY:y});
 poses.push({ParamBreath:1},{ParamAngleZ:-2},{ParamAngleZ:2},{ParamEyeROpen:.5,ParamBreath:1,ParamAngleZ:2,ParamEyeBallX:1,ParamEyeBallY:1});
 for(const pose of poses){window.drawPose(pose);const now=snap(),changed=[];for(const[name,id]of Object.entries(names)){let delta=0;for(let i=0;i<neutral[id].length;i++)delta=Math.max(delta,Math.abs(neutral[id][i]-now[id][i]));if(delta>1e-7)changed.push({name,delta});}checks.push({pose,changed});}
 const raw=core.getModel(),irisIndices=['LIris','RIris'].map(n=>Array.from(raw.drawables.ids).indexOf(names[n]));
 window.drawPose({});return {checks,irisMaskCounts:irisIndices.map(i=>Number(raw.drawables.maskCounts[i])),core:window.state};}''',mesh_map)
 held=[n for n in mesh_map if n.startswith(('Near_','Far_','Sleeve_')) or n=='Cup']
 assert all(not any(x['name'] in held for x in row['changed']) for row in report['checks'])
 assert report['irisMaskCounts']==[1,1]
 if args.transparent_stage:
  opacity=page.evaluate('''(names)=>{const core=window.reviewModel.internalModel.coreModel;window.drawPose({});const ids=Array.from(core.getModel().drawables.ids);return Object.fromEntries(['Background_and_hidden_body','Steam'].map(name=>[name,core.getDrawableOpacity(ids.indexOf(names[name]))]));}''',mesh_map)
  assert opacity['Background_and_hidden_body']==0,opacity
  assert 0<opacity['Steam']<=.15,opacity
  report['stage_opacities']=opacity
 assert any(row['pose']=={'ParamBreath':1} and [x['name'] for x in row['changed']]==['Torso'] for row in report['checks'])
 assert any(row['pose']=={'ParamEyeBallX':1,'ParamEyeBallY':0} and set(x['name'] for x in row['changed'])=={'LIris','RIris'} for row in report['checks'])
 frames=P/'frames';frames.mkdir(exist_ok=True)
 sequence=[1-i/10 for i in range(11)]+[i/10 for i in range(1,11)]
 for i,value in enumerate(sequence):
  page.evaluate('(v)=>window.drawPose({ParamEyeROpen:v,ParamEyeLOpen:v})',value);page.screenshot(path=str(frames/f'blink-{i:02}.png'))
 for name,pose in [('gaze-left',{'ParamEyeBallX':-1}),('gaze-right',{'ParamEyeBallX':1}),('head-left',{'ParamAngleZ':-2}),('head-right',{'ParamAngleZ':2}),('breath-max',{'ParamBreath':1}),('neutral',{})]:
  page.evaluate('(v)=>window.drawPose(v)',pose);page.screenshot(path=str(frames/(name+'.png')))
 video=page.evaluate('window.record()');(P/'both-eyes-review.webm').write_bytes(base64.b64decode(video.pop('base64')))
 assert not errors,errors;assert all(x['cup']==0 for x in video['appliedSamples'])
 assert min(x['eyeL'] for x in video['appliedSamples'])<.1
 assert min(x['eye'] for x in video['appliedSamples'])<.1
 assert max(abs(x['gaze']) for x in video['appliedSamples'])>.5
 assert max(x['breath'] for x in video['appliedSamples'])>.9
 report.update({'javascript_errors':errors,'fixed_meshes':held,'blink_frames':21,'video':video})
 (P/'core-verification.json').write_text(json.dumps(report,indent=2));print('verified',len(report['checks']),'poses, 21 blink frames,',len(video['appliedSamples']),'video samples',flush=True)
 browser.close()
http.shutdown()
