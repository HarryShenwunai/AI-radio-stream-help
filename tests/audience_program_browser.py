"""Actual applied-room -> output action -> real Core source layout; mechanical audio only.
Linux Chrome evidence, not Windows/OBS/viewer/art-naturalness acceptance.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright
import test_character_http as fixtures
from program_output_browser import OfflineBoundary, OFFLINE_CHROME_FLAGS, PROBE, QUESTION, tone

GEOMETRY = r'''()=>{const box=s=>{const b=document.querySelector(s).getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height}};const c=document.querySelector('#caption'),p=document.querySelector('#program'),style=getComputedStyle(c),a=box('#caption'),b=box('#character-space');return {layout:p.dataset.layout,theme:p.dataset.theme,text:c.textContent,caption:a,person:b,disjoint:a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom,full:c.scrollWidth<=c.clientWidth&&c.scrollHeight<=c.clientHeight,font:parseFloat(style.fontSize),foreground:style.color,surface:style.backgroundColor,root:getComputedStyle(document.body).backgroundColor,transform:getComputedStyle(document.querySelector('#character-space')).transform,plays:audioProbe.playCalls,peak:audioProbe.peak,diag:ProgramOutput.getDiagnostics(),requests:programRequests,status:document.querySelector('#status').textContent}}'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--chrome',required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--app-root',type=Path);p.add_argument('--stage-source',type=Path);p.add_argument('--composition-only',action='store_true');p.add_argument('--preparation-only',action='store_true');p.add_argument('--preparation-case',choices=('error','resize'),default='error');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if a.app_root:fixtures.ROOT=a.app_root.resolve()
    os.environ['COMPANION_DEFAULT_LIVE2D']=str(a.model.resolve());f=fixtures.CharacterHTTPTests();f.setUp();os.environ.pop('COMPANION_DEFAULT_LIVE2D',None)
    paths={'core':a.runtime_dir/'live2dcubismcore.min.js','bundle':a.runtime_dir/'build/owner-live2d-runtime.js'}
    class Runtime:
        def status(self):return {'available':True,'core_url':'/live2d-core.js','runtime_url':'/live2d-runtime.js','artifacts':{k:{'available':True,'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for k,v in paths.items()}}
        def read_core(self):return paths['core'].read_bytes()
        def read_bundle(self):return paths['bundle'].read_bytes()
    f.app.live2d_runtime=lambda:Runtime();audio=tone(9);f.app.synthesize=lambda text:audio
    (a.out/'mechanical-tone.wav').write_bytes(audio)
    service=f.app.integrations();base='http://127.0.0.1:'+str(f.server.server_port);boundary=OfflineBoundary(f.server.server_port,True);netlog=a.out/'chrome-private-netlog.json'
    result={'scope':__doc__,'composition_only':a.composition_only,'preparation_only':a.preparation_only,'preparation_case':a.preparation_case,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'executed_stage_sha256':hashlib.sha256((a.stage_source or fixtures.ROOT/'app/static/live-stage.js').read_bytes()).hexdigest(),'model_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'runtime_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},'cases':[],'checks':{},'errors':[],'source_sha256':{n:hashlib.sha256((fixtures.ROOT/n).read_bytes()).hexdigest() for n in ['app/server.py','app/static/connectors-ui.js','app/static/program-scene.js','app/static/live-stage.css','app/static/live-stage.js']}}
    b=hc=sc=None
    try:
        f.post('connectors/bili/rehearsal',{'action':'start','confirm_local':True})
        with sync_playwright() as pw:
            b=pw.chromium.launch(executable_path=a.chrome,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader',*OFFLINE_CHROME_FLAGS,'--log-net-log='+str(netlog.resolve())]);hc=b.new_context(viewport={'width':1440,'height':1000},service_workers='block',record_video_dir=str(a.out/'host-video'));sc=b.new_context(viewport={'width':1920,'height':1080},service_workers='block',record_video_dir=str(a.out/'source-video'));boundary.install(hc);boundary.install(sc);hc.tracing.start(screenshots=True,snapshots=True,sources=True);sc.tracing.start(screenshots=True,snapshots=True,sources=True)
            if a.stage_source:
                text=a.stage_source.read_text();sc.route(base+'/live-stage.js',lambda route:route.fulfill(status=200,body=text,content_type='application/javascript'))
            host=hc.new_page();host.on('pageerror',lambda e:result['errors'].append(str(e)));host.goto(base);host.wait_for_function('()=>window.CompanionApp?.core.get().state');host.locator('#open-companion-controls').click();host.get_by_role('button',name='微信与直播连接').click();host.get_by_role('button',name='本地互动演练',exact=True).click();host.get_by_label('模拟观众消息',exact=True).wait_for()
            stages=[]
            def stop(stage):
                stage.evaluate('()=>{for(const r of audioProbe.records)if(r.recorder.state!=="inactive")r.recorder.stop();}')
                stage.wait_for_function('()=>audioProbe.records.every(r=>Boolean(r.base64))',timeout=3000)
                for index,value in enumerate(stage.evaluate('()=>audioProbe.records.map(r=>r.base64)')):(a.out/f'actual-tone-{len(result.get("captured_audio",[]))}-{index}.webm').write_bytes(base64.b64decode(value))
                result.setdefault('captured_audio',[]).append({'records':len(stage.evaluate('()=>audioProbe.records'))})
                f.post('connectors/bili/output/stop',{});stage.wait_for_function('()=>ProgramOutput.snapshot().enabled===false',timeout=4000)
                assert stage.locator('#caption').inner_text()==''
                stage.evaluate('()=>{enabled=false;epoch++;clear();program.dispose();}')
                stage.wait_for_function('()=>!busy&&pendingProgramFetch===0',timeout=4000);stage.close()
            def open_applied(layout,theme):
                room=hc.new_page();room.goto(base+'/room.html');room.wait_for_function('()=>RoomPreview.loaded');room.locator('#layout-select').select_option(layout);room.locator('#theme-select').select_option(theme);room.locator('#show-caption').check();room.locator('#apply-settings').click();assert room.evaluate('()=>RoomPreview.snapshot().config.applied');result.setdefault('applied_configs',[]).append(room.evaluate('()=>RoomPreview.snapshot().config'));room.close()
                with host.expect_response(lambda response:response.url.endswith('/api/connectors/bili/output/open')) as opened:
                    host.get_by_role('button',name='输出窗口',exact=True).click()
                response=opened.value;assert response.ok;path=response.json()['path'];host.wait_for_function('(path)=>Array.from(document.querySelectorAll("a")).some(a=>a.getAttribute("href")===path)',arg=path);stage=sc.new_page();stages.append(stage);stage.add_init_script("(()=>{const native=requestAnimationFrame;let held=[];window.audienceFramesPaused=false;window.resumeAudienceFrames=()=>{audienceFramesPaused=false;const work=held;held=[];for(const cb of work)native(cb);};window.requestAnimationFrame=cb=>native(t=>{if(audienceFramesPaused)held.push(cb);else cb(t);});})()");stage.add_init_script(PROBE.replace('const scene=api.create(options)', "window.programInjectedSceneError=()=>options.onState({ready:false,error:'Injected renderer ownership failure'});const scene=api.create(options)").replace('status:response.status,fetch_ms','state:data?.state,status:response.status,fetch_ms').replace('if(delay)await new Promise(resolve=>setTimeout(resolve,delay));return response;', 'if(delay)await new Promise(resolve=>setTimeout(resolve,delay));observed.release_ms=performance.now()-requested;observed.signal_aborted_on_return=Boolean(options?.signal?.aborted);return response;'));stage.on('pageerror',lambda e:result['errors'].append(str(e)));stage.on('console',lambda m:result.setdefault('console',[]).append({'type':m.type,'text':m.text}));stage.goto(base+path);stage.wait_for_function('()=>ProgramOutput.getDiagnostics().mocConsistencyChecked===true',timeout=30000);assert not sc.cookies();stage.get_by_role('button',name='启用本页音频').click();return stage
            def approve(text,name):
                event={'source':'local-rehearsal','room_id':'local','event_id':name,'text':QUESTION,'expires_at':time.monotonic()+30,'origin':'local_rehearsal'};job=service.output.begin(event);service.output.finish(job['id'],text,'mechanical-'+name);f.post('connectors/bili/approve',{'id':job['id'],'confirm_output':True});return job
            reply=QUESTION*5
            for layout,theme in ([] if a.composition_only or a.preparation_only else [('right','carbon'),('left','midnight'),('small','daylight')]):
                stage=open_applied(layout,theme);job=approve(reply,layout);stage.wait_for_function('()=>audioProbe.playCalls===1&&document.querySelector("#caption").textContent.length>0',timeout=6000);stage.wait_for_function('()=>audioProbe.peak>0.01',timeout=3000)
                for width,height in [(1920,1080),(1366,768),(1280,720)]:
                    stage.set_viewport_size({'width':width,'height':height});stage.wait_for_timeout(180);row=stage.evaluate(GEOMETRY);row.update(requested_layout=layout,requested_theme=theme,width=width,height=height,job_id=job['id']);row['passed']=row['layout']==layout and row['theme']==theme and row['disjoint'] and row['full'] and row['text']==reply and row['font']>=20 and row['transform']=='none' and row['peak']>0.01;result['cases'].append(row);stage.screenshot(path=str(a.out/f'{layout}-{width}x{height}.png'),omit_background=True)
                stop(stage)
            # A non-repeated original user sentence is a normal-size mechanical echo,
            # never an AI-authored example or a claim about answer quality.
            result['normal_text_source']='Original user sentence in program_output_browser.QUESTION; mechanical echo, not generated reply'
            for layout,theme in ([] if a.preparation_only else [('left','midnight')] if a.composition_only else [('right','carbon'),('left','midnight'),('small','daylight')]):
                stage=open_applied(layout,theme);approve(QUESTION,'normal-'+layout);stage.wait_for_function('()=>audioProbe.peak>0.01&&document.querySelector("#caption").textContent.length>0',timeout=5000)
                for width,height in [(1920,1080),(1366,768),(1280,720)]:
                    stage.set_viewport_size({'width':width,'height':height});stage.wait_for_timeout(180);row=stage.evaluate(GEOMETRY);row.update(requested_layout=layout,requested_theme=theme,width=width,height=height);row['passed']=row['layout']==layout and row['theme']==theme and row['disjoint'] and row['full'] and row['text']==QUESTION and row['font']>=20;result.setdefault('normal_cases',[]).append(row);stage.screenshot(path=str(a.out/f'normal-{layout}-{width}x{height}.png'),omit_background=True)
                if layout=='left':
                    stage.set_viewport_size({'width':1920,'height':1080});stage.wait_for_timeout(180);stage.evaluate('()=>audienceFramesPaused=true');stage.wait_for_timeout(150);frozen=stage.evaluate('()=>ProgramOutput.getStats().frames');stage.screenshot(path=str(a.out/'test-composite-transparent.png'),omit_background=True)
                    for background,color in [('carbon','#17191f'),('lightgray','#e5e7eb')]:
                        stage.evaluate('(color)=>{document.documentElement.style.background=color;document.body.style.background=color}',color);stage.screenshot(path=str(a.out/f'test-composite-{background}.png'));assert stage.evaluate('()=>ProgramOutput.getStats().frames')==frozen
                    stage.evaluate('()=>{document.documentElement.style.background="";document.body.style.background="";resumeAudienceFrames()}')
                    result['composition_scope']='Same frozen Core frame (test-only rAF pause, frame-count invariant) over explicit test-only carbon/lightgray body backgrounds, not approved production backgrounds; asset unchanged'
                result.setdefault('caption_fit_cost',[]).append(stage.evaluate('()=>{const text=document.querySelector("#caption").textContent,t=performance.now();for(let i=0;i<50;i++)fitsCaption(text);document.querySelector("#caption").textContent=text;return {calls:50,elapsed_ms:performance.now()-t}}'))
                stop(stage)
            if not a.composition_only and not a.preparation_only:
                # Unbounded response must fail before any sound, with no hidden text.
                stage=open_applied('right','carbon');job=approve((QUESTION*25)[:700],'overflow');stage.wait_for_function('()=>document.querySelector("#status").textContent.includes("无法完整显示")',timeout=5000);result['checks']['long_answer_rejected_before_sound']=stage.evaluate('()=>audioProbe.playCalls===0&&document.querySelector("#caption").textContent===""');stage.screenshot(path=str(a.out/'overflow-explicit-failure.png'),omit_background=True);stop(stage)
                # Capture claimed preparation, shrink a PC window, then let the original audio response arrive.
                stage=open_applied('left','midnight');stage.set_viewport_size({'width':1920,'height':1080});stage.evaluate('()=>programFaults.audioDelay=600');job=approve(reply,'pending-resize');stage.wait_for_function('()=>programRequests.some(v=>v.action==="audio")',timeout=5000);stage.set_viewport_size({'width':1280,'height':500});stage.wait_for_timeout(1500);result['pending_resize']=stage.evaluate(GEOMETRY);result['checks']['preparing_resize_no_play']=stage.evaluate('()=>audioProbe.playCalls===0&&!programRequests.some(v=>v.action==="receipt"&&v.state==="playing")&&document.querySelector("#caption").textContent===""&&document.querySelector("#status").textContent.includes("无法完整显示")');result['checks']['preparing_resize_failed']=service.output.jobs[job['id']]['state']=='failed';stage.screenshot(path=str(a.out/'preparing-resize.png'),omit_background=True);stop(stage)
                # Inject an actual scene callback error into the real stage/media, not an alert label.
                stage=open_applied('small','daylight');stage.set_viewport_size({'width':1280,'height':720});approve(QUESTION,'scene-error');stage.wait_for_function('()=>audioProbe.peak>0.01',timeout=5000);stage.evaluate('()=>programInjectedSceneError()');stage.wait_for_timeout(450);result['checks']['scene_error_stops_media']=stage.evaluate('()=>lastProgramAudio.paused&&document.querySelector("#caption").textContent===""&&ProgramOutput.snapshot().enabled===false&&Number(ProgramOutput.getStats().mouth||0)===0');stage.screenshot(path=str(a.out/'scene-error.png'),omit_background=True);stop(stage)
            if not a.composition_only and (not a.preparation_only or a.preparation_case=='error'):
                # Same preparation-error branch: actual callback before a delayed audio response.
                stage=open_applied('right','carbon');stage.set_viewport_size({'width':1280,'height':720});stage.evaluate('()=>programFaults.audioDelay=600');job=approve(QUESTION,'preparing-scene-error');stage.wait_for_function('()=>programRequests.some(v=>v.action==="audio")',timeout=5000);result['preparation_stimulus']=stage.evaluate('()=>({playCalls:audioProbe.playCalls,requests:programRequests,at:performance.now()})');assert result['preparation_stimulus']['playCalls']==0;stage.evaluate('()=>programInjectedSceneError()');stage.wait_for_timeout(850);result['preparation_outcome']=stage.evaluate(GEOMETRY);result['checks']['preparing_scene_error_no_play']=stage.evaluate('()=>audioProbe.playCalls===0&&document.querySelector("#caption").textContent===""&&ProgramOutput.snapshot().enabled===false');result['checks']['preparing_scene_error_failed']=service.output.jobs[job['id']]['state']=='failed';stop(stage)
            if a.preparation_only and a.preparation_case=='resize':
                stage=open_applied('left','midnight');stage.set_viewport_size({'width':1920,'height':1080});stage.evaluate('()=>programFaults.audioDelay=600');job=approve(reply,'short-preparing-resize');stage.wait_for_function('()=>programRequests.some(v=>v.action==="audio")',timeout=5000);result['preparation_stimulus']=stage.evaluate('()=>({playCalls:audioProbe.playCalls,requests:programRequests,at:performance.now()})');assert result['preparation_stimulus']['playCalls']==0;stage.set_viewport_size({'width':1280,'height':500});stage.wait_for_timeout(850);result['preparation_outcome']=stage.evaluate(GEOMETRY);result['checks']['preparing_resize_no_play']=stage.evaluate('()=>audioProbe.playCalls===0&&!programRequests.some(v=>v.action==="receipt"&&v.state==="playing")&&document.querySelector("#caption").textContent===""&&document.querySelector("#status").textContent.includes("无法完整显示")');result['checks']['preparing_resize_failed']=service.output.jobs[job['id']]['state']=='failed';stage.screenshot(path=str(a.out/'short-preparing-resize.png'),omit_background=True);stop(stage)
            hc.tracing.stop(path=str(a.out/'host-trace-private.zip'));sc.tracing.stop(path=str(a.out/'source-trace-private.zip'));hc.close();sc.close();b.close();b=None
        result['checks']['nonempty_protocol_coverage']=len(result['cases'])==(0 if a.composition_only or a.preparation_only else 9) and len(result.get('normal_cases',[]))==(0 if a.preparation_only else 3 if a.composition_only else 9);result['network']=boundary.summary(netlog);result['checks']['strict_network']=not result['network']['unexpected_native_destinations'] and not result['network']['blocked_browser_requests'] and not result['network']['blocked_python_requests'] and not result['network']['bridge_failures'] and result['network']['netlog_read_error'] is None;result['passed']=all(v['passed'] for v in result['cases']) and all(v['passed'] for v in result.get('normal_cases',[])) and all(result['checks'].values()) and not result['errors'];return 0 if result['passed'] else 1
    except Exception as error:
        result['error']=repr(error);result['passed']=False;return 1
    finally:
        if b:
            try:hc.tracing.stop(path=str(a.out/'host-trace-private.zip'));sc.tracing.stop(path=str(a.out/'source-trace-private.zip'));b.close()
            except Exception:pass
        result['audit']=list(service.output.audit);(a.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));boundary.enabled=False;f.tearDown();print(json.dumps({'passed':result.get('passed'),'error':result.get('error'),'result':str(a.out/'result.json')},ensure_ascii=False),flush=True)

if __name__=='__main__':raise SystemExit(main())
