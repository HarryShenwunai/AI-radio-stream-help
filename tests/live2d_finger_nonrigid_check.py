"""Independent real-Core finger shape test, distinct from landmark bend-angle tests.

Compares each min/max to the DEFAULT shape, because symmetric opposite bends may
have identical distances to each other. Fits out translation/rotation and checks
pair distances, exact pinned root vertices, and every non-target drawable.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script

parser=argparse.ArgumentParser(description=__doc__)
for name in ['model','recipe','runtime-dir','output']:parser.add_argument('--'+name,required=True)
parser.add_argument('--expect-rigid-negative',action='store_true')
args=parser.parse_args();model=Path(args.model).resolve();setting=json.loads(model.read_text());base=model.parent;moc=base/setting['FileReferences']['Moc'];cdi=base/setting['FileReferences']['DisplayInfo'];display=json.loads(cdi.read_text());mapping={d['Name']:d['Id'] for d in display['Drawables']}
recipe_file=Path(args.recipe).resolve();recipe=json.loads(recipe_file.read_text());fingers=[]
for step in recipe['steps']:
 if step.get('operation')!='author_axis':continue
 request=step.get('request',{});shapes=request.get('shapes',[])
 if not shapes or not str(shapes[0].get('target','')).startswith('$target:finger-'):continue
 arc=next((op for op in shapes[0].get('operations',[]) if op.get('type')=='arc'),None)
 if not arc:continue
 name=shapes[0]['target'].removeprefix('$target:');fingers.append({'name':name,'mesh':mapping[name],'parameter':request['parameter']['id'],'values':sorted({shape['value'] for shape in shapes}),'selected_indices':arc['selection']['indices']})
assert len(fingers)==10 and len({f['mesh'] for f in fingers})==10,'Need ten explicit actual finger arc operations'
core=installed_script(Path(args.runtime_dir).resolve(),'core');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files=[model,moc,cdi,recipe_file,core,Path(__file__).resolve(),Path(__file__).with_name('live2d_original_core_check.py')];sources={str(p):sha(p) for p in files}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page();page.add_script_tag(content='(function(){var WebAssembly={};\n'+core.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
 result=page.evaluate(r'''args=>{
  const bytes=Uint8Array.from(atob(args.encoded),x=>x.charCodeAt(0)),C=Live2DCubismCore;if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core rejects moc');
  const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables,ppu=raw.canvasinfo.PixelsPerUnit;
  const snap=()=>Array.from(d.vertexPositions,v=>Array.from(v));function reset(){p.values.set(p.defaultValues);raw.update();}
  reset();const base=snap(),baseOpacity=Array.from(d.opacities);
  function metrics(a,b){const n=a.length/2;let ax=0,ay=0,bx=0,by=0;for(let i=0;i<a.length;i+=2){ax+=a[i]/n;ay+=a[i+1]/n;bx+=b[i]/n;by+=b[i+1]/n;}let dot=0,cross=0;for(let i=0;i<a.length;i+=2){const x=a[i]-ax,y=a[i+1]-ay,u=b[i]-bx,v=b[i+1]-by;dot+=x*u+y*v;cross+=x*v-y*u;}const angle=Math.atan2(cross,dot),cos=Math.cos(angle),sin=Math.sin(angle);let maxResidual=0,maxPairDistanceDelta=0;for(let i=0;i<a.length;i+=2){const x=cos*(a[i]-ax)-sin*(a[i+1]-ay)+bx,y=sin*(a[i]-ax)+cos*(a[i+1]-ay)+by;maxResidual=Math.max(maxResidual,Math.hypot(x-b[i],y-b[i+1])*ppu);for(let j=i+2;j<a.length;j+=2){maxPairDistanceDelta=Math.max(maxPairDistanceDelta,Math.abs(Math.hypot(a[i]-a[j],a[i+1]-a[j+1])-Math.hypot(b[i]-b[j],b[i+1]-b[j+1]))*ppu);}}return {bestRigidFitMaxResidualSourcePx:maxResidual,maxPairDistanceDeltaSourcePx:maxPairDistanceDelta};}
  const rows=[];for(const spec of args.fingers){const mi=d.ids.indexOf(spec.mesh),pi=p.ids.indexOf(spec.parameter);if(mi<0||pi<0)throw Error('Actual declared finger/parameter missing');const roots=Array.from({length:d.vertexCounts[mi]},(_,i)=>i).filter(i=>!spec.selected_indices.includes(i));const rootsAreActualTriangle=roots.length===3&&Array.from({length:d.indices[mi].length/3},(_,i)=>Array.from(d.indices[mi].slice(i*3,i*3+3))).some(tri=>roots.every(i=>tri.includes(i)));if(!rootsAreActualTriangle)throw Error('Pinned root is not a real Core triangle');const states=[];for(const value of spec.values){reset();p.values[pi]=value;raw.update();const now=snap(),otherChanged=Array.from(d.ids).filter((_,j)=>j!==mi&&(now[j].some((x,k)=>x!==base[j][k])||d.opacities[j]!==baseOpacity[j])),rootMaxDrift=Math.max(...roots.map(i=>Math.hypot(now[mi][i*2]-base[mi][i*2],now[mi][i*2+1]-base[mi][i*2+1])*ppu));states.push({value,...metrics(base[mi],now[mi]),rootMaxDriftSourcePx:rootMaxDrift,nonTargetChanged:otherChanged});}rows.push({...spec,pinnedRootIndices:roots,rootsAreActualTriangle,states});}
  raw.release();moc._release();return {ppu,rows};
 }''',{'encoded':base64.b64encode(moc.read_bytes()).decode(),'fingers':fingers});browser.close()
# .001 source pixel is a numerical-detection floor only, not an art/visibility budget.
epsilon=.001;failures=[]
for finger in result['rows']:
 if not any(s['bestRigidFitMaxResidualSourcePx']>epsilon and s['maxPairDistanceDeltaSourcePx']>epsilon for s in finger['states']):failures.append({'finger':finger['name'],'kind':'requires_true_nonrigid_shape'})
 if any(s['rootMaxDriftSourcePx']!=0 for s in finger['states']):failures.append({'finger':finger['name'],'kind':'pinned_actual_root_triangle_moves'})
 if any(s['nonTargetChanged'] for s in finger['states']):failures.append({'finger':finger['name'],'kind':'non_target_changes'})
expected_negative=args.expect_rigid_negative and any(f['kind']=='requires_true_nonrigid_shape' for f in failures)
report={'status':'expected_rigid_counterexample_reproduced' if expected_negative else 'passed' if not failures else 'failed','scope':'Actual official Core, min/max versus DEFAULT shape, rigid Procrustes fit + pair distances + actual pinned triangle and exact non-target vertices/opacity; no GL/art acceptance','sources':sources,'sources_unchanged':all(sha(Path(k))==v for k,v in sources.items()),'source_pixel_numerical_detection_floor':epsilon,'measurement':result,'failures':failures,'expected_old_rigid_negative':args.expect_rigid_negative,'not_proven':['Visible finger curvature through actual GL','Palm/finger alpha contact','Human finger/hand artwork quality','Full action/CupHold/glue acceptance']}
Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'fingers':len(result['rows']),'failures':failures,'min_actual_nonrigid_residual':min(max(s['bestRigidFitMaxResidualSourcePx'] for s in f['states']) for f in result['rows'])}))
if not (not failures or expected_negative):raise SystemExit(1)
