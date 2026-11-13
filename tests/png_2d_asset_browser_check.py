"""Read-only PNG statistics and actual Chromium composition/audio-cadence bench.

Original source PNGs are never rewritten. Gallery is a controlled test bench,
not the app renderer, actual user microphone, a layered rig or final UI review.
"""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import traceback
import wave

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/workspace/dist/uiux-2026/2d-asset-alpha')
FILES={
 'idle':Path('/workspace/generated_images/exec-fabb6d39-ce45-4047-a70c-b6d6f6dc2164.png'),
 'talk':Path('/workspace/generated_images/exec-29ca6c06-7059-4536-bafb-28697f44c56e.png'),
 'blink':Path('/workspace/generated_images/exec-7385b906-9945-4804-8821-9f98312d09ad.png'),
 'talk_blink':Path('/workspace/generated_images/exec-4585a04d-4dda-4477-8494-1edbc9fe74db.png')}
HTML='''<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;padding:18px;font:14px system-ui;background:#ddd;color:#222}header{height:38px;display:flex;justify-content:space-between}main{display:grid;grid-template-columns:repeat(3,535px);gap:16px}.card{height:790px;position:relative;border:1px solid #aaa}.label{position:absolute;top:8px;left:8px;background:#ddd;color:#222;padding:4px 8px;z-index:2}.card img{display:block;width:535px;height:735px;position:absolute;bottom:0;left:0;object-fit:contain}.black{background:#000}.white{background:#fff}.green{background:#00ff00}
</style><header><strong>2D PNG alpha / state bench — original files unchanged</strong><span id="state">idle</span></header><main><div class="card black"><span class="label">Black #000000</span><img></div><div class="card white"><span class="label">White #FFFFFF</span><img></div><div class="card green"><span class="label">Green #00FF00</span><img></div></main><script>
window.sources={};window.timeline=[];window.ready=(async()=>{for(const state of ['idle','talk','blink','talk_blink']){const image=new Image();image.src='/'+state+'.png';await image.decode();sources[state]=image;}setState('idle');})();
window.setState=state=>{for(const image of document.querySelectorAll('.card img'))image.src=sources[state].src;document.querySelector('#state').textContent=state;};
window.startAudio=async()=>{const audio=new Audio('/cadence.wav'),context=new AudioContext(),source=context.createMediaElementSource(audio),analyser=context.createAnalyser();analyser.fftSize=512;source.connect(analyser);analyser.connect(context.destination);const data=new Uint8Array(analyser.fftSize);window.testAudio=audio;window.testAudioContext=context;let last='';function frame(){analyser.getByteTimeDomainData(data);let sum=0;for(const value of data)sum+=((value-128)/128)**2;const rms=Math.sqrt(sum/data.length),mouth=rms>.025,blink=audio.currentTime%3.2>2.9&&audio.currentTime%3.2<3.05,state=mouth?(blink?'talk_blink':'talk'):(blink?'blink':'idle');if(state!==last){setState(state);timeline.push({at:performance.now(),audio:audio.currentTime,rms,state});last=state;}if(!audio.paused&&!audio.ended)requestAnimationFrame(frame);}await context.resume();await audio.play();requestAnimationFrame(frame);};
window.stopAudio=()=>{testAudio.pause();testAudioContext.close();setState('idle');};</script>'''


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_stats():
    arrays={};stats={};samples={}
    for name,path in FILES.items():
        with Image.open(path) as image:
            assert image.mode=='RGBA' and image.size==(1070,1470),(name,image.mode,image.size)
            data=np.asarray(image).copy()
        arrays[name]=data;alpha=data[:,:,3];rgb=data[:,:,:3]
        red=(rgb[:,:,0]>180)&(rgb[:,:,1]<80)&(rgb[:,:,2]<80)
        yellow=(rgb[:,:,0]>180)&(rgb[:,:,1]>150)&(rgb[:,:,2]<80)
        visible=alpha>160;ys,xs=np.nonzero(visible)
        stats[name]={'source':str(path),'sha256':digest(path),'bytes':path.stat().st_size,
          'dimensions':[1070,1470],'mode':'RGBA','pixels':int(alpha.size),
          'alpha_histogram':{label:int(np.count_nonzero((alpha>=low)&(alpha<=high))) for label,low,high in [('zero',0,0),('one_to_five',1,5),('six_to_63',6,63),('64_to_127',64,127),('128_to_240',128,240),('241_to_254',241,254),('255',255,255)]},
          'alpha_median_where_nonzero':float(np.median(alpha[alpha>0])),
          'alpha_over_160_bbox':[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)],
          'bright_red_by_alpha':{str(cut):int(np.count_nonzero(red&(alpha>cut))) for cut in [0,5,32,128,240]},
          'bright_yellow_by_alpha':{str(cut):int(np.count_nonzero(yellow&(alpha>cut))) for cut in [0,5,32,128,240]},
          'hidden_red_alpha_zero':int(np.count_nonzero(red&(alpha==0))),
          'hidden_yellow_alpha_zero':int(np.count_nonzero(yellow&(alpha==0)))}
        points=[]
        for mask in [red&(alpha>0)&(alpha<=5),yellow&(alpha>0)&(alpha<=5),(alpha==0),((alpha>0)&(alpha<16))]:
            coords=np.argwhere(mask)
            for y,x in coords[::max(1,len(coords)//3)][:3]:points.append({'x':int(x),'y':int(y),'rgba':data[y,x].tolist()})
        samples[name]=points
    reference=arrays['idle'];baseline=reference[:,:,3]>160
    for name,data in arrays.items():
        mask=data[:,:,3]>160;union=baseline|mask;intersection=baseline&mask
        stats[name]['alpha_silhouette_iou_vs_idle']=float(intersection.sum()/union.sum())
        # Fixed image-coordinate ROI, not detected anatomical landmarks.
        for label,(x0,y0,x1,y1) in {'head':(210,0,850,620),'lower_body':(150,650,950,1470)}.items():
            common=intersection[y0:y1,x0:x1]
            a=reference[y0:y1,x0:x1,:3].astype(np.float32);b=data[y0:y1,x0:x1,:3].astype(np.float32)
            difference=np.abs(a-b).mean(axis=2)[common]
            stats[name][label+'_rgb_difference_vs_idle']={'fixed_roi':[x0,y0,x1,y1],'mean_0_to_255':float(difference.mean()),'fraction_above20':float((difference>20).mean())}
    return stats,samples


def cadence_wav():
    rate=24000;t=np.arange(rate*9)/rate
    envelope=((t%0.25)<0.125).astype(np.float32) # Four open/close cycles per second.
    pcm=(np.sin(2*np.pi*440*t)*envelope*7000).astype('<i2').tobytes()
    out=io.BytesIO()
    with wave.open(out,'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
    return out.getvalue()


def main():
    OUT.mkdir(parents=True,exist_ok=True);stats,samples=source_stats();audio=cadence_wav();(OUT/'synthetic-4hz-cadence.wav').write_bytes(audio)
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'scope':'read-only original PNG + actual Chromium img/background composition + controlled real HTMLAudio/RMS state cadence bench; not production app renderer',
      'status':'running','sources':stats,'source_sha_before':{n:digest(p) for n,p in FILES.items()},'browser_checks':{},
      'artwork_modified':False,'layered_live2d_verified':False,'human_visual_acceptance':False,
      'source_pngs_saved_or_reencoded':False,'microphone_used':False,'screen_recording_audio_track':False,
      'cadence':'Actual synthetic HTMLAudio,4Hz envelope;125ms on/125ms off, eight state transitions/second; natural120–150ms eye interval every3.2s.',
      'limits':['Only generated four-frame PNG; not physical 3D, layered PSD/MOC, source art or target Windows/GPU validation','Threshold metrics are selected saturation tests, not a complete color-fringe detector','Body ROI and alpha silhouettes are image-coordinate measures, not anatomical landmark tracking','Visual judgment must inspect actual cadence video; numeric differences alone do not prove perceptual acceptance']}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            key=self.path.split('?',1)[0]
            if key=='/':body=HTML.encode();mime='text/html; charset=utf-8'
            elif key=='/cadence.wav':body=audio;mime='audio/wav'
            elif key.endswith('.png') and key[1:-4] in FILES:body=FILES[key[1:-4]].read_bytes();mime='image/png'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio'])
            context=browser.new_context(viewport={'width':1685,'height':865},record_video_dir=str(OUT/'raw-video'),record_video_size={'width':1685,'height':865})
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle');page.evaluate('()=>ready')
            for state in FILES:
                page.evaluate('(state)=>setState(state)',state);page.wait_for_timeout(250)
                path=OUT/(state+'-black-white-green.png');page.screenshot(path=str(path))
                screenshot=np.asarray(Image.open(path).convert('RGB'))
                result=page.evaluate('''({state,points})=>{const image=sources[state],canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);const decoded=points.map(p=>({...p,actual:Array.from(ctx.getImageData(p.x,p.y,1,1).data)}));const composites={};for(const [name,color]of [['black','#000'],['white','#fff'],['green','#00ff00']]){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle=color;ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);composites[name]=points.map(p=>({x:p.x,y:p.y,source:p.rgba,actual:Array.from(ctx.getImageData(p.x,p.y,1,1).data)}));}canvas.width=canvas.height=0;return {decoded,composites};}''',{'state':state,'points':samples[state]})
                for point in result['decoded']:
                    if point['rgba'][3]==0:assert point['actual']==[0,0,0,0],point
                for name,background in [('black',[0,0,0]),('white',[255,255,255]),('green',[0,255,0])]:
                    for point in result['composites'][name]:
                        alpha=point['source'][3]
                        expected=[round((point['source'][i]*alpha+background[i]*(255-alpha))/255) for i in range(3)]
                        point['expected_srgb_composite']=expected
                        assert max(abs(expected[i]-point['actual'][i]) for i in range(3))<=2,point
                result['screenshot_bright_saturation_counts']={'red':int(np.count_nonzero((screenshot[:,:,0]>180)&(screenshot[:,:,1]<80)&(screenshot[:,:,2]<80))),
                  'yellow':int(np.count_nonzero((screenshot[:,:,0]>180)&(screenshot[:,:,1]>150)&(screenshot[:,:,2]<80)))}
                report['browser_checks'][state]=result
            report['actual_chrome_white_composite_region_differences']=page.evaluate('''()=>{const canvas=document.createElement('canvas');canvas.width=1070;canvas.height=1470;const ctx=canvas.getContext('2d',{willReadFrequently:true});function pixels(state,white){ctx.clearRect(0,0,1070,1470);if(white){ctx.fillStyle='#fff';ctx.fillRect(0,0,1070,1470);}ctx.drawImage(sources[state],0,0);return ctx.getImageData(0,0,1070,1470).data;}const ref=pixels('idle',true),alpha=pixels('idle',false),result={};for(const state of ['talk','blink','talk_blink']){const now=pixels(state,true),a=pixels(state,false);result[state]={};for(const [region,bounds]of [['head',[210,0,850,620]],['lower_body',[150,650,950,1470]],['hands_cup',[430,730,850,1050]]]){let sum=0,signed=0,above=0,count=0;for(let y=bounds[1];y<bounds[3];y++)for(let x=bounds[0];x<bounds[2];x++){const i=(y*1070+x)*4;if(alpha[i+3]<=160||a[i+3]<=160)continue;let d=0;for(let k=0;k<3;k++){d+=Math.abs(now[i+k]-ref[i+k]);signed+=now[i+k]-ref[i+k];}d/=3;sum+=d;above+=d>20;count++;}result[state][region]={fixed_roi:bounds,mean_absolute_rgb_delta:sum/count,mean_signed_rgb_delta:signed/(count*3),fraction_above20:above/count,pixels:count};}}canvas.width=canvas.height=0;return result;}''')
            page.evaluate('()=>startAudio()');page.wait_for_function('()=>testAudio.currentTime>.05&&!testAudio.paused');page.wait_for_timeout(8000)
            report['actual_audio_timeline']=page.evaluate('()=>timeline');report['audio_current_time']=page.evaluate('()=>testAudio.currentTime')
            assert len(report['actual_audio_timeline'])>35,report['actual_audio_timeline']
            assert {'idle','talk','blink','talk_blink'} <= {x['state'] for x in report['actual_audio_timeline']}
            page.evaluate('()=>stopAudio()');page.wait_for_timeout(300);assert page.locator('#state').inner_text()=='idle'
            video=page.video;context.close();video.save_as(str(OUT/'actual-audio-four-state-composition.webm'));browser.close()
            assert errors==[],errors;report['javascript_errors']=errors
        report['status']='passed_composition_and_cadence_not_artwork_approval'
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc());raise
    finally:
        server.shutdown();server.server_close();thread.join(3)
        report['source_sha_after']={n:digest(p) for n,p in FILES.items()};report['source_files_unchanged']=report['source_sha_before']==report['source_sha_after']
        report['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)} for p in OUT.iterdir() if p.is_file()]
        report['reproduce_command']='PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright python tests/png_2d_asset_browser_check.py'
        (ROOT/'review/png-2d-alpha-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'sources':stats,'source_files_unchanged':report['source_files_unchanged']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
