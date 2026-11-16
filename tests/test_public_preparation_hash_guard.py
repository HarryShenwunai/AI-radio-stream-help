"""Fake provider; real local byte hashing and owner cancellation entry points."""
import hashlib
import importlib.machinery
import os
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

import test_compute_runtime as compute_fixture
from test_public_prefix import FakeModel, Formatter, TEMPLATE
from companion_runtime.public_preparation import PreparationKind, PreparationNotReady

OBSERVATIONS = []


class ReadProbe:
    def __init__(self, stream, state, hook):
        self.stream, self.state, self.hook = stream, state, hook

    def __enter__(self):
        self.stream.__enter__()
        return self

    def read(self, size):
        value = self.stream.read(size)
        if value:
            self.state['inside_hash'] = True
            self.state['chunks'] += 1
            self.state['bytes_read'] += len(value)
            if self.state['chunks'] == 1 and self.hook:
                self.hook()
        else:
            self.state['inside_hash'] = False
            self.state['eof'] = True
        return value

    def __exit__(self, *args):
        self.state['inside_hash'] = False
        return self.stream.__exit__(*args)


class HashProbe:
    def __init__(self, digest, state):
        self.digest, self.state = digest, state

    def update(self, value):
        self.state['bytes_hashed'] += len(value)
        return self.digest.update(value)

    def hexdigest(self):
        value = self.digest.hexdigest()
        self.state['actual_hashes'].append(value)
        return value

    def __getattr__(self, name):
        return getattr(self.digest, name)


class PublicPreparationHashGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = compute_fixture.ComputeRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app = self.fixture.app
        self.model = FakeModel()
        self.fixture.module.Llama = lambda **kwargs: self.model
        self.fixture.module.__spec__ = importlib.machinery.ModuleSpec('llama_cpp', loader=None)
        chat = types.ModuleType('llama_cpp.llama_chat_format')
        chat.Jinja2ChatFormatter = Formatter
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'llama_cpp.llama_chat_format': chat}).start()
        patch('companion_runtime.public_prefix.QWEN_TEMPLATE_SHA256',
              hashlib.sha256(TEMPLATE.encode()).hexdigest()).start()
        self.voice_calls = []
        self.app.VOICE_DIR = Path(self.fixture.temp.name) / 'fake-voices'
        self.app.VOICE_DIR.mkdir()
        for name in ('kokoro-v1.0.onnx', 'voices-v1.0.bin'):
            (self.app.VOICE_DIR / name).write_bytes(b'only a small fake voice fixture')
        original_spec = self.app.importlib.util.find_spec
        patch.object(self.app.importlib.util, 'find_spec', side_effect=lambda name:
                     object() if name == 'kokoro_onnx' else original_spec(name)).start()

        def initialize(*, with_resources=False):
            self.voice_calls.append('initialize')
            self.app.LOCAL_VOICE, self.app.G2P = object(), object()
            identity = self.app._local_voice_identity(*self.app._local_voice_files())
            self.app.LOCAL_VOICE_IDENTITY = identity
            return self.app.LocalVoiceResources(self.app.LOCAL_VOICE, self.app.G2P, identity, False)
        self.app.initialize_local_voice = initialize
        self.service = self.app.integrations()
        self.input_bytes = b''

    def set_model_bytes(self, chunks=3):
        self.input_bytes = b'fake-full-sha-not-a-model\n' + b'x' * (chunks * 1024 * 1024 + 17)
        self.app.MODEL.write_bytes(self.input_bytes)
        self.app.DEFAULT_MODEL_SHA256 = hashlib.sha256(self.input_bytes).hexdigest()

    def start(self, hook=None, *, forbid_scope_in_hash=False):
        state = {'inside_hash': False, 'chunks': 0, 'bytes_read': 0, 'bytes_hashed': 0,
                 'eof': False, 'full_scope_calls': 0, 'actual_hashes': []}
        original_open, original_scope, original_sha = Path.open, self.app.public_runtime_scope, hashlib.sha256

        def opening(path, mode='r', *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            return ReadProbe(stream, state, hook) if path == self.app.MODEL and mode == 'rb' else stream

        def scope(service):
            state['full_scope_calls'] += 1
            if forbid_scope_in_hash and state['inside_hash']:
                raise AssertionError('full scope reached inside model SHA loop')
            return original_scope(service)

        def digest(*args, **kwargs):
            result = original_sha(*args, **kwargs)
            return HashProbe(result, state) if not args and not kwargs else result

        try:
            with patch.object(Path, 'open', opening), patch.object(self.app, 'public_runtime_scope', scope), \
                    patch.object(self.app.hashlib, 'sha256', side_effect=digest):
                return self.app.prepare_rehearsal(self.service, {'action': 'start', 'confirm_local': True})
        finally:
            state.pop('inside_hash')
            OBSERVATIONS.append({'test': self.id(), **state})
            self.last_state = state

    def assert_revoked_before_eval_voice_ready(self):
        self.assertEqual(self.model.evals, [])
        self.assertEqual(self.model.completions, [])
        self.assertEqual(self.voice_calls, [])
        self.assertNotEqual(self.service.preparation.status()['state'], 'ready')
        self.assertIsNone(self.service._rehearsal)
        self.assertFalse(self.app.MODEL_LOCK.locked())

    def test_full_sha_has_no_per_chunk_full_scope_and_constant_scope_count(self):
        rows = []
        for size in (1, 8):
            with self.subTest(mebibytes=size):
                self.set_model_bytes(size)
                before = hashlib.sha256(self.app.MODEL.read_bytes()).hexdigest()
                result = self.start(forbid_scope_in_hash=True)
                state = self.last_state
                self.assertTrue(result['started'])
                self.assertTrue(state['eof'])
                self.assertEqual(state['bytes_read'], len(self.input_bytes))
                self.assertEqual(state['bytes_hashed'], len(self.input_bytes))
                self.assertEqual(state['actual_hashes'], [before])
                self.assertEqual(hashlib.sha256(self.app.MODEL.read_bytes()).hexdigest(), before)
                self.assertEqual(self.service.preparation.status()['capabilities']['kind'],
                                 PreparationKind.LOCAL_DEFAULT.value)
                rows.append(state['full_scope_calls'])
                self.app.connector_request('bili/stop', {})
        if len(rows) == 2:
            self.assertEqual(rows[0], rows[1], 'scope I/O must not grow with model chunk count')

    def test_full_validation_cannot_return_true_after_owner_stop_during_its_IO(self):
        from companion_runtime.public_preparation import PreparationCheck
        self.service.begin_rehearsal_preparation({'confirm_local': True})
        ticket = self.service.preparation.begin(self.app.public_runtime_scope(self.service))
        def full_scope_snapshot_then_stop():
            self.app.connector_request('bili/stop', {})
            return True  # A scope snapshot alone could still equal its old value.
        current = PreparationCheck(full_scope_snapshot_then_stop,
                                   lambda: self.service.preparation.current(ticket))
        self.assertFalse(current())
        self.assertEqual(self.service.preparation.status()['state'], 'cancelled')

    def test_owner_stop_during_hash_stops_before_the_next_chunk(self):
        self.set_model_bytes()
        before = self.app.MODEL.read_bytes()
        with self.assertRaises(PreparationNotReady):
            self.start(lambda: self.app.connector_request('bili/stop', {}))
        self.assertEqual(self.last_state['chunks'], 1)
        self.assertEqual(self.app.MODEL.read_bytes(), before)
        self.assert_revoked_before_eval_voice_ready()

    def test_owner_configuration_A_B_A_cannot_revive_the_old_ticket(self):
        self.set_model_bytes()
        def change_back():
            self.app.set_settings({'local_context': 2048})
            self.app.set_settings({'local_context': 4096})
        with self.assertRaises(PreparationNotReady):
            self.start(change_back)
        self.assertEqual(self.last_state['chunks'], 1)
        self.assertEqual(self.app.public_model_settings()['local_context'], 4096)
        self.assert_revoked_before_eval_voice_ready()

    def test_owner_context_A_B_A_cannot_revive_the_old_session(self):
        self.set_model_bytes()
        def change_back():
            self.app.connector_request('bili/context', {'topic': 'temporary', 'allow_public': True})
            self.app.connector_request('bili/context', {'topic': '', 'allow_public': True})
        with self.assertRaises(PreparationNotReady):
            self.start(change_back)
        self.assertEqual(self.last_state['chunks'], 1)
        self.assertEqual(self.service.output.topic, '')
        self.assert_revoked_before_eval_voice_ready()

    def test_actual_resource_revocation_changes_session_and_stops_next_hash_chunk(self):
        self.set_model_bytes()
        def corrupt_resource():
            profile = self.app.catalog().active()
            scene = {'sha256': 'b' * 64, 'character_id': profile['id'],
                     'appearance_id': profile.get('avatar_revision')}
            runtime = {'core': {'sha256': hashlib.sha256(b'approved fake bytes').hexdigest()}}
            output = self.service.output
            token = output.open(scene, runtime=runtime)
            old_session = output.session
            fake_runtime = types.SimpleNamespace(read_core=lambda: b'changed fake bytes')
            with patch.object(self.app, 'live2d_runtime', return_value=fake_runtime):
                with self.assertRaises(self.app.OutputError):
                    self.app.program_resource(output, 'Bearer ' + token,
                                              {'revision': scene['sha256'], 'name': 'core'}, runtime=True)
            self.assertNotEqual(output.session, old_session)
            # This real revoke path cancels output, not the preparation ticket.
            self.assertEqual(self.service.preparation.status()['state'], 'preparing')
        with self.assertRaises(PreparationNotReady):
            self.start(corrupt_resource)
        self.assertEqual(self.last_state['chunks'], 1)
        self.assert_revoked_before_eval_voice_ready()

    def test_external_runtime_config_is_rejected_at_hash_boundary_before_eval(self):
        self.set_model_bytes()
        def outside_write():
            settings = self.app.runtime_settings.read(self.app.DATA)
            self.app.runtime_settings.write(self.app.DATA, {**settings, 'local_context': 2048})
        with self.assertRaises(PreparationNotReady):
            self.start(outside_write)
        self.assertTrue(self.last_state['eof'])
        self.assertEqual(self.last_state['bytes_hashed'], len(self.input_bytes))
        self.assert_revoked_before_eval_voice_ready()

    def test_external_model_replacement_is_rejected_before_eval_or_voice(self):
        self.set_model_bytes()
        def outside_write():
            before = self.app.MODEL.stat()
            self.app.MODEL.write_bytes(b'y' * len(self.input_bytes))
            os.utime(self.app.MODEL, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        with self.assertRaises(PreparationNotReady):
            self.start(outside_write)
        self.assertTrue(self.last_state['eof'])
        self.assert_revoked_before_eval_voice_ready()

    def test_external_voice_change_during_hash_is_rejected_before_prefix_eval(self):
        self.set_model_bytes()
        def outside_write():
            path = self.app.VOICE_DIR / 'kokoro-v1.0.onnx'
            path.write_bytes(b'changed external voice file')
        with self.assertRaises(PreparationNotReady):
            self.start(outside_write)
        self.assertTrue(self.last_state['eof'])
        self.assert_revoked_before_eval_voice_ready()

    def test_owner_role_change_cancels_before_waiting_for_the_model_lock(self):
        self.set_model_bytes()
        other = self.app.catalog().create('second fake role')
        invalidated, errors, worker = threading.Event(), [], []
        original = self.app.invalidate_current_media
        def observed_invalidation():
            original()
            invalidated.set()  # Test synchronization; the real entry cancelled the ticket.
        def switch():
            try:self.app.select_character(other['id'])
            except Exception as error:errors.append(error)
        def during_hash():
            thread = threading.Thread(target=switch)
            worker.append(thread)
            thread.start()
            self.assertTrue(invalidated.wait(2))
        try:
            with patch.object(self.app, 'invalidate_current_media', side_effect=observed_invalidation), \
                    patch.object(self.app, 'state', return_value={}):
                with self.assertRaises(PreparationNotReady):self.start(during_hash)
                for thread in worker:thread.join(3)
        finally:
            for thread in worker:thread.join(3)
        self.assertFalse(any(thread.is_alive() for thread in worker))
        self.assertEqual(errors, [])
        self.assertEqual(self.last_state['chunks'], 1)
        self.assertEqual(self.app.catalog().active()['id'], other['id'])
        self.assert_revoked_before_eval_voice_ready()


if __name__ == '__main__':
    unittest.main()
