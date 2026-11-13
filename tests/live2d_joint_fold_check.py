"""Read real Core cloth triangle winding/area/stretch at authored joint poses.

A diagnostic for the observed paper-edge artifact, not an automatic art detector.
Counts cover all declared cloth triangles; example lists are explicitly bounded.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script
from live2d_joint_poses import joint_combinations, joint_interiors

parser=argparse.ArgumentParser(description=__doc__)
for name in ['model','runtime-dir','output']:parser.add_argument('--'+name,required=True)
parser.add_argument('--joint-combinations',action='store_true',help='Also measure eight same-side corners and four opposite-side combinations')
parser.add_argument('--joint-interiors',action='store_true',help='Also measure fourteen off-integer single/combined joint poses')
args=parser.parse_args();model=Path(args.model).resolve();setting=json.loads(model.read_text());moc=model.parent/setting['FileReferences']['Moc'];cdi=model.parent/setting['FileReferences']['DisplayInfo'];names={row['Id']:row['Name'] for row in json.loads(cdi.read_text())['Drawables']};core=installed_script(Path(args.runtime_dir).resolve(),'core');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();sources={str(p):sha(p) for p in [model,moc,cdi,core,Path(__file__).resolve(),Path(__file__).with_name('live2d_joint_poses.py')]}
roles={'topwear','topwear-backfill','upperarm-l','upperarm-r','forearm-l','forearm-r','cuff-front-l','cuff-front-r'};targets=[key for key,name in names.items() if name in roles]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page();page.add_script_tag(content='(function(){var WebAssembly={};\n'+core.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
 ranges=page.evaluate(r'''encoded=>{const C=Live2DCubismCore,bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0));if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Core consistency failed');const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,result=Array.from(p.ids,(id,i)=>({id,min:p.minimumValues[i],default:p.defaultValues[i],max:p.maximumValues[i]}));raw.release();moc._release();return result;}''',base64.b64encode(moc.read_bytes()).decode())
 combinations=(joint_combinations(ranges) if args.joint_combinations else [])+(joint_interiors(ranges) if args.joint_interiors else [])
 measured=page.evaluate(r'''args=>{
 const bytes=Uint8Array.from(atob(args.encoded),x=>x.charCodeAt(0)),C=Live2DCubismCore;if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core rejects model');const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables,ppu=raw.canvasinfo.PixelsPerUnit;
 function reset(){p.values.set(p.defaultValues);raw.update();}reset();const rest=Array.from(d.vertexPositions,v=>Array.from(v)),targetIndices=args.targets.map(id=>d.ids.indexOf(id));
 function area(v,a,b,c){return ((v[b*2]-v[a*2])*(v[c*2+1]-v[a*2+1])-(v[b*2+1]-v[a*2+1])*(v[c*2]-v[a*2]))*ppu*ppu/2;}
 function metrics(index){const before=rest[index],after=d.vertexPositions[index],tri=d.indices[index],flips=[],collapsed=[],emerging=[];let maxEdgeStretchRatio=1,analyzed=0;for(let offset=0;offset<tri.length;offset+=3){const [a,b,c]=tri.slice(offset,offset+3),base=area(before,a,b,c),posed=area(after,a,b,c);analyzed++;if(Math.abs(base)>=.01&&Math.abs(posed)>=.01&&base*posed<0)flips.push({triangleOffset:offset,indices:[a,b,c],restAreaSourcePx2:base,posedAreaSourcePx2:posed});if(Math.abs(base)>=1&&Math.abs(posed)<Math.abs(base)*.01)collapsed.push(offset);if(Math.abs(base)<.01&&Math.abs(posed)>=1)emerging.push(offset);for(const [u,v]of [[a,b],[b,c],[c,a]]){const length0=Math.hypot(before[u*2]-before[v*2],before[u*2+1]-before[v*2+1])*ppu,length1=Math.hypot(after[u*2]-after[v*2],after[u*2+1]-after[v*2+1])*ppu;if(length0>=.5)maxEdgeStretchRatio=Math.max(maxEdgeStretchRatio,length1/length0);}}return {id:d.ids[index],opacity:d.opacities[index],analyzedTriangles:analyzed,windingFlipCount:flips.length,collapsedCount:collapsed.length,restDegenerateBecameLargeCount:emerging.length,maxEdgeStretchRatio,first30Flips:flips.slice(0,30),first30Collapsed:collapsed.slice(0,30),first30Emerging:emerging.slice(0,30)};}
 const poses=[];for(const id of ['ParamArmL','ParamArmR','ParamForearmL','ParamForearmR']){const i=p.ids.indexOf(id);if(i<0)throw Error('Declared joint missing');for(const value of [p.minimumValues[i],p.maximumValues[i]]){reset();p.values[i]=value;raw.update();poses.push({parameter:id,value,cloth:targetIndices.map(metrics)});}}
 const parameters=Array.from(p.ids,(id,i)=>({id,min:p.minimumValues[i],default:p.defaultValues[i],max:p.maximumValues[i]}));for(const pose of args.combinations||[]){reset();for(const [id,value]of Object.entries(pose.parameters)){const i=p.ids.indexOf(id);if(i<0||value<p.minimumValues[i]||value>p.maximumValues[i])throw Error('Invalid joint combination '+id);p.values[i]=value;}raw.update();poses.push({...pose,cloth:targetIndices.map(metrics)});}
 const result={ppu,coreVersion:C.Version.csmGetVersion(),parameters,poses};raw.release();moc._release();return result;
 }''',{'encoded':base64.b64encode(moc.read_bytes()).decode(),'targets':targets,'combinations':combinations});browser.close()
report={'status':'actual_core_cloth_fold_metrics_measured_not_art_pass','scope':'Real authored joint extremes; all declared cloth triangle areas/winding/edge stretches vs actual default pose. Areas ignore sub.01 sourcepx2 numerical debris; examples capped30 but counts complete. Texture alpha/occlusion not measured.','sources':sources,'sources_unchanged':all(sha(Path(k))==v for k,v in sources.items()),'drawable_names':{key:names[key] for key in targets},'measurement':measured,'not_proven':['Human artwork acceptance','Flipped triangles are visible after alpha/masks','Continuous joint state space or all animation frames']}
Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'poses':[{'id':p.get('name',p.get('parameter')),'value':p.get('parameters',p.get('value')),'flips':sum(d['windingFlipCount'] for d in p['cloth']),'maxEdgeStretch':max(d['maxEdgeStretchRatio'] for d in p['cloth'])} for p in measured['poses']]}))
