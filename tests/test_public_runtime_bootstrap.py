"""Explicit bootstrap dependency seams, no models/ORT/API requests."""
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import test_compute_runtime as compute_fixture
from test_public_prefix import FakeModel, Formatter, TEMPLATE
from companion_runtime.public_preparation import PrefixQualification, PreparationKind, PreparationNotReady, PublicScope


class PublicRuntimeBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.fixture=compute_fixture.ComputeRuntimeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.app=self.fixture.app
        self.scope=PublicScope('character','appearance','session','a'*64);self.current=True;self.voice_calls=[]
        folder=Path(self.fixture.temp.name)/'voice';folder.mkdir();(folder/'kokoro-v1.0.onnx').write_bytes(b'fake model');(folder/'voices-v1.0.bin').write_bytes(b'fake voices');self.app.VOICE_DIR=folder
        original_lookup=self.app.importlib.util.find_spec
        self.addCleanup(patch.stopall);patch.object(self.app.importlib.util,'find_spec',side_effect=lambda name:object() if name=='kokoro_onnx' else original_lookup(name)).start()
        def initialize(*,with_resources=False):
            self.assertFalse(self.app.MODEL_LOCK.locked());self.voice_calls.append('initialize');self.app.LOCAL_VOICE=object();self.app.G2P=object();self.app.LOCAL_VOICE_IDENTITY=self.app._local_voice_identity(folder/'kokoro-v1.0.onnx',folder/'voices-v1.0.bin');return self.app.LocalVoiceResources(self.app.LOCAL_VOICE,self.app.G2P,self.app.LOCAL_VOICE_IDENTITY,False) if with_resources else {'initialized':True,'reused':False}
        self.app.initialize_local_voice=initialize
    def prepare(self):return self.app.prepare_public_runtime(self.scope,'public configured persona','interactive',lambda:self.current)
    def test_remote_configuration_never_constructs_local_or_probes_api(self):
        self.app.set_settings({'engine':'api','api_base':'http://127.0.0.1:9999/v1','api_model':'configured-model'})
        with patch.object(self.app,'settings',return_value={**self.app.settings(),'voice_backend':'external'}),patch.object(self.app.urllib.request,'build_opener',side_effect=AssertionError('No API probe')),patch.object(self.app,'_local_model_identity',side_effect=AssertionError('API must not stat model')):
            result=self.prepare()
        self.assertEqual(result.capabilities.kind,PreparationKind.CONFIGURED_API);self.assertEqual(result.capabilities.prefix,PrefixQualification.NOT_APPLICABLE);self.assertFalse(result.capabilities.provider_constructed);self.assertFalse(result.capabilities.status()['external_services_verified']);self.assertEqual(self.fixture.calls,[]);self.assertEqual(self.voice_calls,[]);self.assertIsNone(result.model)
    def test_remote_missing_secret_and_stale_connection_are_rejected_locally(self):
        self.app.set_settings({'engine':'api','api_base':'https://api.openai.com/v1','api_model':'configured-model'})
        with patch.object(self.app.urllib.request,'build_opener',side_effect=AssertionError('No API probe')):
            with self.assertRaisesRegex(self.app.AppError,'密钥'):self.prepare()
            self.app.set_settings({'api_key':'fake-only-not-a-real-key'})
            result=self.prepare();self.assertEqual(result.capabilities.kind,PreparationKind.CONFIGURED_API)
            self.assertFalse(result.capabilities.status()['external_services_verified'])
            (self.app.DATA/'api-key').write_text('changed-outside-connection-record')
            with self.assertRaisesRegex(self.app.AppError,'不一致'):self.prepare()
        self.assertEqual(self.fixture.calls,[])
        self.assertNotIn('fake-only',str(result.capabilities.status()))
    def test_filename_does_not_qualify_unknown_weights_but_original_provider_remains_available(self):
        named=self.app.MODEL.with_name('qwen3-4b-instruct-2507-q4_k_m.gguf');self.app.MODEL.rename(named);self.app.MODEL=named
        result=self.prepare();self.assertEqual(result.capabilities.kind,PreparationKind.LOCAL_PROVIDER_ONLY);self.assertEqual(result.capabilities.prefix,PrefixQualification.UNSUPPORTED);self.assertTrue(result.capabilities.provider_constructed);self.assertIsNone(result.prefix);self.assertEqual(self.voice_calls,['initialize']);self.assertFalse(self.app.MODEL_LOCK.locked());self.assertIn('model_identity_wall_seconds',result.timings)
    def test_qualified_default_constructs_system_only_and_publishes_no_question_or_audio(self):
        model=FakeModel();Formatter.calls=[]
        def load(**args):self.fixture.calls.append(args);return model
        self.fixture.module.Llama=load;chat=types.ModuleType('llama_cpp.llama_chat_format');chat.Jinja2ChatFormatter=Formatter
        with patch.object(self.app,'DEFAULT_MODEL_SHA256',hashlib.sha256(self.app.MODEL.read_bytes()).hexdigest()),patch('companion_runtime.public_prefix.QWEN_TEMPLATE_SHA256',hashlib.sha256(TEMPLATE.encode()).hexdigest()),patch.dict(sys.modules,{'llama_cpp.llama_chat_format':chat}):result=self.prepare()
        self.assertEqual(result.capabilities.kind,PreparationKind.LOCAL_DEFAULT);self.assertEqual(result.capabilities.prefix,PrefixQualification.PREPARED);self.assertEqual(len(model.evals),1);self.assertEqual(model.completions,[]);self.assertTrue(all(len(row[1])==1 and row[1][0]['role']=='system' for row in Formatter.calls));self.assertTrue(result.capabilities.local_voice_initialized);self.assertIs(result.voice_identity,self.app.LOCAL_VOICE_IDENTITY);self.assertFalse(self.app.MODEL_LOCK.locked());self.assertEqual(self.voice_calls,['initialize']);self.assertNotIn('n_threads_batch',self.fixture.calls[0])
    def test_cancel_before_or_after_model_load_has_no_late_voice_or_ready_result(self):
        self.current=False
        with self.assertRaises(PreparationNotReady):self.prepare()
        self.assertEqual(self.fixture.calls,[]);self.current=True
        original=self.app.load_model
        def cancel_after_load():
            result=original();self.current=False;return result
        with patch.object(self.app,'load_model',side_effect=cancel_after_load),self.assertRaises(PreparationNotReady):self.prepare()
        self.assertFalse(self.app.MODEL_LOCK.locked());self.assertEqual(self.voice_calls,[])
    def test_busy_model_is_not_queued_and_api_configuration_does_not_become_verified(self):
        self.app.MODEL_LOCK.acquire()
        try:
            with self.assertRaises(self.app.AppError):self.prepare()
            self.assertEqual(self.fixture.calls,[])
        finally:self.app.MODEL_LOCK.release()
        with patch.object(self.app,'public_model_settings',return_value={'engine':'api','api_base':'http://127.0.0.1:9999/v1','api_model':''}),self.assertRaises(self.app.AppError):self.prepare()


    def test_new_default_disk_hash_never_qualifies_an_old_loaded_instance(self):
        self.app.load_model();old=self.app.LOCAL_LLM
        self.app.MODEL.write_bytes(b'new bytes with a newly trusted fake default SHA')
        model=FakeModel();self.fixture.module.Llama=lambda **args:model
        chat=types.ModuleType('llama_cpp.llama_chat_format');chat.Jinja2ChatFormatter=Formatter
        with patch.object(self.app,'DEFAULT_MODEL_SHA256',hashlib.sha256(self.app.MODEL.read_bytes()).hexdigest()),patch('companion_runtime.public_prefix.QWEN_TEMPLATE_SHA256',hashlib.sha256(TEMPLATE.encode()).hexdigest()),patch.dict(sys.modules,{'llama_cpp.llama_chat_format':chat}):result=self.prepare()
        self.assertIs(result.model,model);self.assertIsNot(result.model,old);self.assertTrue(old.closed)
        self.assertEqual(result.capabilities.kind,PreparationKind.LOCAL_DEFAULT)

    def test_stale_loaded_identity_and_post_init_voice_swap_are_rejected(self):
        old=self.app.load_model();self.app.MODEL.write_bytes(b'changed on disk')
        with patch.object(self.app,'load_model',return_value=old),self.assertRaises(PreparationNotReady):self.prepare()
        self.assertEqual(self.voice_calls,[])
        original=self.app.initialize_local_voice
        def swapped(**kwargs):
            snapshot=original(**kwargs);self.app.LOCAL_VOICE=object();return snapshot
        with patch.object(self.app,'initialize_local_voice',side_effect=swapped):
            result=self.prepare()
        self.assertFalse(result.capabilities.local_voice_initialized);self.assertIsNone(result.voice)


if __name__=='__main__':unittest.main()
