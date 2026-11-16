"""Same original R3/pinned SDK, old drivers vs production ownership helper.

Uncut 24-second videos and final/authored parameters; no inference, no audio,
no Windows, no claim of frontal art or visible mouth repair.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading
import time
import urllib.parse
import zipfile

from playwright.sync_api import sync_playwright
from program_output_browser import OfflineBoundary, OFFLINE_CHROME_FLAGS

ROOT = Path(__file__).resolve().parents[1]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def namespace(out):
    evidence = json.loads((out/'namespace.json').read_text())
    current = os.readlink('/proc/self/ns/net')
    assert evidence['inner_netns']==current and evidence['outer_netns']!=current
    assert evidence['interfaces']==['lo'] and evidence['close_fds'] is True
    interfaces = [line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line]
    routes = [line for line in Path('/proc/net/route').read_text().splitlines() if line.strip() and not line.startswith('Iface')]
    assert interfaces==['lo'] and not routes, (interfaces, routes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--owner-local', type=Path, required=True)
    p.add_argument('--chrome', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    namespace(a.out)
    model = a.model.read_bytes()
    assert sha(model) == 'ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d'
    with zipfile.ZipFile(io.BytesIO(model)) as z:
        resources = {'/runtime/'+name:z.read(name) for name in z.namelist()}
    resources.update({'/':(ROOT/'tests/audience_motion_probe.html').read_bytes(),
                      '/adapter.mjs':(ROOT/'frontend/live2d-renderer.mjs').read_bytes(),
                      '/owned/core.js':(a.owner_local/'live2dcubismcore.min.js').read_bytes(),
                      '/owned/runtime.js':(a.owner_local/'build/owner-live2d-runtime.js').read_bytes()})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            key = urllib.parse.urlsplit(self.path).path
            data = resources.get(key)
            if data is None:
                self.send_error(404)
                return
            content = 'text/html' if key=='/' else 'application/javascript' if key.endswith(('.js','.mjs')) else 'application/json' if key.endswith('.json') else 'image/png' if key.endswith('.png') else 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    boundary = OfflineBoundary(server.server_port, loopback_transport=True)
    report = {'scope':'Actual original R3 and pinned SDK, production ownership helper A/B; not full product output, Windows or independent visual acceptance',
              'model_sha256':sha(model), 'source_sha256':{key:sha(data) for key,data in resources.items() if key in ['/', '/adapter.mjs', '/owned/core.js', '/owned/runtime.js']},
              'checks':{}, 'runs':{}, 'errors':[], 'model_inference':False, 'video_has_audio':False}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=a.chrome, args=['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader', *OFFLINE_CHROME_FLAGS])
            for mode in ['original','repaired']:
                context = browser.new_context(viewport={'width':720,'height':906}, record_video_dir=str(a.out/mode), record_video_size={'width':720,'height':906})
                boundary.install(context)
                context.tracing.start(screenshots=True,snapshots=True,sources=True)
                page = context.new_page()
                page.on('pageerror', lambda error:report['errors'].append(str(error)))
                page.on('console', lambda msg:report['errors'].append(msg.text) if msg.type=='error' else None)
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.wait_for_function('()=>window.diagnosticReady||window.diagnosticError', timeout=60000)
                assert not page.evaluate('()=>window.diagnosticError')
                bounds = page.locator('canvas').bounding_box()
                assert bounds and bounds['x']==0 and bounds['y']==0 and bounds['width']==720 and bounds['height']==876, bounds
                start = time.monotonic()
                try:
                    samples = page.evaluate('(mode)=>diagnosticDriver(mode)', mode)
                except Exception:
                    partial = page.evaluate('()=>window.driverSamples||[]')
                    (a.out/(mode+'-partial.json')).write_text(json.dumps(partial,ensure_ascii=False))
                    context.tracing.stop(path=str(a.out/(mode+'-failed-trace.zip')))
                    context.close()
                    raise
                report['runs'][mode] = {'wall_seconds':time.monotonic()-start, 'frames':len(samples), 'nominal_seconds':samples[-1]['time'], 'canvas_bounds':bounds}
                (a.out/(mode+'-samples.json')).write_text(json.dumps(samples,ensure_ascii=False,separators=(',',':')))
                page.screenshot(path=str(a.out/(mode+'-last.png')))
                context.tracing.stop(path=str(a.out/(mode+'-trace.zip')))
                context.close()
                report['runs'][mode]['video_files'] = [str(path.relative_to(a.out)) for path in (a.out/mode).glob('*.webm')]
                report['runs'][mode]['samples'] = samples
            browser.close()
        channels = ['ParamEyeLOpen','ParamEyeROpen','ParamBreath','ParamAngleZ','ParamBodyAngleX']
        original_motion=json.loads(resources['/runtime/motions/R3_upper_body.motion3.json'])
        authored_ids={row['Id'] for row in original_motion['Curves'] if row['Target']=='Parameter'}
        owned_channels=[pid for pid in channels if pid in authored_ids]
        report['expected_authored_channels']=owned_channels
        report['cycle_protocol']='Explicit same-Idle stop/start at frame360; two authored12s trajectories. Production automatic loop scheduling is separate.'
        for mode,row in report['runs'].items():
            samples = row['samples']
            row['max_final_minus_authored'] = {pid:max(abs(s['parameters'][pid]-s['authored'][pid]) for s in samples) for pid in channels}
            if mode=='repaired':
                row['owned_sample_counts']={pid:sum(pid in (s['ownership'] or {}).get('authored',[]) for s in samples) for pid in owned_channels}
                row['max_owned_final_minus_authored']={pid:max((abs(s['parameters'][pid]-s['authored'][pid]) for s in samples if pid in (s['ownership'] or {}).get('authored',[])),default=None) for pid in owned_channels}
                row['ownership_profile_changes']=max(s['ownership']['profileChanges'] for s in samples)
            costs = sorted(s['costMs'] for s in samples)
            row['max_wall_minus_nominal_seconds']=max(s['wallTime']-s['time'] for s in samples)
            row['frame_cost_scope']='SDK draw plus measurement work; software renderer and recording, not isolated product overhead'
            row['frame_cost_ms'] = {'median':costs[len(costs)//2], 'p95':costs[int((len(costs)-1)*.95)], 'max':max(costs)}
        old,new = [report['runs'][name]['samples'] for name in ['original','repaired']]
        max_protected = 0.
        for before,after in zip(old,new,strict=True):
            assert before['frame']==after['frame']
            for x,y in zip(before['protected'], after['protected'],strict=True):
                assert x['id']==y['id']
                max_protected=max(max_protected,abs(x['opacity']-y['opacity']),max((abs(a-b) for a,b in zip(x['vertices'], y['vertices'],strict=True)),default=0.))
        report['max_old_new_protected_vertex_or_opacity_delta'] = max_protected
        report['checks']['old_driver_conflict_reproduced'] = max(report['runs']['original']['max_final_minus_authored'].values())>0.1
        report['checks']['repaired_owned_channels_match_authored'] = all(value is not None and value<1e-7 for value in report['runs']['repaired']['max_owned_final_minus_authored'].values())
        report['checks']['owned_channels_nonempty_full_cycle_witness'] = all(count>=720 for count in report['runs']['repaired']['owned_sample_counts'].values())
        report['checks']['two_complete_cycles_each'] = all(r['frames']==721 and r['nominal_seconds']==24 and r['wall_seconds']>=24 for r in report['runs'].values())
        report['checks']['hand_cup_samples_unchanged'] = max_protected==0
        report['max_unowned_fallback_old_new_delta']={pid:max(abs(x['parameters'][pid]-y['parameters'][pid]) for x,y in zip(old,new,strict=True)) for pid in channels if pid not in authored_ids}
        report['checks']['unowned_fallback_unchanged']=all(value==0 for value in report['max_unowned_fallback_old_new_delta'].values())
        report['checks']['no_browser_errors'] = not report['errors']
        report['checks']['no_fixture_network_escape'] = not boundary.blocked_page_requests and not boundary.blocked_python_connects
        report['checks']['original_asset_unchanged'] = sha(a.model.read_bytes())==report['model_sha256']
        report['network'] = {'blocked_page_requests':boundary.blocked_page_requests, 'blocked_python_connects':boundary.blocked_python_connects}
        report['passed'] = all(report['checks'].values())
    except Exception as error:
        report['failure']=str(error)
        raise
    finally:
        for row in report['runs'].values():
            row.pop('samples',None)
        server.shutdown()
        server.server_close()
        worker.join(5)
        (a.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
