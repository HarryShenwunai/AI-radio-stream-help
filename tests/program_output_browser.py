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
import posixpath
import socket
import sys
import urllib.parse
from pathlib import Path
import struct
import threading
import time
import wave
import zipfile

from playwright.sync_api import sync_playwright
import test_character_http as fixtures

QUESTION = '确认 主线应该是在直播现场随机应变的助手 继续修改 给出完整成品'


def validate_mouth_gate_options(args):
    if not args.require_visible_mouth:return
    if not args.completion:raise ValueError('--require-visible-mouth requires --completion; manual stop releases the scene and is a separate disposal observation')
    if args.expect_expiry or args.expect_budget_rejection or args.offline_preflight:
        raise ValueError('visible-mouth acceptance is a separate positive-program gate')


def validate_recorded_replay_options(args):
    if bool(args.replay_result) != bool(args.replay_wav):raise ValueError('recorded replay requires --replay-result and --replay-wav together')
    if not args.replay_result:return
    if args.real_model or args.real_tts or args.expect_expiry or args.expect_budget_rejection or args.offline_preflight:
        raise ValueError('recorded replay cannot combine real providers or negative/preflight modes')
    if not args.input or not args.completion or not args.require_visible_mouth:
        raise ValueError('recorded replay requires original --input, --completion and --require-visible-mouth')


def recorded_wav_seconds(data):
    if len(data)<12 or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE' or struct.unpack_from('<I',data,4)[0]+8!=len(data):
        raise ValueError('recorded WAV must be a complete RIFF/WAVE file')
    offset=12;data_chunks=0
    while offset<len(data):
        if offset+8>len(data):raise ValueError('recorded WAV has an incomplete chunk header')
        size=struct.unpack_from('<I',data,offset+4)[0];data_chunks+=data[offset:offset+4]==b'data';offset+=8+size+(size&1)
        if offset>len(data):raise ValueError('recorded WAV has an incomplete chunk or padding')
    if data_chunks!=1:raise ValueError('recorded WAV requires one complete audio data chunk')
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            frames=audio.getnframes();rate=audio.getframerate();expected=frames*audio.getnchannels()*audio.getsampwidth()
            if frames<=0 or rate<=0 or audio.getcomptype()!='NONE' or len(audio.readframes(frames))!=expected or audio.readframes(1):
                raise ValueError('recorded WAV has incomplete or unsupported PCM frames')
            return frames/rate
    except (wave.Error,EOFError) as error:raise ValueError('recorded WAV is invalid') from error


def load_recorded_replay(result_path,wav_path,current_input):
    raw=result_path.read_bytes();source=json.loads(raw);audio=wav_path.read_bytes()
    if source.get('passed') is not False or source.get('real_model') is not True or source.get('real_tts') is not True or source.get('acceptance_kind')!='positive_program':
        raise ValueError('recorded replay requires a failed single real-model/real-TTS positive-program source')
    outputs=source.get('model_outputs',[]);tts=source.get('tts_outputs',[]);prompts=source.get('model_inputs',[])
    if len(outputs)!=1 or len(tts)!=1 or len(prompts)!=1 or not isinstance(prompts[0],list) or not prompts[0]:
        raise ValueError('recorded replay requires exactly one model output, TTS output and complete prompt')
    reply=outputs[0].get('text')
    if not isinstance(reply,str) or not reply.strip() or reply!=tts[0].get('text') or outputs[0].get('finish_reason')!='stop':
        raise ValueError('recorded model/TTS text pair must match and be complete')
    digest=hashlib.sha256(audio).hexdigest()
    if digest!=tts[0].get('sha256'):raise ValueError('recorded WAV SHA does not match the original TTS output')
    original_input=source.get('raw_input',{})
    for field in ['text','source_text','source_sha256','delivered_text_sha256']:
        if not current_input.get(field) or current_input[field]!=original_input.get(field):raise ValueError('recorded question/input does not match current original --input')
    if hashlib.sha256(current_input['source_text'].encode('utf-8')).hexdigest()!=current_input['source_sha256'] or hashlib.sha256(current_input['text'].encode('utf-8')).hexdigest()!=current_input['delivered_text_sha256']:
        raise ValueError('recorded/current input provenance hash is invalid')
    for value in [outputs[0].get('warm_inference_seconds'),tts[0].get('seconds')]:
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:raise ValueError('recorded provider timing is missing/invalid')
    seconds=recorded_wav_seconds(audio)
    provenance={'source_result':str(result_path.resolve()),'source_result_sha256':hashlib.sha256(raw).hexdigest(),'source_wav':str(wav_path.resolve()),'source_wav_sha256':digest,
                'source_original_passed':source['passed'],'original_failure':source.get('failure'),'original_model_output':outputs[0],'original_tts_output':tts[0],
                'original_input':original_input,'original_prompt':prompts[0],'original_prompt_sha256':hashlib.sha256(json.dumps(prompts[0],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'wav_duration_seconds':seconds,'scope':'Recorded real-provider output replay; original real-time failure remains failed; no current model/TTS inference'}
    return {'reply':reply,'wav':audio,'messages':prompts[0],'provenance':provenance}


def validate_recorded_prompt(replay,messages):
    if messages!=replay['messages']:raise ValueError('current full prompt does not match the recorded original prompt')


def mouth_drawable_from_package(package):
    """Resolve the explicitly required R3 mouth by source metadata, never a fixed ID."""
    with zipfile.ZipFile(package) as archive:
        models = [name for name in archive.namelist() if name.endswith('.model3.json')]
        if len(models) != 1:raise ValueError('Visible-mouth gate requires one model3 manifest')
        model = json.loads(archive.read(models[0]))
        display = model.get('FileReferences', {}).get('DisplayInfo')
        if not isinstance(display, str) or not display:raise ValueError('Visible-mouth gate requires DisplayInfo metadata')
        entry = posixpath.normpath(posixpath.join(posixpath.dirname(models[0]), display))
        if entry.startswith(('/', '../')):raise ValueError('DisplayInfo must stay inside the model package')
        data = archive.read(entry);info = json.loads(data)
        rows = info.get('Drawables', [])
        matches = [row for row in rows if isinstance(row, dict) and row.get('Name') == 'Mouth_open']
        if len(matches) != 1 or not isinstance(matches[0].get('Id'), str) or not matches[0]['Id']:
            raise ValueError('Visible-mouth gate requires one unambiguous Mouth_open drawable')
        mesh_id = matches[0]['Id']
        if sum(isinstance(row, dict) and row.get('Id') == mesh_id for row in rows) != 1:
            raise ValueError('Mouth drawable ID is ambiguous')
        return {'name': 'Mouth_open', 'id': mesh_id, 'display_info': entry, 'display_info_sha256': hashlib.sha256(data).hexdigest()}


def mouth_drawable_observation(diagnostics, mesh_id, *, speaking):
    """Actual Core-opacity prerequisite only; not geometry or independent visual acceptance."""
    rows = diagnostics.get('drawables', [])
    if not isinstance(rows, list):rows=[]
    matches = [row for row in rows if isinstance(row, dict) and row.get('id') == mesh_id]
    opacity = matches[0].get('opacity') if len(matches) == 1 else None
    lip = diagnostics.get('lipSyncValue')
    finite = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    passed = diagnostics.get('available') is True and finite(opacity) and finite(lip) and ((opacity > 0 and lip > 0) if speaking else (opacity == 0 and lip == 0))
    return {'phase': 'speaking' if speaking else 'terminal', 'mesh_id': mesh_id, 'opacity': opacity, 'lip_sync_parameter': lip, 'passed': bool(passed),
            'scope': 'Actual Core drawable opacity prerequisite; screenshot/video still required for pixel/naturalness review'}


MOUTH_DRAWABLE_PHASE_JS = """({id,speaking})=>{
 const diagnostics=ProgramOutput.getDiagnostics({drawables:true});
 const rows=diagnostics.drawables?.filter(row=>row.id===id)||[];
 const mouth=rows.length===1?rows[0]:null;
 const finite=value=>typeof value==='number'&&Number.isFinite(value);
 const match=diagnostics.available===true&&mouth&&finite(mouth.opacity)&&finite(diagnostics.lipSyncValue)&&
   (speaking?(mouth.opacity>0&&diagnostics.lipSyncValue>0&&active?.audio&&!active.audio.paused&&active.audio.currentTime>0):(!active&&mouth.opacity===0&&diagnostics.lipSyncValue===0));
 if(match)window.mouthDrawableObservation={diagnostics,snapshot:ProgramOutput.snapshot(),currentTime:active?.audio?.currentTime??null};
 return Boolean(match)||Boolean(speaking&&!active);
}"""


def record_mouth_drawable(stage, out, report, mapping, *, speaking):
    phase = 'speaking' if speaking else 'terminal'
    stage.evaluate('()=>{window.mouthDrawableObservation=null}')
    try:
        stage.wait_for_function(MOUTH_DRAWABLE_PHASE_JS, arg={'id': mapping['id'], 'speaking': speaking})
    finally:
        observed = stage.evaluate('()=>window.mouthDrawableObservation||({diagnostics:ProgramOutput.getDiagnostics({drawables:true}),snapshot:ProgramOutput.snapshot(),currentTime:active?.audio?.currentTime??null})')
        result = mouth_drawable_observation(observed['diagnostics'], mapping['id'], speaking=speaking)
        report.setdefault('mouth_drawable_observations', {})[phase] = {**result, **observed}
        (out/f'mouth-drawable-{phase}.json').write_text(json.dumps(report['mouth_drawable_observations'][phase], ensure_ascii=False, indent=2))
        stage.screenshot(path=str(out/f'mouth-drawable-{phase}.png'))
        save_checkpoint(out, 'mouth_drawable_'+phase+'_observed', report)
    assert result['passed'], report['mouth_drawable_observations'][phase]
    if speaking:assert observed['snapshot']['active_id'] == report['playing']['snapshot']['active_id'], 'Mouth observation must belong to the same playing job'
    report['checks']['same_job_core_mouth_drawable_opacity_positive' if speaking else 'terminal_core_mouth_drawable_opacity_zero'] = True


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
    p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--real-model',type=Path);p.add_argument('--real-tts',type=Path);p.add_argument('--replay-result',type=Path,help='Replay one failed real-provider result; never a live inference success');p.add_argument('--replay-wav',type=Path,help='Exact original WAV paired with --replay-result');p.add_argument('--faults',action='store_true');p.add_argument('--completion',action='store_true');p.add_argument('--offline-preflight',action='store_true');p.add_argument('--loopback-fixture-transport',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--expect-budget-rejection',action='store_true');p.add_argument('--expect-expiry',action='store_true');p.add_argument('--require-visible-mouth',action='store_true',help='Require the packaged R3 Mouth_open Core drawable opacity during speech and zero after output; does not certify geometry/naturalness');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    validate_recorded_replay_options(a)
    validate_mouth_gate_options(a)
    mouth_mapping=mouth_drawable_from_package(a.model) if a.require_visible_mouth else None
    if a.expect_expiry and (a.real_model or a.real_tts or a.input or a.expect_budget_rejection or a.completion or a.faults or a.offline_preflight):raise ValueError('expiry is a separate fixed-input mechanical delayed-provider run')
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
    replay=load_recorded_replay(a.replay_result,a.replay_wav,input_evidence) if a.replay_result else None
    old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=fixtures.CharacterHTTPTests();f.setUp()
    if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
    else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
    files={'core':a.runtime_dir/'live2dcubismcore.min.js','bundle':a.runtime_dir/'build/owner-live2d-runtime.js'}
    class Runtime:
        def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js','artifacts':{kind:{'available':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for kind,path in files.items()}}
        def read_core(self):return files['core'].read_bytes()
        def read_bundle(self):return files['bundle'].read_bytes()
    f.app.live2d_runtime=lambda:Runtime()
    r={'scope':'Linux PC Chrome; existing original R3 candidate; real Core; runtime-reading fixture; not Windows/OBS/platform/viewer/independent acceptance','real_model':bool(a.real_model),'real_tts':bool(a.real_tts),'viewer_received':False,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':{},'errors':[],'raw_input':input_evidence,'acceptance_kind':'recorded_real_media_replay' if replay else 'negative_generation_expiry' if a.expect_expiry else 'negative_budget_rejection' if a.expect_budget_rejection else 'positive_program','model_package_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'runtime_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()},'phases':[]}
    if replay:
        r['recorded_replay']=replay['provenance'];r['source_original_passed']=replay['provenance']['source_original_passed']
        r['scope']+='; RECORDED real-media replay only, no current provider inference and no real-time provider acceptance'
    r['mouth_drawable_gate']={'required':a.require_visible_mouth,'mapping':mouth_mapping,'scope':'positive playback/terminal Core drawable-opacity gate; not geometry/naturalness acceptance' if a.require_visible_mouth else 'NOT_CHECKED: lipsync parameter observations do not establish a visible mouth'}
    r['tts_call_count']=0
    if a.expect_expiry:r['expiry_protocol']={'provider_delay_seconds':31,'event_ttl_seconds':30,'ui_observation_deadline_seconds':37,'adapter_timeout_seconds':35,'followup_polls':2,'followup_timeout_seconds':2,'scope':'synthetic delayed provider; no real inference, no audio-duration admission claim'}
    r['fixture_initial_character']=f.app.catalog().active()
    def save_progress(checkpoint):save_checkpoint(a.out,checkpoint,r)
    save_progress('prepared_before_model_load')
    boundary=OfflineBoundary(f.server.server_port, a.loopback_fixture_transport)
    netlog=a.out/'chrome-netlog.private.json'
    idle=threading.Event();idle.set();llm=None
    def fixture_model(settings,messages,**kw):
        r.setdefault('model_inputs',[]).append(messages)
        if replay:
            validate_recorded_prompt(replay,messages);r['checks']['replay_current_full_prompt_matches_source']=True
            r.setdefault('model_outputs',[]).append({'text':replay['reply'],'finish_reason':'stop','source':'recorded_real_media_replay','source_result_sha256':replay['provenance']['source_result_sha256']})
            save_progress('recorded_real_model_output_replayed');return replay['reply']
        if a.expect_expiry:
            idle.clear();started=time.monotonic();r['expiry_provider']={'started_monotonic':started}
            save_progress('mechanical_delayed_provider_started')
            try:time.sleep(31)  # Real clock, deliberately later than the unchanged 30s event.
            finally:
                r['expiry_provider'].update(returned_monotonic=time.monotonic(),seconds=time.monotonic()-started)
                idle.set();save_progress('mechanical_late_provider_returned')
            r['expiry_provider']['output_text_sha256']=hashlib.sha256(question.encode()).hexdigest()
        else:save_progress('mechanical_model_fixture_output')
        return question  # Explicit mechanical echo; never a quality/real-model claim.
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
    wav=replay['wav'] if replay else b'' if a.expect_expiry else tone(31 if a.expect_budget_rejection else 3)
    if not a.real_tts and not a.expect_expiry:r['fixture_audio_seconds']=replay['provenance']['wav_duration_seconds'] if replay else 31 if a.expect_budget_rejection else 3
    def synthesize(text):
        r['tts_call_count']+=1
        if a.expect_expiry:raise AssertionError('expired generation must never call TTS')
        if replay and text!=replay['reply']:raise ValueError('replayed TTS text differs from recorded model/TTS pair')
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
            def observe_program_request(request):
                if urllib.parse.urlsplit(request.url).path=='/api/live-output' and request.method=='POST':
                    r.setdefault('program_request_actions',[]).append(request.post_data_json.get('action'))
            def observe_reply_response(response):
                if a.expect_expiry and urllib.parse.urlsplit(response.url).path=='/api/connectors/bili/reply':
                    try:body=response.json()
                    except Exception as error:body={'unreadable':type(error).__name__}
                    r.setdefault('expiry_http_responses',[]).append({'status':response.status,'body':body})
            host.on('response',observe_reply_response)
            def open_stage(faults=None):
                path=f.post('connectors/bili/output/open',{})['path'];stage=sc.new_page();stage.on('request',observe_program_request);stage.on('pageerror',lambda e:r['errors'].append(str(e)))
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
            host.get_by_label('模拟观众消息',exact=True).fill(question);submitted=time.monotonic();host.get_by_role('button',name='加入演练',exact=True).click()
            if a.expect_expiry:
                host.evaluate('''()=>{window.expiryDOM={states:[],approvalAppeared:false};const panel=document.querySelector('[data-contact-page="bili"]');const inspect=node=>{if(node?.nodeType!==1)return;const buttons=node.matches('button')?[node]:Array.from(node.querySelectorAll('button'));if(buttons.some(b=>b.textContent.includes('播放这条回答')))expiryDOM.approvalAppeared=true;};const capture=()=>{const workspace=panel.querySelector('.live-workspace');if(!workspace)return;for(const node of workspace.querySelectorAll('.live-answer')){const row={id:node.dataset.jobId,state:node.dataset.state};const previous=expiryDOM.states.at(-1);if(!previous||previous.id!==row.id||previous.state!==row.state)expiryDOM.states.push(row);}inspect(panel);};window.expiryObserver=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)inspect(node);capture();});expiryObserver.observe(panel,{childList:true,subtree:true,attributes:true});capture();}''')
            started=time.monotonic();host.get_by_role('button',name='准备回答',exact=True).click()
            if a.expect_expiry:
                card=host.locator('.live-answer').filter(has=host.get_by_role('heading',name=question,exact=True));card.wait_for(timeout=7000)
                assert card.get_attribute('data-state')=='generating';job_id=card.get_attribute('data-job-id');assert job_id
                assert card.get_by_role('button',name='播放这条回答',exact=True).count()==0
                host.screenshot(path=str(a.out/'01-host-generating.png'),full_page=True)
                expired=host.locator('.live-answer[data-state="expired"]').filter(has=host.get_by_role('heading',name=question,exact=True))
                expired.wait_for(timeout=max(1,int((submitted+37-time.monotonic())*1000)))
                observed_at=time.monotonic();assert observed_at-submitted<=37
                assert expired.get_attribute('data-job-id')==job_id;assert expired.get_by_text('已过期',exact=True).is_visible()
                host.get_by_text('生成期间弹幕已过期，结果已丢弃。',exact=True).wait_for(timeout=max(1,int((submitted+37-time.monotonic())*1000)))
                responses=r.get('expiry_http_responses',[]);assert len(responses)==1 and responses[0]['status']==409 and responses[0]['body'].get('error')=='生成期间弹幕已过期，结果已丢弃。',responses
                polls=stage.evaluate('()=>programRequests.filter(row=>row.action==="poll").length')
                stage.wait_for_function('(before)=>programRequests.filter(row=>row.action==="poll").length>=before+2',arg=polls,timeout=2000)
                dom=host.evaluate('()=>expiryDOM');assert not dom['approvalAppeared'];assert dom['states'] and dom['states'][0]=={'id':job_id,'state':'generating'} and dom['states'][-1]=={'id':job_id,'state':'expired'},dom;assert all(row['state'] in {'generating','expired'} and row['id']==job_id for row in dom['states']),dom
                assert card.get_attribute('data-state')=='expired' and card.get_by_role('button',name='播放这条回答',exact=True).count()==0
                observed=stage.evaluate('()=>({playCalls:audioProbe.playCalls,peak:audioProbe.peak,caption:document.querySelector("#caption").textContent,lip:ProgramOutput.getDiagnostics().lipSyncValue,active:ProgramOutput.snapshot().active_id})')
                assert observed['playCalls']==0 and observed['peak']==0 and observed['caption']=='' and observed['lip']==0 and observed['active'] is None,observed
                assert r['tts_call_count']==0 and 'audio' not in r.get('program_request_actions',[]) and not r.get('tts_outputs')
                r['expiry_rejection']={'job_id_from_dom':job_id,'visible_expiry_seconds_from_submit':observed_at-submitted,'dom':dom,'http':responses,'program':observed,'tts_call_count':0,'audio_request_count':0,'positive_program_completed':False,'actual_wav_budget_validated':False}
                r['checks'].update(same_job_visible_expiry_and_actual_409=True,late_generation_has_no_approval_or_output=True)
                host.screenshot(path=str(a.out/'02-host-expired.png'),full_page=True);stage.screenshot(path=str(a.out/'03-stage-expired-no-output.png'));save_progress('negative_generation_expiry_observed')
            else:
                approve=host.get_by_role('button',name='播放这条回答',exact=True);approve.wait_for(timeout=35000);r['phases'].append({'phase':'generation_and_review_ready','seconds':time.monotonic()-started});assert stage.locator('#caption').inner_text()=='';assert stage.evaluate('()=>audioProbe.playCalls')==0;r['checks']['review_has_no_output']=True
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
                    stage.wait_for_function('()=>document.querySelector("#caption").textContent.length>0',timeout=30000);r['phases'].append({'phase':'approval_tts_to_media_started','seconds':time.monotonic()-started});stage.wait_for_function('()=>audioProbe.peak>.05 && ProgramOutput.getDiagnostics().lipSyncValue>.01');r['playing']=stage.evaluate('()=>({diagnostics:ProgramOutput.getDiagnostics({drawables:true}),stats:ProgramOutput.getStats(),snapshot:ProgramOutput.snapshot(),caption:document.querySelector("#caption").textContent,peak:audioProbe.peak,currentTime:active.audio.currentTime})');assert r['playing']['currentTime']>0;r['checks']['same_job_real_core_caption_audio_and_lipsync_parameter']=True;save_progress('actual_browser_media_started');assert stage.locator('#status').is_hidden();assert stage.locator('#status').evaluate('(n)=>getComputedStyle(n).display')=='none';r['checks']['playing_hides_owner_status']=True;stage.screenshot(path=str(a.out/'03-stage-playing.png'))
                    if a.require_visible_mouth:record_mouth_drawable(stage,a.out,r,mouth_mapping,speaking=True)
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
                        started=time.monotonic();host.get_by_role('button',name='停止播放',exact=True).click();stage.wait_for_function('()=>!active && document.querySelector("#caption").textContent==="" && (!ProgramOutput.getDiagnostics().available || ProgramOutput.getDiagnostics().lipSyncValue===0)');r['stop_seconds']=time.monotonic()-started;assert r['stop_seconds']<1.5;r['checks']['stop_clears_media_caption_lipsync_parameter']=True;r['manual_stop_scene']=stage.evaluate('()=>({model_available:ProgramOutput.getDiagnostics().available===true,character_canvas_count:document.querySelectorAll("#character-canvas canvas").length,scope:"scene disposal observation; not a zero-opacity mouth claim"})');assert stage.locator('#status').is_visible();stage.screenshot(path=str(a.out/'04-stage-stopped.png'))
            if a.require_visible_mouth and not a.expect_expiry and not a.expect_budget_rejection:record_mouth_drawable(stage,a.out,r,mouth_mapping,speaking=False)
            r['main_timeline']=list(service.output.audit);save_progress('main_media_terminal_observed')
            stage.evaluate('()=>audioProbe.records.forEach(row=>row.recorder.state!=="inactive"&&row.recorder.stop())');stage.wait_for_function('()=>audioProbe.records.every(row=>row.base64)');captures=stage.evaluate('()=>audioProbe.records.map(row=>row.base64)')
            for i,capture in enumerate(captures):(a.out/f'browser-audio-{i}.webm').write_bytes(base64.b64decode(capture))
            r['audio_scope']=('Negative run: no media play or WebAudio output expected; videos have no audio track' if a.expect_budget_rejection or a.expect_expiry else 'Actual browser WebAudio branch, not OS device/OBS/viewer; Playwright videos have no audio track');close_stage(stage)
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
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.locator('#enable').click();job=ready_event('expires-in-playback');page.wait_for_function('()=>active?.started');service.output.jobs[job['id']]['expires_at']=time.monotonic()+1;page.wait_for_function('()=>!active && document.querySelector("#caption").textContent===""');assert service.output.jobs[job['id']]['state']=='expired';assert page.evaluate('()=>ProgramOutput.getDiagnostics().lipSyncValue')==0;r['checks']['expiry_stops_audio_caption_lipsync_parameter']=True;f.post('connectors/bili/output/stop',{});close_stage(page)
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
