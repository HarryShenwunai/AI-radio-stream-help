"""Approved-scene capability tests. Local fixtures, no platform or viewer proof."""
import hashlib
import http.client
import json
import time
import unittest

import test_character_http as fixture


class ProgramOutputHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CharacterHTTPTests()
        self.f.setUp()
        asset = self.f.import_asset()
        self.f.activate(self.f.initial_id, asset['id'])
        self.service = self.f.app.integrations()
        path = self.f.post('connectors/bili/output/open', {})['path']
        self.token = path.split('#')[1]

    def tearDown(self):
        self.f.tearDown()

    def output(self, action, **payload):
        conn = http.client.HTTPConnection('127.0.0.1', self.f.server.server_port, timeout=5)
        try:
            conn.request('POST', '/api/live-output', json.dumps({'action':action, 'client':'program-client', **payload}),
                         {'Authorization':'Bearer '+self.token, 'Content-Type':'application/json'})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def ready(self):
        job = self.service.output.begin({'source':'local', 'room_id':'local', 'event_id':'one',
                                         'text':'UNAPPROVED_QUESTION_CANARY', 'expires_at':time.monotonic()+30})
        self.service.output.jobs[job['id']]['private_extension'] = 'PRIVATE_EXTENSION_CANARY'
        self.service.output.finish(job['id'], '已批准文本', 'generation-1')
        self.f.post('connectors/bili/approve', {'id':job['id'], 'confirm_output':True})
        return job

    def test_scene_and_every_output_response_use_explicit_public_fields(self):
        job = self.ready()
        for action, payload in [('scene', {}), ('poll', {}), ('receipt', {'id':job['id'], 'state':'playing'}), ('receipt', {'id':job['id'], 'state':'completed'})]:
            code, raw = self.output(action, **payload)
            self.assertEqual(code, 200, raw)
            self.assertNotIn(b'UNAPPROVED_QUESTION_CANARY', raw)
            self.assertNotIn(b'PRIVATE_EXTENSION_CANARY', raw)
            for forbidden in ('material', 'recent', 'topic', 'client', 'heartbeat'):
                response = json.loads(raw)
                value = response.get('item', response)
                if value:self.assertNotIn(forbidden, value)
        code, raw = self.output('poll')
        self.assertIsNone(json.loads(raw)['item'])

    def test_scene_assets_are_hash_pinned_and_no_token_in_resource_urls(self):
        code, raw = self.output('scene');self.assertEqual(code, 200)
        scene = json.loads(raw)['scene_snapshot']
        self.assertEqual(scene['character_id'], self.f.initial_id)
        self.assertEqual(scene['appearance_id'], self.f.appearance_id())
        item = scene['asset']['states']['idle']
        self.assertNotIn(self.token, item['url'])
        code, body = self.output('resource', revision=scene['sha256'], name=item['resource'])
        self.assertEqual(code, 200, body)
        self.assertEqual(hashlib.sha256(body).hexdigest(), item['sha256'])
        for name in ['../messages.sqlite3', 'thumbnail.png', 'other.png', None]:
            self.assertEqual(self.output('resource', revision=scene['sha256'], name=name)[0], 409)
        self.assertEqual(self.output('resource', revision='other-scene', name=item['resource'])[0], 409)
        self.f.post('connectors/bili/output/stop', {})
        self.assertEqual(self.output('resource', revision=scene['sha256'], name=item['resource'])[0], 409)

    def test_replaced_asset_revokes_scene_and_late_approval(self):
        self.ready()
        asset = self.f.import_asset(color=(200, 20, 20, 255))
        self.f.activate(self.f.initial_id, asset['id'])
        self.assertEqual(self.output('scene')[0], 409)
        self.assertTrue(all(job['state']=='cancelled' for job in self.service.output.jobs.values()))

    def test_state_projection_does_not_create_integration_or_leak_private_context(self):
        before = self.service.output.revision
        self.service.output.set_context({'topic':'PUBLIC_GENERATION_BACKGROUND', 'allow_public':True})
        status = self.f.state()['live_output']
        self.assertGreater(status['revision'], before)
        self.assertNotIn('topic', status)
        self.assertNotIn('material', status)
        self.assertEqual(status['interaction_mode'], 'interactive')
        self.assertFalse(status['host_talking'])
        self.f.app.INTEGRATIONS.clear()
        self.assertIsNone(self.f.state()['live_output'])
        self.assertEqual(len(self.f.app.INTEGRATIONS), 0)

    def test_missing_installed_runtime_remains_denied_and_changed_bytes_revoke_output(self):
        code, raw = self.output('scene')
        self.assertEqual(code, 200)
        scene = json.loads(raw)['scene_snapshot']
        self.assertFalse(scene['runtime_available'])
        self.assertEqual(self.output('runtime', revision=scene['sha256'], name='core')[0], 409)
        item = scene['asset']['states']['idle']
        path = self.f.app.asset_store(self.f.initial_id).resolve(scene['appearance_id'], item['resource'])
        data = path.read_bytes()
        path.write_bytes(data[:-1]+bytes([data[-1]^1]))
        self.assertEqual(self.output('resource', revision=scene['sha256'], name=item['resource'])[0], 409)
        self.assertEqual(self.output('scene')[0], 409)

    def test_program_nonce_is_not_a_global_csp_relaxation(self):
        code, headers, body = self.f.request('GET', '/live-stage.html', auth=False)
        self.assertEqual(code, 200)
        self.assertIn("'nonce-", headers['Content-Security-Policy'])
        self.assertIn("connect-src 'self' blob:", headers['Content-Security-Policy'])
        self.assertNotIn(b'__RUNTIME_NONCE__', body)
        _, headers, _ = self.f.request('GET', '/')
        self.assertNotIn('nonce-', headers['Content-Security-Policy'])
        self.assertIn("connect-src 'self';", headers['Content-Security-Policy'])
        self.assertNotIn('unsafe-eval', headers['Content-Security-Policy'])
        for path in ['/live2d-core.js', '/live2d-runtime.js', '/api/state']:
            self.assertEqual(self.f.request('GET', path, auth=False)[0], 401)


if __name__ == '__main__':
    unittest.main()
