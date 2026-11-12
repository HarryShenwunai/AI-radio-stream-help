"""Real Chromium MediaRecorder/resampling; synthetic input, fixture transcription.
No real microphone, external service, model quality or target hardware claim.
"""
from pathlib import Path
import base64
import io
import json
import math
import struct
import tempfile
import wave
from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests

ROOT=Path(__file__).resolve().parents[1]

def main():
    fixture=CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
    fixture.setUp()
    report={'date':'2026-11-12','status':'RUNNING','checks':{},'real_microphone':False,'asr_model':'fixture only','external_connections':0}
    captured=[]
    original_status=fixture.app.voice_status
    fixture.app.voice_status=lambda:{**original_status(),'asr':{'ready':True,'reason':'synthetic fixture','max_audio_seconds':60}}
    def transcribe(payload):
        data=base64.b64decode(payload['audio_base64'])
        with wave.open(io.BytesIO(data),'rb') as wav:
            info={'rate':wav.getframerate(),'channels':wav.getnchannels(),'width':wav.getsampwidth(),'frames':wav.getnframes(),'duration':wav.getnframes()/wav.getframerate()}
            samples=struct.unpack('<'+'h'*wav.getnframes(),wav.readframes(wav.getnframes()))
            info['peak']=max(abs(x) for x in samples)
        captured.append(info)
        return {'text':'本机录音测试草稿','character_id':payload['expected_character_id'],'operation_id':payload['operation_id']}
    fixture.app.transcribe_payload=transcribe
    try:
        with tempfile.TemporaryDirectory(prefix='synthetic-mic-') as directory:
            tone=Path(directory)/'synthetic-input.wav'
            with wave.open(str(tone),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
                wav.writeframes(b''.join(struct.pack('<h',int(2500*math.sin(i*2*math.pi*440/48000))) for i in range(48000*8)))
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',f'--use-file-for-fake-audio-capture={tone}'])
                context=browser.new_context(permissions=['microphone'],viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{fixture.server.server_port}')
                page.locator('#character-select option').first.wait_for(state='attached')
                assert page.evaluate('()=>inputMode')=='local'
                report['checks']['local_input_is_default']='passed'
                page.locator('#mic').click()
                page.wait_for_function("()=>localInput.phase==='recording'")
                page.wait_for_timeout(1700);page.locator('#mic').click()
                page.wait_for_function("()=>localInput.phase==='idle'&&document.querySelector('#message-input').value.length>0")
                assert len(captured)==1 and captured[0]['rate']==16000 and captured[0]['channels']==1 and captured[0]['width']==2 and captured[0]['peak']>0
                assert 0<captured[0]['duration']<=60
                report['checks']['actual_mediarecorder_decode_resample_and_pcm_upload']='passed';report['pcm_observation']=captured[0]
                assert page.locator('#message-input').input_value()=='本机录音测试草稿' and not fixture.model_calls
                report['checks']['recognition_fills_draft_without_sending_chat']='passed'
                page.locator('#mic').click();page.wait_for_function("()=>localInput.phase==='recording'")
                page.evaluate("()=>{window.companionDesktopHidden=true;window.dispatchEvent(new Event('companion:desktop-pause'));}")
                assert page.evaluate("()=>localInput.phase==='idle'")
                page.wait_for_timeout(500);assert len(captured)==1
                report['checks']['native_hidden_recording_is_cancelled_without_upload']='passed'
                assert not errors
                report['checks']['javascript_runtime']='passed';report['javascript_errors']=errors
                browser.close()
        report['status']='passed'
    finally:
        fixture.tearDown();(ROOT/'review/voice-input-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
