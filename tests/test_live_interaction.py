"""Scene-specific public context and authorization, using actual HTTP boundaries."""
import json
import time
from types import SimpleNamespace
import unittest
from companion_runtime.live import LiveBinding, LiveIngress
from companion_runtime.live_output import LiveOutput, OutputError
from test_character_http import CharacterHTTPTests

class LiveSceneStateTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.o=LiveOutput(clock=lambda:self.now)
  self.event={'source':'bilibili-open-live','room_id':'123','event_id':'e1','text':'你好','received_at':100.,'expires_at':130.}
 def test_default_without_material_and_strict_opt_in(self):
  self.assertEqual(self.o.begin(self.event)['interaction_mode'],'interactive')
  self.o.set_context({'mode':'strict'})
  with self.assertRaisesRegex(OutputError,'教材'):self.o.begin({**self.event,'event_id':'e2'})
  self.o.set_material('公开材料',True)
  self.assertEqual(self.o.begin({**self.event,'event_id':'e2'})['material'],'公开材料')
 def test_topic_requires_consent_and_invalid_change_keeps_task(self):
  job=self.o.begin(self.event)
  with self.assertRaises(OutputError):self.o.set_context({'topic':'秘密背景'})
  with self.assertRaises(OutputError):self.o.set_context({'mode':[]})
  self.assertEqual(self.o.jobs[job['id']]['state'],'generating')
 def test_topic_switch_and_host_talking_cancel_late_result(self):
  job=self.o.begin(self.event);self.now=101
  self.o.set_context({'topic':'换成音乐','allow_public':True})
  with self.assertRaises(OutputError):self.o.finish(job['id'],'旧主题','late')
  with self.assertRaises(OutputError):self.o.begin({**self.event,'event_id':'e2'})
  fresh={**self.event,'event_id':'e3','received_at':101.}
  self.o.set_context({'host_talking':True})
  with self.assertRaises(OutputError):self.o.begin(fresh)
  self.o.set_context({'host_talking':False});self.o.begin(fresh)
 def test_recent_context_excludes_other_rooms_expired_and_previous_topic(self):
  recent=[{**self.event,'event_id':'ok','text':'聊音乐'}, {**self.event,'event_id':'wrong','room_id':'999'},
          {**self.event,'event_id':'expired','expires_at':99.}]
  job=self.o.begin({**self.event,'event_id':'next'},recent)
  self.assertEqual(job['recent'],[{'event_id':'ok','text':'聊音乐'}])
  self.assertNotIn('recent',self.o.public(job))

class LiveSceneHTTPTests(unittest.TestCase):
 def setUp(self):
  self.f=CharacterHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.s=self.f.app.integrations();self.ingress=LiveIngress(LiveBinding('bilibili-open-live','123'),ttl_seconds=30)
  self.s.bili=SimpleNamespace(ingress=self.ingress,status=lambda:{'state':'local-test-fixture'})
  self.inputs=[]
  self.f.app.generate_once=lambda settings,messages,**kw:(self.inputs.append(messages) or '欢迎来聊聊。')
 def event(self,ident,text):self.ingress.submit({'room_id':'123','event_id':ident,'text':text})
 def test_no_material_greeting_uses_public_context_only(self):
  self.f.post('memories',{'text':'PRIVATE_SCENE_CANARY','expected_character_id':self.f.initial_id})
  self.f.post('connectors/bili/context',{'topic':'今天聊音乐','allow_public':True})
  self.event('one','我喜欢民谣');self.event('two','你呢？')
  result=self.f.post('connectors/bili/reply',{'event_id':'two'})
  context=json.loads(self.inputs[-1][-1]['content'])
  self.assertEqual(context['公开背景'],'今天聊音乐');self.assertEqual(context['近期弹幕_按接收顺序'][0]['text'],'我喜欢民谣')
  self.assertEqual(context['当前观众消息'],'你呢？');self.assertNotIn('PRIVATE_SCENE_CANARY',str(self.inputs))
  self.assertEqual(result['state'],'review');self.assertFalse(result['delivered'])
 def test_strict_and_pause_are_server_enforced(self):
  self.f.post('connectors/bili/context',{'mode':'strict'});self.event('one','你好')
  self.f.post('connectors/bili/reply',{'event_id':'one'},expected=400);self.assertFalse(self.inputs)
  self.f.post('connectors/bili/context',{'mode':'interactive','host_talking':True});self.event('two','你好')
  self.f.post('connectors/bili/reply',{'event_id':'two'},expected=400);self.assertFalse(self.inputs)
 def test_switch_topic_discards_old_pending_events(self):
  self.event('old','之前的话题');self.s.public_events();time.sleep(.001)
  self.f.post('connectors/bili/context',{'topic':'新话题','allow_public':True})
  self.f.post('connectors/bili/reply',{'event_id':'old'},expected=409)
  self.event('new','现在的话题');self.f.post('connectors/bili/reply',{'event_id':'new'})
  self.assertNotIn('之前的话题',str(self.inputs))
