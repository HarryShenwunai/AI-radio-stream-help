"""Operator catalog exposes only identities and appearance, never private state."""
import json
import unittest
import test_character_http

class RoomCatalogTests(unittest.TestCase):
 def setUp(self):
  self.f=test_character_http.CharacterHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown)
 def test_only_public_appearance_metadata_for_every_identity(self):
  f=self.f;f.post('memories',{'text':'ROOM_PRIVATE_ONE','expected_character_id':f.initial_id});second=f.create('ROOM_ID_TWO');f.post('settings',{'personality':'ROOM_PRIVATE_TWO','expected_character_id':second});asset=f.import_asset();f.activate(second,asset['id']);f.select(f.initial_id)
  status,_,body=f.request('GET','/api/room');self.assertEqual(status,200);data=json.loads(body)
  self.assertEqual(data['character']['id'],f.initial_id);self.assertEqual(len(data['characters']),2)
  for p in data['characters']:self.assertEqual(set(p),{'id','name','appearance_id','appearance'})
  self.assertNotIn(b'ROOM_PRIVATE',body);self.assertNotIn(b'api_key',body);self.assertIsNotNone(next(p for p in data['characters'] if p['id']==second)['appearance']);self.assertEqual(f.state()['active_character_id'],f.initial_id)
 def test_archived_identity_is_absent_and_room_requires_auth(self):
  f=self.f;second=f.create('ROOM_ARCHIVED');f.select(f.initial_id);f.post('characters/archive',{'id':second});status,_,body=f.request('GET','/api/room');self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['characters']),1)
  self.assertEqual(f.request('GET','/api/room',auth=False)[0],401)
 def test_design_module_is_served_and_part_of_update(self):
  f=self.f;status,_,body=f.request('GET','/room-design.js');self.assertEqual(status,200);self.assertIn(b'normalize',body)
  import importlib.util
  spec=importlib.util.spec_from_file_location('room_update_check',test_character_http.ROOT/'scripts/app_update.py');app_update=importlib.util.module_from_spec(spec);spec.loader.exec_module(app_update)
  self.assertIn('room-design.js',app_update.STATIC_FILES)
