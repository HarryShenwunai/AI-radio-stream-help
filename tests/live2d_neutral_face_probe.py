"""Actual neutral Core/GL evidence for original mouth revisions, no art edits."""
import argparse
import hashlib
import http.server
import json
import mimetypes
import shlex
import sys
import struct
import threading
import traceback
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright

from live2d_original_core_check import RENDER_CHECK, installed_script


parser = argparse.ArgumentParser(description=__doc__)
for name in ['model', 'source-project', 'runtime-dir', 'output', 'evidence-dir']:
    parser.add_argument('--' + name, required=True)
parser.add_argument('--eye-open', type=float, default=1.0, choices=[.65, .7, .75, .85, 1.0], help='Reviewed read-only eye parameter probe; no MOC modification')
args = parser.parse_args()
model = Path(args.model).resolve()
project = Path(args.source_project).resolve()
evidence = Path(args.evidence_dir).resolve()
evidence.mkdir(parents=True, exist_ok=True)
output = Path(args.output).resolve()
if output.exists():
    raise SystemExit('Refusing to overwrite previous evidence')
root = Path(__file__).resolve().parents[1]
scripts = {'core.js': installed_script(Path(args.runtime_dir), 'core'),
           'framework.js': installed_script(Path(args.runtime_dir), 'bundle'),
           'adapter.js': root / 'app/static/live2d-renderer.js'}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
paths = [p for p in model.parent.rglob('*') if p.is_file()]
paths += [project, Path(__file__).resolve(), Path(__file__).with_name('live2d_original_core_check.py'), Path(__file__).with_name('live2d_joint_poses.py'), *scripts.values()]
sources = {str(p): sha(p) for p in paths}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == '/':
            body = b'<!doctype html><style>body{margin:0;background:#eee}#stage{width:900px;height:900px}</style><div id="stage"></div><script src="/core.js"></script><script src="/framework.js"></script><script src="/adapter.js"></script>'
            mime = 'text/html'
        elif path.lstrip('/') in scripts:
            file = scripts[path.lstrip('/')]
            body = file.read_bytes()
            if path == '/core.js':
                body = b'(function(){var WebAssembly={};\n' + body + b'\nwindow.Live2DCubismCore=Live2DCubismCore;})();'
            mime = 'application/javascript'
        elif path.startswith('/model/'):
            file = (model.parent / path[len('/model/'):]).resolve()
            if not file.is_relative_to(model.parent) or not file.is_file():
                self.send_error(404)
                return
            body = file.read_bytes()
            mime = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
report = {'reproduce_command': 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]), 'status': 'running', 'sources': sources, 'scope': 'Actual default parameters plus explicit reviewed eye-open override pinned immediately before genuine Core update; real transparent WebGL and same fixed 900px camera. No source image edits or AI/audio.', 'artwork_accepted': False, 'checks': {}, 'page_errors': []}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1100, 'height': 950}, record_video_dir=str(evidence / 'raw-video'))
        page = context.new_page()
        report['actual_browser_version'] = browser.version
        report['actual_viewport'] = page.viewport_size
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        base = 'http://127.0.0.1:' + str(server.server_port)
        page.goto(base)
        page.evaluate(RENDER_CHECK, base + '/model/' + model.name)
        measurement = page.evaluate(r'''eyeOpen=>{
          const {model,app,internal,core}=__original,raw=core.getModel(),p=raw.parameters,d=raw.drawables,c=raw.canvasinfo;
          internal.physics=undefined;internal.motionManager.stopAllMotions();internal.motionManager.expressionManager?.resetExpression();
          model.stopLipSync();model.setBreathEnabled(false);model.setEyeBlinkEnabled(false);
          internal.on('beforeModelUpdate',()=>{p.values.set(p.defaultValues);for(const id of ['ParamEyeLOpen','ParamEyeROpen']){const i=p.ids.indexOf(id);if(i<0||eyeOpen<p.minimumValues[i]||eyeOpen>p.maximumValues[i])throw Error('Reviewed eye override outside actual range');p.values[i]=eyeOpen;}window.__actualFaceNeutral=Array.from(p.ids,(id,i)=>({id,value:p.values[i],default:p.defaultValues[i]}));});
          for(let n=0;n<4;n++){model.update(1000/60);app.renderer.render(app.stage);}
          const ids=['ArtMeshMouthClose','ArtMeshMouth','ArtMeshLayer2','ArtMeshLayer3'];
          const meshes=ids.map(id=>{const i=d.ids.indexOf(id);if(i<0)throw Error('Missing actual mouth mesh '+id);const v=d.vertexPositions[i],x=[],y=[],uv=Array.from(d.vertexUvs[i]);for(let j=0;j<v.length;j+=2){x.push(v[j]*c.PixelsPerUnit+c.CanvasOriginX);y.push(c.CanvasOriginY-v[j+1]*c.PixelsPerUnit);}return {id,sourceCanvasBBox:[Math.min(...x),Math.min(...y),Math.max(...x),Math.max(...y)],opacity:d.opacities[i],uvs:uv,textureIndex:d.textureIndices[i]};});
          const gl=app.renderer.gl,w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,b=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,b);let transparent=0,nontransparent=0;for(let i=3;i<b.length;i+=4){if(b[i]===0)transparent++;else nontransparent++;}
          return {actualParameters:__actualFaceNeutral,meshes,canvasInfo:{ppu:c.PixelsPerUnit,width:c.CanvasWidth,height:c.CanvasHeight},actualGL:{width:w,height:h,transparentPixels:transparent,nontransparentPixels:nontransparent,error:gl.getError()},coreEvaluations:__coreEvaluations};
        }''', args.eye_open)
        report['measurement'] = measurement
        report['explicit_parameter_overrides'] = {'ParamEyeLOpen': args.eye_open, 'ParamEyeROpen': args.eye_open}
        report['all_other_parameters_actual_defaults'] = True
        expected = {'ParamMouthOpenY': 0, 'ParamMouthForm': 0, 'ParamEyeLOpen': args.eye_open, 'ParamEyeROpen': args.eye_open}
        actual = {p['id']: p['value'] for p in measurement['actualParameters']}
        expected_float32 = {key: struct.unpack('f', struct.pack('f', value))[0] for key, value in expected.items()}
        report['expected_parameter_values_in_actual_float32_storage'] = expected_float32
        assert all(actual.get(k) == v for k, v in expected_float32.items()), actual
        assert measurement['actualGL']['error'] == 0 and measurement['actualGL']['nontransparentPixels'] > 100
        report['checks']['actual_neutral_parameters_and_real_gl'] = 'passed'
        setting = json.loads(model.read_text())
        closed = next(p for p in measurement['meshes'] if p['id'] == 'ArtMeshMouthClose')
        tex = model.parent / setting['FileReferences']['Textures'][closed['textureIndex']]
        with Image.open(tex) as image:
            uv = closed['uvs']
            us, vs = uv[::2], uv[1::2]
            # Actual SDK vertex shader flips V; sample the original atlas only.
            box = (int(min(us) * image.width), int((1-max(vs)) * image.height),
                   min(image.width, int(max(us) * image.width)+1), min(image.height, int((1-min(vs)) * image.height)+1))
            alpha = image.convert('RGBA').getchannel('A').crop(box)
            report['closed_mouth_actual_uv_atlas_alpha'] = {'file': str(tex), 'crop_bbox': box, 'alpha_extrema': alpha.getextrema(), 'alpha_nonzero_bbox_in_uv_crop': alpha.getbbox(), 'alpha_gt_16_texel_count': sum(alpha.histogram()[17:]), 'scope': 'Read-only actual UV atlas envelope, not deformed-screen alpha or user art acceptance'}
        for mesh in measurement['meshes']:
            mesh.pop('uvs')
        page.screenshot(path=str(evidence / 'neutral-full.png'))
        page.screenshot(path=str(evidence / 'neutral-face.png'), clip={'x': 398, 'y': 190, 'width': 185, 'height': 160})
        page.screenshot(path=str(evidence / 'neutral-mouth.png'), clip={'x': 455, 'y': 285, 'width': 100, 'height': 55})
        report['screenshots'] = [str(evidence / name) for name in ['neutral-full.png', 'neutral-face.png', 'neutral-mouth.png']]
        assert not report['page_errors'], report['page_errors']
        video = page.video
        context.close()
        video.save_as(str(evidence / 'actual-neutral-face.webm'))
        browser.close()
        report['status'] = 'actual_neutral_evidence_captured_not_art_acceptance'
except Exception as error:
    report.update(status='failed', error=str(error), traceback=traceback.format_exc())
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    report['sources_unchanged'] = all(sha(Path(p)) == digest for p, digest in sources.items())
    report['screen_video_has_audio_track'] = False
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'sources_unchanged': report['sources_unchanged'], 'error': report.get('error')}))
raise SystemExit(2 if report['status'] == 'failed' else 0)
