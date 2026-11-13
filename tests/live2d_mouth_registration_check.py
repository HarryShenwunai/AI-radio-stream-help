"""Read real Core mouth/lip bounds; a geometric diagnostic, not an art detector."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import time
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model', required=True)
parser.add_argument('--runtime-dir', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
model = Path(args.model).resolve()
setting = json.loads(model.read_text())
moc_file = model.parent / setting['FileReferences']['Moc']
core_file = installed_script(Path(args.runtime_dir).resolve(), 'core')
source_files = [model, moc_file, core_file, Path(__file__).resolve()]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = {str(p): sha(p) for p in source_files}
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
    page = browser.new_page()
    page.add_script_tag(content='(function(){var WebAssembly={};\n'+core_file.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
    result = page.evaluate(r'''encoded=>{
 const bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0)),C=Live2DCubismCore;
 if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core rejects moc');
 const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables,info=raw.canvasinfo;
 const ids=['ArtMeshMouth','ArtMeshLayer3','ArtMeshLayer2'];for(const id of ids)if(!d.ids.includes(id))throw Error('Actual semantic drawable missing '+id);
 function bounds(id){const index=d.ids.indexOf(id),v=d.vertexPositions[index],xs=[],ys=[];for(let i=0;i<v.length;i+=2){xs.push(v[i]*info.PixelsPerUnit+info.CanvasOriginX);ys.push(info.CanvasOriginY-v[i+1]*info.PixelsPerUnit);}return {id,sourceCanvasXY:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],opacity:d.opacities[index],vertexCount:v.length/2};}
 const open=p.ids.indexOf('ParamMouthOpenY'),form=p.ids.indexOf('ParamMouthForm'),states=[];
 for(const value of [0,.5,1])for(const shape of [-1,0,1]){p.values.set(p.defaultValues);p.values[open]=value;p.values[form]=shape;raw.update();const meshes=ids.map(bounds),[mouth,upper,lower]=meshes.map(m=>m.sourceCanvasXY);states.push({open:value,form:shape,meshes,upperLipToCavitySourcePixelGap:mouth[1]-upper[3],lowerLipToCavitySourcePixelGap:lower[1]-mouth[3],note:'Positive gap means geometric envelopes separated; negative means overlap. This does not inspect texture alpha and is not automatic art acceptance.'});}
 const canvasInfo={width:info.CanvasWidth,height:info.CanvasHeight,originX:info.CanvasOriginX,originY:info.CanvasOriginY,ppu:info.PixelsPerUnit};raw.release();moc._release();return {canvasInfo,states};
}''', base64.b64encode(moc_file.read_bytes()).decode())
    browser.close()
report = {'status':'measured_not_art_acceptance','date_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Actual official Core parameter corners -> real source-canvas mesh bounds; no GL/wrapper, no image edits','sources':sources,'sources_unchanged':all(sha(Path(p))==digest for p,digest in sources.items()),'measurement':result,'not_proven':['Texture-alpha lip/cavity registration','Human artwork acceptance','Lip movement has correct artistic shape']}
Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report['measurement'],ensure_ascii=False))
