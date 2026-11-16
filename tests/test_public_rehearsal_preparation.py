"""Owner HTTP readiness and full generator lifetime; fake local provider only."""
import hashlib
import importlib.machinery
import json
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

import test_character_http
from test_public_prefix import FakeModel, Formatter, TEMPLATE


class StreamingModel(FakeModel):
    def tokenize(self,data,*,add_bos=False,special=True):
        return super().tokenize(data,add_bos=add_bos,special=special)


class PublicRehearsalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.f=test_character_http.CharacterHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.app=self.f.app;self.model=StreamingModel();Formatter.calls=[]
        self.app.MODEL=Path(self.f.tmp.name)/'fake-model.gguf';self.app.MODEL.write_bytes(b'fake-model-no-native-provider')
        self.app.set_settings({'voice_backend':'system'})
        self.service=self.app.integrations();self.addCleanup(patch.stopall)
        chat=types.ModuleType('llama_cpp.llama_chat_format');chat.Jinja2ChatFormatter=Formatter
        patch.dict(sys.modules,{'llama_cpp':types.SimpleNamespace(__spec__=importlib.machinery.ModuleSpec('llama_cpp',loader=None),Llama=lambda **kwargs:self.model,llama_supports_gpu_offload=lambda:False),'llama_cpp.llama_chat_format':chat}).start()
        patch.object(self.app,'DEFAULT_MODEL_SHA256',hashlib.sha256(self.app.MODEL.read_bytes()).hexdigest()).start()
        patch('companion_runtime.public_prefix.QWEN_TEMPLATE_SHA256',hashlib.sha256(TEMPLATE.encode()).hexdigest()).start()
    def start(self,action='start',expected=200):
        return self.f.post('connectors/bili/rehearsal',{'action':action,'confirm_local':True},expected=expected)
    def message(self,text,expected=200):return self.f.post('connectors/bili/rehearsal',{'action':'message','text':text},expected=expected)
    def reply(self,text):
        self.message(text);event=self.service.public_events()[-1]
        return self.f.post('connectors/bili/reply',{'event_id':event['event_id']})
    def test_two_unseen_questions_use_actual_stream_path_and_restore_guard(self):
        self.start();self.assertEqual(len(self.model.evals),1);self.assertEqual(self.model.completions,[])
        for question in ('UNSEEN_INPUT_ONE','DIFFERENT_UNSEEN_INPUT_TWO'):
            result=self.reply(question);self.assertEqual(result['state'],'review')
            self.assertTrue(self.model.completions[-1]['stream']);self.assertEqual(self.model.completions[-1]['max_tokens'],160)
            self.assertNotIn('create_completion',vars(self.model))
        self.assertEqual(len(self.model.completions),2);self.assertNotEqual(self.model.completions[0]['prompt'],self.model.completions[1]['prompt'])
        projected=self.f.state()['public_preparation'];self.assertEqual(projected['state'],'ready')
        self.assertNotIn('UNSEEN',json.dumps(projected));self.assertNotIn('api_key',json.dumps(projected))
        self.assertIsNone(self.service.output.token);self.assertEqual(self.f.audio_calls,[])
    def test_preparing_has_no_ingress_and_stop_rejects_late_ready(self):
        entered=threading.Event();release=threading.Event();self.f.pending_releases.append(release)
        original=self.app.prepare_public_runtime
        def blocked(*args):entered.set();release.wait(3);return original(*args)
        responses=[]
        with patch.object(self.app,'prepare_public_runtime',side_effect=blocked):
            worker=threading.Thread(target=lambda:responses.append(self.f.request('POST','/api/connectors/bili/rehearsal',{'action':'start','confirm_local':True})))
            self.f.pending_threads.append(worker);worker.start();self.assertTrue(entered.wait(2))
            self.assertIsNone(self.service._rehearsal);self.message('MUST_NOT_ENTER',expected=409)
            self.assertEqual(self.service.public_events(),[]);self.assertEqual(self.service.output.jobs,{})
            self.start(expected=409);self.assertEqual(self.service.preparation.status()['state'],'preparing')
            self.f.post('connectors/bili/stop',{});release.set();worker.join(3)
        self.assertEqual(responses[0][0],409);self.assertEqual(self.service.preparation.status()['state'],'cancelled')
        self.assertIsNone(self.service._rehearsal);self.assertFalse(self.service._rehearsal_requested);self.assertEqual(self.model.completions,[])
    def test_context_retry_keeps_material_and_config_or_private_use_revokes(self):
        self.start();self.f.post('connectors/bili/material',{'text':'EXPLICIT_PUBLIC_MATERIAL','allow_public':True})
        self.message('no ingress while context is stale',expected=409)
        self.start('prepare');self.assertEqual(self.service.output.material['text'],'EXPLICIT_PUBLIC_MATERIAL')
        self.app.set_settings({'local_context':2048});self.message('no stale model config',expected=409)
        self.start('prepare')
        with self.app.MODEL_LOCK:
            self.app.generate_once(self.app.settings(),[{'role':'system','content':'PRIVATE_CONTEXT_CANARY'},{'role':'user','content':'private request'}])
        self.assertEqual(self.service.preparation.status()['reason'],'private_turn');self.message('no after private',expected=409)
        self.assertNotIn('PRIVATE_CONTEXT_CANARY',json.dumps(self.service.status()))
    def test_first_start_retains_previously_applied_context_and_owner_refresh_revokes_file_change(self):
        self.f.post('connectors/bili/material',{'text':'FIRST_PUBLIC_MATERIAL','allow_public':True})
        self.f.post('connectors/bili/context',{'topic':'FIRST_PUBLIC_TOPIC','mode':'strict','allow_public':True})
        self.start();self.assertEqual(self.service.output.material['text'],'FIRST_PUBLIC_MATERIAL')
        self.assertEqual(self.service.output.topic,'FIRST_PUBLIC_TOPIC');self.assertEqual(self.service.output.interaction_mode,'strict')
        self.assertEqual(self.service.preparation.status()['state'],'ready')
        self.app.MODEL.write_bytes(b'replaced without settings API')
        state=self.f.state();self.assertEqual(state['public_preparation']['state'],'cancelled')
        self.assertEqual(state['public_preparation']['reason'],'configuration_changed')
        self.assertEqual(self.service.output.material['text'],'FIRST_PUBLIC_MATERIAL')
        self.message('not admitted after file replacement',expected=409);self.assertEqual(self.service.public_events(),[])
    def test_cancel_during_stream_rejects_result_and_restores_generator_guard(self):
        self.start();self.message('UNSEEN_CANCELLATION_INPUT');event=self.service.public_events()[0]
        original=self.model.create_completion
        def cancelling(**kwargs):
            self.model.completions.append(kwargs)
            def stream():
                yield {'choices':[{'delta':{'content':'partial'},'finish_reason':None}]}
                self.app.connector_request('bili/stop',{})
                yield {'choices':[{'delta':{'content':'must not enter'},'finish_reason':'stop'}]}
            return stream()
        self.model.create_completion=cancelling
        self.f.post('connectors/bili/reply',{'event_id':event['event_id']},expected=409)
        self.assertIs(self.model.create_completion,cancelling);self.assertIsNone(self.service.public_generation)
        self.assertFalse(self.app.MODEL_LOCK.locked());self.assertFalse(self.app.TTS_LOCK.locked())
        self.assertTrue(all(job['state']!='review' for job in self.service.output.jobs.values()))
        self.model.create_completion=original


if __name__=='__main__':unittest.main()
