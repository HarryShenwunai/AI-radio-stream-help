"""One approved local program with real existing R3/Core and explicit audio fixtures.

No platform connection, public transmission, Windows or independent UX claim.
Runtime reads below are a fixture over existing owner-local bytes, not a new
license acknowledgement or evidence of a production runtime installation.
"""
import argparse
import base64
import hashlib
import io
import json
import math
import os
import socket
import sys
import urllib.parse
from pathlib import Path
import struct
import threading
import time
import wave

from playwright.sync_api import sync_playwright
import test_character_http as fixtures

QUESTION = '确认 主线应该是在直播现场随机应变的助手 继续修改 给出完整成品'


def tone(seconds=3):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000)
        audio.writeframes(b''.join(struct.pack('<h', int(5000*math.sin(2*math.pi*440*i/24000))) for i in range(int(24000*seconds))))
    return out.getvalue()


PROBE = r"""(()=>{
 window.programFaults={};window.pendingProgramFetch=0;window.programRequests=[];window.programLoadErrors=[];let sceneApi;Object.defineProperty(window,'ProgramScene',{configurable:true,get:()=>sceneApi,set:api=>{sceneApi={...api,create(options){const scene=api.create(options),sync=scene.sync;scene.sync=async function(){try{return await sync.apply(scene,arguments);}catch(error){programLoadErrors.push({name:error.name,message:error.message});throw error;}};return scene;}};}});window.audioProbe={peak:0,chunks:[],records:[],playCalls:0};
 const nativeFetch=window.fetch;window.fetch=async function(url,options){pendingProgramFetch++;try{const requested=performance.now(),response=await nativeFetch.apply(this,arguments);let data;try{data=JSON.parse(options?.body||'{}')}catch{}const observed={action:data?.action,status:response.status,fetch_ms:performance.now()-requested};programRequests.push(observed);if(data?.action==='scene')response.clone().json().then(value=>{const s=value.scene_snapshot;observed.scene={sha256:s?.sha256,format:s?.asset?.format,appearance_id:s?.appearance_id,resource_count:Object.keys(s?.asset?.resources||{}).length};}).catch(error=>observed.error=error.message);if(['resource','runtime'].includes(data?.action))response.clone().arrayBuffer().then(async bytes=>{observed.bytes=bytes.byteLength;observed.sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');}).catch(error=>observed.error=error.message);let delay=0;if(data?.action==='audio')delay=window.programFaults.audioDelay||0;if(data?.action==='scene')delay=window.programFaults.sceneDelay||0;if(data?.action==='receipt'){if(data.state==='completed'&&window.programFaults.dropCompleted)throw new Error('Injected completed response loss');delay=window.programFaults[data.state+'Delay']||0;}if(delay)await new Promise(resolve=>setTimeout(resolve,delay));return response;}finally{pendingProgramFetch--;}};
 const nativePlay=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=async function(){audioProbe.playCalls++;if(programFaults.rejectPlay)throw new DOMException('Injected rejection','NotAllowedError');const result=await nativePlay.call(this);window.lastProgramAudio=this;if(programFaults.pauseDuringReceipt)setTimeout(()=>this.pause(),80);return result;};
 const resume=AudioContext.prototype.resume;AudioContext.prototype.resume=function(){if(programFaults.rejectResume)return Promise.reject(new Error('Injected context resume rejection'));return resume.apply(this,arguments);};
 const createSource=AudioContext.prototype.createMediaElementSource;AudioContext.prototype.createMediaElementSource=function(audio){if(programFaults.rejectSource)throw Error('Injected source failure');const source=createSource.call(this,audio),sink=this.createMediaStreamDestination();source.connect(sink);const recorder=new MediaRecorder(sink.stream);const row={recorder,chunks:[]};audioProbe.records.push(row);recorder.ondataavailable=e=>row.chunks.push(e.data);recorder.onstop=async()=>{const bytes=new Uint8Array(await new Blob(row.chunks).arrayBuffer());row.base64=btoa(String.fromCharCode(...bytes));};recorder.start();return source;};
 const createAnalyser=AudioContext.prototype.createAnalyser;AudioContext.prototype.createAnalyser=function(){const analyser=createAnalyser.call(this),read=analyser.getByteTimeDomainData.bind(analyser);analyser.getByteTimeDomainData=function(samples){read(samples);audioProbe.peak=Math.max(audioProbe.peak,...Array.from(samples,v=>Math.abs((v-128)/128)));};return analyser;};
})()"""



# Official flag descriptions: GoogleChrome/chrome-launcher/docs/chrome-flags-for-tools.md.
# Flags reduce background activity; interception and observed NetLog are recorded
# separately rather than treating a flag's presence as a whole-process proof.
# Preserve this installed Playwright driver's entire original disabled list.
# The acceptance environment records this list; do not replace it with one flag.
PLAYWRIGHT_DISABLED_FEATURES = [
    'AvoidUnnecessaryBeforeUnloadCheckSync', 'BoundaryEventDispatchTracksNodeRemoval',
    'DestroyProfileOnBrowserClose', 'DialMediaRouteProvider', 'GlobalMediaControls',
    'HttpsUpgrades', 'LensOverlay', 'MediaRouter', 'PaintHolding',
    'ThirdPartyStoragePartitioning', 'BlockOriginHeaderModificationOnRedirect',
    'Translate', 'AutoDeElevate', 'OptimizationHints', 'msForceBrowserSignIn',
    'msEdgeUpdateLaunchServicesPreferredVersion',
]
CHECKPOINT_LOCK = threading.Lock()


def save_checkpoint(out, checkpoint, observations):
    with CHECKPOINT_LOCK:
        value = {'kind':'incomplete-checkpoint', 'acceptance_report':False,
                 'checkpoint':checkpoint, 'monotonic_at':time.monotonic(),
                 'observations':{key:value for key,value in dict(observations).items() if key!='passed'}}
        temporary = out/'progress.tmp.json'
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        os.replace(temporary, out/'progress.json')


OFFLINE_CHROME_FLAGS = [
    '--disable-background-networking', '--disable-component-update',
    '--disable-domain-reliability', '--disable-sync', '--no-first-run',
    '--metrics-recording-only', '--no-pings', '--disable-quic',
    '--enable-features=EnableIPv6ReachabilityOverride',
    '--disable-features='+','.join([*PLAYWRIGHT_DISABLED_FEATURES, 'HappyEyeballsV3', 'HappyEyeballsV2']),
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
]


class OfflineBoundary:
    def __init__(self, port, loopback_transport=False):
        self.port = port
        self.loopback_transport = loopback_transport
        self.fulfilled_fixture_requests = 0
        self.bridge_failures = []
        self.transport_timings = []
        self.enabled = True
        self.probing = False
        self.allowed_page_requests = 0
        self.allowed_python_connects = 0
        self.blocked_page_requests = []
        self.blocked_python_connects = []
        sys.addaudithook(self._audit)

    def _audit(self, event, args):
        if not self.enabled or event not in {'socket.connect', 'socket.getaddrinfo'}:
            return
        if event == 'socket.connect':
            sock, address = args
            if sock.family == socket.AF_UNIX:
                return  # Playwright/asyncio local IPC; never an IP connection.
            host, port = address[:2]
        else:
            host, port = args[:2]
        if host == '127.0.0.1' and port == self.port:
            self.allowed_python_connects += 1
            return
        self.blocked_python_connects.append({'event':event, 'host':str(host)[:253],
                                             'port':port, 'expected_probe':self.probing})
        raise PermissionError('offline acceptance blocked non-fixture Python socket')

    def _allowed(self, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme == 'blob':
            parsed = urllib.parse.urlsplit(url[5:])
        return (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                and parsed.port == self.port and not parsed.username and not parsed.password)

    def install(self, context):
        def route(request):
            if self._allowed(request.request.url):
                self.allowed_page_requests += 1
                parsed = urllib.parse.urlsplit(request.request.url)
                if not self.loopback_transport or parsed.scheme == 'blob':
                    request.continue_()
                    return
                # No generic proxy: destination is the known fixture literal and
                # port, never a browser-provided hostname. Keep this request's
                # own auth/cookie/body; do not acquire the owner's credentials.
                started=time.monotonic();response=None
                try:
                    # Driver-owned response avoids copying large model bodies
                    # through Python/base64. No redirect or retry may broaden
                    # the already-validated exact fixture request.
                    response=request.fetch(url=request.request.url,
                        method=request.request.method,headers=request.request.all_headers(),
                        post_data=request.request.post_data_buffer,max_redirects=0,max_retries=0,timeout=35000)
                    fetched=time.monotonic()
                    if 300<=response.status<400 and response.headers.get('location'):
                        target=urllib.parse.urlsplit(urllib.parse.urljoin(request.request.url,response.headers['location']))
                        self.blocked_page_requests.append({'scheme':target.scheme,'host':target.hostname,
                            'port':target.port,'kind':'redirect_response','expected_probe':self.probing})
                        self.transport_timings.append({'path':parsed.path,'status':response.status,
                            'fetch_seconds':fetched-started,'blocked_redirect':True,'fulfill_seconds':0})
                        request.abort('blockedbyclient')
                        return  # This fixture adapter supports no redirect chains.
                    request.fulfill(response=response)
                    self.fulfilled_fixture_requests += 1
                    self.transport_timings.append({'path':parsed.path,'status':response.status,
                        'content_length':response.headers.get('content-length'),
                        'fetch_seconds':fetched-started,'fulfill_seconds':time.monotonic()-fetched})
                except Exception as error:
                    self.bridge_failures.append(type(error).__name__)
                    request.abort('failed')
                finally:
                    if response:response.dispose()
                return
            parsed = urllib.parse.urlsplit(request.request.url)
            self.blocked_page_requests.append({'scheme':parsed.scheme,
                'host':parsed.hostname, 'port':parsed.port, 'kind':request.request.resource_type,
                'expected_probe':self.probing})
            request.abort('blockedbyclient')
        context.route('**/*', route)
        # This application has no WebSocket dependency; block handshake/frames
        # explicitly because HTTP route interception is not a WebSocket firewall.
        def websocket(route):
            parsed = urllib.parse.urlsplit(route.url)
            self.blocked_page_requests.append({'scheme':parsed.scheme,
                'host':parsed.hostname, 'port':parsed.port, 'kind':'websocket',
                'expected_probe':self.probing})
            route.close(code=1008, reason='offline acceptance')
        context.route_web_socket('**/*', websocket)

    def summary(self, netlog_path):
        native = []
        transport_jobs = set()
        try:
            data = json.loads(netlog_path.read_text())
            types = {value:key for key,value in data.get('constants', {}).get('logEventTypes', {}).items()}
            for event in data.get('events', []):
                name = types.get(event.get('type'), '')
                if name in {'TCP_CONNECT_JOB_CONNECT','TRANSPORT_CONNECT_JOB_CONNECT'}:transport_jobs.add(name)
                if name not in {'TCP_CONNECT_ATTEMPT', 'UDP_CONNECT'}:
                    continue
                params = event.get('params', {})
                address = params.get('address') or params.get('remote_address')
                if address:
                    native.append({'event':name, 'address':address})
            unexpected = [row for row in native if row['address'] != '127.0.0.1:'+str(self.port)]
            error = None
        except (OSError, ValueError) as exc:
            unexpected = []
            error = type(exc).__name__
        return {'fixture_port':self.port, 'loopback_fixture_transport':self.loopback_transport,
                'native_browser_http_verified':not self.loopback_transport,
                'transport_backend':'playwright_route_fetch' if self.loopback_transport else 'native_browser',
                'fixture_transport_timings':self.transport_timings,
                'fulfilled_fixture_requests':self.fulfilled_fixture_requests,
                'bridge_failures':self.bridge_failures, 'allowed_page_requests':self.allowed_page_requests,
                'allowed_python_connects':self.allowed_python_connects,
                'blocked_browser_requests':self.blocked_page_requests,
                'blocked_python_requests':self.blocked_python_connects,
                'native_connect_events':native, 'transport_jobs':sorted(transport_jobs), 'unexpected_native_destinations':unexpected,
                'netlog_read_error':error,
                'limits':'Context routes cover page requests; Chromium flags and NetLog observe browser networking. Python audit covers Python socket calls, not native ONNX/C sockets or OS-wide packet traffic. Blob authorization remains the production manifest/hash check; browser routes may not see blob reads.'}


def offline_preflight(args):
    """No weights loaded and no TTS; exercise blocking before any real rerun."""
    out = args.out
    f = fixtures.CharacterHTTPTests();f.setUp()
    original_get=f.app.Handler._get
    def fixture_get(handler):
        if urllib.parse.urlsplit(handler.path).path=='/offline-fixture-redirect':
            return handler.reply(302,b'','text/plain',extra_headers={'Location':'http://blocked.invalid/'})
        return original_get(handler)
    f.app.Handler._get=fixture_get
    boundary = OfflineBoundary(f.server.server_port, args.loopback_fixture_transport)
    report = {'scope':'Offline harness preflight only; no model, TTS or live acceptance', 'checks':{},
              'requested_chrome_flags':OFFLINE_CHROME_FLAGS,
              'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    netlog = out/'chrome-netlog.private.json'
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=args.chrome,
                args=['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
                      *OFFLINE_CHROME_FLAGS, '--log-net-log='+str(netlog.resolve()), '--net-log-capture-mode=Default'])
            context = browser.new_context(service_workers='block');boundary.install(context)
            page = context.new_page();page.goto(f'http://127.0.0.1:{f.server.server_port}/')
            page.wait_for_function('()=>window.CompanionApp?.core.get().state')
            report['checks']['fixture_http_works']=True
            report['checks']['owner_set_cookie_preserved']=any(cookie['name']=='companion' for cookie in context.cookies())
            stage_context=browser.new_context(service_workers='block');boundary.install(stage_context)
            stage=stage_context.new_page();response=stage.goto(f'http://127.0.0.1:{f.server.server_port}/live-stage.html')
            stage.wait_for_function('()=>typeof ProgramOutput!=="undefined"')
            status=stage.evaluate('async()=>{const response=await fetch("/api/state",{credentials:"omit"});return response.status}')
            report['checks']['stage_without_owner_cookie_still_unauthorized']=status==401 and not stage_context.cookies()
            report['checks']['program_csp_nonce_preserved']="'nonce-" in response.headers['content-security-policy']
            stage_context.close()
            boundary.probing = True
            try:
                probe = context.new_page()
                try:probe.goto('http://blocked.invalid/', timeout=3000)
                except Exception:pass
                probe.close()
                report['checks']['page_external_navigation_blocked']=any(row['host']=='blocked.invalid' for row in boundary.blocked_page_requests)
                if args.loopback_fixture_transport:
                    before=len(boundary.blocked_page_requests);redirected=context.new_page()
                    try:redirected.goto(f'http://127.0.0.1:{f.server.server_port}/offline-fixture-redirect',timeout=3000)
                    except Exception:pass
                    redirected.close()
                    report['checks']['driver_does_not_follow_external_redirect']=(any(row['path']=='/offline-fixture-redirect' and row['status']==302 for row in boundary.transport_timings) and any(row['host']=='blocked.invalid' and row['kind']=='redirect_response' for row in boundary.blocked_page_requests[before:]))
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.connect(('192.0.2.1', 443))
                except PermissionError:
                    report['checks']['python_external_connect_blocked_before_system_call']=True
                else:
                    report['checks']['python_external_connect_blocked_before_system_call']=False
            finally:
                boundary.probing = False
            page.wait_for_timeout(1000)
            report['chrome'] = browser.version
            context.close();browser.close()
        report['network'] = boundary.summary(netlog)
        if args.loopback_fixture_transport:
            report['checks']['explicit_fixture_transport_without_native_http']=not report['network']['transport_jobs'] and not report['network']['native_connect_events'] and boundary.fulfilled_fixture_requests>0 and not boundary.bridge_failures
        else:
            report['checks']['legacy_transport_path_observed']=report['network']['transport_jobs']==['TRANSPORT_CONNECT_JOB_CONNECT']
        report['checks']['native_connects_only_fixture']=not report['network']['unexpected_native_destinations'] and not report['network']['netlog_read_error']
        report['checks']['no_unexpected_python_or_page_connects']=not any(not row['expected_probe'] for row in [*boundary.blocked_page_requests,*boundary.blocked_python_connects])
        save_checkpoint(out,'offline_preflight_observed',report)
        saved=json.loads((out/'progress.json').read_text())
        report['checks']['atomic_checkpoint_is_not_acceptance']=saved['acceptance_report'] is False and 'passed' not in saved['observations'] and not (out/'progress.tmp.json').exists()
        report['passed'] = all(report['checks'].values())
    finally:
        boundary.enabled = False;f.app.Handler._get=original_get;f.tearDown()
        (out/'offline-preflight.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False));assert report['passed']


def main():
    p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--real-model',type=Path);p.add_argument('--real-tts',type=Path);p.add_argument('--faults',action='store_true');p.add_argument('--completion',action='store_true');p.add_argument('--offline-preflight',action='store_true');p.add_argument('--loopback-fixture-transport',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--expect-budget-rejection',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if a.offline_preflight:
        if a.real_model or a.real_tts:raise ValueError('offline preflight never loads model or TTS')
        return offline_preflight(a)
    if a.expect_budget_rejection and (a.completion or a.faults):raise ValueError('budget rejection is a separate negative run, never positive completion')
    question=QUESTION
    input_evidence={'origin':'local_rehearsal','text':question,'source':'user conversation; functional replay, not held-out learning task', 'source_version':'original long input; unchanged'}
    if a.input:
        raw=a.input.read_bytes();source_text=raw.decode('utf-8');question=source_text.strip()
        if not 1<=len(question)<=300:raise ValueError('explicit input must contain 1–300 characters')
        digest=hashlib.sha256(raw).hexdigest()
        input_evidence.update(text=question,source_text=source_text,source='explicit local input file; synthetic development replay, not a real viewer or learning outcome',source_file=str(a.input.resolve()),source_sha256=digest,source_version='sha256:'+digest)
    input_evidence['delivered_text_sha256']=hashlib.sha256(question.encode('utf-8')).hexdigest()
    old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=fixtures.CharacterHTTPTests();f.setUp()
    if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
    else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
    files={'core':a.runtime_dir/'live2dcubismcore.min.js','bundle':a.runtime_dir/'build/owner-live2d-runtime.js'}
    class Runtime:
        def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js','artifacts':{kind:{'available':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for kind,path in files.items()}}
        def read_core(self):return files['core'].read_bytes()
        def read_bundle(self):return files['bundle'].read_bytes()
    f.app.live2d_runtime=lambda:Runtime()
    r={'scope':'Linux PC Chrome; existing original R3 candidate; real Core; runtime-reading fixture; not Windows/OBS/platform/viewer/independent acceptance','real_model':bool(a.real_model),'real_tts':bool(a.real_tts),'viewer_received':False,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':{},'errors':[],'raw_input':input_evidence,'acceptance_kind':'negative_budget_rejection' if a.expect_budget_rejection else 'positive_program','model_package_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'runtime_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()},'phases':[]}
    r['fixture_initial_character']=f.app.catalog().active()
    def save_progress(checkpoint):save_checkpoint(a.out,checkpoint,r)
    save_progress('prepared_before_model_load')
    boundary=OfflineBoundary(f.server.server_port, a.loopback_fixture_transport)
    netlog=a.out/'chrome-netlog.private.json'
    idle=threading.Event();idle.set();llm=None
    def fixture_model(settings,messages,**kw):
        r.setdefault('model_inputs',[]).append(messages)
        save_progress('mechanical_model_fixture_output')
        return question  # Explicit mechanical echo; no answer-quality claim.
    f.app.generate_once=fixture_model
    if a.real_model:
        from llama_cpp import Llama
        started=time.monotonic();llm=Llama(model_path=str(a.real_model),n_ctx=4096,n_threads=4,n_batch=256,verbose=False);r['model_cold_load_seconds']=time.monotonic()-started;save_progress('real_model_cold_load_completed')
        def actual_model(settings,messages,**kw):
            r.setdefault('model_inputs',[]).append(messages);started=time.monotonic();idle.clear()
            try:result=llm.create_chat_completion(messages=messages,max_tokens=kw.get('max_tokens',160),temperature=.65,top_p=.9,repeat_penalty=1.1,seed=42)
            finally:idle.set()
            choice=result['choices'][0];r.setdefault('model_outputs',[]).append({'text':choice['message']['content'],'finish_reason':choice['finish_reason'],'warm_inference_seconds':time.monotonic()-started,'usage':result.get('usage')})
            save_progress('real_model_output_recorded')
            if choice['finish_reason']!='stop':raise RuntimeError('Incomplete model response rejected')
            return choice['message']['content']
        f.app.generate_once=actual_model
    wav=tone(31 if a.expect_budget_rejection else 3)
    if not a.real_tts:r['fixture_audio_seconds']=31 if a.expect_budget_rejection else 3
    def synthesize(text):
        started=time.monotonic();audio=f.real_synthesize(text) if a.real_tts else wav;index=len(r.setdefault('tts_outputs',[]));(a.out/f'output-{index}.wav').write_bytes(audio);r['tts_outputs'].append({'text':text,'sha256':hashlib.sha256(audio).hexdigest(),'seconds':time.monotonic()-started});save_progress('tts_output_recorded');return audio
    if a.real_tts:f.app.VOICE_DIR=a.real_tts.resolve()
    f.app.synthesize=synthesize
    service=f.app.integrations();base=f'http://127.0.0.1:{f.server.server_port}'
    try:
        f.post('connectors/bili/rehearsal',{'action':'start','confirm_local':True})
        with sync_playwright() as pw:
            b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader',*OFFLINE_CHROME_FLAGS,'--log-net-log='+str(netlog.resolve()),'--net-log-capture-mode=Default']);hc=b.new_context(viewport={'width':1440,'height':1000},service_workers='block',record_video_dir=str(a.out/'host-video'));sc=b.new_context(viewport={'width':1280,'height':720},service_workers='block',record_video_dir=str(a.out/'stage-video'));boundary.install(hc);boundary.install(sc);r['requested_chrome_flags']=OFFLINE_CHROME_FLAGS;hc.tracing.start(screenshots=True,snapshots=True,sources=True);sc.tracing.start(screenshots=True,snapshots=True,sources=True)
            host=hc.new_page();host.on('pageerror',lambda e:r['errors'].append(str(e)));host.goto(base);host.wait_for_function('()=>window.CompanionApp?.core.get().state');assert any(c['name']=='companion' for c in hc.cookies());r['checks']['owner_set_cookie_preserved']=True
            host.locator('#open-companion-controls').click();host.get_by_role('button',name='微信与直播连接').click();host.get_by_role('button',name='本地互动演练',exact=True).click();host.get_by_label('模拟观众消息',exact=True).wait_for()
            def open_stage(faults=None):
                path=f.post('connectors/bili/output/open',{})['path'];stage=sc.new_page();stage.on('pageerror',lambda e:r['errors'].append(str(e)))
                stage.add_init_script(PROBE+'\nObject.assign(programFaults,'+json.dumps(faults or {})+');')
                stage.on('console',lambda message:r.setdefault('browser_console',[]).append({'type':message.type,'text':message.text}));stage.on('response',lambda response:r.setdefault('response_status',[]).append({'path':urllib.parse.urlsplit(response.url).path,'status':response.status}))
                opened=stage.goto(base+path);assert "'nonce-" in opened.headers['content-security-policy'];r['checks']['program_csp_nonce_preserved']=True
                return stage
            def close_stage(page):
                # Assertions/evidence precede this adapter-only teardown. A
                # debugger-paused poll must finish before target detachment.
                before=page.evaluate('()=>({busy,pending:pendingProgramFetch})')
                page.evaluate('()=>{enabled=false;epoch++;clear();program.dispose();}')
                page.wait_for_function('()=>!busy&&pendingProgramFetch===0',timeout=3000)
                r.setdefault('fixture_close_drains',[]).append({'before':before,'after':page.evaluate('()=>({busy,pending:pendingProgramFetch})')})
                page.close()
            r['fixture_scene_before_open']=f.app.program_scene_snapshot()[0];save_progress('host_rehearsal_ready_before_scene')
            assert (r['fixture_scene_before_open'].get('asset') or {}).get('format')=='live2d',r['fixture_scene_before_open']
            stage=open_stage();stage.wait_for_timeout(3000);r['startup_probe']=stage.evaluate('()=>({text:document.body.innerText,stats:ProgramOutput.getStats(),diag:ProgramOutput.getDiagnostics(),snapshot:ProgramOutput.snapshot(),core:Boolean(window.Live2DCubismCore),runtime:Boolean(window.CompanionLive2DRuntime),requests:window.programRequests,load_errors:window.programLoadErrors})');(a.out/'startup-probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r['startup_probe'],ensure_ascii=False),flush=True);stage.screenshot(path=str(a.out/'startup-probe.png'));stage.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true||document.querySelector("#status").textContent.includes("输出已停止")',timeout=60000);assert stage.evaluate('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true'),r['startup_probe'];r['resource_probe']=stage.evaluate('()=>programRequests');stage.get_by_role('button',name='启用本页音频').click();assert not sc.cookies();assert stage.request.get(base+'/api/state').status==401;r['checks']['real_core_without_private_cookie']=True
            host.get_by_label('模拟观众消息',exact=True).fill(question);host.get_by_role('button',name='加入演练',exact=True).click();started=time.monotonic();host.get_by_role('button',name='准备回答',exact=True).click();approve=host.get_by_role('button',name='播放这条回答',exact=True);approve.wait_for(timeout=35000);r['phases'].append({'phase':'generation_and_review_ready','seconds':time.monotonic()-started});assert stage.locator('#caption').inner_text()=='';assert stage.evaluate('()=>audioProbe.playCalls')==0;r['checks']['review_has_no_output']=True
            host.screenshot(path=str(a.out/'01-host-review.png'),full_page=True);stage.screenshot(path=str(a.out/'02-stage-ready.png'))
            host.on('dialog',lambda dialog:dialog.accept());started=time.monotonic();approve.click()
            if a.expect_budget_rejection:
                deadline=time.monotonic()+35
                while time.monotonic()<deadline and not any(j['state']=='failed' for j in service.output.jobs.values()):stage.wait_for_timeout(50)
                last=list(service.output.jobs.values())[-1]
                assert last['state']=='failed' and last.get('failure_reason')=='insufficient_playback_budget',service.output.owner_status()
                host.wait_for_function('(id)=>CompanionApp.core.get().state.live_output?.jobs.some(j=>j.id===id&&j.state==="failed"&&j.failure_reason==="insufficient_playback_budget")',arg=last['id'],timeout=10000)
                stage.wait_for_timeout(700)
                observed=stage.evaluate('()=>({playCalls:audioProbe.playCalls,peak:audioProbe.peak,caption:document.querySelector("#caption").textContent,lip:ProgramOutput.getDiagnostics().lipSyncValue,active:ProgramOutput.snapshot().active_id})')
                assert observed['playCalls']==0 and observed['peak']==0 and observed['caption']=='' and observed['lip']==0 and observed['active'] is None,observed
                assert host.get_by_text('剩余时限不足，未播放',exact=True).is_visible()
                states=[row['state'] for row in service.output.audit if row['id']==last['id']]
                assert not {'claimed','playing','completed'}.intersection(states)
                r['budget_rejection']={'observation':observed,'states':states,'job':service.output.public(last),'positive_program_completed':False}
                r['checks']['known_impossible_track_not_started']=True;r['checks']['host_sees_specific_budget_reason']=True
                save_progress('negative_budget_rejection_observed');stage.screenshot(path=str(a.out/'03-stage-budget-rejected.png'));host.screenshot(path=str(a.out/'04-host-budget-rejected.png'),full_page=True)
            else:
                stage.wait_for_function('()=>document.querySelector("#caption").textContent.length>0',timeout=30000);r['phases'].append({'phase':'approval_tts_to_media_started','seconds':time.monotonic()-started});stage.wait_for_function('()=>audioProbe.peak>.05 && ProgramOutput.getDiagnostics().lipSyncValue>.01');r['playing']=stage.evaluate('()=>({diagnostics:ProgramOutput.getDiagnostics(),stats:ProgramOutput.getStats(),snapshot:ProgramOutput.snapshot(),caption:document.querySelector("#caption").textContent,peak:audioProbe.peak,currentTime:active.audio.currentTime})');assert r['playing']['currentTime']>0;r['checks']['same_job_real_core_caption_audio_and_mouth']=True;save_progress('actual_browser_media_started');assert stage.locator('#status').is_hidden();assert stage.locator('#status').evaluate('(n)=>getComputedStyle(n).display')=='none';r['checks']['playing_hides_owner_status']=True;stage.screenshot(path=str(a.out/'03-stage-playing.png'))
                for width in [1024,1280]:
                    stage.set_viewport_size({'width':width,'height':720});bounds=stage.evaluate('()=>{const a=document.querySelector("#caption").getBoundingClientRect(),b=document.querySelector("#character-space").getBoundingClientRect();return {caption:{left:a.left,right:a.right,top:a.top,bottom:a.bottom},character:{left:b.left,right:b.right,top:b.top,bottom:b.bottom},overflow:document.documentElement.scrollWidth>innerWidth}}');assert bounds['caption']['right']<=bounds['character']['left'] and not bounds['overflow'];r.setdefault('pc_layout_bounds',[]).append({'width':width,**bounds});stage.screenshot(path=str(a.out/f'03-stage-playing-{width}.png'))
                r['checks']['caption_does_not_cover_character_at_pc_sizes']=True
                if a.completion:
                    stage.wait_for_function('()=>!active && document.querySelector("#status").textContent.includes("本页播放结束")',timeout=30000)
                    last=next(job for job in service.output.jobs.values() if job['id']==r['playing']['snapshot']['active_id']);assert last['state']=='completed'
                    assert stage.locator('#caption').inner_text()=='';assert stage.evaluate('()=>ProgramOutput.getDiagnostics().lipSyncValue')==0
                    host.wait_for_function('(id)=>CompanionApp.core.get().state.live_output?.jobs.some(j=>j.id===id&&j.state==="completed")',arg=last['id'],timeout=10000)
                    r['checks']['full_actual_media_ended_and_both_ends_completed']=True;stage.screenshot(path=str(a.out/'04-stage-completed.png'));host.screenshot(path=str(a.out/'05-host-completed.png'),full_page=True)
                else:
                    assert stage.evaluate('()=>Boolean(active?.audio&&!active.audio.paused)'),'stop must interrupt active media'
                    started=time.monotonic();host.get_by_role('button',name='停止播放',exact=True).click();stage.wait_for_function('()=>!active && document.querySelector("#caption").textContent==="" && (!ProgramOutput.getDiagnostics().available || ProgramOutput.getDiagnostics().lipSyncValue===0)');r['stop_seconds']=time.monotonic()-started;assert r['stop_seconds']<1.5;r['checks']['stop_clears_media_caption_mouth']=True;assert stage.locator('#status').is_visible();stage.screenshot(path=str(a.out/'04-stage-stopped.png'))
            r['main_timeline']=list(service.output.audit);save_progress('main_media_terminal_observed')
            stage.evaluate('()=>audioProbe.records.forEach(row=>row.recorder.state!=="inactive"&&row.recorder.stop())');stage.wait_for_function('()=>audioProbe.records.every(row=>row.base64)');captures=stage.evaluate('()=>audioProbe.records.map(row=>row.base64)')
            for i,capture in enumerate(captures):(a.out/f'browser-audio-{i}.webm').write_bytes(base64.b64decode(capture))
            r['audio_scope']=('Negative run: no media play or WebAudio output expected; videos have no audio track' if a.expect_budget_rejection else 'Actual browser WebAudio branch, not OS device/OBS/viewer; Playwright videos have no audio track');close_stage(stage)
            # Subsequent cases isolate lifecycle faults from the model/voice providers.
            if a.faults:
                f.post('connectors/bili/output/stop',{})
                f.app.generate_once=fixture_model;f.app.synthesize=lambda text:wav
                def ready_event(name):
                    event={'source':'local-rehearsal','room_id':'local','event_id':name,'text':question,'expires_at':time.monotonic()+30,'origin':'local_rehearsal'};job=service.output.begin(event);service.output.finish(job['id'],question,'fixture-'+name);f.post('connectors/bili/approve',{'id':job['id'],'confirm_output':True});return job
                for name,fault in [('reject-play',{'rejectPlay':True}),('reject-resume',{'rejectResume':True}),('reject-source',{'rejectSource':True}),('pause-in-receipt',{'playingDelay':700,'pauseDuringReceipt':True})]:
                    page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('(v)=>Object.assign(programFaults,v)',fault);page.locator('#enable').click();job=ready_event(name);page.wait_for_function('()=>document.querySelector("#enable").hidden===false && document.querySelector("#status").textContent.length>0');deadline=time.monotonic()+3
                    while service.output.jobs[job['id']]['state'] not in {'failed','cancelled','expired'} and time.monotonic()<deadline:page.wait_for_timeout(20)
                    assert service.output.jobs[job['id']]['state']=='failed',(name,service.output.status());assert page.locator('#caption').inner_text()=='';states=[entry['state'] for entry in service.output.audit if entry['id']==job['id']]
                    if name!='pause-in-receipt':assert 'playing' not in states,(name,states)
                    r['checks'][name]=True;r.setdefault('fault_audits',{})[name]=states;page.screenshot(path=str(a.out/(name+'.png')));f.post('connectors/bili/output/stop',{});close_stage(page)
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.audioDelay=1200');page.locator('#enable').click();job=ready_event('late-audio-after-stop');page.wait_for_function('()=>active!==null');f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>!active && !ProgramOutput.snapshot().enabled');page.wait_for_timeout(1400);assert page.evaluate('()=>audioProbe.playCalls')==0;assert page.locator('#caption').inner_text()=='';r['checks']['late_audio_after_stop_cannot_play']=True;close_stage(page)
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.locator('#enable').click();job=ready_event('expires-in-playback');page.wait_for_function('()=>active?.started');service.output.jobs[job['id']]['expires_at']=time.monotonic()+1;page.wait_for_function('()=>!active && document.querySelector("#caption").textContent===""');assert service.output.jobs[job['id']]['state']=='expired';assert page.evaluate('()=>ProgramOutput.getDiagnostics().lipSyncValue')==0;r['checks']['expiry_stops_audio_caption_mouth']=True;f.post('connectors/bili/output/stop',{});close_stage(page)
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.dropCompleted=true');page.locator('#enable').click();job=ready_event('completed-response-lost');page.wait_for_function('()=>document.querySelector("#status").textContent==="播放回执未确认"');page.wait_for_timeout(700);assert service.output.jobs[job['id']]['state']=='completed';assert page.locator('#status').inner_text()=='播放回执未确认';assert page.locator('#status').is_visible();assert page.locator('#caption').inner_text()=='';r['checks']['lost_completion_response_stays_unconfirmed']=True;page.screenshot(path=str(a.out/'completed-unconfirmed.png'));f.post('connectors/bili/output/stop',{});close_stage(page)
                page=open_stage({'sceneDelay':1400});page.locator('#enable').click();f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>document.querySelector("#status").textContent.includes("连接失效")');page.wait_for_timeout(1600);assert page.evaluate('()=>ProgramOutput.snapshot().scene_sha256') is None;assert not page.evaluate('()=>ProgramOutput.getDiagnostics().available');r['checks']['late_warm_scene_cannot_restore_character']=True;close_stage(page)
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.completedDelay=1500');page.locator('#enable').click();first=ready_event('late-completed-before-next')
                deadline=time.monotonic()+10
                while service.output.jobs[first['id']]['state']!='completed' and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert service.output.jobs[first['id']]['state']=='completed'
                second=ready_event('next-during-old-completed');page.wait_for_function('(id)=>active?.id===id && active.started',arg=second['id']);page.wait_for_timeout(1700);assert page.evaluate('()=>active?.id')==second['id'];assert '正在输出' in page.locator('#status').inner_text();r['checks']['late_completed_cannot_overwrite_next_job']=True
                f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>!active');close_stage(page)
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.completedDelay=1500');page.locator('#enable').click();first=ready_event('late-completed-after-stop')
                deadline=time.monotonic()+10
                while service.output.jobs[first['id']]['state']!='completed' and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert service.output.jobs[first['id']]['state']=='completed';f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>document.querySelector("#status").textContent.includes("连接失效")');page.wait_for_timeout(1700);assert '连接失效' in page.locator('#status').inner_text();r['checks']['late_completed_cannot_overwrite_stop']=True;close_stage(page)
            r['jobs']=service.output.owner_status();r['environment']={'chrome':b.version,'python':os.sys.version,'windows':False};r['checks']['no_platform_connection']=service.bili is None and service._thread is None;r['passed']=all(r['checks'].values()) and not r['errors'];hc.tracing.stop(path=str(a.out/'host-trace.zip'));sc.tracing.stop(path=str(a.out/'stage-trace.zip'));sc.close();hc.close();b.close()
    except Exception as error:
        r['failure']=str(error);r['jobs']=service.output.owner_status()
        try:
            r['stage_failure']=stage.evaluate('()=>({text:document.body.innerText,stats:ProgramOutput.getStats(),diag:ProgramOutput.getDiagnostics(),snapshot:ProgramOutput.snapshot()})');stage.screenshot(path=str(a.out/'failure.png'));sc.tracing.stop(path=str(a.out/'stage-failure-trace.zip'))
        except Exception:pass
        raise
    finally:
        idle.wait(120)
        if llm:llm.close()
        r['network']=boundary.summary(netlog);r['checks']['offline_boundary_observed']=not r['network']['unexpected_native_destinations'] and not r['network']['netlog_read_error'] and not boundary.blocked_page_requests and not boundary.blocked_python_connects and not boundary.bridge_failures
        r['passed']=bool(r.get('passed')) and r['checks']['offline_boundary_observed'];boundary.enabled=False
        f.tearDown();(a.out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':r.get('passed'),'checks':r['checks'],'out':str(a.out)},ensure_ascii=False));assert r['passed']


if __name__=='__main__':main()
