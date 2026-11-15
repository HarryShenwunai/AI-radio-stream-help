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
 window.programFaults={};window.audioProbe={peak:0,chunks:[],records:[],playCalls:0};
 const nativeFetch=window.fetch;window.fetch=async function(url,options){const response=await nativeFetch.apply(this,arguments);let data;try{data=JSON.parse(options?.body||'{}')}catch{}let delay=0;if(data?.action==='audio')delay=window.programFaults.audioDelay||0;if(data?.action==='scene')delay=window.programFaults.sceneDelay||0;if(data?.action==='receipt'){if(data.state==='completed'&&window.programFaults.dropCompleted)throw new Error('Injected completed response loss');delay=window.programFaults[data.state+'Delay']||0;}if(delay)await new Promise(resolve=>setTimeout(resolve,delay));return response;};
 const nativePlay=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=async function(){audioProbe.playCalls++;if(programFaults.rejectPlay)throw new DOMException('Injected rejection','NotAllowedError');const result=await nativePlay.call(this);window.lastProgramAudio=this;if(programFaults.pauseDuringReceipt)setTimeout(()=>this.pause(),80);return result;};
 const resume=AudioContext.prototype.resume;AudioContext.prototype.resume=function(){if(programFaults.rejectResume)return Promise.reject(new Error('Injected context resume rejection'));return resume.apply(this,arguments);};
 const createSource=AudioContext.prototype.createMediaElementSource;AudioContext.prototype.createMediaElementSource=function(audio){if(programFaults.rejectSource)throw Error('Injected source failure');const source=createSource.call(this,audio),sink=this.createMediaStreamDestination();source.connect(sink);const recorder=new MediaRecorder(sink.stream);const row={recorder,chunks:[]};audioProbe.records.push(row);recorder.ondataavailable=e=>row.chunks.push(e.data);recorder.onstop=async()=>{const bytes=new Uint8Array(await new Blob(row.chunks).arrayBuffer());row.base64=btoa(String.fromCharCode(...bytes));};recorder.start();return source;};
 const createAnalyser=AudioContext.prototype.createAnalyser;AudioContext.prototype.createAnalyser=function(){const analyser=createAnalyser.call(this),read=analyser.getByteTimeDomainData.bind(analyser);analyser.getByteTimeDomainData=function(samples){read(samples);audioProbe.peak=Math.max(audioProbe.peak,...Array.from(samples,v=>Math.abs((v-128)/128)));};return analyser;};
})()"""


def main():
    p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--real-model',type=Path);p.add_argument('--real-tts',type=Path);p.add_argument('--faults',action='store_true');p.add_argument('--completion',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    old=os.environ.get('COMPANION_DEFAULT_LIVE2D');os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=fixtures.CharacterHTTPTests();f.setUp()
    if old is None:os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
    else:os.environ['COMPANION_DEFAULT_LIVE2D']=old
    files={'core':a.runtime_dir/'live2dcubismcore.min.js','bundle':a.runtime_dir/'build/owner-live2d-runtime.js'}
    class Runtime:
        def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js','artifacts':{kind:{'available':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for kind,path in files.items()}}
        def read_core(self):return files['core'].read_bytes()
        def read_bundle(self):return files['bundle'].read_bytes()
    f.app.live2d_runtime=lambda:Runtime()
    r={'scope':'Linux PC Chrome; existing original R3 candidate; real Core; runtime-reading fixture; not Windows/OBS/platform/viewer/independent acceptance','real_model':bool(a.real_model),'real_tts':bool(a.real_tts),'viewer_received':False,'checks':{},'errors':[],'raw_input':{'origin':'local_rehearsal','text':QUESTION,'source':'user conversation; functional replay, not held-out learning task'},'model_package_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'runtime_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()},'phases':[]}
    idle=threading.Event();idle.set();llm=None
    def fixture_model(settings,messages,**kw):
        r.setdefault('model_inputs',[]).append(messages)
        return QUESTION  # Explicit mechanical echo; no answer-quality claim.
    f.app.generate_once=fixture_model
    if a.real_model:
        from llama_cpp import Llama
        started=time.monotonic();llm=Llama(model_path=str(a.real_model),n_ctx=4096,n_threads=4,n_batch=256,verbose=False);r['model_cold_load_seconds']=time.monotonic()-started
        def actual_model(settings,messages,**kw):
            r.setdefault('model_inputs',[]).append(messages);started=time.monotonic();idle.clear()
            try:result=llm.create_chat_completion(messages=messages,max_tokens=kw.get('max_tokens',160),temperature=.65,top_p=.9,repeat_penalty=1.1,seed=42)
            finally:idle.set()
            choice=result['choices'][0];r.setdefault('model_outputs',[]).append({'text':choice['message']['content'],'finish_reason':choice['finish_reason'],'warm_inference_seconds':time.monotonic()-started,'usage':result.get('usage')})
            if choice['finish_reason']!='stop':raise RuntimeError('Incomplete model response rejected')
            return choice['message']['content']
        f.app.generate_once=actual_model
    wav=tone()
    def synthesize(text):
        started=time.monotonic();audio=f.real_synthesize(text) if a.real_tts else wav;index=len(r.setdefault('tts_outputs',[]));(a.out/f'output-{index}.wav').write_bytes(audio);r['tts_outputs'].append({'text':text,'sha256':hashlib.sha256(audio).hexdigest(),'seconds':time.monotonic()-started});return audio
    if a.real_tts:f.app.VOICE_DIR=a.real_tts.resolve()
    f.app.synthesize=synthesize
    service=f.app.integrations();base=f'http://127.0.0.1:{f.server.server_port}'
    try:
        f.post('connectors/bili/rehearsal',{'action':'start','confirm_local':True})
        with sync_playwright() as pw:
            b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader']);hc=b.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(a.out/'host-video'));sc=b.new_context(viewport={'width':1280,'height':720},record_video_dir=str(a.out/'stage-video'));hc.tracing.start(screenshots=True,snapshots=True,sources=True);sc.tracing.start(screenshots=True,snapshots=True,sources=True)
            host=hc.new_page();host.on('pageerror',lambda e:r['errors'].append(str(e)));host.goto(base);host.wait_for_function('()=>window.CompanionApp?.core.get().state')
            host.locator('#open-companion-controls').click();host.get_by_role('button',name='微信与直播连接').click();host.get_by_role('button',name='本地互动演练',exact=True).click()
            def open_stage(faults=None):
                path=f.post('connectors/bili/output/open',{})['path'];stage=sc.new_page();stage.on('pageerror',lambda e:r['errors'].append(str(e)))
                stage.add_init_script(PROBE+'\nObject.assign(programFaults,'+json.dumps(faults or {})+');')
                stage.on('console',lambda message:r.setdefault('browser_console',[]).append({'type':message.type,'text':message.text}));stage.on('response',lambda response:r.setdefault('response_status',[]).append({'path':response.url.split('?')[0],'status':response.status}))
                stage.goto(base+path)
                return stage
            stage=open_stage();stage.wait_for_timeout(3000);r['startup_probe']=stage.evaluate('()=>({text:document.body.innerText,stats:ProgramOutput.getStats(),diag:ProgramOutput.getDiagnostics(),snapshot:ProgramOutput.snapshot(),core:Boolean(window.Live2DCubismCore),runtime:Boolean(window.CompanionLive2DRuntime)})');(a.out/'startup-probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r['startup_probe'],ensure_ascii=False),flush=True);stage.screenshot(path=str(a.out/'startup-probe.png'));stage.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);stage.get_by_role('button',name='启用本页音频').click();assert not sc.cookies();assert stage.request.get(base+'/api/state').status==401;r['checks']['real_core_without_private_cookie']=True
            host.get_by_label('模拟观众消息',exact=True).fill(QUESTION);host.get_by_role('button',name='加入演练',exact=True).click();started=time.monotonic();host.get_by_role('button',name='准备回答',exact=True).click();approve=host.get_by_role('button',name='播放这条回答',exact=True);approve.wait_for(timeout=35000);r['phases'].append({'phase':'generation_and_review_ready','seconds':time.monotonic()-started});assert stage.locator('#caption').inner_text()=='';assert stage.evaluate('()=>audioProbe.playCalls')==0;r['checks']['review_has_no_output']=True
            host.screenshot(path=str(a.out/'01-host-review.png'),full_page=True);stage.screenshot(path=str(a.out/'02-stage-ready.png'))
            host.on('dialog',lambda dialog:dialog.accept());started=time.monotonic();approve.click();stage.wait_for_function('()=>document.querySelector("#caption").textContent.length>0',timeout=30000);r['phases'].append({'phase':'approval_tts_to_media_started','seconds':time.monotonic()-started});stage.wait_for_function('()=>audioProbe.peak>.05 && ProgramOutput.getDiagnostics().lipSyncValue>.01');r['playing']=stage.evaluate('()=>({diagnostics:ProgramOutput.getDiagnostics(),stats:ProgramOutput.getStats(),snapshot:ProgramOutput.snapshot(),caption:document.querySelector("#caption").textContent,peak:audioProbe.peak,currentTime:active.audio.currentTime})');assert r['playing']['currentTime']>0;r['checks']['same_job_real_core_caption_audio_and_mouth']=True;assert stage.locator('#status').is_hidden();assert stage.locator('#status').evaluate('(n)=>getComputedStyle(n).display')=='none';r['checks']['playing_hides_owner_status']=True;stage.screenshot(path=str(a.out/'03-stage-playing.png'))
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
            stage.evaluate('()=>audioProbe.records.forEach(row=>row.recorder.state!=="inactive"&&row.recorder.stop())');stage.wait_for_function('()=>audioProbe.records.every(row=>row.base64)');captures=stage.evaluate('()=>audioProbe.records.map(row=>row.base64)')
            for i,capture in enumerate(captures):(a.out/f'browser-audio-{i}.webm').write_bytes(base64.b64decode(capture))
            r['audio_scope']='Actual browser WebAudio branch, not OS device/OBS/viewer; Playwright videos have no audio track';stage.close()
            # Subsequent cases isolate lifecycle faults from the model/voice providers.
            if a.faults:
                f.post('connectors/bili/output/stop',{})
                f.app.generate_once=fixture_model;f.app.synthesize=lambda text:wav
                def ready_event(name):
                    event={'source':'local-rehearsal','room_id':'local','event_id':name,'text':QUESTION,'expires_at':time.monotonic()+30,'origin':'local_rehearsal'};job=service.output.begin(event);service.output.finish(job['id'],QUESTION,'fixture-'+name);f.post('connectors/bili/approve',{'id':job['id'],'confirm_output':True});return job
                for name,fault in [('reject-play',{'rejectPlay':True}),('reject-resume',{'rejectResume':True}),('reject-source',{'rejectSource':True}),('pause-in-receipt',{'playingDelay':700,'pauseDuringReceipt':True})]:
                    page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('(v)=>Object.assign(programFaults,v)',fault);page.locator('#enable').click();job=ready_event(name);page.wait_for_function('()=>document.querySelector("#enable").hidden===false && document.querySelector("#status").textContent.length>0');deadline=time.monotonic()+3
                    while service.output.jobs[job['id']]['state'] not in {'failed','cancelled','expired'} and time.monotonic()<deadline:time.sleep(.02)
                    assert service.output.jobs[job['id']]['state']=='failed',(name,service.output.status());assert page.locator('#caption').inner_text()=='';states=[entry['state'] for entry in service.output.audit if entry['id']==job['id']]
                    if name!='pause-in-receipt':assert 'playing' not in states,(name,states)
                    r['checks'][name]=True;r.setdefault('fault_audits',{})[name]=states;page.screenshot(path=str(a.out/(name+'.png')));f.post('connectors/bili/output/stop',{});page.close()
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.audioDelay=1200');page.locator('#enable').click();job=ready_event('late-audio-after-stop');page.wait_for_function('()=>active!==null');f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>!active && !ProgramOutput.snapshot().enabled');page.wait_for_timeout(1400);assert page.evaluate('()=>audioProbe.playCalls')==0;assert page.locator('#caption').inner_text()=='';r['checks']['late_audio_after_stop_cannot_play']=True;page.close()
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.locator('#enable').click();job=ready_event('expires-in-playback');service.output.jobs[job['id']]['expires_at']=time.monotonic()+1;page.wait_for_function('()=>active?.started');page.wait_for_function('()=>!active && document.querySelector("#caption").textContent===""');assert service.output.jobs[job['id']]['state']=='expired';assert page.evaluate('()=>ProgramOutput.getDiagnostics().lipSyncValue')==0;r['checks']['expiry_stops_audio_caption_mouth']=True;f.post('connectors/bili/output/stop',{});page.close()
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.dropCompleted=true');page.locator('#enable').click();job=ready_event('completed-response-lost');page.wait_for_function('()=>document.querySelector("#status").textContent==="播放回执未确认"');page.wait_for_timeout(700);assert service.output.jobs[job['id']]['state']=='completed';assert page.locator('#status').inner_text()=='播放回执未确认';assert page.locator('#status').is_visible();assert page.locator('#caption').inner_text()=='';r['checks']['lost_completion_response_stays_unconfirmed']=True;page.screenshot(path=str(a.out/'completed-unconfirmed.png'));f.post('connectors/bili/output/stop',{});page.close()
                page=open_stage({'sceneDelay':1400});page.locator('#enable').click();f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>document.querySelector("#status").textContent.includes("连接失效")');page.wait_for_timeout(1600);assert page.evaluate('()=>ProgramOutput.snapshot().scene_sha256') is None;assert not page.evaluate('()=>ProgramOutput.getDiagnostics().available');r['checks']['late_warm_scene_cannot_restore_character']=True;page.close()
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.completedDelay=1500');page.locator('#enable').click();first=ready_event('late-completed-before-next')
                deadline=time.monotonic()+10
                while service.output.jobs[first['id']]['state']!='completed' and time.monotonic()<deadline:time.sleep(.02)
                assert service.output.jobs[first['id']]['state']=='completed'
                second=ready_event('next-during-old-completed');page.wait_for_function('(id)=>active?.id===id && active.started',arg=second['id']);page.wait_for_timeout(1700);assert page.evaluate('()=>active?.id')==second['id'];assert '正在输出' in page.locator('#status').inner_text();r['checks']['late_completed_cannot_overwrite_next_job']=True
                f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>!active');page.close()
                page=open_stage();page.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=60000);page.evaluate('()=>programFaults.completedDelay=1500');page.locator('#enable').click();first=ready_event('late-completed-after-stop')
                deadline=time.monotonic()+10
                while service.output.jobs[first['id']]['state']!='completed' and time.monotonic()<deadline:time.sleep(.02)
                assert service.output.jobs[first['id']]['state']=='completed';f.post('connectors/bili/output/stop',{});page.wait_for_function('()=>document.querySelector("#status").textContent.includes("连接失效")');page.wait_for_timeout(1700);assert '连接失效' in page.locator('#status').inner_text();r['checks']['late_completed_cannot_overwrite_stop']=True;page.close()
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
        f.tearDown();(a.out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':r.get('passed'),'checks':r['checks'],'out':str(a.out)},ensure_ascii=False));assert r['passed']


if __name__=='__main__':main()
