"""Real SQLite provenance/privacy tests; providers are explicitly synthetic."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from companion_runtime.preference_learning import (PreferenceLearningError, PreferenceLearningStore,
    PreferenceProviderReply, PreferenceSuggestion)


class PreferenceLearningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'profile.sqlite3'
        self.role = str(uuid4())
        self.current = True
        self.calls = []
        with self.connect() as connection:
            connection.executescript('''
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                INSERT INTO settings VALUES('memory_mode','"relevant"');
                CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,role TEXT,text TEXT,kind TEXT DEFAULT 'chat');
                CREATE TABLE memories(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT,created TEXT,source TEXT);
                CREATE TABLE forgotten(digest TEXT PRIMARY KEY,created TEXT);
            ''')
        def provider(request, cancel):
            self.calls.append(request)
            return PreferenceProviderReply(tuple(PreferenceSuggestion(source.source_message_id,
                source.text.splitlines()[0].strip()) for source in request.sources), 'synthetic-test-only')
        self.store = PreferenceLearningStore(self.path, self.role, provider=provider,
                                            is_scope_current=lambda: self.current)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def source(self, text='我喜欢喝温水。', *, role='user', kind='chat'):
        with self.connect() as connection:
            return connection.execute('INSERT INTO messages(role,text,kind) VALUES(?,?,?)', (role, text, kind)).lastrowid

    def collect(self, source_id=None, *, request_id=None):
        return self.store.collect(request_id or uuid4().hex, [source_id or self.source()])

    def candidate(self, source_id=None):
        result = self.collect(source_id)
        self.assertEqual(result['status'], 'proposed', result)
        return result['candidates'][0]

    def memories(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM memories')]

    def mode(self, value):
        with self.connect() as connection:
            connection.execute("UPDATE settings SET value=? WHERE key='memory_mode'", (json.dumps(value),))

    def forget(self, text):
        digest = hashlib.sha256(text.strip().encode()).hexdigest()
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO forgotten VALUES(?,'now')", (digest,))

    def test_no_automatic_call_or_memory_and_confirmation_is_idempotent(self):
        source_id = self.source()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.memories(), [])
        candidate = self.candidate(source_id)
        self.assertEqual(self.memories(), [])
        self.assertEqual(candidate['source_message_id'], source_id)
        self.assertEqual(candidate['source_digest'], hashlib.sha256('我喜欢喝温水。'.encode()).hexdigest())
        self.assertEqual(candidate['role_scope'], self.role)
        confirmed = self.store.decide(candidate['candidate_id'], 'confirm')
        self.assertEqual(confirmed['status'], 'confirmed')
        self.assertEqual(self.store.decide(candidate['candidate_id'], 'confirm'), confirmed)
        self.assertEqual(len(self.memories()), 1)
        self.assertEqual(self.memories()[0]['text'], '我喜欢喝温水。')
        self.assertEqual(self.memories()[0]['source'], 'confirmed-preference:' + candidate['candidate_id'])

    def test_memory_off_never_calls_provider_or_writes_candidates(self):
        source_id = self.source()
        self.mode('off')
        with self.assertRaises(PreferenceLearningError) as error:
            self.collect(source_id)
        self.assertEqual(error.exception.code, 'memory_disabled')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.memories(), [])

    def test_memory_off_blocks_confirmation_but_allows_reject_and_delete(self):
        first = self.candidate()
        second = self.candidate(self.source('我希望你不要反复提旧事。'))
        self.mode('off')
        with self.assertRaises(PreferenceLearningError):
            self.store.decide(first['candidate_id'], 'confirm')
        self.assertEqual(self.store.decide(first['candidate_id'], 'reject')['status'], 'rejected')
        self.assertEqual(self.store.decide(second['candidate_id'], 'delete')['text'], '')
        self.assertEqual(self.memories(), [])

    def test_missing_provider_reports_unavailable_without_fake_candidates(self):
        self.store.provider = None
        result = self.collect()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['error'], 'provider_not_configured')
        self.assertEqual(result['candidates'], [])
        self.assertFalse(result['automatic_learning'])

    def test_only_user_chat_sources_are_accepted(self):
        for role, kind in [('assistant', 'chat'), ('system', 'chat'), ('tool', 'chat'), ('user', 'vision'), ('user', 'reminder')]:
            source_id = self.source(role=role, kind=kind)
            with self.subTest(role=role, kind=kind), self.assertRaises(PreferenceLearningError):
                self.collect(source_id)
        self.assertEqual(self.calls, [])

    def test_model_cannot_rewrite_truncate_or_invent_a_preference(self):
        source_id = self.source('我喜欢喝温水，但运动之后更喜欢凉水。')
        for quote in ['用户喜欢温水。', '我喜欢喝温水', '我喜欢喝咖啡。', '我喜欢喝温水，但运动之后更喜欢凉水。\n']:
            self.store.provider = lambda request, cancel: PreferenceProviderReply((PreferenceSuggestion(source_id, quote),), 'synthetic')
            with self.subTest(quote=quote):
                self.assertEqual(self.collect(source_id)['status'], 'failed')
                self.assertEqual(self.store.list(), [])
                self.assertEqual(self.memories(), [])

    def test_nonexplicit_and_conditional_or_third_person_lines_are_not_preferences(self):
        for text in ['今天天气很好。', '如果我喜欢咖啡，你会怎么办？', '她说她喜欢喝温水。', '角色设定：我喜欢喝温水。']:
            with self.subTest(text=text):
                self.assertEqual(self.collect(self.source(text))['status'], 'failed')
        self.assertEqual(self.store.list(), [])

    def test_full_explicit_line_selected_from_bounded_user_message(self):
        source_id = self.source('今天想随便聊聊。\n我不喜欢你总是催我学习。\n先说到这里。')
        self.store.provider = lambda request, cancel: PreferenceProviderReply((PreferenceSuggestion(source_id, '我不喜欢你总是催我学习。'),), 'synthetic')
        candidate = self.candidate(source_id)
        self.assertEqual(candidate['text'], '我不喜欢你总是催我学习。')

    def test_source_missing_changed_or_forgotten_invalidates_pending_and_redacts(self):
        for operation in ('delete', 'edit', 'forget'):
            source_id = self.source('我喜欢喝温水。' + operation)
            candidate = self.candidate(source_id)
            with self.connect() as connection:
                if operation == 'delete':
                    connection.execute('DELETE FROM messages WHERE id=?', (source_id,))
                elif operation == 'edit':
                    connection.execute('UPDATE messages SET text=? WHERE id=?', ('我喜欢冷水。', source_id))
            if operation == 'forget':
                self.forget(candidate['text'])
            with self.subTest(operation=operation):
                with self.assertRaises(PreferenceLearningError):
                    self.store.decide(candidate['candidate_id'], 'confirm')
                row = next(row for row in self.store.list() if row['candidate_id'] == candidate['candidate_id'])
                self.assertEqual(row['text'], '')
                self.assertIn(row['status'], ('stale', 'forgotten'))
                self.assertEqual(self.memories(), [])

    def test_list_redacts_pending_sources_and_request_cache_cannot_leak_old_text(self):
        source_id = self.source()
        request_id = uuid4().hex
        candidate = self.store.collect(request_id, [source_id])['candidates'][0]
        with self.connect() as connection:
            connection.execute('DELETE FROM messages WHERE id=?', (source_id,))
        self.assertEqual(self.store.list()[0]['text'], '')
        cached = self.store.collect(request_id, [source_id])
        self.assertEqual(cached['candidates'][0]['text'], '')
        self.assertNotIn(candidate['text'], json.dumps(cached, ensure_ascii=False))
        self.assertEqual(len(self.calls), 1)

    def test_confirmed_memory_can_outlive_cleared_chat_but_not_deleted_memory(self):
        candidate = self.candidate()
        confirmed = self.store.decide(candidate['candidate_id'], 'confirm')
        with self.connect() as connection:
            connection.execute('DELETE FROM messages')
        self.assertEqual(self.store.list()[0]['status'], 'confirmed')
        self.assertEqual(self.store.decide(candidate['candidate_id'], 'confirm'), confirmed)
        with self.connect() as connection:
            connection.execute('DELETE FROM memories')
        self.assertEqual(self.store.list()[0]['status'], 'stale')
        self.assertEqual(self.store.list()[0]['text'], '')
        with self.assertRaises(PreferenceLearningError):
            self.store.decide(candidate['candidate_id'], 'confirm')

    def test_external_forget_redacts_confirmed_candidate_immediately_and_no_reconstruction(self):
        candidate = self.candidate()
        self.store.decide(candidate['candidate_id'], 'confirm')
        self.forget(candidate['text'])
        self.assertEqual(self.store.reconcile(), 1)
        self.assertEqual(self.store.list()[0]['status'], 'forgotten')
        self.assertEqual(self.store.list()[0]['text'], '')
        self.assertEqual(self.memories(), [])
        with self.assertRaises(PreferenceLearningError):
            self.collect(candidate['source_message_id'])

    def test_external_memory_edit_preserves_new_manual_text_but_redacts_old_candidate(self):
        candidate = self.candidate()
        self.store.decide(candidate['candidate_id'], 'confirm')
        with self.connect() as connection:
            connection.execute('UPDATE memories SET text=?', ('我喜欢冷水。',))
        self.assertEqual(self.store.list()[0]['text'], '')
        self.assertEqual(self.store.list()[0]['status'], 'stale')
        self.assertEqual(self.memories()[0]['text'], '我喜欢冷水。')

    def test_reject_deduplicates_without_resurfacing_and_never_writes_memory(self):
        source_id = self.source()
        candidate = self.candidate(source_id)
        self.assertEqual(self.store.decide(candidate['candidate_id'], 'reject')['status'], 'rejected')
        repeated = self.candidate(source_id)
        self.assertEqual(repeated['candidate_id'], candidate['candidate_id'])
        self.assertEqual(repeated['status'], 'rejected')
        with self.assertRaises(PreferenceLearningError):
            self.store.decide(candidate['candidate_id'], 'confirm')
        self.assertEqual(self.memories(), [])

    def test_delete_confirmed_memory_forgets_and_clears_candidate_text(self):
        candidate = self.candidate()
        self.store.decide(candidate['candidate_id'], 'confirm')
        removed = self.store.decide(candidate['candidate_id'], 'delete')
        self.assertEqual(removed['status'], 'deleted')
        self.assertEqual(removed['text'], '')
        self.assertEqual(self.memories(), [])
        self.assertEqual(self.store.decide(candidate['candidate_id'], 'delete')['text'], '')
        with self.assertRaises(PreferenceLearningError):
            self.collect(candidate['source_message_id'])

    def test_correction_requires_new_real_user_source_and_separate_confirmation(self):
        candidate = self.candidate()
        self.store.decide(candidate['candidate_id'], 'confirm')
        source_id = self.source('我更喜欢凉水。')
        replacement = self.store.correct(candidate['candidate_id'], source_id, '我更喜欢凉水。')
        self.assertEqual(replacement['previous_source_message_id'], candidate['source_message_id'])
        self.assertEqual(replacement['status'], 'pending')
        self.assertEqual(self.memories(), [])
        old = next(row for row in self.store.list() if row['candidate_id'] == candidate['candidate_id'])
        self.assertEqual(old['text'], '')
        self.assertEqual(old['status'], 'corrected')
        self.store.decide(replacement['candidate_id'], 'confirm')
        self.assertEqual([row['text'] for row in self.memories()], ['我更喜欢凉水。'])

    def test_invalid_correction_never_removes_old_confirmed_memory(self):
        candidate = self.candidate()
        self.store.decide(candidate['candidate_id'], 'confirm')
        for source_id, quote in [(candidate['source_message_id'], candidate['text']),
                                 (self.source('我喜欢冷水。', role='assistant'), '我喜欢冷水。'),
                                 (self.source('我喜欢凉水。'), '我喜欢咖啡。')]:
            with self.subTest(source_id=source_id), self.assertRaises(PreferenceLearningError):
                self.store.correct(candidate['candidate_id'], source_id, quote)
            self.assertEqual(self.memories()[0]['text'], candidate['text'])

    def test_request_id_cache_deduplicates_provider_and_conflicting_ids_rejected(self):
        source_id = self.source()
        request_id = uuid4().hex
        first = self.store.collect(request_id, [source_id])
        self.assertEqual(self.store.collect(request_id, [source_id]), first)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(PreferenceLearningError):
            self.store.collect(request_id, [self.source('我喜欢咖啡。')])

    def test_scope_binding_and_inactive_role_are_rejected(self):
        with self.assertRaises(PreferenceLearningError):
            PreferenceLearningStore(self.path, str(uuid4()))
        candidate = self.candidate()
        self.current = False
        for action in (lambda: self.collect(), lambda: self.store.list(),
                       lambda: self.store.decide(candidate['candidate_id'], 'confirm')):
            with self.assertRaises(PreferenceLearningError):
                action()
        self.assertEqual(self.memories(), [])

    def test_bounded_source_ids_and_large_history_are_rejected_before_provider(self):
        for ids in ([], [True], [0], ['1'], [1, 1], list(range(1, 14)), '1'):
            with self.subTest(ids=ids), self.assertRaises(PreferenceLearningError):
                self.store.collect(uuid4().hex, ids)
        with self.assertRaises(PreferenceLearningError):
            self.collect(self.source('我喜欢' + '水' * 3000))
        ids = [self.source('我喜欢' + '水' * 2500) for _ in range(5)]
        with self.assertRaises(PreferenceLearningError):
            self.store.collect(uuid4().hex, ids)
        self.assertEqual(self.calls, [])

    def test_malformed_provider_and_unrequested_message_cannot_create_candidates(self):
        requested = self.source()
        other = self.source('我喜欢咖啡。')
        replies = [None, {}, PreferenceProviderReply((PreferenceSuggestion(other, '我喜欢咖啡。'),), 'synthetic'),
                   PreferenceProviderReply((), ''), PreferenceProviderReply(tuple(PreferenceSuggestion(requested, '我喜欢喝温水。') for _ in range(11)), 'synthetic')]
        for reply in replies:
            self.store.provider = lambda request, cancel: reply
            with self.subTest(reply=reply):
                self.assertEqual(self.collect(requested)['status'], 'failed')
                self.assertEqual(self.store.list(), [])

    def test_memory_limit_does_not_insert_sixty_first_entry(self):
        candidate = self.candidate()
        with self.connect() as connection:
            connection.executemany("INSERT INTO memories(text,created,source) VALUES(?,'now','manual')", [(str(index),) for index in range(60)])
        with self.assertRaises(PreferenceLearningError) as error:
            self.store.decide(candidate['candidate_id'], 'confirm')
        self.assertEqual(error.exception.code, 'memory_limit_reached')
        self.assertEqual(len(self.memories()), 60)

    def test_concurrent_confirmation_creates_one_memory(self):
        candidate = self.candidate()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.store.decide(candidate['candidate_id'], 'confirm'), range(4)))
        self.assertTrue(all(row['status'] == 'confirmed' for row in results))
        self.assertEqual(len(self.memories()), 1)

    def test_late_noncooperative_provider_cannot_survive_cancel_or_memory_off(self):
        for action in ('cancel', 'memory_off', 'source_changed', 'scope_changed'):
            source_id = self.source('我喜欢喝温水。' + action)
            entered, release = threading.Event(), threading.Event()
            def provider(request, cancel):
                entered.set()
                if not release.wait(4):
                    raise TimeoutError('test release missing')
                return PreferenceProviderReply((PreferenceSuggestion(source_id, request.sources[0].text),), 'synthetic')
            self.store.provider = provider
            request_id = uuid4().hex
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.collect, source_id, request_id=request_id)
                self.assertTrue(entered.wait(2))
                if action == 'cancel':
                    self.assertEqual(self.store.cancel_generating(), 1)
                elif action == 'memory_off':
                    self.mode('off')
                elif action == 'source_changed':
                    with self.connect() as connection:
                        connection.execute('UPDATE messages SET text=? WHERE id=?', ('我喜欢咖啡。', source_id))
                else:
                    self.current = False
                release.set()
                result = future.result(timeout=3)
            self.assertIn(result['status'], ('cancelled', 'failed'))
            self.assertEqual(result['candidates'], [])
            self.current = True
            self.mode('relevant')
            self.assertEqual(self.store.list(), [])
            self.assertEqual(self.memories(), [])

    def test_restart_does_not_rerun_interrupted_provider(self):
        with self.connect() as connection:
            connection.execute("INSERT INTO preference_requests VALUES('interrupted','digest','generating',NULL,'[]','','old-runtime','now')")
        restarted = PreferenceLearningStore(self.path, self.role, provider=self.store.provider, runtime_session='new-runtime')
        with self.connect() as connection:
            row = connection.execute("SELECT status,error FROM preference_requests WHERE request_id='interrupted'").fetchone()
        self.assertEqual(tuple(row), ('failed', 'interrupted_on_restart'))
        self.assertEqual(self.calls, [])
        self.assertEqual(restarted.list(), [])

    def test_stale_store_never_recreates_deleted_role_database(self):
        self.path.unlink()
        with self.assertRaises(PreferenceLearningError) as error:
            self.store.list()
        self.assertEqual(error.exception.code, 'role_database_unavailable')
        self.assertFalse(self.path.exists())

    def test_bounded_216_traces_648_actions_preserve_confirmation_and_forget_invariants(self):
        actions = ('confirm', 'reject', 'delete', 'forget', 'remove_source', 'memory_off')
        operations = 0
        for trace in itertools.product(actions, repeat=3):
            with self.subTest(trace=trace):
                with self.connect() as connection:
                    for table in ('preference_requests', 'preference_candidates', 'messages', 'memories', 'forgotten'):
                        connection.execute('DELETE FROM ' + table)
                self.mode('relevant')
                source_id = self.source()
                candidate = self.candidate(source_id)
                confirmed_once = False
                forgotten = False
                memory_off = False
                for action in trace:
                    before = len(self.memories())
                    try:
                        if action in ('confirm', 'reject', 'delete'):
                            result = self.store.decide(candidate['candidate_id'], action)
                            if action == 'confirm' and result['status'] == 'confirmed':
                                confirmed_once = True
                            if action == 'delete':
                                forgotten = True
                        elif action == 'forget':
                            self.forget(candidate['text'])
                            forgotten = True
                        elif action == 'remove_source':
                            with self.connect() as connection:
                                connection.execute('DELETE FROM messages WHERE id=?', (source_id,))
                        else:
                            self.mode('off')
                            memory_off = True
                    except PreferenceLearningError:
                        pass
                    self.store.reconcile()
                    memories = self.memories()
                    self.assertLessEqual(len(memories), 1)
                    if memories:
                        self.assertTrue(confirmed_once, (trace, action))
                        self.assertFalse(forgotten, (trace, action))
                    if memory_off:
                        self.assertLessEqual(len(memories), before, (trace, action))
                    operations += 1
        self.assertEqual(operations, 648)


if __name__ == '__main__':
    unittest.main()
