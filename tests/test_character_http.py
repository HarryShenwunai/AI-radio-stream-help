"""Independent PNG-character HTTP acceptance with isolated SQLite and fake AI.

Real image encode/decode and actual HTTP routes are exercised. No Live2D,
external account, microphone or production user data is used.
"""
from __future__ import annotations

import base64
from contextlib import closing, contextmanager
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
import wave

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]


def png_fixture(color=(40, 100, 210, 220), size=(96, 160), *, comment=None):
    out = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if comment is not None:
        info.add_text('Comment', comment)
    Image.new('RGBA', size, color).save(out, format='PNG', pnginfo=info)
    return out.getvalue()


def wav_fixture():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b'\0\0' * 240)
    return out.getvalue()


@contextmanager
def recorded_local_provider():
    """An actual loopback-only endpoint recording fake credentials; no paid API."""
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            calls.append({'path': self.path, 'authorization': self.headers.get('Authorization'), 'body': json.loads(body)})
            data = json.dumps({'choices': [{'message': {'content': '本机模型夹具回复'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)


class CharacterHTTPTests(unittest.TestCase):
    def setUp(self):
        self.module_name = 'character_http_' + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(self.module_name, ROOT/'app/server.py')
        self.app = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.app
        spec.loader.exec_module(self.app)
        self.tmp = tempfile.TemporaryDirectory(prefix='character-http-')
        self.app.DATA = Path(self.tmp.name)
        self.app.init()
        self.pending_releases = []
        self.pending_threads = []
        self.model_calls = []
        self.audio_calls = []

        def generate(settings, messages, on_delta=None, cancel=None, on_status=None):
            self.model_calls.append(messages)
            if on_delta:
                on_delta('独立验收回复。')
            self.app.check_cancel(cancel)
            return '独立验收回复。'

        def synthesize(text):
            self.audio_calls.append(text)
            return wav_fixture()

        self.app.generate = generate
        self.app.synthesize = synthesize
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.server.daemon_threads = True
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        _, headers, _ = self.request('GET', '/')
        self.cookie = headers['Set-Cookie'].split(';', 1)[0]
        self.initial_id = self.state()['active_character_id']

    def tearDown(self):
        for release in self.pending_releases:
            release.set()
        for worker in self.pending_threads:
            worker.join(5)
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(5)
        self.tmp.cleanup()
        sys.modules.pop(self.module_name, None)

    def request(self, method, path, payload=None, *, auth=True, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {}
        if auth and hasattr(self, 'cookie'):
            headers.update({'Cookie': self.cookie, 'X-Companion': 'local-app'})
        if origin:
            headers['Origin'] = origin
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers['Content-Type'] = 'application/json'
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def post(self, route, data, *, expected=200):
        status, _, body = self.request('POST', '/api/'+route, data)
        self.assertEqual(status, expected, (route, status, body))
        return json.loads(body)

    def state(self):
        status, _, body = self.request('GET', '/api/state')
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def create(self, name='另一个角色'):
        self.post('characters/create', {'name': name})
        state = self.state()
        self.assertNotEqual(state['active_character_id'], self.initial_id)
        return state['active_character_id']

    def select(self, character_id):
        self.post('characters/select', {'id': character_id})
        self.assertEqual(self.state()['active_character_id'], character_id)

    def import_asset(self, character_id=None, *, color=(40, 100, 210, 220), states=None):
        cid = character_id or self.state()['active_character_id']
        states = states or {'idle': png_fixture(color)}
        payload = {'character_id': cid, 'states': {
            key: {'filename': '用户自选-'+key+'.png', 'data_base64': base64.b64encode(data).decode()}
            for key, data in states.items()
        }}
        result = self.post('characters/assets/import', payload)
        self.assertIn('asset', result)
        self.assertIn('id', result['asset'])
        return result['asset']

    def activate(self, cid, asset_id):
        self.post('characters/assets/activate', {'character_id': cid, 'asset_id': asset_id})

    def assets(self, cid):
        status, _, body = self.request('GET', '/api/characters/assets?character_id='+cid)
        self.assertEqual(status, 200, body)
        return json.loads(body)['assets']

    def appearance_id(self):
        character = self.state()['active_character']
        return character.get('appearance_id', character.get('avatar_revision'))

    def chat(self, text='测试聊天', *, rid=None):
        cid = self.state()['active_character_id']
        return self.post('chat', {'text': text, 'request_id': rid or str(uuid.uuid4()), 'expected_character_id': cid})

    def test_unauthorized_and_foreign_origin_cannot_upload_or_read_characters(self):
        for method, route, data in [
            ('GET', '/api/characters', None),
            ('POST', '/api/characters/create', {'name': '未授权'}),
            ('POST', '/api/characters/assets/import', {'character_id': self.initial_id, 'states': {}}),
        ]:
            with self.subTest(route=route):
                status, _, _ = self.request(method, route, data, auth=False)
                self.assertIn(status, (401, 403))
        status, _, _ = self.request('POST', '/api/characters/create', {'name': '外站'}, origin='https://untrusted.invalid')
        self.assertEqual(status, 403)
        self.assertEqual(len(self.state()['characters']), 1)

    def test_new_identity_has_separate_memories_chat_tasks_and_personality(self):
        self.post('memories', {'text': 'ALPHA_ONLY_CANARY', 'expected_character_id': self.initial_id})
        self.post('settings', {'personality': 'ALPHA_ONLY_PERSONALITY', 'expected_character_id': self.initial_id})
        self.post('tasks', {'title': 'ALPHA_ONLY_TASK', 'minutes': 25, 'kind': 'reminder', 'expected_character_id': self.initial_id})
        self.chat('ALPHA_ONLY_CHAT')
        second = self.create('角色乙')
        state = self.state()
        self.assertNotIn('ALPHA_ONLY', json.dumps(state, ensure_ascii=False))
        self.assertEqual(state['memories'], [])
        self.assertEqual(state['tasks'], [])
        self.assertEqual(state['settings']['name'], '角色乙')
        self.post('memories', {'text': 'BETA_ONLY_CANARY', 'expected_character_id': second})
        self.select(self.initial_id)
        state = self.state()
        self.assertIn('ALPHA_ONLY_CANARY', str(state['memories']))
        self.assertNotIn('BETA_ONLY_CANARY', str(state['memories']))
        self.assertIn('ALPHA_ONLY_CHAT', str(state['messages']))
        self.assertEqual(state['settings']['personality'], 'ALPHA_ONLY_PERSONALITY')

    def test_preview_is_not_activation_and_appearance_change_keeps_relationship(self):
        self.post('memories', {'text': '外观更新不能丢失', 'expected_character_id': self.initial_id})
        reply = self.chat('换外观前的对话')
        before = self.appearance_id()
        asset = self.import_asset()
        self.assertEqual(self.appearance_id(), before)
        self.activate(self.initial_id, asset['id'])
        self.assertEqual(self.appearance_id(), asset['id'])
        state = self.state()
        self.assertIn('外观更新不能丢失', str(state['memories']))
        self.assertTrue(any(message['id'] == reply['message']['id'] for message in state['messages']))

    def test_state_images_and_revision_rollback_are_user_driven(self):
        first = self.import_asset(states={
            'idle': png_fixture(), 'talk': png_fixture((200, 70, 50, 255)),
            'blink': png_fixture((20, 30, 50, 255)), 'talk_blink': png_fixture((70, 40, 90, 255)),
        })
        self.assertEqual(set(first['states']), {'idle', 'talk', 'blink', 'talk_blink'})
        self.activate(self.initial_id, first['id'])
        second = self.import_asset(color=(20, 200, 50, 255))
        self.activate(self.initial_id, second['id'])
        self.assertEqual(self.appearance_id(), second['id'])
        self.activate(self.initial_id, first['id'])
        self.assertEqual(self.appearance_id(), first['id'])
        self.assertEqual({asset['id'] for asset in self.assets(self.initial_id)}, {first['id'], second['id']})

    def test_uploaded_resources_need_auth_and_do_not_leak_paths_or_metadata(self):
        asset = self.import_asset(states={'idle': png_fixture(comment='PRIVATE_METADATA_CANARY')})
        self.assertNotIn(self.tmp.name, json.dumps(asset))
        resource = asset['states']['idle']['resource']
        url = f'/api/assets/{asset["id"]}/{resource}'
        status, headers, body = self.request('GET', url)
        self.assertEqual(status, 200, body)
        self.assertIn('image/png', headers.get('Content-Type', ''))
        with Image.open(io.BytesIO(body)) as image:
            image.load()
            self.assertEqual(image.size, (96, 160))
            self.assertNotIn('Comment', image.info)
        status, _, _ = self.request('GET', url, auth=False)
        self.assertIn(status, (401, 403))
        self.assertNotIn(b'PRIVATE_METADATA_CANARY', body)
        for bad in [f'/api/assets/{asset["id"]}/../companion.db', f'/api/assets/{asset["id"]}/%2e%2e%2fcompanion.db', '/api/assets/not-a-uuid/idle.png']:
            with self.subTest(path=bad):
                status, _, result = self.request('GET', bad)
                self.assertIn(status, (400, 403, 404))
                self.assertNotIn(b'SQLite format', result)

    def test_invalid_import_preserves_active_appearance_and_asset_list(self):
        good = self.import_asset()
        self.activate(self.initial_id, good['id'])
        before = len(self.assets(self.initial_id))
        invalids = [
            {'idle': {'filename': 'fake.png', 'data_base64': base64.b64encode(b'not a png').decode()}},
            {'idle': {'filename': 'bad.png', 'data_base64': '!!!'}},
            {'idle': {'filename': 'oversize.png', 'data_base64': 'A' * (4 * 1024 * 1024 * 4 // 3 + 16)}},
            {'idle': {'filename': ['incorrect-field-type.png'], 'data_base64': base64.b64encode(png_fixture()).decode()}},
            {'script': {'filename': 'payload.js', 'data_base64': base64.b64encode(b'alert(1)').decode()}},
            {'talk': {'filename': 'no-idle.png', 'data_base64': base64.b64encode(png_fixture()).decode()}},
            {'idle': {'filename': 'big.png', 'data_base64': base64.b64encode(png_fixture(size=(4097, 1))).decode()}},
        ]
        for states in invalids:
            with self.subTest(states=list(states)):
                status, _, _ = self.request('POST', '/api/characters/assets/import', {'character_id': self.initial_id, 'states': states})
                self.assertIn(status, (400, 413))
                self.assertEqual(self.appearance_id(), good['id'])
                self.assertEqual(len(self.assets(self.initial_id)), before)

    def test_stale_page_cannot_write_or_read_old_message_as_new_identity(self):
        reply = self.chat('旧角色专属话语')
        self.create('新角色')
        for route, payload in [
            ('memories', {'text': '不能写到新角色'}),
            ('settings', {'personality': '不能改到新角色'}),
            ('chat', {'text': '不能送到新角色', 'request_id': str(uuid.uuid4())}),
            ('speech', {'message_id': reply['message']['id']}),
        ]:
            with self.subTest(route=route):
                status, _, _ = self.request('POST', '/api/'+route, {**payload, 'expected_character_id': self.initial_id})
                self.assertEqual(status, 409)
        self.assertNotIn('不能写到新角色', str(self.state()['memories']))
        self.assertEqual(self.audio_calls, [])

    def test_switch_invalidates_old_generation_even_when_request_id_is_reused(self):
        rid = str(uuid.uuid4())
        first = self.chat('身份甲的回答', rid=rid)
        second_id = self.create('身份乙')
        second = self.chat('身份乙的回答', rid=rid)
        self.assertNotEqual(first['generation_id'], second['generation_id'])
        status, _, _ = self.request('POST', '/api/speech', {
            'text': first['message']['text'], 'request_id': rid,
            'generation_id': first['generation_id'], 'expected_character_id': second_id,
        })
        self.assertEqual(status, 409)
        self.assertEqual(self.audio_calls, [])

    def test_switch_during_synthesis_rejects_late_audio(self):
        response = self.chat()
        entered, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)
        def delayed(text):
            entered.set()
            self.assertTrue(release.wait(8))
            return wav_fixture()
        self.app.synthesize = delayed
        collected = []
        thread = threading.Thread(target=lambda: collected.append(self.request('POST', '/api/speech', {
            'text': response['message']['text'], 'request_id': response['request_id'],
            'generation_id': response['generation_id'], 'expected_character_id': self.initial_id,
        })))
        self.pending_threads.append(thread)
        thread.start()
        self.assertTrue(entered.wait(3))
        self.create('合成期间切换')
        release.set()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(collected[0][0], 409, collected)
        self.assertNotIn(b'RIFF', collected[0][2])

    def test_delete_identity_during_synthesis_rejects_late_audio_without_server_error(self):
        second_id = self.create('保留身份')
        self.select(self.initial_id)
        response = self.chat('随后删除的回复')
        entered, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)
        def delayed(text):
            entered.set()
            self.assertTrue(release.wait(8))
            return wav_fixture()
        self.app.synthesize = delayed
        collected = []
        worker = threading.Thread(target=lambda: collected.append(self.request('POST', '/api/speech', {
            'text': response['message']['text'], 'request_id': response['request_id'],
            'generation_id': response['generation_id'], 'expected_character_id': self.initial_id,
        })))
        self.pending_threads.append(worker)
        worker.start()
        self.assertTrue(entered.wait(3))
        self.select(second_id)
        self.post('characters/delete', {'id': self.initial_id})
        release.set()
        worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertIn(collected[0][0], (404, 409), collected)
        self.assertNotIn(b'RIFF', collected[0][2])

    def test_active_asset_cannot_be_deleted_and_inactive_revision_can(self):
        first = self.import_asset()
        second = self.import_asset(color=(10, 30, 40, 255))
        self.activate(self.initial_id, first['id'])
        self.post('characters/assets/delete', {'character_id': self.initial_id, 'asset_id': first['id']}, expected=409)
        self.post('characters/assets/delete', {'character_id': self.initial_id, 'asset_id': second['id']})
        self.assertEqual([asset['id'] for asset in self.assets(self.initial_id)], [first['id']])
        status, _, _ = self.request('GET', f'/api/assets/{second["id"]}/idle.png')
        self.assertEqual(status, 404)

    def test_asset_from_another_identity_cannot_be_activated_or_deleted(self):
        first = self.import_asset()
        second_id = self.create('其他身份')
        for action in ['activate', 'delete']:
            status, _, _ = self.request('POST', '/api/characters/assets/'+action, {'character_id': second_id, 'asset_id': first['id']})
            self.assertIn(status, (403, 404, 409))
        self.select(self.initial_id)
        self.assertEqual([asset['id'] for asset in self.assets(self.initial_id)], [first['id']])

    def test_archive_restore_keeps_relationship_but_permanent_delete_removes_profile(self):
        self.post('memories', {'text': '归档仍保留的事实', 'expected_character_id': self.initial_id})
        second_id = self.create('留下的角色')
        self.post('characters/archive', {'id': self.initial_id})
        self.post('characters/restore', {'id': self.initial_id})
        self.select(self.initial_id)
        self.assertIn('归档仍保留的事实', str(self.state()['memories']))
        self.select(second_id)
        self.post('characters/delete', {'id': self.initial_id})
        self.assertFalse(any(character['id'] == self.initial_id for character in self.state()['characters']))
        self.post('characters/delete', {'id': second_id}, expected=409)
        self.assertEqual(self.state()['active_character_id'], second_id)

    def test_malicious_ids_and_privilege_claims_do_not_modify_catalog(self):
        before = self.state()['characters']
        for route, payload in [
            ('characters/select', {'id': '../../companion.db'}),
            ('characters/create', {'name': '越权', 'role': 'owner'}),
            ('characters/assets/import', {'character_id': '../../elsewhere', 'states': {}}),
        ]:
            with self.subTest(route=route):
                status, _, _ = self.request('POST', '/api/'+route, payload)
                self.assertIn(status, (400, 403, 404))
        self.assertEqual(self.state()['characters'], before)

    def test_rename_updates_catalog_and_invalid_rename_is_not_half_applied(self):
        self.post('settings', {'name': '新名字', 'expected_character_id': self.initial_id})
        state = self.state()
        self.assertEqual(state['settings']['name'], '新名字')
        self.assertEqual(state['active_character']['name'], '新名字')
        self.assertEqual(next(item['name'] for item in state['characters'] if item['id'] == self.initial_id), '新名字')
        status, _, _ = self.request('POST', '/api/settings', {'name': '长' * 81, 'expected_character_id': self.initial_id})
        self.assertEqual(status, 400)
        self.assertEqual(self.state()['settings']['name'], '新名字')
        self.assertEqual(self.state()['active_character']['name'], '新名字')

    def test_switch_cancels_active_generation_and_does_not_commit_wrong_identity(self):
        entered = threading.Event()
        def slow(settings, messages, on_delta=None, cancel=None, on_status=None):
            if on_delta:
                on_delta('旧角色未完成片段')
            entered.set()
            self.assertTrue(cancel.wait(8))
            self.app.check_cancel(cancel)
            return '不应保存'
        self.app.generate = slow
        responses = []
        worker = threading.Thread(target=lambda: responses.append(self.request('POST', '/api/chat', {
            'text': '正在生成时切角色', 'request_id': str(uuid.uuid4()), 'expected_character_id': self.initial_id,
        })))
        self.pending_threads.append(worker)
        worker.start()
        self.assertTrue(entered.wait(3))
        self.create('新身份')
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(responses[0][0], 200)
        self.assertTrue(json.loads(responses[0][2])['cancelled'])
        self.assertNotIn('正在生成时切角色', str(self.state()['messages']))
        self.select(self.initial_id)
        self.assertFalse(any(message['role'] == 'assistant' and message['kind'] == 'chat' for message in self.state()['messages']))

    def test_inactive_or_archived_identity_does_not_dispatch_old_reminders(self):
        self.post('tasks', {'title': '不应在另一角色出现', 'minutes': 1/60, 'kind': 'reminder', 'expected_character_id': self.initial_id})
        self.create('当前角色')
        self.post('characters/archive', {'id': self.initial_id})
        self.app.scheduler_tick(time.time() + 2)
        self.assertFalse(any(message['kind'] == 'reminder' for message in self.state()['messages']))
        self.post('characters/restore', {'id': self.initial_id})
        self.select(self.initial_id)
        task = self.state()['tasks'][0]
        self.assertEqual(task['status'], 'paused')

    def test_model_connection_is_shared_and_switch_cannot_revive_old_provider(self):
        with recorded_local_provider() as (base_a, _), recorded_local_provider() as (base_b, _):
            self.post('settings', {'engine': 'api', 'api_base': base_a, 'api_model': 'model-a', 'api_key': 'fake-key-a', 'expected_character_id': self.initial_id})
            second_id = self.create('第二角色连接')
            self.assertEqual(self.state()['settings']['api_base'], base_a)
            self.post('settings', {'api_base': base_b, 'api_model': 'model-b', 'api_key': 'fake-key-b', 'expected_character_id': second_id})
            self.select(self.initial_id)
            for key, expected in {'engine': 'api', 'api_base': base_b, 'api_model': 'model-b'}.items():
                self.assertEqual(self.state()['settings'][key], expected)
            self.app.init()
            self.assertEqual(self.state()['settings']['api_base'], base_b)
            self.assertNotIn('fake-key-', json.dumps(self.state()))

    def test_stale_model_snapshot_is_rejected_before_any_provider_receives_credentials(self):
        with recorded_local_provider() as (base_a, calls_a), recorded_local_provider() as (base_b, calls_b):
            self.post('settings', {'engine': 'api', 'api_base': base_a, 'api_model': 'model-a', 'api_key': 'fake-key-a', 'expected_character_id': self.initial_id})
            stale = self.app.settings()
            self.post('settings', {'api_base': base_b, 'api_model': 'model-b', 'api_key': 'fake-key-b', 'expected_character_id': self.initial_id})
            with self.assertRaises(self.app.AppError) as rejected:
                list(self.app.remote_tokens(stale, [{'role': 'user', 'content': '过期请求不得发送'}], None))
            self.assertEqual(rejected.exception.status, 409)
            self.assertEqual(calls_a, [])
            self.assertEqual(calls_b, [])
            self.assertEqual(list(self.app.remote_tokens(self.app.settings(), [{'role': 'user', 'content': '当前连接'}], None)), ['本机模型夹具回复'])
            self.assertEqual(len(calls_b), 1)
            self.assertEqual(calls_b[0]['authorization'], 'Bearer fake-key-b')
            self.assertEqual(calls_b[0]['body']['model'], 'model-b')
            self.assertEqual(calls_a, [])

    def test_provider_change_requires_new_key_and_partial_key_write_fails_closed(self):
        with recorded_local_provider() as (base_a, calls_a), recorded_local_provider() as (base_b, calls_b):
            self.post('settings', {'engine': 'api', 'api_base': base_a, 'api_model': 'model-a', 'api_key': 'fake-key-a', 'expected_character_id': self.initial_id})
            self.post('settings', {'api_base': base_b, 'expected_character_id': self.initial_id}, expected=400)
            self.assertEqual(self.state()['settings']['api_base'], base_a)
            (self.app.DATA/'api-key').write_text('fake-partial-crash-key')
            with self.assertRaises(self.app.AppError) as rejected:
                list(self.app.remote_tokens(self.app.settings(), [{'role': 'user', 'content': '不应发送'}], None))
            self.assertEqual(rejected.exception.status, 503)
            self.assertEqual(calls_a, [])
            self.assertEqual(calls_b, [])

    def test_legacy_unsupported_name_is_normalized_without_touching_source(self):
        for index, old_name in enumerate(['长' * 81, '旧名字\n有控制字符']):
            with self.subTest(name_kind=index):
                folder = Path(self.tmp.name) / ('legacy-name-' + str(index))
                folder.mkdir()
                original = folder / 'companion.db'
                with closing(sqlite3.connect(original)) as connection, connection:
                    connection.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                    connection.execute('INSERT INTO settings VALUES (?,?)', ('name', json.dumps(old_name, ensure_ascii=False)))
                before = hashlib.sha256(original.read_bytes()).hexdigest()
                self.app.DATA = folder
                self.app.init()
                state = self.state()
                self.assertTrue(1 <= len(state['settings']['name']) <= 80)
                self.assertNotIn('\n', state['settings']['name'])
                self.assertEqual(state['settings']['name'], state['active_character']['name'])
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)

    def test_legacy_database_is_migrated_without_modifying_original(self):
        legacy_root = Path(self.tmp.name)/'legacy-case'
        legacy_root.mkdir()
        legacy = legacy_root/'companion.db'
        with closing(sqlite3.connect(legacy)) as conn, conn:
            conn.executescript('''
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,role TEXT NOT NULL,text TEXT NOT NULL,created TEXT NOT NULL,request_id TEXT,kind TEXT DEFAULT 'chat');
                CREATE TABLE memories(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT NOT NULL,created TEXT NOT NULL,source TEXT NOT NULL);
                CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,due REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created TEXT NOT NULL,kind TEXT DEFAULT 'reminder');
                CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE forgotten(digest TEXT PRIMARY KEY,created TEXT NOT NULL);
            ''')
            conn.execute('INSERT INTO settings VALUES (?,?)', ('name', json.dumps('旧数据角色', ensure_ascii=False)))
            conn.execute('INSERT INTO memories(text,created,source) VALUES (?,?,?)', ('LEGACY_MEMORY_CANARY', self.app.now(), 'manual'))
            conn.execute('INSERT INTO messages(role,text,created,request_id,kind) VALUES (?,?,?,?,?)', ('user', 'LEGACY_CHAT_CANARY', self.app.now(), 'legacy-request', 'chat'))
        original_hash = hashlib.sha256(legacy.read_bytes()).hexdigest()
        self.app.DATA = legacy_root
        self.app.init()
        state = self.state()
        self.assertEqual(state['settings']['name'], '旧数据角色')
        self.assertIn('LEGACY_MEMORY_CANARY', str(state['memories']))
        self.assertIn('LEGACY_CHAT_CANARY', str(state['messages']))
        self.post('memories', {'text': '迁移后独立写入', 'expected_character_id': state['active_character_id']})
        self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(), original_hash)
        self.app.init()
        self.assertEqual(self.state()['active_character_id'], state['active_character_id'])
        self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(), original_hash)


if __name__ == '__main__':
    unittest.main(verbosity=2)
