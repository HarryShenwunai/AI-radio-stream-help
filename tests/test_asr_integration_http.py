"""Application ASR/runtime HTTP boundaries with an explicitly fake recognizer.

HTTP, WAV validation, SQLite and cancellation races are real. Recognition
accuracy, microphone access and target hardware are separate acceptance gates.
"""
import base64
import io
import threading
import unittest
import wave

import test_character_http as character_http
from companion_runtime.voice import Transcription, validate_wav


def recording():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*8000)
    return stream.getvalue()


class ASRIntegrationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=character_http.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
        self.fixture.setUp()

    def tearDown(self):self.fixture.tearDown()

    def payload(self,operation='independent-asr-operation'):
        return {'audio_base64':base64.b64encode(recording()).decode(),'operation_id':operation,
                'expected_character_id':self.fixture.state()['active_character_id']}

    def fake_recognizer(self,entered=None,release=None):
        calls=[]
        class FakeASR:
            def __init__(self,*args,**kwargs):pass
            def diagnostics(self):return {'ready':True,'local_only':True,'recording_uploaded_to_cloud':False}
            def transcribe_wav(self,audio,cancel=None):
                validate_wav(audio);calls.append(audio)
                if entered:entered.set()
                if release and not release.wait(8):raise AssertionError('test ASR release timed out')
                # Ignore cancel deliberately; application must reject late work.
                return Transcription('ASR_PRIVATE_CANARY',(),.5,'zh',.01)
        self.fixture.app.LocalASR=FakeASR
        return calls

    def test_voice_and_hardware_status_require_owner_cookie_and_hide_key(self):
        f=self.fixture
        f.post('settings',{'api_key':'fake-status-secret','expected_character_id':f.initial_id})
        for endpoint in ['voice/status','runtime/diagnostics']:
            with self.subTest(endpoint=endpoint):
                self.assertIn(f.request('GET','/api/'+endpoint,auth=False)[0],(401,403))
                status,_,body=f.request('GET','/api/'+endpoint)
                self.assertEqual(status,200,body);self.assertNotIn(b'fake-status-secret',body)

    def test_invalid_asr_device_precision_pairs_fail_before_saving(self):
        f=self.fixture;before=f.state()['settings']
        for device,precision in [('cpu','float16'),('cuda','int8')]:
            with self.subTest(device=device,precision=precision):
                f.post('settings',{'asr_device':device,'asr_compute_type':precision,'expected_character_id':f.initial_id},expected=400)
                after=f.state()['settings']
                self.assertEqual(after['asr_device'],before['asr_device'])
                self.assertEqual(after['asr_compute_type'],before['asr_compute_type'])
                self.assertEqual(f.request('GET','/api/voice/status')[0],200)

    def test_device_only_change_selects_compatible_default(self):
        f=self.fixture
        f.post('settings',{'asr_device':'cuda','expected_character_id':f.initial_id})
        self.assertEqual(f.state()['settings']['asr_compute_type'],'float16')
        f.post('settings',{'asr_device':'cpu','expected_character_id':f.initial_id})
        self.assertEqual(f.state()['settings']['asr_compute_type'],'int8')

    def test_runtime_shared_across_roles_but_personality_is_not(self):
        f=self.fixture
        f.post('settings',{'local_compute':'auto','local_gpu_layers':8,'local_context':2048,
                          'voice_backend':'system','personality':'IDENTITY_ONLY_PERSONALITY','expected_character_id':f.initial_id})
        f.create('另一运行配置身份');settings=f.state()['settings']
        self.assertEqual(settings['local_compute'],'auto');self.assertEqual(settings['local_gpu_layers'],8)
        self.assertEqual(settings['voice_backend'],'system');self.assertNotEqual(settings['personality'],'IDENTITY_ONLY_PERSONALITY')

    def test_invalid_wav_and_stale_identity_do_not_start_recognizer(self):
        f=self.fixture;calls=self.fake_recognizer();payload=self.payload()
        payload['audio_base64']=base64.b64encode(b'not a WAV').decode();f.post('transcribe',payload,expected=415)
        old=f.initial_id;f.create('新录音身份');payload=self.payload();payload['expected_character_id']=old
        f.post('transcribe',payload,expected=409);self.assertEqual(calls,[])

    def test_transcript_is_returned_without_persisting_chat_or_memory(self):
        f=self.fixture;self.fake_recognizer();result=f.post('transcribe',self.payload())
        self.assertEqual(result['text'],'ASR_PRIVATE_CANARY');self.assertEqual(result['character_id'],f.initial_id)
        self.assertNotIn('ASR_PRIVATE_CANARY',str(f.state()['messages']))
        self.assertNotIn('ASR_PRIVATE_CANARY',str(f.state()['memories']));self.assertEqual(f.app.VOICE_OPERATIONS,{})

    def test_switch_during_recognition_discards_late_result(self):
        f=self.fixture;entered,release=threading.Event(),threading.Event()
        f.pending_releases.append(release);self.fake_recognizer(entered,release);result=[];payload=self.payload()
        worker=threading.Thread(target=lambda:result.append(f.request('POST','/api/transcribe',payload)))
        f.pending_threads.append(worker);worker.start();self.assertTrue(entered.wait(3));f.create('识别途中切换')
        release.set();worker.join(4);self.assertFalse(worker.is_alive());self.assertEqual(result[0][0],409,result)
        self.assertNotIn(b'ASR_PRIVATE_CANARY',result[0][2]);self.assertEqual(f.app.VOICE_OPERATIONS,{})

    def test_stop_rejects_uncancellable_recognizer_and_releases_single_flight(self):
        f=self.fixture;entered,release=threading.Event(),threading.Event()
        f.pending_releases.append(release);self.fake_recognizer(entered,release);result=[];payload=self.payload('cancel-this-asr')
        worker=threading.Thread(target=lambda:result.append(f.request('POST','/api/transcribe',payload)))
        f.pending_threads.append(worker);worker.start();self.assertTrue(entered.wait(3))
        f.post('transcribe',self.payload('second-asr'),expected=409)
        stopped=f.post('transcribe/stop',{'operation_id':'cancel-this-asr','expected_character_id':f.initial_id})
        self.assertTrue(stopped['invalidated']);release.set();worker.join(4)
        self.assertEqual(result[0][0],409,result);self.assertNotIn(b'ASR_PRIVATE_CANARY',result[0][2])
        self.assertEqual(f.app.VOICE_OPERATIONS,{});self.fake_recognizer()
        self.assertEqual(f.post('transcribe',self.payload('after-cancel'))['text'],'ASR_PRIVATE_CANARY')

    def test_stop_before_upload_registration_prevents_later_recognition(self):
        f=self.fixture;calls=self.fake_recognizer()
        f.post('transcribe/stop',{'operation_id':'stop-arrived-first','expected_character_id':f.initial_id})
        f.post('transcribe',self.payload('stop-arrived-first'),expected=409)
        self.assertEqual(calls,[]);self.assertEqual(f.app.VOICE_OPERATIONS,{})


if __name__=='__main__':unittest.main(verbosity=2)
