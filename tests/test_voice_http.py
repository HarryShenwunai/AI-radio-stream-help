"""Real loopback HTTP transport with a WAV fixture, not a GPT-SoVITS model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from companion_runtime.voice import ExternalTTS,ExternalTTSConfig,VoiceCancelled,VoiceError
from test_voice import wav_bytes


class VoiceHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests=[];cls.stop=threading.Event()
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cls.requests.append((self.path,data,self.headers.get('Authorization')))
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location',f'http://127.0.0.1:{self.server.server_port}/leak');self.end_headers();return
                if self.path=='/error':body=b'{"error":"fixture"}'
                else:body=wav_bytes()
                self.send_response(200);self.send_header('Content-Type','audio/wav' if self.path!='/error' else 'application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
                if self.path=='/cancel':cls.stop.set()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.worker.join(2)
    def setUp(self):self.requests.clear();self.stop.clear()
    def provider(self,path):
        return ExternalTTS(ExternalTTSConfig(f'http://127.0.0.1:{self.server.server_port}{path}','owner.wav',api_key='fixture-only'))
    def test_actual_request_and_complete_wav_response(self):
        self.assertEqual(self.provider('/tts').synthesize('你好'),wav_bytes())
        self.assertEqual(self.requests[0][0],'/tts');self.assertEqual(self.requests[0][1]['text'],'你好')
        self.assertEqual(self.requests[0][1]['ref_audio_path'],'owner.wav');self.assertFalse(self.requests[0][1]['streaming_mode'])
    def test_redirect_is_rejected_without_forwarding_credentials(self):
        with self.assertRaises(VoiceError) as error:self.provider('/redirect').synthesize('你好')
        self.assertEqual(error.exception.code,'tts_redirect');self.assertEqual(len(self.requests),1)
        self.assertEqual(self.requests[0][2],'Bearer fixture-only')
    def test_provider_error_body_is_not_treated_as_audio(self):
        with self.assertRaises(VoiceError) as error:self.provider('/error').synthesize('你好')
        self.assertEqual(error.exception.code,'tts_invalid_audio')
    def test_cancellation_after_provider_receives_request_discards_response(self):
        with self.assertRaises(VoiceCancelled):self.provider('/cancel').synthesize('你好',self.stop)
        self.assertEqual(len(self.requests),1)

if __name__=='__main__':unittest.main()
