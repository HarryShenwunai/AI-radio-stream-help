"""Export a private measurement snapshot from actual owner-installed Cubism Core.

Only for original models: never publish vendor sample coordinates via this tool.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',required=True)
parser.add_argument('--runtime-dir',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
model=Path(args.model).resolve();setting=json.loads(model.read_text());moc=model.parent/setting['FileReferences']['Moc'];core=installed_script(Path(args.runtime_dir).resolve(),'core')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources={str(p):sha(p) for p in [model,moc,core,Path(__file__).resolve()]}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page()
 page.add_script_tag(content='(function(){var WebAssembly={};\n'+core.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
 data=page.evaluate(r'''encoded=>{
  const bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0)),C=Live2DCubismCore;
  if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Real Core rejects moc');
  const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables,c=raw.canvasinfo;
  p.values.set(p.defaultValues);raw.update();
  const drawables=Array.from(d.ids,(id,i)=>({id,index:i,positions:Array.from(d.vertexPositions[i]),triangleIndices:Array.from(d.indices[i]),uvs:Array.from(d.vertexUvs[i]),opacity:d.opacities[i],vertexCount:d.vertexCounts[i],textureIndex:d.textureIndices[i],masks:Array.from(d.masks[i]),renderOrder:d.renderOrders[i],drawOrder:d.drawOrders[i]}));
  const result={coreVersion:C.Version.csmGetVersion(),mocVersion:C.Version.csmGetMocVersion(moc,bytes.buffer),consistency:1,pose:'actual parameter defaults, raw Core.update performed, no framework/physics/animation',canvasInfo:{width:c.CanvasWidth,height:c.CanvasHeight,originX:c.CanvasOriginX,originY:c.CanvasOriginY,ppu:c.PixelsPerUnit},coordinateTransform:'canvasX=coreX*ppu+originX; canvasY=originY-coreY*ppu',parameters:Array.from(p.ids,(id,i)=>({id,index:i,min:p.minimumValues[i],default:p.defaultValues[i],max:p.maximumValues[i],value:p.values[i]})),parts:Array.from(raw.parts.ids,(id,i)=>({id,index:i,opacity:raw.parts.opacities[i]})),drawables};
  raw.release();moc._release();return result;
 }''',base64.b64encode(moc.read_bytes()).decode())
 browser.close()
report={'status':'measured_private_original_model_snapshot','sources':sources,'sources_unchanged':all(sha(Path(p))==digest for p,digest in sources.items()),'measurement':data,'not_proven':['barycentric landmarks are anatomically correct','hand/cup binding or art acceptance']}
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n')
print(json.dumps({'status':report['status'],'drawables':len(data['drawables']),'output':str(output.resolve()),'bytes':output.stat().st_size,'sha256':sha(output),'sources_unchanged':report['sources_unchanged']}))
