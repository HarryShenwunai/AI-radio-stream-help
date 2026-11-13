"""Local audio/provider fixtures only; real ASR smoke is recorded separately."""
from pathlib import Path
import io
import json
import struct
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import wave

from companion_runtime.voice import (AudioLimits, ExternalTTS, ExternalTTSConfig, LocalASR,
                                     VoiceCancelled, VoiceError, download_asr_model,
                                     validate_tts_endpoint, validate_wav)


def wav_bytes(seconds=.2, rate=16000, channels=1, width=2):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(channels);wav.setsampwidth(width);wav.setframerate(rate)
        wav.writeframes(b'\0' * (int(seconds * rate) * width * channels))
    return out.getvalue()


class AudioValidationTests(unittest.TestCase):
    def test_valid_mono_pcm16_metadata(self):
        value=validate_wav(wav_bytes(.25, 24000))
        self.assertEqual(value.duration_seconds,.25);self.assertEqual(value.pcm_bytes,12000)

    def test_wrong_types_and_disguised_containers(self):
        for value in [bytearray(wav_bytes()),'RIFF',b'OggS'+b'\0'*80,b'RIFF'+b'\0'*80]:
            with self.subTest(value=type(value).__name__),self.assertRaises(VoiceError):validate_wav(value)

    def test_size_and_duration_both_enforced(self):
        with self.assertRaises(VoiceError) as error:validate_wav(wav_bytes(),AudioLimits(max_bytes=100))
        self.assertEqual(error.exception.status,413)
        with self.assertRaises(VoiceError):validate_wav(wav_bytes(.3),AudioLimits(max_seconds=.25))
        with self.assertRaises(VoiceError):validate_wav(wav_bytes(.02))

    def test_stereo_or_wrong_width_or_rate_rejected_for_upload(self):
        for args in [{'channels':2},{'width':1},{'rate':11025}]:
            with self.subTest(args=args),self.assertRaises(VoiceError):validate_wav(wav_bytes(**args))

    def test_truncation_and_appended_data_rejected(self):
        audio=wav_bytes()
        for damaged in [audio[:-1],audio+b'extra',audio[:42]]:
            with self.assertRaises(VoiceError):validate_wav(damaged)

    def test_forged_frame_alignment_rejected(self):
        audio=bytearray(wav_bytes());struct.pack_into('<I',audio,40,len(audio)-44-1)
        with self.assertRaises(VoiceError):validate_wav(bytes(audio))

    def test_duplicate_data_chunk_rejected(self):
        data=wav_bytes();data=data+b'data'+struct.pack('<I',2)+b'\0\0'
        data=data[:4]+struct.pack('<I',len(data)-8)+data[8:]
        with self.assertRaises(VoiceError):validate_wav(data)

    def test_float_format_rejected(self):
        audio=bytearray(wav_bytes());struct.pack_into('<H',audio,20,3)
        with self.assertRaises(VoiceError):validate_wav(bytes(audio))

    def test_invalid_pcm_byte_rate_and_block_alignment_rejected(self):
        for offset,value in [(28,1),(32,7)]:
            audio=bytearray(wav_bytes())
            struct.pack_into('<I' if offset==28 else '<H',audio,offset,value)
            with self.assertRaises(VoiceError):validate_wav(bytes(audio))

    def test_limits_are_not_bool_nan_or_unbounded(self):
        for kw in [{'max_bytes':True},{'max_seconds':float('nan')},{'channels':(3,)},{'sample_rates':()}]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):AudioLimits(**kw)


class ASRFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for name in ('model.bin','config.json','tokenizer.json','vocabulary.txt'):(self.root/name).touch()
        self.calls=[]
        outer=self
        class Model:
            def __init__(self,path,**kwargs):outer.calls.append(('load',path,kwargs))
            def transcribe(self,audio,**kwargs):
                outer.calls.append(('transcribe',kwargs))
                return iter([types.SimpleNamespace(start=0.,end=.2,text='你好。')]),types.SimpleNamespace(language='zh')
        self.Model=Model
    def tearDown(self):self.tmp.cleanup()
    def test_actual_callback_results_and_local_only_model_load(self):
        asr=LocalASR(self.root,model_factory=self.Model)
        result=asr.transcribe_wav(wav_bytes())
        self.assertEqual(result.text,'你好。');self.assertEqual(result.device,'cpu')
        self.assertTrue(self.calls[0][2]['local_files_only']);self.assertEqual(self.calls[1][1]['language'],'zh')
        self.assertFalse(self.calls[1][1]['condition_on_previous_text']);self.assertTrue(self.calls[1][1]['vad_filter'])
        asr.transcribe_wav(wav_bytes());self.assertEqual(sum(x[0]=='load' for x in self.calls),1)

    def test_invalid_audio_rejected_before_loading(self):
        with self.assertRaises(VoiceError):LocalASR(self.root,model_factory=self.Model).transcribe_wav(b'not audio')
        self.assertEqual(self.calls,[])

    def test_pre_cancel_does_not_load_or_transcribe(self):
        stop=threading.Event();stop.set()
        with self.assertRaises(VoiceCancelled):LocalASR(self.root,model_factory=self.Model).transcribe_wav(wav_bytes(),stop)
        self.assertEqual(self.calls,[])

    def test_native_work_returned_after_cancel_is_discarded(self):
        stop=threading.Event()
        class Model(self.Model):
            def transcribe(self,audio,**kwargs):
                def parts():
                    stop.set();yield types.SimpleNamespace(start=0.,end=.2,text='不能返回')
                return parts(),types.SimpleNamespace(language='zh')
        with self.assertRaises(VoiceCancelled):LocalASR(self.root,model_factory=Model).transcribe_wav(wav_bytes(),stop)

    def test_concurrency_is_bounded(self):
        entered,release=threading.Event(),threading.Event();results=[]
        class Model(self.Model):
            def transcribe(self,audio,**kwargs):
                entered.set();release.wait(3)
                return super().transcribe(audio,**kwargs)
        asr=LocalASR(self.root,model_factory=Model)
        worker=threading.Thread(target=lambda:results.append(asr.transcribe_wav(wav_bytes())))
        worker.start();self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(VoiceError) as error:asr.transcribe_wav(wav_bytes())
            self.assertEqual(error.exception.code,'asr_busy')
        finally:release.set();worker.join(3)
        self.assertFalse(worker.is_alive());self.assertEqual(len(results),1)

    def test_silence_failure_and_lock_recovery(self):
        class Empty(self.Model):
            def transcribe(self,*args,**kwargs):return iter([]),types.SimpleNamespace(language='zh')
        asr=LocalASR(self.root,model_factory=Empty)
        for unused in range(2):
            with self.assertRaises(VoiceError) as error:asr.transcribe_wav(wav_bytes())
            self.assertEqual(error.exception.code,'no_speech')

    def test_missing_dependency_and_model_have_diagnostics(self):
        with patch('companion_runtime.voice.importlib.util.find_spec',return_value=None):
            status=LocalASR(self.root).diagnostics();self.assertFalse(status['ready']);self.assertIn('组件',status['reason'])
        (self.root/'model.bin').unlink();status=LocalASR(self.root,model_factory=self.Model).diagnostics()
        self.assertFalse(status['ready']);self.assertFalse(status['model_present'])

    def test_invalid_timestamps_and_text_budget_rejected(self):
        class Bad(self.Model):
            def transcribe(self,audio,**kwargs):
                return iter([types.SimpleNamespace(start=0.,end=float('nan'),text='a')]),types.SimpleNamespace(language='zh')
        with self.assertRaises(VoiceError) as error:LocalASR(self.root,model_factory=Bad).transcribe_wav(wav_bytes())
        self.assertEqual(error.exception.code,'asr_invalid_result')
        class Huge(self.Model):
            def transcribe(self,audio,**kwargs):
                return iter([types.SimpleNamespace(start=0.,end=.2,text='a'*4001)]),types.SimpleNamespace(language='zh')
        with self.assertRaises(VoiceError):LocalASR(self.root,model_factory=Huge).transcribe_wav(wav_bytes())

    def test_av19_regression_is_detected_before_saying_ready(self):
        with patch('companion_runtime.voice.importlib.util.find_spec',return_value=object()), patch('companion_runtime.voice.importlib.metadata.version',side_effect=lambda name:'19.0.2' if name=='av' else '1.2.1'):
            status=LocalASR(self.root).diagnostics()
        self.assertFalse(status['ready']);self.assertIn('PyAV',status['reason'])

    def test_owner_model_choice_is_not_arbitrary_download_url(self):
        with self.assertRaises(VoiceError):download_asr_model('https://attacker.invalid/model',self.root)
        with self.assertRaises(ValueError):LocalASR(self.root,device='arbitrary')


class Response(io.BytesIO):
    def __init__(self,body,headers=None,on_read=None):
        super().__init__(body);self.headers=headers or {};self.on_read=on_read
    def read1(self,n=-1):
        if self.on_read:self.on_read()
        return self.read(n)


class Opener:
    def __init__(self,body,headers=None,on_read=None):self.body,self.headers,self.on_read=body,headers,on_read;self.requests=[]
    def open(self,request,timeout):
        self.requests.append((request,timeout));return Response(self.body,self.headers,self.on_read)


class ExternalTTSFixtureTests(unittest.TestCase):
    def config(self,**kwargs):return ExternalTTSConfig('http://127.0.0.1:9880/tts','owner-approved-reference.wav',**kwargs)
    def test_url_policy(self):
        for url in ['file:///etc/passwd','http://remote.invalid/tts','http://0.0.0.0/tts','https://169.254.169.254/tts','https://user:secret@service.invalid/tts','https://host/tts?model=evil','https://host/tts#frag']:
            with self.subTest(url=url),self.assertRaises(VoiceError):validate_tts_endpoint(url)
        self.assertEqual(validate_tts_endpoint('https://owner.example/tts'),'https://owner.example/tts')
        self.assertEqual(validate_tts_endpoint('http://[::1]:9880/tts'),'http://[::1]:9880/tts')

    def test_owner_config_and_text_only_payload(self):
        audio=wav_bytes(channels=2);opener=Opener(audio)
        result=ExternalTTS(self.config(),opener=opener).synthesize('真实模型生成的这句话。')
        self.assertEqual(result,audio)
        request,timeout=opener.requests[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,'http://127.0.0.1:9880/tts');self.assertFalse(body['streaming_mode'])
        self.assertEqual(body['ref_audio_path'],'owner-approved-reference.wav');self.assertEqual(body['media_type'],'wav')

    def test_malformed_or_wrong_container_never_returned_as_audio(self):
        for data in [b'{"error":"bad"}',b'OggS'+b'\0'*60,wav_bytes()[:-3]]:
            with self.subTest(data=data[:5]),self.assertRaises(VoiceError) as error:ExternalTTS(self.config(),opener=Opener(data)).synthesize('你好')
            self.assertEqual(error.exception.code,'tts_invalid_audio');self.assertEqual(error.exception.status,502)

    def test_header_and_stream_byte_limits(self):
        for opener in [Opener(wav_bytes(),{'Content-Length':'999999999'}),Opener(b'a'*101),Opener(wav_bytes(),{'Content-Length':'invalid'})]:
            with self.assertRaises(VoiceError) as error:ExternalTTS(self.config(max_bytes=100),opener=opener).synthesize('你好')
            self.assertEqual(error.exception.code,'tts_response_too_large')

    def test_content_length_mismatch(self):
        audio=wav_bytes()
        with self.assertRaises(VoiceError) as error:ExternalTTS(self.config(),opener=Opener(audio,{'Content-Length':str(len(audio)+3)})).synthesize('你好')
        self.assertEqual(error.exception.code,'tts_invalid_audio')

    def test_cancelled_before_or_during_response_not_returned(self):
        stop=threading.Event();stop.set();opener=Opener(wav_bytes())
        with self.assertRaises(VoiceCancelled):ExternalTTS(self.config(),opener=opener).synthesize('你好',stop)
        self.assertEqual(opener.requests,[])
        stop.clear();opener=Opener(wav_bytes(),on_read=stop.set)
        with self.assertRaises(VoiceCancelled):ExternalTTS(self.config(),opener=opener).synthesize('你好',stop)

    def test_redirect_handler_never_forwards_credentials(self):
        from companion_runtime.voice import _NoRedirect
        with self.assertRaises(VoiceError) as error:_NoRedirect().redirect_request(None,None,302,'redirect',{},'https://elsewhere.invalid')
        self.assertEqual(error.exception.code,'tts_redirect')

    def test_missing_reference_not_silently_enabled(self):
        with self.assertRaises(VoiceError):ExternalTTSConfig('http://localhost:9880/tts','')
        with self.assertRaises(ValueError):self.config(timeout_seconds=float('inf'))

if __name__=='__main__':unittest.main()
