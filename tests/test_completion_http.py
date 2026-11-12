"""Independent integrated VRM HTTP acceptance; no live accounts or real AI."""
import base64
import json
import unittest

import test_character_http as character_http
from vrm_fixtures import fixtures


class CompletionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = character_http.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
        self.fixture.setUp()
        self.models = fixtures()

    def tearDown(self):
        self.fixture.tearDown()

    def import_vrm(self, name='valid-single-mesh-vrm1.vrm', cid=None, expected=200):
        f = self.fixture
        return f.post('characters/assets/import', {
            'character_id': cid or f.state()['active_character_id'], 'format': 'vrm',
            'model': {'filename': name, 'data_base64': base64.b64encode(self.models[name]).decode()}
        }, expected=expected)

    def test_two_original_structures_vrm0_and_vrm1_are_actual_http_resources(self):
        f = self.fixture
        for name, version in [('valid-single-mesh-vrm1.vrm', '1'), ('valid-textured-multi-mesh-vrm0.vrm', '0')]:
            with self.subTest(version=version):
                asset = self.import_vrm(name)['asset']
                self.assertEqual(asset['format'], 'vrm')
                self.assertEqual(asset['vrm_version'], version)
                self.assertTrue(asset['capabilities']['model_3d'])
                self.assertIsNone(f.appearance_id())
                status, headers, body = f.request('GET', asset['model']['url'])
                self.assertEqual(status, 200, body)
                self.assertEqual(body[:4], b'glTF')
                self.assertNotIn('https://untrusted.invalid/', body.decode('utf-8', errors='ignore'))
                status, _, _ = f.request('GET', asset['model']['url'], auth=False)
                self.assertIn(status, (401,403))

    def test_bad_models_preserve_current_png_and_do_not_publish_new_revisions(self):
        f = self.fixture
        old = f.import_asset()
        f.activate(f.initial_id, old['id'])
        for name in self.models:
            if name.startswith('bad-'):
                with self.subTest(name=name):
                    self.import_vrm(name, expected=400)
                    self.assertEqual(f.appearance_id(), old['id'])
                    self.assertEqual(len(f.assets(f.initial_id)), 1)

    def test_preview_vrm_is_not_active_and_swap_back_preserves_relationship(self):
        f = self.fixture
        f.post('memories', {'text':'VRM_RELATIONSHIP_CANARY','expected_character_id':f.initial_id})
        old = f.import_asset()
        f.activate(f.initial_id, old['id'])
        model = self.import_vrm()['asset']
        self.assertEqual(f.appearance_id(), old['id'])
        f.activate(f.initial_id, model['id'])
        self.assertIn('VRM_RELATIONSHIP_CANARY', str(f.state()['memories']))
        f.activate(f.initial_id, old['id'])
        self.assertEqual(f.appearance_id(), old['id'])
        self.assertIn('VRM_RELATIONSHIP_CANARY', str(f.state()['memories']))

    def test_foreign_identity_cannot_activate_or_delete_another_vrm(self):
        f = self.fixture
        asset = self.import_vrm()['asset']
        second = f.create('VRM隔离测试')
        f.post('characters/assets/activate', {'character_id':second,'asset_id':asset['id']}, expected=404)
        f.post('characters/assets/delete', {'character_id':second,'asset_id':asset['id']}, expected=404)
        self.assertEqual(f.assets(second), [])
        self.assertEqual(len(f.assets(f.initial_id)), 1)

    def test_new_vrm_appearance_invalidates_previous_generation_audio(self):
        f = self.fixture
        reply = f.chat('形象切换前的回答')
        asset = self.import_vrm()['asset']
        f.activate(f.initial_id, asset['id'])
        status, _, body = f.request('POST', '/api/speech', {
            'text':reply['message']['text'],'request_id':reply['request_id'],
            'generation_id':reply['generation_id'],'expected_character_id':f.initial_id})
        self.assertEqual(status,409,body)
        self.assertEqual(f.audio_calls,[])

    def test_selected_vrm_persists_reinitialize_and_remains_isolated_after_return(self):
        f = self.fixture
        asset = self.import_vrm('valid-textured-multi-mesh-vrm0.vrm')['asset']
        f.activate(f.initial_id, asset['id'])
        second = f.create('全新身份')
        self.assertIsNone(f.appearance_id())
        f.select(f.initial_id)
        f.app.init()
        self.assertEqual(f.appearance_id(),asset['id'])
        self.assertEqual(f.state()['active_character']['appearance']['vrm_version'],'0')
        f.select(second)
        self.assertEqual(f.assets(second),[])

    def test_vrm_resource_path_and_malformed_model_fields_are_refused(self):
        f = self.fixture
        for model in [None, {'filename':'x.vrm','data_base64':[]}, {'filename':'x.vrm','data_base64':'!!!'}]:
            f.post('characters/assets/import', {'character_id':f.initial_id,'format':'vrm','model':model}, expected=400)
        asset = self.import_vrm()['asset']
        for resource in ['../companion.db','%2e%2e%2fcompanion.db','model.js']:
            status,_,body=f.request('GET','/api/assets/'+asset['id']+'/'+resource+'?character_id='+f.initial_id)
            self.assertIn(status,(400,403,404))
            self.assertNotIn(b'SQLite format',body)

    def test_live2d_structure_fixture_cannot_activate_without_licensed_runtime(self):
        from test_live2d_assets import archive,files
        f=self.fixture;old=f.import_asset();f.activate(f.initial_id,old['id'])
        payload=archive(files(True))
        asset=f.post('characters/assets/import',{'character_id':f.initial_id,'format':'live2d',
            'model':{'filename':'synthetic-structure-only.zip','data_base64':base64.b64encode(payload).decode()}})['asset']
        self.assertEqual(asset['format'],'live2d')
        self.assertFalse(asset['runtime']['core_consistency_verified'])
        status,_,body=f.request('GET','/api/live2d/runtime')
        self.assertEqual(status,200);self.assertFalse(json.loads(body)['available'])
        f.post('characters/assets/activate',{'character_id':f.initial_id,'asset_id':asset['id']},expected=409)
        self.assertEqual(f.appearance_id(),old['id'])
        self.assertIn(f.request('GET','/live2d-core.js')[0],(400,404,409,503))

    def test_live2d_model_motion_physics_display_resources_are_served_as_parseable_json(self):
        from test_live2d_assets import archive,files
        f=self.fixture;source=archive(files(True))
        asset=f.post('characters/assets/import',{'character_id':f.initial_id,'format':'live2d',
            'model':{'filename':'original-structure-only.zip','data_base64':base64.b64encode(source).decode()}})['asset']
        descriptors=[asset['model']]+list(asset['resources'].values())
        tested=[]
        for descriptor in descriptors:
            if descriptor['resource'].endswith('.json'):
                status,headers,body=f.request('GET',descriptor['url'])
                self.assertEqual(status,200,body)
                self.assertIn('application/json',headers['Content-Type'])
                parsed=json.loads(body);self.assertIsInstance(parsed,dict)
                tested.append(descriptor['resource'])
        for suffix in ['.model3.json','.motion3.json','.physics3.json','.cdi3.json']:
            self.assertTrue(any(name.endswith(suffix) for name in tested),(suffix,tested))


if __name__ == '__main__':
    unittest.main(verbosity=2)
