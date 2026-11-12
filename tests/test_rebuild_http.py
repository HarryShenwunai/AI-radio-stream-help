"""Real loopback Handler acceptance; synthetic model replies prove no semantics.

Uses isolated databases and actual HTTP/auth/scoping/migrations. No external
provider, physical camera, screen capture, GPU or Windows acceptance is implied.
"""
from __future__ import annotations

import base64
import datetime as dt
import http.client
import io
import json
import sqlite3
import threading
import time
import unittest
import uuid

from PIL import Image

import test_character_http as fixture
from companion_runtime.assistance import ProviderReply
from companion_runtime.preference_learning import PreferenceProviderReply, PreferenceSuggestion
from companion_runtime.perception_tracking import FaceTrackingManager


class SyntheticVision:
    def __init__(self, entered=None, release=None, *, fail=False):
        self.entered, self.release, self.fail = entered, release, fail
        self.calls = 0

    def status(self):
        return {'configured': True, 'processing': 'local', 'provider': 'synthetic-test-only',
                'inference_verified': False}

    def describe(self, image, mime_type, prompt, cancel):
        self.calls += 1
        if self.entered:
            self.entered.set()
        if self.release and not self.release.wait(8):
            raise TimeoutError('test release missing')
        if self.fail:
            raise RuntimeError('PRIVATE_PROVIDER_ERROR')
        return 'SYNTHETIC_DESCRIPTION_NOT_SEMANTIC_PROOF'


class RebuildHTTPTests(unittest.TestCase):
    setUp = fixture.CharacterHTTPTests.setUp
    tearDown = fixture.CharacterHTTPTests.tearDown
    request = fixture.CharacterHTTPTests.request
    post = fixture.CharacterHTTPTests.post
    state = fixture.CharacterHTTPTests.state
    create = fixture.CharacterHTTPTests.create
    select = fixture.CharacterHTTPTests.select
    import_asset = fixture.CharacterHTTPTests.import_asset
    activate = fixture.CharacterHTTPTests.activate
    chat = fixture.CharacterHTTPTests.chat

    def get(self, path):
        status, _, body = self.request('GET', path)
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def install_vision(self, provider=None):
        value = provider or SyntheticVision()
        self.app.host_services()['manager'].configure(value)
        return value

    def start_capture(self, kind='screen'):
        return self.post('perception/session/start', {
            'kind': kind, 'consent_confirmed': True,
            'expected_character_id': self.state()['active_character_id'],
        })['session_id']

    def frame_payload(self, sid, **changes):
        output = io.BytesIO()
        Image.new('RGB', (32, 24), '#c8b090').save(output, format='PNG')
        payload = {'session_id': sid, 'request_id': uuid.uuid4().hex,
                   'image_base64': base64.b64encode(output.getvalue()).decode(),
                   'mime_type': 'image/png', 'captured_at_ms': int(time.time() * 1000),
                   'expected_character_id': self.state()['active_character_id']}
        payload.update(changes)
        return payload

    def asynchronous_post(self, path, payload):
        result = {}
        def run():
            try:
                status, headers, raw = self.request('POST', '/api/' + path, payload)
                result.update(status=status, headers=headers, body=json.loads(raw))
            except Exception as error:
                result['exception'] = error
        thread = threading.Thread(target=run, daemon=True)
        self.pending_threads.append(thread)
        thread.start()
        return thread, result

    def test_new_routes_owner_cookie_required_and_plugin_bearer_does_not_grant_access(self):
        routes = [('GET', '/api/devices', None), ('GET', '/api/perception/status', None),
                  ('POST', '/api/devices', {'camera': False}),
                  ('POST', '/api/perception/session/start', {'kind': 'screen', 'consent_confirmed': True}),
                  ('POST', '/api/perception/config', {'enabled': False}),
                  ('POST', '/api/perception/frame', {'session_id': 'test'}),
                  ('POST', '/api/perception/session/stop', {'session_id': 'test'}),
                  ('POST', '/api/assistance/proposals', {'kind': 'schedule'}),
                  ('POST', '/api/assistance/decision', {'action_id': 'test', 'decision': 'confirm'}),
                  ('POST', '/api/assistance/pause', {'paused': True}),
                  ('POST', '/api/preferences/collect', {'request_id': 'test', 'source_message_ids': [1]}),
                  ('POST', '/api/preferences/decision', {'candidate_id': 'test', 'decision': 'confirm'}),
                  ('POST', '/api/preferences/correct', {'candidate_id': 'test', 'source_message_id': 1, 'exact_quote': '我喜欢茶。'}),
                  ('GET', '/api/perception/tracking/status', None),
                  ('POST', '/api/perception/tracking/session/start', {'consent_confirmed': True}),
                  ('POST', '/api/perception/tracking/session/stop', {'session_id': 'test'}),
                  ('POST', '/api/perception/tracking/frame', {'session_id': 'test'}),
                  ('POST', '/api/perception/tracking/install', {'consent_confirmed': True})]
        for method, path, payload in routes:
            with self.subTest(method=method, path=path):
                status, _, _ = self.request(method, path, payload, auth=False)
                self.assertIn(status, (401, 403))
                connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
                try:
                    connection.request(method, path, body=json.dumps(payload or {}),
                                       headers={'Authorization': 'Bearer SYNTHETIC_PLUGIN_TOKEN',
                                                'X-Companion': 'local-app', 'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    self.assertIn(response.status, (401, 403))
                    response.read()
                finally:
                    connection.close()
        self.assertTrue(self.get('/api/devices')['camera']['declared_available'])
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])
        self.assertEqual(self.state()['assistance']['proposals'], [])

    def test_foreign_origin_and_scope_spoofing_are_rejected_before_mutation(self):
        status, _, _ = self.request('POST', '/api/devices', {'camera': False}, origin='https://foreign.invalid')
        self.assertEqual(status, 403)
        for field, value in [('channel', 'bilibili'), ('source', 'plugin'), ('owner', 'other'),
                             ('scope', 'public'), ('permissions', ['capture'])]:
            with self.subTest(field=field):
                self.post('devices', {'camera': False, field: value}, expected=403)
        self.assertTrue(self.get('/api/devices')['camera']['declared_available'])

    def test_declared_defaults_do_not_start_capture_and_no_display_keeps_pc_vision(self):
        devices = self.get('/api/devices')
        for item in devices.values():
            self.assertTrue(item['declared_available'])
            self.assertEqual(item['detection'], 'not_checked')
            self.assertEqual(item['permission'], 'not_requested')
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])
        self.install_vision()
        self.post('devices', {'display': False})
        sid = self.start_capture('screen')
        result = self.post('perception/frame', self.frame_payload(sid))
        self.assertEqual(result['session_id'], sid)
        self.assertEqual(result['description'], 'SYNTHETIC_DESCRIPTION_NOT_SEMANTIC_PROOF')

    def test_camera_absent_stops_only_camera_session_and_reenable_does_not_restart(self):
        self.install_vision()
        camera = self.start_capture('camera')
        screen = self.start_capture('screen')
        self.post('devices', {'camera': False})
        sessions = self.get('/api/perception/status')['sessions']
        self.assertEqual([session['session_id'] for session in sessions], [screen])
        error = self.post('perception/session/start', {'kind': 'camera', 'consent_confirmed': True}, expected=409)
        self.assertEqual(error['code'], 'camera_disabled')
        self.post('perception/frame', self.frame_payload(camera), expected=409)
        self.post('perception/frame', self.frame_payload(screen))
        self.post('devices', {'camera': True})
        self.assertEqual([session['session_id'] for session in self.get('/api/perception/status')['sessions']], [screen])

    def test_microphone_absent_blocks_asr_but_preserves_tts_and_other_capture(self):
        self.install_vision()
        camera = self.start_capture('camera')
        screen = self.start_capture('screen')
        cancel = threading.Event()
        self.app.VOICE_OPERATIONS['synthetic-recording'] = cancel
        try:
            self.post('devices', {'microphone': False})
            self.assertTrue(cancel.is_set())
        finally:
            self.app.VOICE_OPERATIONS.pop('synthetic-recording', None)
        self.post('transcribe', {'audio_base64': 'not-valid-audio'}, expected=409)
        status, headers, body = self.request('POST', '/api/speech', {'text': '输入停用仍可朗读。'})
        self.assertEqual(status, 200, body)
        self.assertEqual(headers['Content-Type'], 'audio/wav')
        self.assertTrue(body.startswith(b'RIFF'))
        self.assertEqual(self.audio_calls, ['输入停用仍可朗读。'])
        self.assertEqual({item['session_id'] for item in self.get('/api/perception/status')['sessions']}, {camera, screen})

    def test_perception_errors_and_private_session_id_do_not_collide(self):
        error = self.post('perception/session/start', {'kind': 'screen', 'consent_confirmed': True}, expected=503)
        self.assertEqual(error['code'], 'vision_not_configured')
        self.install_vision()
        error = self.post('perception/session/start', {'kind': 'screen'}, expected=403)
        self.assertEqual(error['code'], 'consent_required')
        sid = self.start_capture()
        self.assertNotEqual(sid, 'local-private')
        bad = self.post('perception/frame', self.frame_payload(sid, image_base64='bad!'), expected=400)
        self.assertEqual(bad['code'], 'invalid_frame')
        payload = self.frame_payload(sid)
        result = self.post('perception/frame', payload)
        self.assertEqual(result['request_id'], payload['request_id'])
        self.assertFalse(result['retained'])
        self.assertEqual(self.post('perception/frame', payload), result)
        limited = self.post('perception/frame', self.frame_payload(sid), expected=429)
        self.assertEqual(limited['code'], 'rate_limited')
        self.post('perception/session/stop', {'session_id': sid})
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])

    def test_provider_failure_is_redacted_and_configuration_returns_no_key(self):
        self.post('perception/config', {'enabled': False, 'base_url': 'http://127.0.0.1:9/v1',
                                        'model': 'synthetic', 'api_key': 'PRIVATE_FIXTURE_KEY'})
        status = self.get('/api/perception/status')
        self.assertNotIn('PRIVATE_FIXTURE_KEY', json.dumps(status))
        self.assertTrue(status['config']['has_api_key'])
        self.install_vision(SyntheticVision(fail=True))
        error = self.post('perception/frame', self.frame_payload(self.start_capture()), expected=502)
        self.assertEqual(error['code'], 'provider_failed')
        self.assertNotIn('PRIVATE_PROVIDER_ERROR', json.dumps(error))

    def test_assistance_resolves_only_server_observations_and_stop_revokes_them(self):
        self.install_vision()
        sid = self.start_capture()
        observation = self.post('perception/frame', self.frame_payload(sid))
        calls = []
        def generate_once(settings, messages, **kwargs):
            calls.append(messages)
            return '仅证明授权观察传递的合成建议。'
        self.app.generate_once = generate_once
        payload = {'request_id': uuid.uuid4().hex, 'expected_character_id': self.initial_id,
                   'kind': 'game', 'inputs': {'query': '请解释眼前局面', 'game': '协议测试游戏'},
                   'observation_id': observation['observation_id']}
        proposal = self.post('assistance/proposals', payload)['proposal']
        self.assertEqual(proposal['status'], 'proposed')
        self.assertEqual(len(calls), 1)
        supplied = json.loads(calls[0][1]['content'])['inputs']['observation']
        self.assertEqual(supplied['description'], observation['description'])
        self.assertEqual(supplied['session_id'], sid)
        self.assertEqual(supplied['observation_id'], observation['observation_id'])
        self.assertEqual(proposal['permission_scope'], 'read_only')
        self.assertFalse(proposal['result']['external_actions'])
        self.assertNotIn(observation['description'], json.dumps(proposal))
        forged = {**payload, 'request_id': uuid.uuid4().hex, 'observation_id': 'invented-observation'}
        error = self.post('assistance/proposals', forged, expected=409)
        self.assertEqual(error['code'], 'observation_unavailable')
        self.post('perception/session/stop', {'session_id': sid})
        payload['request_id'] = uuid.uuid4().hex
        error = self.post('assistance/proposals', payload, expected=409)
        self.assertEqual(error['code'], 'observation_unavailable')
        self.assertEqual(len(calls), 1)

    def test_devices_persist_across_role_changes_and_stale_scope_update_is_rejected(self):
        self.post('devices', {'display': False, 'camera': False, 'microphone': False})
        self.create()
        devices = self.get('/api/devices')
        self.assertTrue(all(not item['declared_available'] for item in devices.values()))
        self.post('devices', {'camera': True, 'expected_character_id': self.initial_id}, expected=409)
        self.assertFalse(self.get('/api/devices')['camera']['declared_available'])
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])

    def test_role_switch_cancels_late_vision_and_stale_stop_cannot_stop_new_session(self):
        entered, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)
        self.install_vision(SyntheticVision(entered, release))
        old = self.start_capture()
        thread, result = self.asynchronous_post('perception/frame', self.frame_payload(old))
        self.assertTrue(entered.wait(3))
        self.create()
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])
        new = self.start_capture()
        self.post('perception/session/stop', {'session_id': old})
        self.assertEqual([item['session_id'] for item in self.get('/api/perception/status')['sessions']], [new])
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertNotIn('exception', result)
        self.assertEqual(result['status'], 409, result)
        self.assertNotIn('description', result['body'])

    def test_appearance_switch_cancels_late_vision(self):
        asset = self.import_asset()
        entered, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)
        self.install_vision(SyntheticVision(entered, release))
        old = self.start_capture()
        thread, result = self.asynchronous_post('perception/frame', self.frame_payload(old))
        self.assertTrue(entered.wait(3))
        self.activate(self.initial_id, asset['id'])
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertNotIn('exception', result)
        self.assertEqual(result['status'], 409, result)
        self.assertNotIn('description', result['body'])
        self.assertEqual(self.get('/api/perception/status')['sessions'], [])

    def test_schedule_confirmation_is_idempotent_and_reminder_has_exact_provenance(self):
        due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=3)
        payload = {'request_id': uuid.uuid4().hex, 'expected_character_id': self.initial_id,
                   'kind': 'schedule', 'inputs': {'title': '真实本机提醒夹具', 'due_at': due.isoformat()}}
        proposal = self.post('assistance/proposals', payload)['proposal']
        self.assertEqual(proposal['status'], 'proposed')
        self.assertEqual(self.state()['tasks'], [])
        repeated = self.post('assistance/proposals', payload)['proposal']
        self.assertEqual(repeated['action_id'], proposal['action_id'])
        decision = {'action_id': proposal['action_id'], 'decision': 'confirm', 'expected_character_id': self.initial_id}
        confirmed = self.post('assistance/decision', decision)['proposal']
        self.assertEqual(confirmed['status'], 'confirmed')
        self.assertEqual(self.post('assistance/decision', decision)['proposal'], confirmed)
        state = self.state()
        self.assertEqual(len(state['tasks']), 1)
        task = state['tasks'][0]
        self.assertEqual(task['assistance_action_id'], proposal['action_id'])
        self.app.quiet = lambda *_: False
        self.app.scheduler_tick(task['due'] + 1)
        self.app.scheduler_tick(task['due'] + 2)
        reminders = [item for item in self.state()['messages'] if item['kind'] == 'reminder']
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]['task_id'], task['id'])
        self.assertEqual(confirmed['result']['task_id'], task['id'])

    def test_restore_invalidates_old_schedule_binding_for_empty_and_task_backups(self):
        for with_task in (False, True):
            with self.subTest(with_task=with_task):
                due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=3)
                proposal = self.post('assistance/proposals', {'request_id': uuid.uuid4().hex,
                    'kind': 'schedule', 'inputs': {'title': '恢复关联回归夹具', 'due_at': due.isoformat()}})['proposal']
                decision = {'action_id': proposal['action_id'], 'decision': 'confirm'}
                confirmed = self.post('assistance/decision', decision)['proposal']
                old_task = confirmed['result']['task_id']
                backup = {'messages': [], 'memories': [], 'tasks': ([{
                    'title': '备份约定需重新启用', 'due': due.timestamp(), 'status': 'pending',
                    'kind': 'reminder', 'id': old_task, 'assistance_action_id': proposal['action_id']
                }] if with_task else [])}
                self.post('restore', {'backup': backup})
                state = self.state()
                actual = next(item for item in state['assistance']['proposals'] if item['action_id'] == proposal['action_id'])
                self.assertEqual(actual['status'], 'cancelled')
                self.assertFalse(actual['result']['local_schedule_created'])
                self.assertTrue(actual['result']['local_schedule_cancelled'])
                self.assertEqual(actual['result']['cancel_reason'], 'backup_restore')
                self.assertEqual(actual['result']['previous_task_id'], old_task)
                self.assertNotIn('task_id', actual['result'])
                self.post('assistance/decision', decision, expected=409)
                if with_task:
                    self.assertEqual(len(state['tasks']), 1)
                    self.assertEqual(state['tasks'][0]['status'], 'paused')
                    self.assertNotEqual(state['tasks'][0]['id'], old_task)
                    self.assertIsNone(state['tasks'][0]['assistance_action_id'])
                else:
                    self.assertEqual(state['tasks'], [])
                with self.app.db() as connection:
                    count = connection.execute("SELECT count(*) FROM assistance_events WHERE action_id=? AND event='backup_restore_cancelled_schedule'", (proposal['action_id'],)).fetchone()[0]
                self.assertEqual(count, 1)

    def test_restore_failure_rolls_back_task_memory_message_and_proposal_invalidation(self):
        self.chat('恢复事务回滚消息夹具')
        self.post('memories', {'text': '恢复事务回滚事实夹具'})
        due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=3)
        proposal = self.post('assistance/proposals', {'request_id': uuid.uuid4().hex,
            'kind': 'schedule', 'inputs': {'title': '不能半恢复的原约定', 'due_at': due.isoformat()}})['proposal']
        decision = {'action_id': proposal['action_id'], 'decision': 'confirm'}
        confirmed = self.post('assistance/decision', decision)['proposal']
        before = self.state()
        # Valid JSON with an invalid nested status reaches the transaction, after
        # its DELETEs and proposal updates. The resulting TypeError must roll back
        # all of them, including the audit association added for backup restore.
        self.post('restore', {'backup': {'messages': [], 'memories': [], 'tasks': [{
            'title': '无效状态夹具', 'due': due.timestamp(), 'status': []
        }]}}, expected=400)
        after = self.state()
        for key in ('messages', 'memories', 'tasks'):
            self.assertEqual(after[key], before[key], key)
        actual = next(item for item in after['assistance']['proposals'] if item['action_id'] == proposal['action_id'])
        self.assertEqual(actual, confirmed)
        self.assertEqual(self.post('assistance/decision', decision)['proposal'], confirmed)
        with self.app.db() as connection:
            count = connection.execute("SELECT count(*) FROM assistance_events WHERE action_id=? AND event='backup_restore_cancelled_schedule'", (proposal['action_id'],)).fetchone()[0]
        self.assertEqual(count, 0)

    def test_pause_and_legacy_cancel_preserve_user_control_and_role_isolation(self):
        self.post('tasks', {'title': '旧版约定保留', 'minutes': 4})
        task = self.state()['tasks'][0]
        self.post('assistance/pause', {'paused': True})
        self.assertEqual(self.state()['tasks'][0]['status'], 'paused')
        self.post('assistance/pause', {'paused': False})
        self.assertEqual(self.state()['tasks'][0]['status'], 'paused')
        second = self.create()
        self.post('assistance/cancel-task', {'task_id': task['id'], 'expected_character_id': second}, expected=404)
        self.select(self.initial_id)
        self.post('assistance/cancel-task', {'task_id': task['id']})
        self.post('assistance/cancel-task', {'task_id': task['id']})
        self.assertEqual(self.state()['tasks'][0]['status'], 'cancelled')

    def test_old_schema_migration_preserves_rows_without_guessing_message_task(self):
        path = self.app.catalog().db_path(self.initial_id)
        with sqlite3.connect(path) as connection:
            connection.execute('DROP INDEX assistance_task_once')
            connection.execute('ALTER TABLE tasks DROP COLUMN assistance_action_id')
            connection.execute('ALTER TABLE messages DROP COLUMN task_id')
            connection.execute("INSERT INTO tasks(id,title,due,status,created,kind) VALUES(77,'旧版任务',?,'paused',?,'reminder')", (time.time() + 200, self.app.now()))
            connection.execute("INSERT INTO messages(id,role,text,created,kind) VALUES(88,'assistant','旧提醒无可靠来源',?,'reminder')", (self.app.now(),))
        self.app.ASSISTANCE_STORES.clear()
        self.app.init_profile(self.initial_id)
        state = self.state()
        self.assertEqual(state['tasks'][0]['id'], 77)
        self.assertIsNone(state['tasks'][0]['assistance_action_id'])
        old = next(item for item in state['messages'] if item['id'] == 88)
        self.assertEqual(old['text'], '旧提醒无可靠来源')
        self.assertIsNone(old['task_id'])

    def test_late_assistance_cannot_revive_after_role_or_appearance_change(self):
        for mutation in ('appearance', 'role'):
            with self.subTest(mutation=mutation):
                current_id = self.state()['active_character_id']
                asset = self.import_asset(current_id) if mutation == 'appearance' else None
                store = self.app.assistance_store()
                entered, release = threading.Event(), threading.Event()
                self.pending_releases.append(release)
                def provider(request, cancel):
                    entered.set()
                    if not release.wait(8):
                        raise TimeoutError('test release missing')
                    return ProviderReply('LATE_PRIVATE_ADVICE_MUST_NOT_APPEAR', 'synthetic-test-only')
                store.provider = provider
                thread, result = self.asynchronous_post('assistance/proposals', {
                    'request_id': uuid.uuid4().hex, 'expected_character_id': current_id,
                    'kind': 'brainstorm', 'inputs': {'query': '仅用于取消协议的合成请求'}})
                self.assertTrue(entered.wait(3))
                route = 'characters/assets/activate' if mutation == 'appearance' else 'characters/create'
                change = {'character_id': current_id, 'asset_id': asset['id']} if mutation == 'appearance' else {'name': '取消后再切换'}
                # A noncooperative provider may still hold resources. The host
                # cancels its ledger and refuses mutation until it has drained;
                # it must not claim the role changed while the action is alive.
                self.post(route, change, expected=409)
                self.assertEqual(self.state()['active_character_id'], current_id)
                self.assertEqual(store.list()[0]['status'], 'cancelled')
                self.assertEqual(store.list()[0]['summary'], '')
                release.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertNotIn('exception', result)
                self.assertNotIn('LATE_PRIVATE_ADVICE', json.dumps(result))
                self.assertIn(result['status'], (200, 409), result)
                if result['status'] == 200:
                    self.assertEqual(result['body']['proposal']['status'], 'cancelled')
                records = store.list()
                self.assertTrue(records)
                self.assertEqual(records[0]['status'], 'cancelled')
                self.assertEqual(records[0]['summary'], '')
                self.post(route, change)
                if mutation == 'appearance':
                    self.assertEqual(self.state()['active_character']['appearance_id'], asset['id'])
                else:
                    self.assertNotEqual(self.state()['active_character_id'], current_id)
                self.assertNotIn('LATE_PRIVATE_ADVICE', json.dumps(self.state()))

    def preference_fixture(self):
        calls = []
        def generate_once(settings, messages, **kwargs):
            calls.append(messages)
            sources = json.loads(messages[1]['content'])
            return json.dumps({'candidates': [{'source_message_id': source['source_message_id'],
                                              'exact_quote': source['text']} for source in sources]}, ensure_ascii=False)
        self.app.generate_once = generate_once
        return calls

    def preference_source(self, text='我喜欢桂花乌龙茶。'):
        self.chat(text)
        return next(item['id'] for item in reversed(self.state()['messages']) if item['role'] == 'user' and item['text'] == text)

    def collect_preference(self, source_id, request_id=None):
        return self.post('preferences/collect', {'request_id': request_id or uuid.uuid4().hex,
                         'source_message_ids': [source_id], 'expected_character_id': self.state()['active_character_id']})

    def test_preferences_actual_json_adapter_confirmation_idempotency_and_forget_context(self):
        calls = self.preference_fixture()
        source_id = self.preference_source()
        request_id = uuid.uuid4().hex
        result = self.collect_preference(source_id, request_id)
        candidate = result['candidates'][0]
        self.assertEqual(result['status'], 'proposed')
        self.assertEqual(self.state()['memories'], [])
        decision = {'candidate_id': candidate['candidate_id'], 'decision': 'confirm'}
        confirmed = self.post('preferences/decision', decision)['candidate']
        self.assertEqual(self.post('preferences/decision', decision)['candidate'], confirmed)
        self.assertEqual(len(calls), 1)
        memory = self.state()['memories'][0]
        self.assertEqual(memory['text'], '我喜欢桂花乌龙茶。')
        self.post('memories/delete', {'id': memory['id'], 'clear_context': True})
        state = self.state()
        self.assertEqual(state['memories'], [])
        self.assertEqual(state['preference_learning']['candidates'][0]['text'], '')
        self.assertEqual(state['preference_learning']['candidates'][0]['status'], 'forgotten')
        self.assertFalse(any(item['kind'] == 'chat' for item in state['messages']))
        self.post('preferences/decision', decision, expected=409)
        cached = self.collect_preference(source_id, request_id)
        self.assertEqual(cached['candidates'][0]['text'], '')
        self.assertEqual(len(calls), 1)
        self.chat('换个话题聊聊。')
        self.assertNotIn('桂花乌龙茶', json.dumps(self.model_calls[-1], ensure_ascii=False))

    def test_preferences_reject_memory_off_and_old_source_invalidation(self):
        calls = self.preference_fixture()
        first_source = self.preference_source()
        first = self.collect_preference(first_source)['candidates'][0]
        self.post('preferences/decision', {'candidate_id': first['candidate_id'], 'decision': 'reject'})
        self.post('preferences/decision', {'candidate_id': first['candidate_id'], 'decision': 'confirm'}, expected=409)
        self.assertEqual(self.state()['memories'], [])
        second_source = self.preference_source('我希望你不要反复催我学习。')
        second = self.collect_preference(second_source)['candidates'][0]
        self.post('settings', {'memory_mode': 'off'})
        count = len(calls)
        self.post('preferences/collect', {'request_id': uuid.uuid4().hex, 'source_message_ids': [second_source]}, expected=409)
        self.post('preferences/decision', {'candidate_id': second['candidate_id'], 'decision': 'confirm'}, expected=409)
        self.assertEqual(len(calls), count)
        self.post('settings', {'memory_mode': 'relevant'})
        self.post('conversation/clear', {})
        state = self.state()
        self.assertTrue(all(item['text'] == '' for item in state['preference_learning']['candidates']))
        self.post('preferences/decision', {'candidate_id': second['candidate_id'], 'decision': 'confirm'}, expected=409)
        self.assertEqual(self.state()['memories'], [])

    def test_preferences_correction_retains_only_new_source_and_requires_confirmation(self):
        self.preference_fixture()
        old_source = self.preference_source()
        first = self.collect_preference(old_source)['candidates'][0]
        self.post('preferences/decision', {'candidate_id': first['candidate_id'], 'decision': 'confirm'})
        new_source = self.preference_source('我更喜欢凉水。')
        corrected = self.post('preferences/correct', {'candidate_id': first['candidate_id'],
                              'source_message_id': new_source, 'exact_quote': '我更喜欢凉水。'})['candidate']
        self.assertEqual(corrected['status'], 'pending')
        self.assertEqual(corrected['previous_source_message_id'], old_source)
        state = self.state()
        self.assertEqual(state['memories'], [])
        chat = [item for item in state['messages'] if item['kind'] == 'chat']
        self.assertEqual([item['id'] for item in chat], [new_source])
        self.assertNotIn('桂花乌龙茶', json.dumps(state, ensure_ascii=False))
        self.post('preferences/decision', {'candidate_id': corrected['candidate_id'], 'decision': 'confirm'})
        self.assertEqual([item['text'] for item in self.state()['memories']], ['我更喜欢凉水。'])

    def test_preferences_noncooperative_collect_delete_guard_and_cache_eviction_recover(self):
        source_id = self.preference_source()
        old_id = self.state()['active_character_id']
        old_path = self.app.catalog().db_path(old_id)
        key = (str(self.app.DATA.resolve()), old_id)
        store = self.app.preference_store()
        entered, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)
        def provider(request, cancel):
            entered.set()
            if not release.wait(8):
                raise TimeoutError('test release missing')
            return PreferenceProviderReply((PreferenceSuggestion(source_id, '我喜欢桂花乌龙茶。'),), 'synthetic-test-only')
        store.provider = provider
        thread, result = self.asynchronous_post('preferences/collect', {
            'request_id': uuid.uuid4().hex, 'source_message_ids': [source_id], 'expected_character_id': old_id})
        self.assertTrue(entered.wait(3))
        self.post('characters/create', {'name': '等取消完成'}, expected=409)
        self.assertEqual(self.state()['active_character_id'], old_id)
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertNotIn('exception', result)
        self.assertEqual(result['status'], 200, result)
        self.assertEqual(result['body']['status'], 'cancelled')
        self.assertEqual(result['body']['candidates'], [])
        new_id = self.create()
        self.post('characters/delete', {'id': old_id})
        self.assertFalse(old_path.exists())
        self.assertNotIn(key, self.app.PREFERENCE_STORES)
        self.assertEqual(self.state()['active_character_id'], new_id)
        self.post('characters/create', {'name': '删除后继续创建'})
        self.assertFalse(old_path.exists())
        self.assertNotIn('桂花乌龙茶', json.dumps(self.state(), ensure_ascii=False))

    def test_tracking_http_uses_explicit_synthetic_engine_and_camera_absence_stops_only_tracking(self):
        class SyntheticFaceEngine:
            def __init__(self):
                self.initialized = 0
            def status(self):
                return {'configured': True, 'provider': 'synthetic-test-only', 'processing': 'local',
                        'inference_verified': False, 'professional_eye_tracking': False}
            def initialize(self):
                self.initialized += 1
            def estimate(self, image, cancel):
                return {'synthetic_protocol_fixture': True, 'face_present': False,
                        'professional_eye_tracking': False}
            def close(self):
                pass
        self.install_vision()
        services = self.app.host_services()
        services['tracking'].close()
        engine = SyntheticFaceEngine()
        scope = self.app.perception_scope()
        services['tracking'] = FaceTrackingManager(services['face_model'].model_path,
            engine=engine, is_scope_current=lambda value: value == self.app.perception_scope() and value.epoch == services['epoch'])
        self.post('perception/tracking/session/start', {}, expected=403)
        self.assertEqual(engine.initialized, 0)
        screen = self.start_capture()
        tracking = self.post('perception/tracking/session/start', {'consent_confirmed': True})['session_id']
        self.assertNotEqual(tracking, 'local-private')
        self.assertEqual(engine.initialized, 1)
        payload = self.frame_payload(tracking)
        result = self.post('perception/tracking/frame', payload)
        self.assertTrue(result['tracking']['synthetic_protocol_fixture'])
        self.assertFalse(result['tracking']['professional_eye_tracking'])
        self.assertEqual(scope, self.app.perception_scope())
        self.post('devices', {'camera': False})
        self.assertEqual(self.get('/api/perception/tracking/status')['sessions'], [])
        self.assertEqual([item['session_id'] for item in self.get('/api/perception/status')['sessions']], [screen])
        self.post('perception/tracking/session/start', {'consent_confirmed': True}, expected=409)
        self.post('perception/tracking/frame', self.frame_payload(tracking), expected=409)
        self.post('devices', {'camera': True})
        self.assertEqual(self.get('/api/perception/tracking/status')['sessions'], [])
        self.assertEqual(engine.initialized, 1)


if __name__ == '__main__':
    unittest.main()
