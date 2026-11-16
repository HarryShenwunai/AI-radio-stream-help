"""Approved-scene capability tests. Local fixtures, no platform or viewer proof."""
import hashlib
import http.client
import json
import time
import unittest

import test_character_http as fixture
from test_live_output import pcm_wav


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

    def ready(self, event_id='one'):
        job = self.service.output.begin({'source':'local', 'room_id':'local', 'event_id':event_id,
                                         'text':'UNAPPROVED_QUESTION_CANARY', 'expires_at':time.monotonic()+30})
        self.service.output.jobs[job['id']]['private_extension'] = 'PRIVATE_EXTENSION_CANARY'
        self.service.output.finish(job['id'], '已批准文本', 'generation-1')
        self.f.post('connectors/bili/approve', {'id':job['id'], 'confirm_output':True})
        return job

    def test_insufficient_budget_blocks_ready_and_exposes_owner_reason(self):
        self.f.app.synthesize = lambda text: pcm_wav(31*8000)
        job = self.service.output.begin({'source':'local', 'room_id':'local', 'event_id':'budget',
                                        'text':'synthetic event', 'expires_at':time.monotonic()+30})
        self.service.output.finish(job['id'], '机械文本夹具', 'fixture-budget')
        self.f.post('connectors/bili/approve', {'id':job['id'], 'confirm_output':True}, expected=400)
        status = self.f.state()['live_output']['jobs'][0]
        self.assertEqual(status['state'], 'failed')
        self.assertEqual(status['failure_reason'], 'insufficient_playback_budget')
        self.assertEqual(status['audio_duration_seconds'], 31)
        self.assertLess(status['playback_budget_remaining_seconds'], 30)
        self.assertIsNone(json.loads(self.output('poll')[1])['item'])
        code, body = self.output('audio', id=job['id'])
        self.assertEqual(code, 409);self.assertFalse(body.startswith(b'RIFF'))
        self.assertNotIn('playing', [row['state'] for row in self.service.output.audit])

    def test_claim_and_audio_http_recheck_actual_duration(self):
        for boundary in ('claim', 'audio'):
            with self.subTest(boundary=boundary):
                job = self.ready('budget-'+boundary);output = self.service.output
                stored=output.jobs[job['id']]
                self.assertEqual((stored['audio_frames'],stored['audio_sample_rate']), (2400,24000))
                self.assertEqual(stored['audio_duration_seconds'], .1)
                self.assertEqual(len(stored['audio']), 4844)
                deadline = stored['expires_at']
                if boundary == 'audio':
                    output.clock = lambda: deadline - 1
                    self.assertEqual(self.output('poll')[0], 200)
                output.clock = lambda: deadline - .05
                if boundary == 'claim':self.assertIsNone(json.loads(self.output('poll')[1])['item'])
                else:
                    code, body = self.output('audio', id=job['id'])
                    self.assertEqual(code, 409);self.assertFalse(body.startswith(b'RIFF'))
                self.assertEqual(output.jobs[job['id']]['failure_reason'], 'insufficient_playback_budget')
                self.assertNotIn('audio', output.jobs[job['id']])
                output.clock = time.monotonic
                # A fresh event/session is required; a failed item is never replayed.
                output.cancel()
                self.token = self.f.post('connectors/bili/output/open', {})['path'].split('#')[1]

    def test_explicit_output_presentation_is_validated_frozen_and_hashed(self):
        original=json.loads(self.output('scene')[1])['scene_snapshot']
        self.f.post('connectors/bili/output/stop', {})
        opened=self.f.post('connectors/bili/output/open', {'presentation':{'layout':'left','theme':'midnight'}})
        self.token=opened['path'].split('#')[1]
        scene=json.loads(self.output('scene')[1])['scene_snapshot']
        self.assertEqual((scene['layout'],scene['theme']),('left','midnight'))
        self.assertEqual(scene['character_id'],original['character_id'])
        self.assertEqual(scene['appearance_id'],original['appearance_id'])
        self.assertNotEqual(scene['sha256'],original['sha256'])
        self.assertEqual(self.f.post('connectors/bili/output/open', {})['path'],opened['path'])
        self.f.post('connectors/bili/output/open', {'presentation':{'layout':'small','theme':'daylight'}},expected=409)
        self.assertEqual(json.loads(self.output('scene')[1])['scene_snapshot']['sha256'],scene['sha256'])
        self.assertEqual(self.f.post('connectors/bili/output/open', {'presentation':{'layout':'left','theme':'midnight'}})['path'],opened['path'])

    def test_invalid_presentation_cannot_revoke_or_replace_open_output(self):
        before=json.loads(self.output('scene')[1])['scene_snapshot']
        for value in (None,False,[],{'layout':'mirror'},{'layout':False},{'layout':[]},{'theme':False},{'theme':'url(private)'},{'character_id':self.f.initial_id},{'showCaption':False}):
            with self.subTest(value=value):
                self.f.post('connectors/bili/output/open',{'presentation':value},expected=400)
                self.assertEqual(json.loads(self.output('scene')[1])['scene_snapshot']['sha256'],before['sha256'])

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
