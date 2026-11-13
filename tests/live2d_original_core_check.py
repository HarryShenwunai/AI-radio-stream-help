"""Independent original-export validation using separately licensed, actual Cubism Core.

No downloads, fixture artwork generation, adapter mocks, or product modifications.
The supplied directory must be an ORIGINAL export; provenance is reported, not inferred.
A successful run proves this export/Core pair's geometry and rendering, not art quality.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import mimetypes
import shlex
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright
from live2d_joint_poses import joint_combinations, joint_interiors

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_script(root: Path, kind: str) -> Path:
    revision = json.loads((root / f'{kind}.json').read_text())['revision']
    directory = root / 'revisions' / revision
    path = directory / 'script.js'
    record = json.loads((directory / 'record.json').read_text())
    if sha(path) != record['sha256']:
        raise ValueError('Owner-installed runtime hash mismatch')
    return path


RAW_CHECK = r"""async ({modelURL,required}) => {
 const setting=await(await fetch(modelURL)).json(),refs=setting.FileReferences;
 const url=new URL(refs.Moc,modelURL),buffer=await(await fetch(url)).arrayBuffer();
 const C=Live2DCubismCore,latest=C.Version.csmGetLatestMocVersion();
 const header=Array.from(new Uint8Array(buffer,0,Math.min(8,buffer.byteLength)));
 if(header.slice(0,4).join(',')!=='77,79,67,51')throw Error('MOC3 magic rejected');
 if(header[4]>latest)throw Error(`Export MOC ${header[4]} exceeds installed Core ${latest}`);
 const consistency=C.Moc.prototype.hasMocConsistency(buffer);
 if(consistency!==1)throw Error('Official csmHasMocConsistency rejected ORIGINAL export');
 const moc=C.Moc.fromArrayBuffer(buffer);if(!moc)throw Error('Official Core cannot revive ORIGINAL moc');
 const raw=C.Model.fromMoc(moc);if(!raw)throw Error('Official Core cannot construct model');
 const p=raw.parameters,d=raw.drawables;
 function snapshot(){return Array.from(d.vertexPositions,vertices=>Array.from(vertices));}
 function diff(a,b){let vertices=0,drawables=[];for(let j=0;j<a.length;j++){let changes=0;for(let k=0;k<a[j].length;k++)if(Math.abs(a[j][k]-b[j][k])>1e-7)changes++;if(changes){drawables.push(d.ids[j]);vertices+=changes;}}return {coordinates:vertices,drawables};}
 function reset(){p.values.set(p.defaultValues);raw.update();}
 reset();const baseline=snapshot();raw.update();const noop=diff(baseline,snapshot());
 if(noop.coordinates)throw Error('Unchanged raw Core geometry is nondeterministic');
 const info=[];for(let i=0;i<p.count;i++){
  const bounds=[p.minimumValues[i],p.defaultValues[i],p.maximumValues[i]];
  if(!bounds.every(Number.isFinite)||bounds[0]>bounds[1]||bounds[1]>bounds[2])throw Error('Invalid parameter range '+p.ids[i]);
  reset();p.values[i]=bounds[0];raw.update();const low=snapshot(),lowOpacity=Array.from(d.opacities);
  reset();p.values[i]=bounds[2];raw.update();const high=snapshot(),highOpacity=Array.from(d.opacities);
  if(!high.flat().every(Number.isFinite)||!low.flat().every(Number.isFinite))throw Error('Nonfinite Core vertices '+p.ids[i]);
  const geometry=diff(low,high),opacity=lowOpacity.filter((x,j)=>Math.abs(x-highOpacity[j])>1e-7).length;
  info.push({id:p.ids[i],min:bounds[0],default:bounds[1],max:bounds[2],geometry,opacityChanges:opacity});
 }
 for(const id of required){const entry=info.find(x=>x.id===id);if(!entry)throw Error('Required ORIGINAL rig parameter missing: '+id);if(!entry.geometry.coordinates&&!entry.opacityChanges)throw Error('Parameter exists but has no Core deformation: '+id);}
 const drawables=[];for(let i=0;i<d.count;i++){
  if(d.textureIndices[i]<0||d.textureIndices[i]>=refs.Textures.length)throw Error('Invalid texture index');
  if(Array.from(d.indices[i]).some(x=>x>=d.vertexCounts[i]))throw Error('Invalid triangle vertex index');
  if(Array.from(d.masks[i]).some(x=>x>=d.count))throw Error('Invalid mask drawable index');
  drawables.push({id:d.ids[i],vertexCount:d.vertexCounts[i],indexCount:d.indexCounts[i],texture:d.textureIndices[i],maskCount:d.maskCounts[i]});
 }
 const result={coreVersion:C.Version.csmGetVersion(),latestMocVersion:latest,header,consistency,parameters:info,drawables,partCount:raw.parts.count,noop};
 raw.release();moc._release();return result;
}"""

RENDER_CHECK = r"""async modelURL => {
 const {PIXI,Live2DModel}=CompanionLive2DRuntime;PIXI.Assets.setPreferences({preferWorkers:false,preferCreateImageBitmap:false});
 const app=new PIXI.Application();await app.init({width:900,height:900,backgroundAlpha:0,preference:'webgl',autoStart:false,sharedTicker:false,preserveDrawingBuffer:true});
 app.ticker.stop();document.querySelector('#stage').append(app.canvas);
 const model=await Live2DModel.from(modelURL,{autoUpdate:false,autoFocus:false,autoHitTest:false,motionPreload:'NONE',checkMocConsistency:true});
 model.setEyeBlinkEnabled(false);model.setBreathEnabled(false);model.stopLipSync();
 const internal=model.internalModel;internal.motionManager.stopAllMotions();internal.motionManager.state.shouldRequestIdleMotion=()=>false;
 const productTextureHook=typeof window.CompanionLive2D?.refreshActiveTextures==='function';if(productTextureHook){app.renderer.runners.prerender.add({prerender(){CompanionLive2D.refreshActiveTextures(app.renderer,model);}});}
 model.anchor.set(.5,.5);model.scale.set(Math.min(850/internal.width,850/internal.height));model.position.set(450,450);app.stage.addChild(model);window.__coreEvaluations=0;internal.on('beforeModelUpdate',()=>{window.__coreEvaluations++;});for(let i=0;i<3;i++){model.update(1000/60);app.renderer.render(app.stage);}
 window.__original={app,model,internal,core:internal.coreModel};window.__modelURL=modelURL;
 function pixels(){app.renderer.render(app.stage);const gl=app.renderer.gl,w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,b=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,b);let colored=0,transparent=0;for(let i=0;i<b.length;i+=4){if(b[i+3]>16&&(b[i]||b[i+1]||b[i+2]))colored++;if(b[i+3]===0)transparent++;}return {colored,transparent,error:gl.getError(),width:w,height:h};}
 window.__pixels=pixels;return {productTextureHook,pixels:pixels(),textureCount:model.textures.length,physicsAvailable:Boolean(internal.physics),expressions:internal.motionManager.expressionManager?.definitions?.map?.(x=>x.Name)||null};
}"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Original export model3.json, never vendor sample')
    parser.add_argument('--runtime-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--provenance', required=True, help='Original layered fixture/source provenance JSON')
    parser.add_argument('--source-psd', required=True, help='The actual layered source PSD, or PSD ancestor for a persisted authored project')
    parser.add_argument('--source-project', help='Persisted authored project actually consumed by an edited export')
    parser.add_argument('--require-parameter', action='append', default=[])
    parser.add_argument('--require-physics', action='store_true')
    parser.add_argument('--require-expression', action='store_true')
    parser.add_argument('--require-motion', action='store_true')
    parser.add_argument('--probe-pixels', action='store_true', help='Diagnostic only: skip sidecar tests; not full acceptance')
    parser.add_argument('--visual-rois', help='Optional export-specific framebuffer parameter ROIs JSON; never a universal anatomy rule')
    parser.add_argument('--product-adapter', help='Optional actual product adapter bundle for controlled lifetime regression')
    parser.add_argument('--parameter-midpoints', action='store_true', help='Also capture the actual midpoint pose for each required parameter')
    parser.add_argument('--joint-combinations', action='store_true', help='Also capture eight same-side shoulder/elbow corners and four opposite-side poses')
    parser.add_argument('--joint-interiors', action='store_true', help='Also capture fourteen off-integer single/combined joint poses')
    parser.add_argument('--reviewed-poses', help='Optional explicit original-model pose/alpha-row diagnostic JSON; not an art threshold')
    args = parser.parse_args()
    model = Path(args.model).resolve()
    runtime = Path(args.runtime_dir).resolve()
    provenance = Path(args.provenance).resolve()
    source_psd = Path(args.source_psd).resolve()
    source_project = Path(args.source_project).resolve() if args.source_project else None
    if source_psd.read_bytes()[:4] != b'8BPS':
        raise ValueError('Provide the actual layered source PSD')
    output = Path(args.output).resolve()
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    scripts = {name: installed_script(runtime, kind) for name, kind in [('core.js', 'core'), ('framework.js', 'bundle')]}
    if args.product_adapter:
        scripts['adapter.js'] = Path(args.product_adapter).resolve()
    family = {str(path): sha(path) for path in model.parent.rglob('*') if path.is_file() and not path.is_symlink()}
    roi_file = Path(args.visual_rois).resolve() if args.visual_rois else None
    visual_rois = json.loads(roi_file.read_text()) if roi_file else {}
    pose_file = Path(args.reviewed_poses).resolve() if args.reviewed_poses else None
    pose_spec = json.loads(pose_file.read_text()) if pose_file else {}
    if len(pose_spec.get('poses', [])) > 32 or len(pose_spec.get('alpha_probe_rows', [])) > 32:
        raise ValueError('Reviewed pose/row diagnostic exceeds finite probe budget')
    sources = {**family, **({str(pose_file): sha(pose_file)} if pose_file else {}), **({str(roi_file): sha(roi_file)} if roi_file else {}), **({str(source_project): sha(source_project)} if source_project else {}), str(source_psd): sha(source_psd), str(model): sha(model), str(provenance): sha(provenance), str(Path(__file__).resolve()): sha(Path(__file__).resolve()), str(Path(__file__).with_name('live2d_joint_poses.py')): sha(Path(__file__).with_name('live2d_joint_poses.py')), **{str(p): sha(p) for p in scripts.values()}}
    report = {'status': 'RUNNING', 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'scope': 'original export + real owner-installed official Core; direct raw geometry and actual software WebGL; no product adapter', 'sources': sources, 'provenance': json.loads(provenance.read_text()), 'checks': {}, 'not_proven': ['user artwork likeness/production art quality', 'Windows/4060/physical camera', 'official Editor CMO3 reopen/edit', 'SDK publication rights', 'all exports/parameters', 'Audio RMS/lip-sync through the product adapter', 'real-time frame rate or performance; sidecars use fixed 1/60s simulation']}
    report['acceptance_complete'] = not args.probe_pixels
    report['reproduce_command'] = 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    report['export_family_files'] = family
    report['model3_file'] = str(model)
    report['source_psd_file'] = str(source_psd)
    report['source_project_file'] = str(source_project) if source_project else None
    report['visual_rois'] = visual_rois
    errors = []
    warnings = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/':
                data = b'<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#eee}#stage{width:900px;height:900px}</style><div id="stage"></div><script src="/core.js"></script><script src="/framework.js"></script>'
                if 'adapter.js' in scripts:
                    data += b'<script src="/adapter.js"></script>'
                mime = 'text/html'
            elif path.lstrip('/') in scripts:
                p = scripts[path.lstrip('/')]
                data = p.read_bytes()
                if path == '/core.js':
                    # Same owner runtime execution path: Core's built-in asm implementation.
                    data = b'(function(){var WebAssembly={};\n' + data + b'\nwindow.Live2DCubismCore=Live2DCubismCore;})();'
                mime = 'application/javascript'
            elif path.startswith('/model/'):
                p = (model.parent / path[len('/model/'):]).resolve()
                if not p.is_relative_to(model.parent) or not p.is_file() or p.is_symlink():
                    self.send_error(404)
                    return
                data = p.read_bytes()
                mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--autoplay-policy=no-user-gesture-required'])
            context = browser.new_context(viewport={'width': 1100, 'height': 950}, record_video_dir=str(evidence / 'video'))
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: warnings.append({'type': message.type, 'text': message.text}) if message.type in {'error','warning'} else None)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('()=>window.Live2DCubismCore&&window.CompanionLive2DRuntime')
            model_url = f'http://127.0.0.1:{server.server_port}/model/{model.name}'
            try:
                report['raw_core'] = page.evaluate(RAW_CHECK, {'modelURL': model_url, 'required': args.require_parameter})
                assert len(report['raw_core']['drawables']) >= 3, 'Original multilayer fixture requires independently drawable geometry'
                assert any(p['geometry']['coordinates'] for p in report['raw_core']['parameters']), 'Static image MOC is not a rig'
                report['checks']['official_consistency_and_parameter_geometry'] = 'passed'
                report['render'] = page.evaluate(RENDER_CHECK, model_url)
                assert report['render']['pixels']['colored'] > 100 and report['render']['pixels']['error'] == 0
                report['checks']['actual_webgl_original_export'] = 'passed'
                page.screenshot(path=str(evidence / 'original-neutral.png'))
                refs = json.loads(model.read_text())['FileReferences']
                report['sidecars'] = {}
                for name, required in [('Physics', args.require_physics), ('Expressions', args.require_expression), ('Motions', args.require_motion)]:
                    if required and not refs.get(name):
                        raise AssertionError(f'Required ORIGINAL {name} sidecar absent')
                if not args.probe_pixels:
                    if refs.get('Physics'):
                        result = page.evaluate('''async()=>{const {core,internal}=__original,raw=core.getModel(),p=raw.parameters;const physics=internal.physics;if(!physics||typeof physics.evaluate!=='function')throw Error('Real framework physics not loaded');const snap=()=>({params:Array.from(p.values),vertices:Array.from(raw.drawables.vertexPositions,v=>Array.from(v))});p.values.set(p.defaultValues);for(let i=0;i<120;i++){physics.evaluate(core,1/60);raw.update();}const baseline=snap();const input=p.ids.indexOf('ParamAngleX');if(input<0)throw Error('Controlled physics impulse ParamAngleX unavailable');const trace=[];for(let t=0;t<120;t++){p.values[input]=t<30?p.maximumValues[input]:p.defaultValues[input];physics.evaluate(core,1/60);raw.update();trace.push(snap());}return {baseline,trace,input:p.ids[input],ids:Array.from(p.ids)};}''')
                        ids = result['ids']
                        varying = [ids[i] for i in range(len(ids)) if i != ids.index(result['input']) and any(abs(row['params'][i] - result['baseline']['params'][i]) > 1e-6 for row in result['trace'])]
                        assert varying, 'Physics JSON loaded but controlled impulse changes no downstream Core parameters'
                        assert any(row['vertices'] != result['baseline']['vertices'] for row in result['trace']), 'Physics changes no actual Core geometry'
                        report['sidecars']['physics'] = {'downstream_parameters': varying, 'frames': len(result['trace'])}
                        report['checks']['real_framework_physics_to_core_geometry'] = 'passed'
                    sidecar_run = page.evaluate(r"""async refs=>{
     const {model,core,internal,app}=__original,raw=core.getModel(),parameters=raw.parameters;
     internal.physics=undefined;model.setEyeBlinkEnabled(false);model.setBreathEnabled(false);model.stopLipSync();
     internal.motionManager.stopAllMotions();internal.motionManager.state.shouldRequestIdleMotion=()=>false;
     let observed;const capture=()=>{observed=Array.from(parameters.values);};internal.on('beforeModelUpdate',capture);
     const verts=()=>Array.from(raw.drawables.vertexPositions,v=>Array.from(v));
     function step(n){let frames=[];for(let i=0;i<n;i++){model.update(1000/60);app.renderer.render(app.stage);frames.push({parameters:observed,vertices:verts()});}return frames;}
     function reset(){internal.motionManager.stopAllMotions();internal.motionManager.expressionManager?.resetExpression();step(90);parameters.values.set(parameters.defaultValues);core.saveParameters();step(2);return {parameters:observed,vertices:verts()};}
     const baseline=reset(),negative=step(60);
     const noOperation={parameterChanges:negative.filter(f=>JSON.stringify(f.parameters)!==JSON.stringify(baseline.parameters)).length,geometryChanges:negative.filter(f=>JSON.stringify(f.vertices)!==JSON.stringify(baseline.vertices)).length,frames:60};
     const expressions=[];
     for(const item of refs.Expressions||[]){
      const before=reset();const definition=await(await fetch(new URL(item.File,window.__modelURL))).json();
      if(!await model.expression(item.Name))throw Error('Expression load failed '+item.Name);
      const frames=step(90),after=frames.at(-1),targetIds=definition.Parameters.map(p=>p.Id),targetChanges=targetIds.filter(id=>{let index=parameters.ids.indexOf(id);return index>=0&&frames.some(f=>Math.abs(f.parameters[index]-before.parameters[index])>1e-6);});
      const changedDrawables=Array.from(raw.drawables.ids).filter((_,j)=>frames.some(f=>JSON.stringify(f.vertices[j])!==JSON.stringify(before.vertices[j])));
      expressions.push({name:item.Name,targetIds,targetChanges,changedDrawables,before:before.parameters,after:after.parameters});
     }
     const motions=[];
     for(const [group,items]of Object.entries(refs.Motions||{}))for(let index=0;index<items.length;index++){
      const before=reset();if(!await model.motion(group,index,3))throw Error('Motion load failed '+group);
      const frames=step(90),changedIds=Array.from(parameters.ids).filter((_,j)=>frames.some(f=>Math.abs(f.parameters[j]-before.parameters[j])>1e-6));
      const changedDrawables=Array.from(raw.drawables.ids).filter((_,j)=>frames.some(f=>JSON.stringify(f.vertices[j])!==JSON.stringify(before.vertices[j])));
      motions.push({group,index,changedIds,changedDrawables});
     }
     internal.off('beforeModelUpdate',capture);return {noOperation,expressions,motions,method:'fixed 1/60s simulation with a real framework render/Core update on EVERY step; physics/automatic blink/breath/idle/lipSync disabled for isolation'};
    }""", refs)
                    report['sidecars']['isolation'] = sidecar_run
                    assert sidecar_run['noOperation']['parameterChanges'] == 0, 'No-operation control changes Core parameters'
                    assert sidecar_run['noOperation']['geometryChanges'] == 0, 'No-operation control changes Core geometry'
                    report['checks']['sidecar_no_operation_negative_control'] = 'passed'
                    if refs.get('Expressions'):
                        assert all(item['targetChanges'] and item['changedDrawables'] for item in sidecar_run['expressions']), 'An expression lacks isolated declared-parameter and geometry effects'
                        report['checks']['all_real_expressions_change_declared_core_parameters_and_geometry'] = 'passed'
                    if refs.get('Motions'):
                        assert all(item['changedIds'] and item['changedDrawables'] for item in sidecar_run['motions']), 'A motion lacks isolated Core parameter and geometry effects'
                        report['checks']['all_real_motions_change_core_parameters_and_geometry'] = 'passed'
                page.screenshot(path=str(evidence / 'original-sidecars.png'))
                page.evaluate(r"""()=>{const {model,core,internal}=__original;internal.physics=undefined;internal.motionManager.stopAllMotions();internal.motionManager.expressionManager?.resetExpression();model.setEyeBlinkEnabled(false);model.setBreathEnabled(false);model.stopLipSync();const raw=core.getModel();window.__sweep={index:-1,value:0};internal.on('beforeModelUpdate',()=>{raw.parameters.values.set(raw.parameters.defaultValues);if(__sweep.values){for(const [index,value]of __sweep.values)raw.parameters.values[index]=value;}else if(__sweep.index>=0)raw.parameters.values[__sweep.index]=__sweep.value;});window.__sweepPixels=(id,value,baseline,parameters)=>{const index=raw.parameters.ids.indexOf(id);if(index<0)throw Error('Missing pixel sweep parameter '+id);__sweep={index,value};if(parameters)__sweep.values=Object.entries(parameters).map(([name,v])=>{const i=raw.parameters.ids.indexOf(name);if(i<0||v<raw.parameters.minimumValues[i]||v>raw.parameters.maximumValues[i])throw Error('Invalid combined joint value '+name);return [i,v];});model.update(1000/60);__original.app.renderer.render(__original.app.stage);const gl=__original.app.renderer.gl,width=gl.drawingBufferWidth,height=gl.drawingBufferHeight,bytes=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);const geometry=Array.from(raw.drawables.vertexPositions,v=>Array.from(v)).flat(),health={glError:gl.getError(),contextLost:gl.isContextLost(),coreEvaluations:window.__coreEvaluations,nonfiniteCoordinates:geometry.filter(x=>!Number.isFinite(x)).length,minCoordinate:Math.min(...geometry),maxCoordinate:Math.max(...geometry),visibleDrawables:Array.from(raw.drawables.opacities).filter(x=>x>0).length,opaquePixels:0};for(let i=3;i<bytes.length;i+=4)if(bytes[i]>16)health.opaquePixels++;if(baseline){window.__pixelBaseline=bytes;return {width,height,health};}let changed=0,outsideROI=0,minX=width,minY=height,maxX=-1,maxY=-1;const roi=window.__pixelROIs?.[id];for(let i=0;i<bytes.length;i+=4){if(bytes[i]!==__pixelBaseline[i]||bytes[i+1]!==__pixelBaseline[i+1]||bytes[i+2]!==__pixelBaseline[i+2]||bytes[i+3]!==__pixelBaseline[i+3]){changed++;const x=(i/4)%width,y=Math.floor(i/4/width);if(roi&&(x<roi[0]||x>roi[2]||y<roi[1]||y>roi[3]))outsideROI++;minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y);}}const alphaProbeRows=(window.__reviewedAlphaRows||[]).map(r=>{if(![r.y,r.start_x,r.end_x].every(Number.isInteger)||r.y<0||r.y>=height||r.start_x<0||r.end_x<r.start_x||r.end_x>=width)throw Error('Invalid reviewed alpha row');const empty=[];let min=255,max=0;for(let x=r.start_x;x<=r.end_x;x++){const alpha=bytes[((height-1-r.y)*width+x)*4+3];min=Math.min(min,alpha);max=Math.max(max,alpha);if(alpha===0)empty.push(x);}return {...r,minAlpha:min,maxAlpha:max,exactZeroAlphaXs:empty,exactZeroAlphaCount:empty.length,coordinates:'actual framebuffer, top-left origin (GL readPixels Y flipped)'};});return {id,changedPixels:changed,outsideROIPixels:roi?outsideROI:null,declaredROI:roi||null,bounds:changed?[minX,minY,maxX,maxY]:null,width,height,health,alphaProbeRows};};}""")
                page.evaluate('rois=>window.__pixelROIs=rois', visual_rois.get('parameters', {}))
                page.evaluate('rows=>window.__reviewedAlphaRows=rows', pose_spec.get('alpha_probe_rows', []))
                report['visible_parameter_sweeps'] = []
                for parameter_id in args.require_parameter:
                    parameter = next(p for p in report['raw_core']['parameters'] if p['id'] == parameter_id)
                    minimum = page.evaluate('p=>__sweepPixels(p.id,p.value,true)', {'id': parameter_id, 'value': parameter['min']})
                    page.screenshot(path=str(evidence / f'{parameter_id}-min.png'))
                    midpoint = None
                    if args.parameter_midpoints:
                        midpoint = page.evaluate('p=>__sweepPixels(p.id,p.value,false)', {'id': parameter_id, 'value': (parameter['min'] + parameter['max']) / 2})
                        page.screenshot(path=str(evidence / f'{parameter_id}-mid.png'))
                    observed = page.evaluate('p=>__sweepPixels(p.id,p.value,false)', {'id': parameter_id, 'value': parameter['max']})
                    page.screenshot(path=str(evidence / f'{parameter_id}-max.png'))
                    observed['minimum'] = minimum
                    if midpoint is not None:
                        observed['midpoint'] = midpoint
                    report['visible_parameter_sweeps'].append(observed)
                    assert observed['health']['glError'] == 0 and not observed['health']['contextLost'], 'WebGL context/error during ' + parameter_id
                    assert not observed['health']['nonfiniteCoordinates'], 'Nonfinite Core geometry during ' + parameter_id
                    assert observed['health']['opaquePixels'] > 100, 'Stage lost all model pixels during ' + parameter_id
                invisible = [p['id'] for p in report['visible_parameter_sweeps'] if p['changedPixels'] == 0]
                assert not invisible, 'Required parameter only moves hidden geometry / no actual visible pixel effect: ' + ', '.join(invisible)
                report['checks']['required_parameters_have_actual_visible_pixel_effects'] = 'passed'
                outside = [p['id'] for p in report['visible_parameter_sweeps'] if p.get('outsideROIPixels')]
                assert not outside, 'Required parameter deforms pixels outside the explicitly reviewed anatomy ROI: ' + ', '.join(outside)
                if visual_rois:
                    report['checks']['export_specific_reviewed_anatomy_rois'] = 'passed'

                if args.joint_combinations or args.joint_interiors or pose_spec.get('poses'):
                    report['combined_joint_pose_screenshots'] = []
                    report['combined_joint_neutral_baseline'] = page.evaluate('()=>__sweepPixels("ParamArmL",0,true)')
                    poses = (joint_combinations(report['raw_core']['parameters']) if args.joint_combinations else []) + (joint_interiors(report['raw_core']['parameters']) if args.joint_interiors else []) + pose_spec.get('poses', [])
                    for pose in poses:
                        observed = page.evaluate('p=>__sweepPixels("ParamArmL",0,false,p.parameters)', pose)
                        image = evidence / (pose['name'] + '.png')
                        page.screenshot(path=str(image))
                        observed.update(pose=pose, screenshot=str(image))
                        report['combined_joint_pose_screenshots'].append(observed)
                        health = observed['health']
                        assert health['glError'] == 0 and not health['contextLost'] and not health['nonfiniteCoordinates'] and health['opaquePixels'] > 100, 'Combined joint rendering unhealthy: ' + pose['name']
                    report['checks']['combined_joint_poses_rendered_for_independent_art_review'] = 'passed'
                assert not errors, errors
                report['status'] = 'passed'
            except Exception:
                page.screenshot(path=str(evidence / 'failure.png'))
                raise
            finally:
                video = page.video
                context.close()
                video.save_as(str(evidence / 'original-core.webm'))
                browser.close()
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        report['javascript_errors'] = errors
        report['browser_warnings'] = warnings
        report['sources_unchanged_during_checks'] = all(Path(path).is_file() and sha(Path(path)) == digest for path, digest in sources.items())
        report['evidence_dir'] = str(evidence)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'checks': report['checks'], 'error': report.get('error'), 'output': str(output)}, ensure_ascii=False))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
