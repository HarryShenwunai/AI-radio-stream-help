"""Multimodal wire-format and redaction tests; responses are explicit stubs."""
import base64
import json
import threading
import unittest
from unittest.mock import patch
import urllib.error

from companion_runtime.perception import OpenAICompatibleVisionProvider, PerceptionError


class Response:
    def __init__(self, value): self.value=value
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,limit): return self.value[:limit]


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.provider=OpenAICompatibleVisionProvider('http://127.0.0.1:5555/v1','explicit-image-model','SECRET')
    def invoke(self,raw):
        with patch('urllib.request.OpenerDirector.open',return_value=Response(raw)) as request:
            text=self.provider.describe(b'jpeg-synthetic-protocol-data','image/jpeg','Look here',threading.Event())
        return text,request
    def test_multimodal_payload_and_auth(self):
        result,request=self.invoke(json.dumps({'choices':[{'message':{'content':'explicit synthetic answer'}}]}).encode())
        self.assertEqual(result,'explicit synthetic answer')
        wire=request.call_args.args[0]
        self.assertEqual(wire.full_url,'http://127.0.0.1:5555/v1/chat/completions')
        self.assertEqual(wire.get_header('Authorization'),'Bearer SECRET')
        data=json.loads(wire.data)
        self.assertEqual(data['model'],'explicit-image-model')
        self.assertFalse(data['stream']);self.assertEqual(data['max_tokens'],512)
        messages=data['messages'];self.assertEqual(len(messages),2)
        self.assertIn('untrusted',messages[0]['content'])
        frame=messages[1]['content'][1]['image_url']['url']
        self.assertEqual(base64.b64decode(frame.split(',')[1]),b'jpeg-synthetic-protocol-data')
        self.assertNotIn('tools',data)
    def test_bounded_description(self):
        result,_=self.invoke(json.dumps({'choices':[{'message':{'content':'a'*3000}}]}).encode())
        self.assertEqual(len(result),2000)
    def test_invalid_bodies_are_sanitized(self):
        for raw in (b'SECRET provider page',b'{}',b'{"choices":[]}',
                    b'{"choices":[{"message":{"content":[]}}]}',b'x'*524289):
            with self.subTest(raw_size=len(raw)):
                with self.assertRaises(PerceptionError) as caught:self.invoke(raw)
                self.assertEqual(caught.exception.code,'provider_failed')
                self.assertNotIn('SECRET',str(caught.exception))
    def test_network_exception_is_sanitized(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=urllib.error.URLError('SECRET URL and body')):
            with self.assertRaises(PerceptionError) as caught:
                self.provider.describe(b'private','image/jpeg','',threading.Event())
        self.assertNotIn('SECRET',str(caught.exception))
    def test_late_cancel_drops_provider_reply(self):
        cancel=threading.Event()
        class LateResponse(Response):
            def read(self,limit):
                cancel.set();return super().read(limit)
        with patch('urllib.request.OpenerDirector.open',return_value=LateResponse(
                b'{"choices":[{"message":{"content":"late private content"}}]}')):
            with self.assertRaises(PerceptionError) as caught:
                self.provider.describe(b'private','image/jpeg','',cancel)
        self.assertEqual(caught.exception.code,'cancelled')


if __name__=='__main__':unittest.main()
