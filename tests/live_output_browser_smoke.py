"""Chrome smoke: synthetic Bili ingress, deterministic math answer, PCM tone.

This is NOT a Bili account test, model evaluation, real TTS or OBS/viewer proof.
Run PYTHONPATH=src:tests python3 tests/live_output_browser_smoke.py --chrome PATH --out DIR
"""
import argparse
import base64
import hashlib
import io
import json
import math
import platform
import resource
import sys
from pathlib import Path
import struct
import time
from types import SimpleNamespace
import wave
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests
from companion_runtime.live import LiveBinding, LiveIngress

MATERIAL = '自编 A-Level 数学冒烟材料（非考试局真题）。M1：y=x²−3x+2，导数为dy/dx=2x−3。M2：x=2时，y=0，切线斜率为1，切线方程y=x−2。'
ANSWER = '根据M1，dy/dx=2x−3；代入x=2得到斜率1。根据M2，切点为(2,0)，所以切线是y=x−2。'
QUESTION = '曲线y=x²−3x+2在x=2处的切线是什么？'


def tone():
    out = io.BytesIO()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
        stream.writeframes(b''.join(struct.pack('<h', int(5000*math.sin(2*math.pi*440*i/24000))) for i in range(24000*6)))
    return out.getvalue()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chrome',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    f=CharacterHTTPTests();f.setUp();report={'kind':'synthetic-local-smoke','real_bili':False,'real_tts':False,'viewer_received':False,'checks':{},'errors':[]}
    wav=tone();(out/'fixture-tone.wav').write_bytes(wav)
    f.app.generate_once=lambda settings,messages,**kw: (report.setdefault('model_inputs',[]).append(messages) or ANSWER)
    f.app.synthesize=lambda text: (report.setdefault('tts_inputs',[]).append(text) or wav)
    service=f.app.integrations();ingress=LiveIngress(LiveBinding('bilibili-open-live','123'),ttl_seconds=30,dedupe_seconds=60)
    service.bili=SimpleNamespace(ingress=ingress,status=lambda:{'state':'local-test-fixture'})
    base=f'http://127.0.0.1:{f.server.server_port}'
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=args.chrome,headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader'])
            context=browser.new_context(viewport={'width':1280,'height':960},record_video_dir=str(out/'host-video'))
            context.tracing.start(screenshots=True,snapshots=True,sources=True)
            host=context.new_page();host.on('pageerror',lambda e:report['errors'].append(str(e)))
            host.goto(base);host.wait_for_function('()=>window.CompanionApp?.core.get().state')
            host.locator('#open-companion-controls').click();host.get_by_role('button',name='微信与直播连接').click();host.get_by_role('button',name='哔哩哔哩直播预览',exact=True).click()
            host.get_by_label('本场公开教材',exact=True).fill(MATERIAL)
            host.get_by_label('允许在直播中使用这份教材',exact=True).check()
            host.get_by_role('button',name='保存教材').click()
            host.wait_for_timeout(150)
            host.get_by_role('button',name='输出窗口').click()
            link=host.get_by_role('link',name='打开输出窗口 ↗');link.wait_for();path=link.get_attribute('href')
            stage_context=browser.new_context(viewport={'width':1280,'height':720},record_video_dir=str(out/'stage-video'))
            stage_context.tracing.start(screenshots=True,snapshots=True,sources=True)
            stage_context.add_init_script("""(()=>{
              const play=HTMLMediaElement.prototype.play;
              window.smokeAudio={peak:0,chunks:[],done:false};
              HTMLMediaElement.prototype.play=async function(){
                if(!this._smokeSource){
                  const ctx=new AudioContext(),source=ctx.createMediaElementSource(this),analyser=ctx.createAnalyser(),sink=ctx.createMediaStreamDestination();
                  source.connect(analyser);analyser.connect(ctx.destination);analyser.connect(sink);this._smokeSource=source;
                  const recorder=new MediaRecorder(sink.stream);recorder.ondataavailable=e=>window.smokeAudio.chunks.push(e.data);
                  recorder.onstop=async()=>{const b=new Blob(window.smokeAudio.chunks,{type:'audio/webm'});const a=new Uint8Array(await b.arrayBuffer());window.smokeAudio.base64=btoa(String.fromCharCode(...a));window.smokeAudio.done=true;};
                  window.smokeAudio.stop=()=>recorder.stop();recorder.start();await ctx.resume();
                  const samples=new Float32Array(analyser.fftSize);setInterval(()=>{analyser.getFloatTimeDomainData(samples);window.smokeAudio.peak=Math.max(window.smokeAudio.peak,...samples.map(Math.abs));},30);
                }
                return play.call(this);
              };
            })();""")
            stage=stage_context.new_page();stage.on('pageerror',lambda e:report['errors'].append(str(e)))
            stage.goto(base+path);stage.get_by_role('button',name='启用本页音频').click()
            assert not stage_context.cookies(), 'output-only page must not acquire private application cookie'
            report['checks']['stage_has_no_private_cookie']=True
            assert stage.request.get(base+'/api/state').status==401
            ingress.submit({'room_id':'123','event_id':'smoke-1','text':QUESTION})
            host.get_by_role('button',name='刷新').click()
            host.get_by_role('button',name='准备回答').click()
            approve=host.get_by_role('button',name='播放这条回答');approve.wait_for()
            assert stage.locator('#caption').inner_text()==''
            approve.scroll_into_view_if_needed()
            host.screenshot(path=str(out/'01-host-review.png'),full_page=True)
            report['checks']['no_output_before_approval']=True
            assert host.get_by_text(QUESTION,exact=True).count()==1, 'question duplicated across cards'
            stop=host.get_by_role('button',name='停止播放',exact=True)
            for width,name in [(390,'mobile'),(1280,'desktop')]:
                host.set_viewport_size({'width':width,'height':960})
                approve.scroll_into_view_if_needed()
                assert host.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
                box=stop.bounding_box();assert box and box['y']>=0 and box['y']+box['height']<=960
                host.screenshot(path=str(out/('04-'+name+'.png')))
            host.evaluate("()=>document.documentElement.dataset.theme='night'")
            host.wait_for_timeout(200)
            host.screenshot(path=str(out/'05-night.png'))
            contrast=[]
            for theme in ['night','day']:
                host.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                for hover in [False,True]:
                    if hover:approve.hover()
                    else:host.mouse.move(5,5)
                    host.wait_for_timeout(180)
                    ratio=approve.evaluate(r"""el=>{const s=getComputedStyle(el),lum=c=>{let a=c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*a[0]+.7152*a[1]+.0722*a[2]};const a=lum(s.color),b=lum(s.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)}""")
                    assert ratio>=4.5,(theme,hover,ratio)
                    contrast.append({'theme':theme,'hover':hover,'ratio':ratio})
            report['primary_button_contrast']=contrast
            host.locator('[data-contact-page=bili]').screenshot(path=str(out/'06-live-desk.png'))
            host.evaluate("()=>document.documentElement.dataset.theme='day'")
            report['checks']['single_question_mobile_stop_visible']=True

            host.on('dialog',lambda dialog:dialog.accept())
            approve.click();stage.wait_for_function("()=>document.querySelector('#caption').textContent.length>0")
            assert stage.locator('#caption').inner_text()==ANSWER
            stage.wait_for_timeout(300)
            report['playback_before_stop']=stage.evaluate('({time:active.audio.currentTime,paused:active.audio.paused,readyState:active.audio.readyState})')
            assert report['playback_before_stop']['time']>0 and not report['playback_before_stop']['paused']
            stage.screenshot(path=str(out/'02-stage-playing.png'))
            start=time.monotonic();host.get_by_role('button',name='停止播放',exact=True).click()
            stage.wait_for_function("()=>document.querySelector('#caption').textContent==='' && active===null")
            report['stop_observed_ms']=round((time.monotonic()-start)*1000,1)
            assert report['stop_observed_ms']<1500
            stage.screenshot(path=str(out/'03-stage-stopped.png'))
            stage.evaluate('()=>window.smokeAudio.stop()')
            stage.wait_for_function('()=>window.smokeAudio.done')
            capture=stage.evaluate('()=>({base64:window.smokeAudio.base64,peak:window.smokeAudio.peak})')
            assert capture['peak']>0.05
            (out/'browser-output.webm').write_bytes(base64.b64decode(capture['base64']))
            report['browser_audio_peak']=capture['peak']
            report['audio_capture_scope']='Chrome WebAudio graph; not OS speaker or OBS/viewer capture'
            report['checks']['playing_cancel_stops_audio_and_caption']=True
            report['cancelled_job']=service.output.status()
            newpath=f.post('connectors/bili/output/open',{})['path']
            stage.goto(base+newpath);stage.wait_for_function('()=>location.hash==="" && !enabled');stage.get_by_role('button',name='启用本页音频').click()
            ingress.submit({'room_id':'123','event_id':'smoke-2','text':QUESTION})
            reply=f.post('connectors/bili/reply',{'event_id':'smoke-2'})
            f.post('connectors/bili/approve',{'id':reply['id'],'confirm_output':True})
            stage.wait_for_function("()=>document.querySelector('#caption').textContent.length>0")
            stage.wait_for_function("()=>document.querySelector('#caption').textContent==='' && active===null")
            assert service.output.jobs[reply['id']]['state']=='completed'
            assert not service.output.jobs[reply['id']]['delivered']
            stage.evaluate('()=>window.smokeAudio.stop()');stage.wait_for_function('()=>window.smokeAudio.done')
            capture=stage.evaluate('()=>window.smokeAudio.base64')
            (out/'browser-completed-output.webm').write_bytes(base64.b64decode(capture))
            report['checks']['full_playback_completes_without_delivery_claim']=True
            report['jobs']=service.output.status()
            report['environment']={'python':sys.version,'platform':platform.platform(),'chrome':browser.version,'parent_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            report['raw_events']=[{'origin':'synthetic','room_id':'123','event_id':ident,'text':QUESTION} for ident in ['smoke-1','smoke-2']]

            # Source-wave is attached separately: Playwright video has no audio track.
            report['fixture_audio_sha256']=hashlib.sha256(wav).hexdigest()
            report['video_has_audio_track']=False
            assert not report['errors']
            context.tracing.stop(path=str(out/'host-trace.zip'));stage_context.tracing.stop(path=str(out/'stage-trace.zip'))
            stage_context.close();context.close();browser.close()
            report['passed']=True
    except Exception as error:
        report['failure']=str(error)
        report['failed_jobs']=service.output.status()
        raise
    finally:
        f.tearDown();(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':report.get('passed',False),'stop_ms':report.get('stop_observed_ms'),'evidence':str(out)},ensure_ascii=False))

if __name__=='__main__':main()
