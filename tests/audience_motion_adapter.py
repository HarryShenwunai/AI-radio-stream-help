"""Actual complete adapter natural Idle boundary and SDK swallowed-error probe.

No inference/audio/capture device, only the existing original R3 and runtime.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.parse

from playwright.sync_api import sync_playwright
from companion_runtime.assets import AssetStore
from program_output_browser import OfflineBoundary, OFFLINE_CHROME_FLAGS
from audience_motion_comparison import namespace, sha

ROOT = Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--owner-local',type=Path,required=True)
    p.add_argument('--chrome',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);namespace(a.out)
    original=a.model.read_bytes();assert sha(original)=='ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d'
    store=AssetStore(a.out/'isolated-fixture-assets');asset=store.import_live2d(original,'existing-R3.zip')
    paths={};role='fixture-approved-original'
    for item in [asset['model'],*asset['resources'].values()]:
        item['url']='/api/assets/'+asset['id']+'/'+item['resource']+'?character_id='+role
        paths[urllib.parse.urlsplit(item['url']).path]=store.resolve(asset['id'],item['resource']).read_bytes()
    paths.update({'/adapter.html':(ROOT/'tests/audience_motion_adapter_probe.html').read_bytes(),'/fixture.json':json.dumps(asset).encode(),
                  '/adapter.js':(ROOT/'app/static/live2d-renderer.js').read_bytes(),'/owned/core.js':(a.owner_local/'live2dcubismcore.min.js').read_bytes(),
                  '/owned/runtime.js':(a.owner_local/'build/owner-live2d-runtime.js').read_bytes()})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass
        def do_GET(self):
            key=urllib.parse.urlsplit(self.path).path;data=paths.get(key)
            if data is None:self.send_error(404);return
            ctype='text/html' if key.endswith('.html') else 'application/javascript' if key.endswith('.js') else 'application/json' if key.endswith('.json') else 'image/png' if key.endswith('.png') else 'application/octet-stream'
            self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();boundary=OfflineBoundary(server.server_port,loopback_transport=True)
    r={'scope':'Actual production adapter with pinned original R3, natural Idle and real SDK callback failure; not Windows, live service or independent aesthetic acceptance','model_sha256':sha(original),'adapter_sha256':sha(paths['/adapter.js']),'viewer_policy':'setExpanded(false), existing collapsedFps30','checks':{},'console_errors':[]}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader',*OFFLINE_CHROME_FLAGS])
            context=browser.new_context(viewport={'width':720,'height':906});boundary.install(context);page=context.new_page();page.on('console',lambda msg:r['console_errors'].append(msg.text) if msg.type=='error' else None)
            base=f'http://127.0.0.1:{server.server_port}';page.goto(base+'/adapter.html');page.wait_for_function('()=>window.probeReady||window.probeFailure',timeout=60000);assert not page.evaluate('()=>window.probeFailure');assert page.evaluate('()=>adapterLoaded')
            begin=time.monotonic();page.wait_for_timeout(25500);samples=page.evaluate('()=>{probeStop=true;return adapterSamples;}');r['natural_wall_seconds']=time.monotonic()-begin;r['renderer_version']=page.evaluate('()=>rendererVersion');r['natural_errors']=page.evaluate('()=>adapterErrors');r['final']=page.evaluate('()=>({stats:adapter.getStats(),diagnostics:adapter.getDiagnostics()})');page.screenshot(path=str(a.out/'natural-last.png'));(a.out/'natural-samples.json').write_text(json.dumps(samples,ensure_ascii=False))
            owned=[s for s in samples if s['ownership']['authored']];unowned=[s for s in samples if not s['ownership']['authored']];r['natural_owned_samples']=len(owned);r['natural_unowned_times_ms']=[s['at'] for s in unowned]
            r['boundary_samples']=[s for s in samples if 11200<=s['at']<=13200 or 23200<=s['at']<=25200]
            r['checks']['natural_25s_real_adapter_no_errors']=r['natural_wall_seconds']>=25 and not r['natural_errors'] and not r['console_errors'] and r['final']['stats']['state']=='ready'
            r['checks']['authored_motion_seen_before_and_after_12s']=any(5000<s['at']<11000 for s in owned) and any(13000<s['at']<23000 for s in owned)
            r['checks']['no_unowned_insert_after_authored_start']=not [s for s in samples if s['at']>=owned[0]['at'] and not s['ownership']['authored']]
            r['checks']['cup_pose_constant']=all(s['parameters']['ParamCupLower']==0 and s['parameters']['ParamCupVisible']==1 for s in samples)
            r['cached_idle_cancel_probe']=page.evaluate('''async()=>{
                await adapter.applyControls({idleMotion:false});
                const manager=probeSdkModel.internalModel.motionManager,group=manager.groups.idle,cached=manager.motionGroups[group][0],originalLoad=manager.loadMotion;
                let release;manager.loadMotion=()=>new Promise(resolve=>release=resolve);
                const pending=manager.startRandomMotion(group,1),reservedBefore=manager.state.reservedIdleGroup;
                await adapter.applyControls({idleMotion:false});
                const reservedAfterCancel=manager.state.reservedIdleGroup??null;
                release(cached);const started=await pending;manager.loadMotion=originalLoad;
                return {reservedBefore,reservedAfterCancel,started,currentGroup:manager.state.currentGroup??null,queueLength:manager.queueManager._motions.length};
            }''')
            marker=page.evaluate('()=>adapter.getStats().frames');page.wait_for_function('n=>adapter.getStats().frames>n+1',arg=marker)
            r['cached_idle_cancel_probe']['ownership_after_frames']=page.evaluate('()=>adapter.getDiagnostics().ownership')
            r['checks']['cancelled_cached_idle_cannot_restart']=not r['cached_idle_cancel_probe']['started'] and r['cached_idle_cancel_probe']['queueLength']==0
            page.evaluate('()=>adapter.setHidden(true)');frames=page.evaluate('()=>adapter.getStats().frames');page.wait_for_timeout(400);r['checks']['hidden_no_new_frames']=page.evaluate('()=>adapter.getStats().frames')==frames;context.close()
            context=browser.new_context(viewport={'width':720,'height':906});boundary.install(context);page=context.new_page();fault_errors=[];page.on('console',lambda msg:fault_errors.append(msg.text) if msg.type=='error' else None);page.goto(base+'/adapter.html?fault=1');page.wait_for_function('()=>window.probeReady||window.probeFailure',timeout=60000);page.wait_for_function('()=>adapter.getStats().state==="error"',timeout=10000);r['fault']=page.evaluate('()=>({stats:adapter.getStats(),errors:adapterErrors})');frames=r['fault']['stats']['frames'];page.wait_for_timeout(400);r['checks']['real_sdk_bad_tail_reaches_error_and_stops']=bool(r['fault']['errors']) and page.evaluate('()=>adapter.getStats().frames')==frames;r['fault_console_errors']=fault_errors;page.screenshot(path=str(a.out/'fault-error.png'));context.close();browser.close()
        r['checks']['original_model_unchanged']=sha(a.model.read_bytes())==r['model_sha256'];r['checks']['fixture_network_boundary']=not boundary.blocked_page_requests and not boundary.blocked_python_connects;r['passed']=all(r['checks'].values())
    except Exception as error:
        r['failure']=str(error);raise
    finally:
        server.shutdown();server.server_close();worker.join(5);(a.out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':r.get('passed'),'checks':r['checks'],'natural_unowned_times_ms':r.get('natural_unowned_times_ms')},ensure_ascii=False))
    if not r['passed']:raise SystemExit(1)

if __name__=='__main__':main()
