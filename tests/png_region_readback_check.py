"""Actual production Canvas2D read-only controls, then real test-tone playback.

Never changes context creation flags/rendering code. First-read differences are
measured separately; later region invariance still requires exact RGBA equality.
"""
from pathlib import Path
import hashlib
import json

from playwright.sync_api import sync_playwright

import test_character_http as fixtures
from png_2d_asset_browser_check import cadence_wav

ROOT=Path(__file__).resolve().parents[1]


def main():
    package=json.loads(Path('/workspace/dist/character-2d.companion.json').read_text())
    f=fixtures.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality');f.setUp()
    original=f.app.state;f.app.state=lambda:{**original(),'local_voice_available':True}
    f.app.synthesize=lambda text:cadence_wav();f.app.set_settings({'voice':False});f.chat('独立只读控制测试输入')
    asset=f.post('characters/assets/import',{'character_id':f.initial_id,'states':package['states'],'animation_regions':package['animation_regions']})['asset']
    f.post('characters/assets/activate',{'character_id':f.initial_id,'asset_id':asset['id']})
    source=ROOT/'app/static/scene-controller.js'
    report={'scope':'actual app production Canvas2D and same SwiftShader browser flags; synthetic TTS; no rendering/context flag modification',
            'status':'running','source_sha_before':hashlib.sha256(source.read_bytes()).hexdigest(),
            'animation_regions':package['animation_regions'],'checks':{},'first_readback_cause':'unknown; GPU/CPU readback conversion is an inference, not established cause'}
    try:
        with sync_playwright() as pw:
            b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--autoplay-policy=no-user-gesture-required','--mute-audio','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
            p=b.new_page(viewport={'width':1440,'height':1000});p.goto('http://127.0.0.1:'+str(f.server.server_port),wait_until='networkidle')
            p.wait_for_function('()=>window.CompanionApp?.scene.ready&&document.querySelector(".regional-png-canvas")')
            result=p.evaluate('''regions=>{const c=document.querySelector('.regional-png-canvas'),ctx=c.getContext('2d');window.__regions=regions;window.__rgbaDelta=(a,b)=>{let outside=0,inside=0,max=0;for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){const i=(y*c.width+x)*4,allowed=Object.values(regions).some(r=>x>=r.x&&x<r.x+r.width&&y>=r.y&&y<r.y+r.height);let d=0;for(let k=0;k<4;k++)d=Math.max(d,Math.abs(a[i+k]-b[i+k]));if(!d)continue;max=Math.max(max,d);if(allowed)inside++;else outside++;}return {outside,inside,maxChannelDelta:max};};const first=ctx.getImageData(0,0,c.width,c.height).data,second=ctx.getImageData(0,0,c.width,c.height).data,third=ctx.getImageData(0,0,c.width,c.height).data;window.__stableCanvasReference=third;return {first_to_second:__rgbaDelta(first,second),second_to_third:__rgbaDelta(second,third)};}''',package['animation_regions'])
            report['pure_read_controls']=result
            assert result['second_to_third']=={'outside':0,'inside':0,'maxChannelDelta':0},result
            report['checks']['second_third_immediate_pure_read_exact_stability']='passed'
            p.locator('#reply-read').click();p.wait_for_function('()=>CompanionApp.scene.getStats().mouth===1&&CompanionApp.speech.audio?.currentTime>.05')
            result=p.evaluate('''()=>{const c=document.querySelector('.regional-png-canvas');return __rgbaDelta(__stableCanvasReference,c.getContext('2d').getImageData(0,0,c.width,c.height).data);}''')
            report['actual_audio_composite_delta']=result
            assert result['outside']==0 and result['inside']>0,result
            report['checks']['actual_audio_changes_only_regions_exact_outside_zero']='passed'
            p.locator('#stop-speaking').click();p.wait_for_function('()=>!CompanionApp.speech.audio&&CompanionApp.scene.getStats().mouth===0');b.close()
        report['status']='passed'
    except Exception as error:report.update(status='failed',error=str(error));raise
    finally:
        f.tearDown();report['source_sha_after']=hashlib.sha256(source.read_bytes()).hexdigest();report['source_changed']=report['source_sha_before']!=report['source_sha_after']
        if report['source_changed']:report['status']='source_changed_not_final'
        (ROOT/'review/png-region-stable-readback-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
