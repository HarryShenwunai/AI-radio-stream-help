"""Final ORIGINAL full rig: real local Qwen -> Kokoro -> Audio/Analyser/Core -> stop.

Never substitutes generate/synthesize, never downloads weights or SDK, and never
uses the prior PNG/VRM/geometry report as evidence for this model. Requires the
final, SHA-bound full hand/cup acceptance report before loading the real provider.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shlex
import sys
import tempfile
import threading
import time
import traceback
from urllib.parse import urlsplit
import wave
import zipfile
from playwright.sync_api import sync_playwright
from hand_cup_contract import validate as validate_rig_contract
from live2d_original_core_check import installed_script

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


AUDIO_OBSERVATION = r"""(()=>{
 window.__evidenceBlobs=new Map();window.__observedAnalysers=[];
 const make=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{const url=make(blob);__evidenceBlobs.set(url,blob);return url;};
 const Context=window.AudioContext||window.webkitAudioContext;
 if(Context){const create=Context.prototype.createAnalyser;Context.prototype.createAnalyser=function(...args){const node=Reflect.apply(create,this,args);__observedAnalysers.push(node);return node;};}
 window.__actualAudioRMS=()=>{let peak=0;for(const node of __observedAnalysers){const values=new Uint8Array(node.fftSize);node.getByteTimeDomainData(values);let sum=0;for(const x of values)sum+=((x-128)/128)**2;peak=Math.max(peak,Math.sqrt(sum/values.length));}return peak;};
})();"""

MOUTH_PROOF = r"""async options=>{
 const response=await fetch(options.mocURL,{credentials:'same-origin'});if(!response.ok)throw Error('Cannot read the actual imported MOC');
 const bytes=await response.arrayBuffer(),C=Live2DCubismCore,actualServedMocSha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');if(actualServedMocSha256!==options.expectedMocSha256)throw Error('Served MOC differs from the accepted original artifact');if(C.Moc.prototype.hasMocConsistency(bytes)!==1)throw Error('Actual official Core rejects final MOC');
 const moc=C.Moc.fromArrayBuffer(bytes),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables;
 const lips=options.lipSyncIds.map(id=>{const index=p.ids.indexOf(id);if(index<0)throw Error('LipSync group names an absent actual Core parameter');return {id,index,default:p.defaultValues[index],max:p.maximumValues[index]};});
 const snapshot=()=>Array.from(d.ids,(id,index)=>({id,opacity:d.opacities[index],vertices:Array.from(d.vertexPositions[index])}));
 const differs=(a,b)=>a.opacity!==b.opacity||a.vertices.some((x,i)=>x!==b.vertices[i]);
 p.values.set(p.defaultValues);raw.update();const rest=snapshot();for(const lip of lips)p.values[lip.index]=lip.max;raw.update();const open=snapshot();
 const causalIds=open.filter((value,i)=>differs(value,rest[i])).map(x=>x.id);if(!causalIds.length)throw Error('Final LipSync parameters have no real Core geometry/opacity effect');
 function evaluate(diagnostic){
  if(diagnostic.verticesTruncated||diagnostic.drawablesTruncated)throw Error('Exact Core diagnostics were truncated');
  const values=new Map(diagnostic.parameters.map(x=>[x.id,x.value]));
  for(let i=0;i<p.count;i++){const value=values.get(p.ids[i]);if(!Number.isFinite(value))throw Error('Missing final evaluated Core input '+p.ids[i]);p.values[i]=value;}
  raw.update();const expected=snapshot(),actual=new Map(diagnostic.drawables.map(x=>[x.id,x]));
  const actualMatches=causalIds.every(id=>{const a=actual.get(id),b=expected.find(x=>x.id===id);return a&&Array.isArray(a.vertices)&&a.opacity===b.opacity&&a.vertices.length===b.vertices.length&&a.vertices.every((x,i)=>x===b.vertices[i]);});
  for(const lip of lips)p.values[lip.index]=lip.default;raw.update();const muted=snapshot();
  const causalChanged=causalIds.filter(id=>differs(expected.find(x=>x.id===id),muted.find(x=>x.id===id)));
  return {coreEvaluations:diagnostic.coreEvaluations,lipSyncEnabled:diagnostic.lipSyncEnabled,lipParameters:lips.map(lip=>({id:lip.id,value:values.get(lip.id),default:lip.default})),actualMouthEqualsIndependentCoreAtAllActualInputs:actualMatches,changedByMouthOnlyCounterfactual:causalChanged,method:'Hold every actual head/body/breath/physics input fixed; set ONLY actual LipSync IDs to defaults in a separate official raw Core instance. Body/breath/physics inputs remain at their actual dynamic values; package idle/expression is paused for voice isolation.'};
 }
 window.__realLive2DMouth={evaluate,lipSyncIds:lips.map(x=>x.id),causalIds,dispose(){raw.release();moc._release();}};
 window.__realLiveTrace=[];window.__realLiveTraceTimer=setInterval(()=>{const audio=CompanionApp.speech.audio;if(__realLiveTrace.length>=1500)return;if(audio&&!audio.paused){const diagnostic=CompanionApp.scene.getDiagnostics();__realLiveTrace.push({at:performance.now(),time:audio.currentTime,duration:audio.duration,paused:audio.paused,rms:__actualAudioRMS(),mouth:CompanionApp.scene.getStats().mouth,lipSyncEnabled:diagnostic.lipSyncEnabled,lipParameters:diagnostic.parameters.filter(x=>__realLive2DMouth.lipSyncIds.includes(x.id)).map(x=>({id:x.id,value:x.value}))});}},25);
 return {actualServedMocSha256,coreVersion:C.Version.csmGetVersion(),officialConsistency:1,lipSyncIds:lips.map(x=>x.id),causalDrawables:causalIds,actualParameterCount:p.count,actualDrawableCount:d.count};
}"""


def zip_binding(path: Path, contract: dict) -> tuple[dict, list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive names')
        models = [name for name in names if name.endswith('.model3.json')]
        if len(models) != 1:
            raise ValueError('Require one final model3 file')
        if archive.getinfo(models[0]).file_size > 4 * 1024 * 1024:
            raise ValueError('model3 exceeds validation budget')
        data = archive.read(models[0])
        setting = json.loads(data)
        ref = PurePosixPath(setting['FileReferences']['Moc'])
        if ref.is_absolute() or '..' in ref.parts or '\\' in str(ref):
            raise ValueError('Unsafe MOC reference')
        moc_name = str(PurePosixPath(models[0]).parent / ref)
        if archive.getinfo(moc_name).file_size > 64 * 1024 * 1024:
            raise ValueError('MOC exceeds validation budget')
        moc = archive.read(moc_name)
        if hashlib.sha256(data).hexdigest() != contract['model_binding']['model3_sha256']:
            raise ValueError('Final ZIP model3 does not match the actual accepted rig')
        if hashlib.sha256(moc).hexdigest() != contract['model_binding']['moc3_sha256']:
            raise ValueError('Final ZIP MOC does not match the actual accepted rig')
    lips = [pid for group in setting.get('Groups', []) if group.get('Target') == 'Parameter' and group.get('Name') == 'LipSync' for pid in group.get('Ids', [])]
    if not lips or len(lips) > 8 or len(set(lips)) != len(lips):
        raise ValueError('Final model must declare bounded, distinct actual LipSync parameters')
    return setting, lips


def binding_paths(args) -> tuple[list[Path], dict, list[str]]:
    package, contract_file, landmarks_file, source, rig_report = [Path(getattr(args, key)).resolve() for key in ('model_zip', 'contract', 'landmarks', 'source_manifest', 'rig_acceptance_report')]
    contract, landmarks = json.loads(contract_file.read_text()), json.loads(landmarks_file.read_text())
    validate_rig_contract(contract, landmarks)
    for field, path in [('landmarks_sha256', landmarks_file), ('source_manifest_sha256', source)]:
        if contract['model_binding'][field] != sha(path):
            raise ValueError('Final rig source binding mismatch: ' + field)
    _, lips = zip_binding(package, contract)
    accepted = json.loads(rig_report.read_text())
    if accepted.get('status') != 'passed' or accepted.get('sources_unchanged') is not True:
        raise ValueError('Actual full hand/cup acceptance must PASS on a stable final source before true provider run')
    required_rig_checks = {'reviewed_contract_and_exact_final_export_binding', 'held_body_breath_extreme_combinations_keep_both_actual_grip_contacts', 'authored_hold_detach_wave_empty_hands_actions_real_core_and_gl', 'strong_actual_geometry_grip_unknown_id_negative_controls'}
    if not all(accepted.get('checks', {}).get(key) == 'passed' for key in required_rig_checks):
        raise ValueError('An intermediate candidate report cannot substitute for complete actual hand/cup acceptance')
    runtime = Path(args.runtime_dir).resolve()
    vendor = []
    for kind in ('core', 'bundle'):
        script = installed_script(runtime, kind)
        vendor += [runtime / (kind + '.json'), script.parent / 'record.json', script]
    required = {sha(contract_file), sha(landmarks_file), sha(source), *(contract['model_binding'][key] for key in ('model3_sha256','moc3_sha256','landmarks_sha256','source_manifest_sha256')), *(sha(path) for path in vendor)}
    if not required <= set(accepted.get('sources', {}).values()):
        raise ValueError('Rig PASS report is not bound to this final model/contract/source/new owner runtime')
    for name, digest in accepted.get('sources', {}).items():
        path = Path(name)
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Source changed since full rig acceptance: ' + name)
    manifest = json.loads(source.read_text())
    art = []
    for layer in manifest.get('layers', []):
        path = (source.parent / layer['file']).resolve()
        if not path.is_relative_to(source.parent) or path.is_symlink() or sha(path) != layer['sha256']:
            raise ValueError('Final original layer changed')
        art.append(path)
    product = [ROOT / 'app/server.py', *(ROOT / 'src/companion_runtime').rglob('*.py'), *(p for p in (ROOT / 'app/static').iterdir() if p.suffix in {'.js', '.html', '.css', '.png', '.jpg', '.webp', '.svg'})]
    helpers = [Path(__file__).resolve(), ROOT / 'tests/hand_cup_contract.py', ROOT / 'tests/live2d_original_core_check.py', ROOT / 'tests/live2d_joint_poses.py']
    return list(dict.fromkeys([package, contract_file, landmarks_file, source, rig_report, *art, *vendor, *product, *helpers])), contract, lips


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('model-zip', 'contract', 'landmarks', 'source-manifest', 'rig-acceptance-report'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--runtime-dir', default='/workspace/.live2d/owner-generated-runtime-check')
    parser.add_argument('--models', default='/workspace/companion/models')
    parser.add_argument('--voices', default='/workspace/companion/voices')
    parser.add_argument('--output', default=str(ROOT / 'review/real-live2d-companion-browser-check.json'))
    parser.add_argument('--evidence-dir')
    args = parser.parse_args()
    output_report = Path(args.output).resolve()
    if output_report.exists():
        raise SystemExit('Refusing to overwrite a prior real-provider report; select a new --output')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    evidence = Path(args.evidence_dir or str(ROOT.parent / 'dist' / ('evidence-real-live2d-' + stamp))).resolve()
    if evidence.exists() and any(evidence.iterdir()):
        raise SystemExit('Refusing to overwrite prior evidence; select a new --evidence-dir')
    evidence.mkdir(parents=True, exist_ok=True)
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'checks': {}, 'models_mocked': False, 'actual_provider_invoked': False, 'scope': 'Real private app HTTP + local CPU Qwen/Kokoro + FINAL original full Live2D + actual HTMLAudio/Analyser/official Core, stop and conservative next prompt', 'browser_external_requests': [], 'microphone_used': False, 'screen_video_has_audio_track': False, 'wav_saved_separately': True, 'windows_or_rtx4060_verified': False, 'human_voice_or_art_accepted': False, 'p95_measured': False, 'evidence_directory': str(evidence), 'reproduce_command': 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])}
    paths = []; app = server = worker = browser = context = page = video = data_holder = None; errors = []
    try:
        paths, contract, lips = binding_paths(args)
        report['source_sha256_before'] = {str(path): sha(path) for path in paths}
        report['checks']['final_full_rig_and_new_owner_runtime_source_binding'] = 'passed'
        os.environ['COMPANION_MODELS'] = str(Path(args.models).resolve())
        os.environ['COMPANION_VOICES'] = str(Path(args.voices).resolve())
        os.environ['COMPANION_LIVE2D_RUNTIME'] = str(Path(args.runtime_dir).resolve())
        data_holder = tempfile.TemporaryDirectory(prefix='real-original-live2d-')
        with contextlib.nullcontext(data_holder.name) as data:
            spec = importlib.util.spec_from_file_location('real_original_live2d_browser_app', ROOT / 'app/server.py')
            app = importlib.util.module_from_spec(spec); sys.modules[spec.name] = app; spec.loader.exec_module(app)
            app.DATA = Path(data); app.init()
            app.set_settings({'engine': 'local', 'memory_mode': 'off', 'voice': True, 'voice_backend': 'kokoro', 'conversation_mode': 'listen', 'local_compute': 'cpu', 'local_gpu_layers': 0, 'proactive': False, 'study': False})
            assets = [app.MODEL, app.VOICE_DIR / 'kokoro-v1.0.onnx', app.VOICE_DIR / 'voices-v1.0.bin']
            if not all(path.is_file() for path in assets):
                raise ValueError('Existing Linux model/voice assets are required; no download/fallback is authorized')
            report['actual_model_assets'] = [{'file': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in assets]
            server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); server.daemon_threads = True
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start(); base = 'http://127.0.0.1:' + str(server.server_port)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--autoplay-policy=no-user-gesture-required', '--mute-audio', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, record_video_dir=str(evidence / 'raw-video'), record_video_size={'width': 1440, 'height': 1000})
                context.add_init_script(AUDIO_OBSERVATION)
                def route(value):
                    if urlsplit(value.request.url).hostname not in {'127.0.0.1', 'localhost', None}:
                        report['browser_external_requests'].append(value.request.url); value.abort()
                    else:
                        value.continue_()
                context.route('**/*', route); page = context.new_page(); video = page.video
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base, wait_until='networkidle'); page.wait_for_function('()=>CompanionApp?.core.get().state?.active_character_id')
                role = page.evaluate('()=>CompanionApp.core.scope().character_id')
                response = page.request.post(base + '/api/characters/assets/import', headers={'X-Companion': 'local-app'}, data={'character_id': role, 'format': 'live2d', 'model': {'filename': Path(args.model_zip).name, 'data_base64': base64.b64encode(Path(args.model_zip).read_bytes()).decode()}}, timeout=60000)
                assert response.status == 200, (response.status, response.text()[:500])
                asset = response.json()['asset']; assert asset['format'] == 'live2d'
                assert not page.request.get(base + '/api/state').json()['active_character'].get('appearance_id')
                response = page.request.post(base + '/api/characters/assets/activate', headers={'X-Companion': 'local-app'}, data={'character_id': role, 'asset_id': asset['id']})
                assert response.status == 200, (response.status, response.text()[:500])
                page.evaluate('()=>CompanionApp.core.refresh(true)')
                page.wait_for_function('()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>=3', timeout=60000)
                assert page.locator('#character-canvas canvas.live2d-canvas').count() == 1
                initial = page.evaluate('()=>CompanionApp.scene.getDiagnostics({drawables:true,includeVertices:true})')
                assert not initial.get('verticesTruncated') and not initial.get('drawablesTruncated')
                assert contract['parameters']['cup_hold'] in {p['id'] for p in initial['parameters']}, 'This is not the final authored full rig'
                moc_resources = [value for name, value in asset['resources'].items() if name.endswith('.moc3')]
                assert len(moc_resources) == 1
                report['mouth_proof_model'] = page.evaluate(MOUTH_PROOF, {'mocURL': moc_resources[0]['url'], 'lipSyncIds': lips, 'expectedMocSha256': contract['model_binding']['moc3_sha256']})
                assert page.evaluate('()=>CompanionApp.core.get().state.settings.memory_mode') == 'off'
                # Prevent a package idle facial curve from masquerading as Audio mouth.
                # Natural breathing/blink/physics remain enabled; no parameter pins.
                page.evaluate('()=>CompanionApp.scene.applyControls({reset:true,idleMotion:false,expression:null})')
                marker = page.evaluate('()=>CompanionApp.scene.getDiagnostics().coreEvaluations')
                page.wait_for_function('n=>CompanionApp.scene.getDiagnostics().coreEvaluations>=n+3', arg=marker)
                controlled = page.evaluate('()=>CompanionApp.scene.getDiagnostics()')
                assert all(p['value'] == p['default'] for p in controlled['parameters'] if p['id'] in lips), 'Mouth was not neutral without Audio/idle expression'
                report['voice_control_conditions'] = {'idle_motion': False, 'expression': None, 'breath_and_blink': controlled['automatic'], 'physics': controlled['physics'], 'parameter_pins': False, 'authored_pose_reset_to_actual_defaults_before_observation': True, 'reason': 'Isolate Audio contribution while body/breath/hair remain dynamic; never require whole-model geometry exact0'}
                report['initial_scene'] = {'coreVersion': initial['coreVersion'], 'coreEvaluations': initial['coreEvaluations'], 'drawableCount': initial['drawableCount'], 'parameterCount': len(initial['parameters']), 'physics': initial['physics'], 'automatic': initial['automatic']}
                report['checks']['actual_final_zip_import_activation_and_official_core_ready'] = 'passed'
                page.screenshot(path=str(evidence / '01-final-original-rig-ready.png'))
                started = time.monotonic(); report['actual_provider_invoked'] = True; page.locator('#compose-text').fill('我今天有点累，请用二十五个字左右的一句话陪我放松，不要提问。'); page.locator('#send-message').click()
                page.wait_for_function("()=>Boolean(CompanionApp.core.get().chat?.text)||CompanionApp.core.get().failed||CompanionApp.core.get().state.messages.some(m=>m.role==='assistant'&&m.kind==='chat')", timeout=180000)
                report['first_text_or_error_seconds'] = round(time.monotonic() - started, 3); page.screenshot(path=str(evidence / '02-actual-qwen-stream.png'))
                page.wait_for_function('()=>!CompanionApp.core.get().chat', timeout=180000)
                failed = page.evaluate('()=>CompanionApp.core.get().failed'); assert not failed, failed
                reply = page.evaluate("()=>CompanionApp.core.get().state.messages.filter(m=>m.role==='assistant'&&m.kind==='chat').at(-1)")
                assert reply and reply['text']; report['actual_reply'] = reply['text']; report['reply_seconds'] = round(time.monotonic() - started, 3)
                report['checks']['actual_local_qwen_reply_with_memory_off'] = 'passed'
                page.wait_for_function("()=>{const a=CompanionApp.speech.audio,d=CompanionApp.scene.getDiagnostics();return a&&!a.paused&&a.currentTime>.03&&a.currentTime<a.duration&&__actualAudioRMS()>.001&&CompanionApp.scene.getStats().mouth>.005&&d.lipSyncEnabled&&d.parameters.some(p=>__realLive2DMouth.lipSyncIds.includes(p.id)&&p.value>p.default+.00001);}", timeout=180000)
                report['audio_rms_observed_seconds'] = round(time.monotonic() - started, 3)
                encoded = page.evaluate("""async()=>{const blob=__evidenceBlobs.get(CompanionApp.speech.audio.src);if(!blob)throw Error('Actual playing Kokoro Blob missing');const bytes=new Uint8Array(await blob.arrayBuffer());let text='';for(const x of bytes)text+=String.fromCharCode(x);return btoa(text);}""")
                wav_bytes = base64.b64decode(encoded, validate=True); (evidence / 'actual-kokoro-response.wav').write_bytes(wav_bytes)
                with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
                    report['actual_wav'] = {'sha256': hashlib.sha256(wav_bytes).hexdigest(), 'bytes': len(wav_bytes), 'seconds': wav.getnframes() / wav.getframerate(), 'rate': wav.getframerate(), 'channels': wav.getnchannels()}
                # Reading/saving the real WAV can cross a genuine speech pause. Take
                # RMS + actual Core snapshot + mouth-only counterfactual in ONE
                # browser callback; never mistake a later silent frame for failure.
                page.wait_for_function('''()=>{const a=CompanionApp.speech.audio,d=CompanionApp.scene.getDiagnostics({drawables:true,includeVertices:true}),rms=__actualAudioRMS();if(!a||a.paused||a.currentTime>=a.duration||rms<=.001||!d.lipSyncEnabled||!d.parameters.some(p=>__realLive2DMouth.lipSyncIds.includes(p.id)&&p.value>p.default+.00001))return false;const proof=__realLive2DMouth.evaluate(d);if(!proof.changedByMouthOnlyCounterfactual)return false;window.__actualCausalAudioFrame={proof,rms,position:a.currentTime,duration:a.duration};return true;}''', timeout=5000)
                frame = page.evaluate('()=>__actualCausalAudioFrame')
                proof = frame['proof']
                assert proof['actualMouthEqualsIndependentCoreAtAllActualInputs'], proof
                assert proof['changedByMouthOnlyCounterfactual'], proof
                report['actual_mouth_causal_proof'] = proof; report['observed_real_analyser_rms'] = frame['rms']; report['causal_audio_frame'] = {key: frame[key] for key in ('position', 'duration')}
                report['checks']['actual_kokoro_audio_analyser_and_causal_core_mouth_geometry'] = 'passed'
                page.screenshot(path=str(evidence / '03-actual-kokoro-live2d-mouth.png'))
                report['stop_request_state'] = page.evaluate('()=>{const a=CompanionApp.speech.audio;return {active:Boolean(a&&!a.paused&&a.currentTime<a.duration),position:a?.currentTime,duration:a?.duration,coreEvaluations:CompanionApp.scene.getDiagnostics().coreEvaluations};}')
                assert report['stop_request_state']['active'], 'Audio ended before stop; cannot claim actual interruption'
                stop_started = time.monotonic(); page.locator('#stop-speaking').click()
                page.wait_for_function('before=>{const d=CompanionApp.scene.getDiagnostics();return !CompanionApp.speech.audio&&CompanionApp.scene.getStats().mouth===0&&!d.lipSyncEnabled&&d.coreEvaluations>=before+3&&d.parameters.filter(p=>__realLive2DMouth.lipSyncIds.includes(p.id)).every(p=>p.value===p.default);}', arg=report['stop_request_state']['coreEvaluations'], timeout=2000)
                report['observed_stop_seconds'] = round(time.monotonic() - stop_started, 3)
                page.wait_for_timeout(700); assert page.evaluate('()=>!CompanionApp.speech.audio&&!CompanionApp.scene.getDiagnostics().lipSyncEnabled')
                report['checks']['actual_bounded_stop_neutral_core_mouth_no_late_audio'] = 'passed'
                deadline = time.monotonic() + 3; receipt = None
                while time.monotonic() < deadline:
                    with app.db() as connection:
                        row = connection.execute('SELECT receipt FROM playback_context WHERE message_id=?', (reply['id'],)).fetchone(); memories = connection.execute('SELECT count(*) FROM memories').fetchone()[0]
                    receipt = json.loads(row['receipt']) if row else None
                    if receipt and receipt.get('status') == 'stopped': break
                    page.wait_for_timeout(50)
                assert receipt and receipt['status'] == 'stopped', receipt
                confirmed = receipt.get('confirmed_text', ''); assert reply['text'].startswith(confirmed) and len(confirmed) < len(reply['text'])
                prompt = app.build_prompt(app.settings()); assistants = [m['content'] for m in prompt if m['role'] == 'assistant']
                assert assistants == ([confirmed] if confirmed else []), 'Unheard assistant tail entered next prompt'
                assert memories == 0 and app.settings()['memory_mode'] == 'off'
                assert page.locator('#current-reply-text').inner_text() == reply['text']
                report['actual_receipt'] = {key: receipt.get(key) for key in ('status', 'position_seconds', 'duration_seconds', 'confirmed_text', 'evidence', 'reason')}; report['next_prompt_assistant_entries'] = assistants
                report['checks']['unheard_tail_excluded_real_sqlite_receipt_ui_text_preserved'] = 'passed'
                report['media_trace'] = page.evaluate('()=>{clearInterval(__realLiveTraceTimer);return __realLiveTrace;}')
                assert any(t['rms'] > .001 for t in report['media_trace'])
                assert not errors and not report['browser_external_requests'], (errors, report['browser_external_requests'])
                report['checks']['no_page_exception_or_external_browser_request'] = 'passed'
                report['compute_runtime'] = dict(app.COMPUTE_STATUS); page.screenshot(path=str(evidence / '04-actual-stopped-context-safe.png')); page.evaluate('()=>__realLive2DMouth.dispose()')
                context.close(); context = None; video.save_as(str(evidence / 'actual-qwen-kokoro-original-live2d-stop.webm')); browser.close(); browser = None
            report['max_rss_kib_linux_process'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed' if report['actual_provider_invoked'] else 'blocked_before_provider_run', error=str(error), traceback=traceback.format_exc())
        if page:
            try: page.screenshot(path=str(evidence / 'FAILED.png'))
            except Exception: pass
    finally:
        if context:
            try:
                context.close()
                if video: video.save_as(str(evidence / 'partial-failure.webm'))
            except Exception: pass
        if browser:
            try: browser.close()
            except Exception: pass
        if app: app.STOP.set()
        if server: server.shutdown(); server.server_close()
        if worker: worker.join(5)
        if data_holder:
            try: data_holder.cleanup()
            except Exception as error: report['temporary_data_cleanup_error'] = str(error)
        report['page_errors'] = errors; report['source_sha256_after'] = {str(path): sha(path) for path in paths if path.is_file()}
        report['source_changed_during_run'] = report.get('source_sha256_before', {}) != report['source_sha256_after']
        if report['source_changed_during_run']: report['status'] = 'source_changed_during_run_not_final_acceptance'
        report['evidence_files'] = {str(path): sha(path) for path in evidence.iterdir() if path.is_file()}
        output_report.parent.mkdir(parents=True, exist_ok=True); output_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'checks': report['checks'], 'error': report.get('error'), 'report': str(output_report)}, ensure_ascii=False))
    if report['status'] != 'passed': raise SystemExit(1)


if __name__ == '__main__':
    main()
