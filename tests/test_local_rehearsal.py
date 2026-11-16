"""Actual owner HTTP boundaries; no platform network or credentials."""
import json
import unittest
import test_character_http
from companion_runtime.connectors import ConnectorError

class RehearsalTests(unittest.TestCase):
 def setUp(self):
  self.f=test_character_http.CharacterHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown);self.s=self.f.app.integrations();self.inputs=[]
  # Existing boundary fixture uses configured loopback transport only; the
  # focused preparation suite separately exercises actual fake local streaming.
  self.f.app.set_settings({'engine':'api','api_base':'http://127.0.0.1:9999/v1','api_model':'fixture-not-contacted','voice_backend':'external'})
  self.f.app.generate_once=lambda settings,messages,**kw:(self.inputs.append(messages) or '你好，欢迎来聊聊。')
 def start(self):return self.f.post('connectors/bili/rehearsal',{'action':'start','confirm_local':True})
 def message(self,text):return self.f.post('connectors/bili/rehearsal',{'action':'message','text':text})
 def test_no_network_no_auto_generation_and_real_review_path(self):
  self.start();self.message('你好')
  status=self.s.status();self.assertEqual(status['bili']['state'],'local_rehearsal');self.assertIsNone(self.s.bili);self.assertIsNone(self.s._thread);self.assertFalse(self.inputs)
  event=status['public_events'][0];self.assertEqual(event['origin'],'local_rehearsal')
  reply=self.f.post('connectors/bili/reply',{'event_id':event['event_id']});self.assertEqual(reply['state'],'review');self.assertEqual(reply['origin'],'local_rehearsal');self.assertFalse(reply['delivered'])
  self.f.post('connectors/bili/approve',{'id':reply['id']},expected=400)
 def test_invalid_input_is_rejected_instead_of_false_success(self):
  self.start()
  for text in ['', ' '*3, 'x'*301]:
   self.f.post('connectors/bili/rehearsal',{'action':'message','text':text},expected=400)
  with self.assertRaises(ConnectorError):self.s.rehearse({'action':'message','text':'\ud800'})
  self.assertEqual(self.s.public_events(),[])
 def test_restart_keeps_public_material_and_topic_but_clears_jobs_and_revokes_output(self):
  self.start();self.message('旧问题');event=self.s.public_events()[0];reply=self.f.post('connectors/bili/reply',{'event_id':event['event_id']});old=self.s.output
  self.s.output.set_material('旧材料',True);self.s.output.set_context({'topic':'旧话题','allow_public':True});token=self.s.output.open()
  self.start();self.assertIsNone(old.token);self.assertNotEqual(self.s.output.session,old.session);self.assertEqual(self.s.output.material['text'],'旧材料');self.assertEqual(self.s.output.topic,'旧话题');self.assertEqual(self.s.public_events(),[])
  self.f.post('connectors/bili/reply',{'event_id':event['event_id']},expected=409)
 def test_stop_rejects_further_messages_and_does_not_restart(self):
  self.start();self.f.post('connectors/bili/stop',{});self.message_after_stop()
  self.assertEqual(self.s.status()['bili']['state'],'not_connected');self.assertIsNone(self.s._thread)
 def message_after_stop(self):self.f.post('connectors/bili/rehearsal',{'action':'message','text':'你好'},expected=409)
 def test_unauthenticated_client_cannot_start_or_inject(self):
  for action in [{'action':'start','confirm_local':True},{'action':'message','text':'你好'}]:
   status,_,_=self.f.request('POST','/api/connectors/bili/rehearsal',action,auth=False);self.assertEqual(status,403)
 def test_start_requires_explicit_action(self):
  self.f.post('connectors/bili/rehearsal',{'action':'start'},expected=400);self.assertIsNone(self.s._rehearsal)
