"""Actual Core triangles + real atlas alpha establish three source ownership probes.

Then independently executes arm/finger extremes and 27 detached cup ROOT corners.
Source alpha or authoring bounding boxes alone never establish runtime ownership.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import math
from PIL import Image
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script

parser=argparse.ArgumentParser(description=__doc__)
for name in ['model','manifest','snapshot','runtime-dir','output']:
 parser.add_argument('--'+name,required=True)
parser.add_argument('--cup-hold-parameter',default='ParamCupHold',help='Explicit held-mode switch for this authored rig; detached probes set it to0 when present')
args=parser.parse_args();model=Path(args.model).resolve();setting=json.loads(model.read_text());base=model.parent
manifest_file=Path(args.manifest).resolve();manifest=json.loads(manifest_file.read_text());snapshot_file=Path(args.snapshot).resolve();snapshot=json.loads(snapshot_file.read_text());rest=snapshot['measurement']
moc_file=base/setting['FileReferences']['Moc'];cdi_file=base/setting['FileReferences']['DisplayInfo'];cdi=json.loads(cdi_file.read_text());core=installed_script(Path(args.runtime_dir).resolve(),'core')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert snapshot['sources'][str(moc_file)]==sha(moc_file),'Wrong-model rest snapshot rejected'
name_to_id={d['Name']:d['Id'] for d in cdi['Drawables']};id_to_name={v:k for k,v in name_to_id.items()}
files=[model,moc_file,cdi_file,core,manifest_file,snapshot_file,Path(__file__).resolve(),Path(__file__).with_name('live2d_original_core_check.py'),*[base/path for path in setting['FileReferences']['Textures']]];sources={str(p):sha(p) for p in files}
textures=[Image.open(base/path).convert('RGBA') for path in setting['FileReferences']['Textures']]
c=rest['canvasInfo']
def coords(drawable):
 v=drawable['positions'];return [(v[i]*c['ppu']+c['originX'],c['originY']-v[i+1]*c['ppu']) for i in range(0,len(v),2)]
def bary(point,a,b,c):
 den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
 if abs(den)<1e-12:return None
 w0=((b[1]-c[1])*(point[0]-c[0])+(c[0]-b[0])*(point[1]-c[1]))/den;w1=((c[1]-a[1])*(point[0]-c[0])+(a[0]-c[0])*(point[1]-c[1]))/den;w2=1-w0-w1
 return [w0,w1,w2] if min(w0,w1,w2)>=-1e-8 else None

def alpha_sample(image,u,v):
 # Official Cubism vertex shader v_texCoord.y=1.0-v_texCoord.y, no textureFlipY.
 x=u*image.width-.5;y=(1-v)*image.height-.5;x0=math.floor(x);y0=math.floor(y);a=0
 for ox in [0,1]:
  for oy in [0,1]:
   px=max(0,min(image.width-1,x0+ox));py=max(0,min(image.height-1,y0+oy));weight=(1-abs(x-(x0+ox)))*(1-abs(y-(y0+oy)));a+=image.getpixel((px,py))[3]*weight
 return a

def hits(point):
 owners=[]
 for drawable in rest['drawables']:
  xy=coords(drawable);triangles=drawable['triangleIndices'];uv=drawable['uvs'];found=[]
  for offset in range(0,len(triangles),3):
   indices=triangles[offset:offset+3];weights=bary(point,*[xy[i] for i in indices])
   if weights is None:continue
   u=sum(weights[j]*uv[indices[j]*2] for j in range(3));v=sum(weights[j]*uv[indices[j]*2+1] for j in range(3));alpha=alpha_sample(textures[drawable['textureIndex']],u,v)*drawable['opacity'];found.append({'triangleOffset':offset,'indices':indices,'weights':weights,'uv':[u,v],'effectiveAtlasAlpha':alpha})
  if found:owners.append({'id':drawable['id'],'name':id_to_name.get(drawable['id']),'samples':found,'maxEffectiveAlpha':max(x['effectiveAtlasAlpha'] for x in found)})
 return owners

probes=[];anchors=[]
for spec in manifest['semantic_probes']:
 point=[spec['x'],spec['y']];owners=hits(point);by_name={entry['name']:entry for entry in owners};expected=by_name.get(spec['expected_layer']);forbidden={name:by_name.get(name,{}).get('maxEffectiveAlpha',0) for name in spec['forbidden_layers']}
 assert expected and expected['maxEffectiveAlpha']>=8,('Actual Core/atlas expected owner missing',spec['name'],owners)
 assert all(value<8 for value in forbidden.values()),('Forbidden actual alpha owner',spec['name'],forbidden)
 sample=max(expected['samples'],key=lambda s:s['effectiveAtlasAlpha']);anchor={'name':spec['name'],'meshId':expected['id'],'indices':sample['indices'],'weights':sample['weights'],'sourceCanvas':point};anchors.append(anchor)
 probes.append({'name':spec['name'],'sourceCanvas':point,'expectedCoreMesh':expected['id'],'expectedCoreAtlasAlpha':expected['maxEffectiveAlpha'],'forbiddenCoreAtlasAlpha':forbidden,'allActualOwners':owners,'actualTriangleAnchor':anchor})
# A deliberately wrong semantic assignment at the SAME real point must be rejected.
wrong_assignment_rejected=all(all(entry.get('maxEffectiveAlpha',0)<8 for entry in p['allActualOwners'] if entry['name'] in manifest['semantic_probes'][i]['forbidden_layers']) for i,p in enumerate(probes))
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page();page.add_script_tag(content='(function(){var WebAssembly={};\n'+core.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
 actual=page.evaluate(r'''args=>{
  const bytes=Uint8Array.from(atob(args.encoded),x=>x.charCodeAt(0)),C=Live2DCubismCore;if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core rejects moc');
  const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables,c=raw.canvasinfo;
  const holdIndex=p.ids.indexOf(args.cupHoldParameter);function reset(){p.values.set(p.defaultValues);if(holdIndex>=0)p.values[holdIndex]=0;raw.update();}
  function points(){return args.anchors.map(a=>{const i=d.ids.indexOf(a.meshId),v=d.vertexPositions[i];return {name:a.name,xy:[a.indices.reduce((s,index,j)=>s+a.weights[j]*v[index*2],0)*c.PixelsPerUnit+c.CanvasOriginX,c.CanvasOriginY-a.indices.reduce((s,index,j)=>s+a.weights[j]*v[index*2+1],0)*c.PixelsPerUnit]};});}
  reset();const baseline=points(),base=Array.from(d.vertexPositions,v=>Array.from(v));
  function changed(){return Array.from(d.ids).filter((_,i)=>d.vertexPositions[i].some((x,j)=>x!==base[i][j]));}
  const protectedIds=args.anchors.map(a=>a.meshId),palms=args.palms,armRows=[];
  for(let i=0;i<p.count;i++)if(/^Param(Arm|Forearm|Hand|Finger)/.test(p.ids[i]))for(const value of [p.minimumValues[i],p.maximumValues[i]]){
   reset();p.values[i]=value;raw.update();const current=points(),maxProtectedMotion=Math.max(...current.map((a,j)=>Math.hypot(a.xy[0]-baseline[j].xy[0],a.xy[1]-baseline[j].xy[1]))),changes=changed();
   if(maxProtectedMotion>1e-6)throw Error('Arm/finger deforms protected torso source ownership '+p.ids[i]);
   armRows.push({parameter:p.ids[i],value,changedDrawables:changes,maxProtectedMotion,torsoEdgeGeometryMayChange:changes.some(id=>protectedIds.includes(id))});
  }
  const index=id=>{const i=p.ids.indexOf(id);if(i<0)throw Error('Missing cup parameter '+id);return i;},ix=index('ParamCupX'),iy=index('ParamCupY'),ir=index('ParamCupRotation'),iv=index('ParamCupVisible'),cupRows=[];
  for(const x of [p.minimumValues[ix],p.defaultValues[ix],p.maximumValues[ix]])for(const y of [p.minimumValues[iy],p.defaultValues[iy],p.maximumValues[iy]])for(const r of [p.minimumValues[ir],p.defaultValues[ir],p.maximumValues[ir]]){
   reset();p.values[ix]=x;p.values[iy]=y;p.values[ir]=r;raw.update();const changes=changed();
   if(changes.some(id=>id!==args.cup))throw Error('Detached cup ROOT deforms another real mesh');
   if(Array.from(d.vertexPositions).some(v=>v.some(n=>!Number.isFinite(n))))throw Error('Nonfinite cup corner');
   cupRows.push({x,y,rotation:r,changedDrawables:changes,palmsUnchanged:palms.every(id=>!changes.includes(id))});
  }
  const visible=[];for(const value of [0,1]){reset();p.values[iv]=value;raw.update();const i=d.ids.indexOf(args.cup),changes=changed(),opacity=d.opacities[i];if(changes.length||opacity!==value)throw Error('Cup visibility does not isolate exact real cup opacity');visible.push({value,cupOpacity:opacity,geometryChanged:changes});}
  const result={armRows,cupRows,cupVisibility:visible,baselineAnchors:baseline,cupHoldParameterPresent:holdIndex>=0,detachedHoldOverride:holdIndex>=0?{id:args.cupHoldParameter,value:0}:null};raw.release();moc._release();return result;
 }''',{'encoded':base64.b64encode(moc_file.read_bytes()).decode(),'anchors':anchors,'cup':name_to_id['cup'],'palms':[name_to_id['hand-l'],name_to_id['hand-r']],'cupHoldParameter':args.cup_hold_parameter})
 browser.close()
report={'status':'bounded_semantic_and_detached_cup_checks_passed','scope':'Actual Core rest triangles/UVs + actual atlas alpha; three reviewed source ownership points; 32 arm/hand/finger extremes and 27 detached cup ROOT corners, exact three protected torso barycentric points and palm isolation; legitimate shoulder glue may change other torso vertices; NOT held grip/glue or art acceptance','sources':sources,'sources_unchanged':all(sha(Path(k))==v for k,v in sources.items()),'probes':probes,'forbidden_owner_alpha_predicate_would_reject_assignment':wrong_assignment_rejected,'actual_core_operations':actual,'not_proven':['CupHold/grip coupling','Cuff/shoulder/elbow seams or occlusion','All parameter combinations or continuous motions','Texture alpha interpretation at deformed non-rest points','Human/user art acceptance']}
Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'probes':[(p['name'],p['expectedCoreAtlasAlpha'],p['forbiddenCoreAtlasAlpha']) for p in probes],'arm_extremes':len(actual['armRows']),'cup_corners':len(actual['cupRows']),'cupHold':actual['cupHoldParameterPresent']}))
