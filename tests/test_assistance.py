"""Real SQLite, bounded CSV and controlled provider concurrency; no account IO."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import itertools
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from companion_runtime.assistance import AssistanceError, AssistanceStore, ProviderReply, analyze_csv, migrate_connection


class AssistanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / 'profile.sqlite3'
        self.role = str(uuid4())
        self.clock = 1800000000.0
        self.store = AssistanceStore(self.path, self.role, clock=lambda:self.clock)

    def tearDown(self):
        self.temporary.cleanup()

    def schedule(self, request='request-1', title='吃晚饭'):
        due = dt.datetime.fromtimestamp(self.clock + 3600, dt.timezone.utc).isoformat()
        return self.store.create(request, 'schedule', {'title':title, 'due_at':due})

    def rows(self, query, args=()):
        with sqlite3.connect(self.path) as connection:
            return connection.execute(query, args).fetchall()

    def error(self, code, call):
        with self.assertRaises(AssistanceError) as caught:call()
        self.assertEqual(code, caught.exception.code)

    def test_schedule_is_proposal_until_explicit_confirm_then_idempotent(self):
        proposal = self.schedule()
        self.assertEqual('proposed', proposal['status'])
        self.assertEqual('local_schedule', proposal['permission_scope'])
        self.assertEqual([], self.rows('SELECT * FROM tasks'))
        self.assertEqual(proposal, self.schedule())
        accepted = self.store.decide(proposal['action_id'], 'confirm')
        self.assertEqual('confirmed', accepted['status'])
        self.assertEqual(accepted, self.store.decide(proposal['action_id'], 'confirm'))
        self.assertEqual(1, len(self.rows('SELECT * FROM tasks')))
        self.assertEqual(False, accepted['result']['external_actions'])

    def test_same_request_different_input_conflicts_without_second_task(self):
        self.schedule()
        self.error('request_id_conflict', lambda:self.schedule(title='另一件事'))
        self.assertEqual(1, len(self.store.list()))

    def test_ten_concurrent_confirmations_create_exactly_one_real_task(self):
        proposal = self.schedule()
        def confirm(_):
            peer = AssistanceStore(self.path, self.role, clock=lambda:self.clock)
            return peer.decide(proposal['action_id'], 'confirm')['result']['task_id']
        with ThreadPoolExecutor(max_workers=10) as pool:ids = list(pool.map(confirm, range(10)))
        self.assertEqual(1, len(set(ids)))
        self.assertEqual(1, len(self.rows('SELECT id FROM tasks')))

    def test_real_sqlite_failure_rolls_back_task_and_confirmation_atomically(self):
        proposal = self.schedule()
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TRIGGER fail_confirmation BEFORE UPDATE OF status ON assistance_proposals WHEN NEW.status='confirmed' BEGIN SELECT RAISE(ABORT,'controlled storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.decide(proposal['action_id'], 'confirm')
        self.assertEqual('proposed', self.store.get(proposal['action_id'])['status'])
        self.assertEqual([], self.rows('SELECT id FROM tasks'))
        with sqlite3.connect(self.path) as connection:connection.execute('DROP TRIGGER fail_confirmation')
        self.store.decide(proposal['action_id'], 'confirm')
        self.assertEqual(1, len(self.rows('SELECT id FROM tasks')))

    def test_rejected_and_cancelled_proposals_cannot_be_revived(self):
        for decision in ('reject', 'cancel'):
            proposal = self.schedule(decision)
            result = self.store.decide(proposal['action_id'], decision)
            self.assertEqual(result, self.store.decide(proposal['action_id'], decision))
            self.error('proposal_already_terminal', lambda:self.store.decide(proposal['action_id'], 'confirm'))
        self.assertEqual([], self.rows('SELECT id FROM tasks'))

    def test_confirmed_schedule_cancel_updates_old_scheduler_table(self):
        proposal = self.schedule()
        accepted = self.store.decide(proposal['action_id'], 'confirm')
        self.store.decide(proposal['action_id'], 'cancel')
        self.assertEqual([('cancelled',)], self.rows('SELECT status FROM tasks WHERE id=?', (accepted['result']['task_id'],)))
        reopened = AssistanceStore(self.path, self.role, clock=lambda:self.clock)
        self.assertEqual('cancelled', reopened.get(proposal['action_id'])['status'])

    def test_same_id_retry_after_due_is_still_idempotent_but_confirm_is_rejected(self):
        proposal = self.schedule()
        inputs = proposal['inputs']
        self.clock += 4000
        self.assertEqual(proposal['action_id'], self.store.create('request-1', 'schedule', inputs)['action_id'])
        self.error('due_out_of_range', lambda:self.store.decide(proposal['action_id'], 'confirm'))
        self.assertEqual([], self.rows('SELECT id FROM tasks'))

    def test_invalid_schedule_times_or_external_fields_do_not_write(self):
        for due in ('tomorrow', '2026-01-01T12:00:00', '2026-01-01T12:00:00+00:00'):
            with self.assertRaises(AssistanceError):self.store.create('bad', 'schedule', {'title':'a', 'due_at':due})
        valid = dt.datetime.fromtimestamp(self.clock+10, dt.timezone.utc).isoformat()
        self.error('invalid_inputs', lambda:self.store.create('bad', 'schedule', {'title':'a', 'due_at':valid, 'calendar_token':'secret'}))
        self.assertEqual([], self.store.list())

    def test_cross_role_database_and_action_lookup_are_rejected(self):
        proposal = self.schedule()
        other_role = str(uuid4())
        self.error('role_scope_mismatch', lambda:AssistanceStore(self.path, other_role))
        other = AssistanceStore(self.root/'other.sqlite3', other_role)
        self.error('proposal_not_found', lambda:other.get(proposal['action_id']))
        self.error('proposal_not_found', lambda:other.decide(proposal['action_id'], 'confirm'))

    def test_restart_keeps_unconfirmed_proposal_and_does_not_execute(self):
        proposal = self.schedule()
        reopened = AssistanceStore(self.path, self.role, clock=lambda:self.clock, runtime_session='next-runtime')
        self.assertEqual(proposal, reopened.get(proposal['action_id']))
        self.assertEqual([], self.rows('SELECT id FROM tasks'))

    def test_all_unconfigured_advice_is_honestly_unavailable(self):
        for kind in ('outfit', 'dinner', 'brainstorm', 'game'):
            inputs = {'query':'请根据当前材料分析', 'context':'用户提供的明确材料'}
            if kind == 'game':inputs.update({'game':'自述棋局'})
            result = self.store.create(kind, kind, inputs)
            self.assertEqual('unavailable', result['status'])
            self.assertEqual('', result['summary'])
            self.error('proposal_already_terminal', lambda:self.store.decide(result['action_id'], 'confirm'))
        self.assertFalse(self.store.snapshot()['external_execution_enabled'])

    def test_real_provider_contract_is_explicit_capability_and_has_no_memory_access(self):
        observed = []
        def provider(request, cancel):
            observed.append((request, cancel.is_set()))
            return ProviderReply('基于你给出的库存，两种晚餐选择如下。', 'controlled-test-provider')
        store = AssistanceStore(self.path, self.role, provider=provider, provider_kinds={'dinner'}, clock=lambda:self.clock)
        result = store.create('dinner', 'dinner', {'query':'晚餐怎么吃', 'context':'现有番茄和面条'})
        self.assertEqual('proposed', result['status'])
        self.assertEqual('现有番茄和面条', observed[0][0].inputs['context'])
        self.assertEqual('controlled-test-provider', result['source_evidence'][-1]['provider_id'])
        self.assertEqual('read_only', result['permission_scope'])
        self.assertEqual('confirmed', store.decide(result['action_id'], 'confirm')['status'])
        self.assertEqual([], self.rows('SELECT id FROM tasks'))
        self.assertEqual('unavailable', store.create('other', 'brainstorm', {'query':'想点子'})['status'])

    def test_provider_exception_is_sanitized_and_retry_does_not_rerun(self):
        calls = []
        def provider(request, cancel):
            calls.append(request.request_id)
            raise RuntimeError('secret-token-and-private-path')
        store = AssistanceStore(self.path, self.role, provider=provider, provider_kinds={'brainstorm'})
        result = store.create('failure', 'brainstorm', {'query':'想点子'})
        self.assertEqual('failed', result['status'])
        self.assertEqual('provider_failed', result['error'])
        self.assertNotIn('secret-token', json.dumps(result))
        self.assertEqual(result, store.create('failure', 'brainstorm', {'query':'想点子'}))
        self.assertEqual(1, len(calls))

    def test_cancel_from_another_store_signals_actual_provider_and_discards_late_reply(self):
        entered, release = threading.Event(), threading.Event()
        tokens = []
        def provider(request, cancel):
            tokens.append(cancel);entered.set()
            if not release.wait(3):raise AssertionError('Fixture was not released')
            return ProviderReply('迟到建议不能复活', 'controlled-provider')
        store = AssistanceStore(self.path, self.role, provider=provider, provider_kinds={'brainstorm'})
        results = []
        worker = threading.Thread(target=lambda:results.append(store.create('slow', 'brainstorm', {'query':'点子'})))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            peer = AssistanceStore(self.path, self.role)
            proposal = peer.list()[0]
            peer.decide(proposal['action_id'], 'cancel')
            self.assertTrue(tokens[0].is_set())
        finally:release.set();worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual('cancelled', results[0]['status'])
        self.assertEqual('', results[0]['summary'])

    def test_restart_fails_interrupted_provider_without_reexecution(self):
        entered, release = threading.Event(), threading.Event()
        def provider(request, cancel):
            entered.set();release.wait(3)
            return ProviderReply('迟到', 'controlled-provider')
        store = AssistanceStore(self.path, self.role, provider=provider, provider_kinds={'brainstorm'}, runtime_session='first')
        worker = threading.Thread(target=lambda:store.create('interrupted', 'brainstorm', {'query':'点子'}))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            reopened = AssistanceStore(self.path, self.role, runtime_session='second')
            result = reopened.list()[0]
            self.assertEqual('failed', result['status'])
            self.assertEqual('interrupted_on_restart', result['error'])
        finally:release.set();worker.join(3)
        self.assertEqual('failed', reopened.list()[0]['status'])

    def test_actual_process_exit_and_reopen_fails_unfinished_generation(self):
        script = '''
import os,sys
from pathlib import Path
from companion_runtime.assistance import AssistanceStore
def provider(request,cancel):
    os._exit(0)
store=AssistanceStore(Path(sys.argv[1]),sys.argv[2],provider=provider,provider_kinds={'brainstorm'})
store.create('abrupt-process','brainstorm',{'query':'点子'})
'''
        process = subprocess.run([sys.executable, '-c', script, str(self.path), self.role], capture_output=True, timeout=5)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual([('generating',)], self.rows("SELECT status FROM assistance_proposals WHERE request_id='abrupt-process'"))
        reopened = AssistanceStore(self.path, self.role)
        result = reopened.create('abrupt-process', 'brainstorm', {'query':'点子'})
        self.assertEqual(('failed', 'interrupted_on_restart'), (result['status'], result['error']))

    def test_game_context_and_unknown_permissions_are_not_invented(self):
        self.error('game_context_required', lambda:self.store.create('game', 'game', {'query':'帮我赢', 'game':'未知游戏'}))
        self.error('invalid_inputs', lambda:self.store.create('buy', 'dinner', {'query':'晚饭', 'permission_scope':'purchase'}))
        self.error('invalid_kind', lambda:self.store.create('control', 'game_control', {'query':'开枪'}))
        self.error('invalid_kind', lambda:self.store.create('array', [], {}))
        self.error('invalid_decision', lambda:self.store.decide('valid-id', {}))

    def test_input_and_result_bounds_are_enforced(self):
        for inputs in ({'query':'x'*2001}, {'query':'x', 'context':'y'*6001}, {'query':'\ud800'}):
            with self.assertRaises(AssistanceError):self.store.create('bad', 'dinner', inputs)
        for limit in (True, 0, 101, '5'):
            self.error('invalid_limit', lambda:self.store.list(limit))
        with patch('companion_runtime.assistance.MAX_PROPOSALS', 2):
            one = self.schedule('one');self.schedule('two')
            self.error('proposal_limit_reached', lambda:self.schedule('three'))
            self.store.decide(one['action_id'], 'reject')
            self.assertEqual('proposed', self.schedule('three')['status'])

    def test_additive_migration_preserves_legacy_rows_without_guessing_message_link(self):
        old = self.root/'legacy.sqlite3'
        with sqlite3.connect(old) as connection:
            connection.executescript("CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT,due REAL,status TEXT,created TEXT,kind TEXT);CREATE TABLE messages(id INTEGER PRIMARY KEY,role TEXT,text TEXT,created TEXT,request_id TEXT,kind TEXT);")
            connection.execute("INSERT INTO tasks VALUES(7,'旧约定',1,'pending','old','reminder')")
            connection.execute("INSERT INTO messages VALUES(8,'assistant','旧提示','old',NULL,'reminder')")
        store = AssistanceStore(old, self.role)
        with sqlite3.connect(old) as connection:
            self.assertEqual(('旧提示', None), connection.execute('SELECT text,task_id FROM messages').fetchone())
            self.assertEqual(('旧约定', None), connection.execute('SELECT title,assistance_action_id FROM tasks').fetchone())
        self.assertEqual(7, store.snapshot()['legacy_tasks'][0]['id'])
        store.cancel_legacy_task(7)
        self.assertEqual('cancelled', store.snapshot()['legacy_tasks'][0]['status'])

    def test_migration_does_not_implicitly_commit_its_callers_transaction(self):
        path = self.root/'migration-rollback.sqlite3'
        with sqlite3.connect(path) as connection:connection.execute('CREATE TABLE before_migration(value TEXT)')
        with sqlite3.connect(path) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT INTO before_migration VALUES('must roll back')")
            migrate_connection(connection)
            connection.rollback()
            self.assertEqual([], connection.execute('SELECT * FROM before_migration').fetchall())
            self.assertEqual([], connection.execute("SELECT name FROM sqlite_master WHERE name='assistance_proposals'").fetchall())

    def test_pause_stops_old_agreements_and_resume_does_not_rearm_them(self):
        proposal = self.schedule()
        self.store.decide(proposal['action_id'], 'confirm')
        snapshot = self.store.set_proactive_paused(True)
        self.assertTrue(snapshot['proactive_paused'])
        self.assertEqual('paused', snapshot['legacy_tasks'][0]['status'])
        snapshot = self.store.set_proactive_paused(False)
        self.assertFalse(snapshot['proactive_paused'])
        self.assertEqual('paused', snapshot['legacy_tasks'][0]['status'])
        self.error('invalid_paused', lambda:self.store.set_proactive_paused(1))

    def test_linked_task_cancel_is_visible_in_proposal_and_completed_is_protected(self):
        proposal = self.schedule()
        accepted = self.store.decide(proposal['action_id'], 'confirm')
        task_id = accepted['result']['task_id']
        with sqlite3.connect(self.path) as connection:connection.execute("UPDATE tasks SET status='completed' WHERE id=?", (task_id,))
        self.error('task_already_completed', lambda:self.store.cancel_legacy_task(task_id))
        self.error('task_already_completed', lambda:self.store.decide(proposal['action_id'], 'cancel'))
        with sqlite3.connect(self.path) as connection:connection.execute("UPDATE tasks SET status='done' WHERE id=?", (task_id,))
        self.store.cancel_legacy_task(task_id)
        self.assertEqual('cancelled', self.store.get(proposal['action_id'])['status'])

    def test_every_terminal_decision_order_keeps_at_most_one_task(self):
        for index, decisions in enumerate(itertools.product(('confirm', 'reject', 'cancel'), repeat=3)):
            proposal = self.schedule('sequence-' + str(index))
            for decision in decisions:
                try:self.store.decide(proposal['action_id'], decision)
                except AssistanceError as error:self.assertEqual(409, error.status)
            self.assertLessEqual(len(self.rows('SELECT id FROM tasks WHERE assistance_action_id=?', (proposal['action_id'],))), 1)

    def test_csv_proposal_has_actual_statistics_and_does_not_store_raw_cells(self):
        result = self.store.create('csv', 'data_analysis', {'csv_text':'name,amount\nsecret-cell-123,10\nother,20\n', 'filename':'sales.csv'})
        self.assertEqual('proposed', result['status'])
        self.assertEqual('30', result['result']['columns'][1]['sum'])
        self.assertNotIn('csv_text', result['inputs'])
        self.assertNotIn('secret-cell-123', ''.join(str(row) for row in self.rows('SELECT inputs,result,source_evidence FROM assistance_proposals')))
        self.assertFalse(result['result']['formula_execution'])


class CSVTests(unittest.TestCase):
    def test_exact_decimal_statistics_and_missing_mixed_cells(self):
        result = analyze_csv('value,note\n0.1,a\n0.2,b\n,c\nunknown,d\n')
        column = result['columns'][0]
        self.assertEqual((4, 2), (result['row_count'], result['column_count']))
        self.assertEqual(('0.3', '0.15', 1, 1, 'mixed'), (column['sum'], column['mean'], column['missing'], column['non_numeric_count'], column['type']))

    def test_quoted_delimiter_newline_and_bom_are_real_csv(self):
        result = analyze_csv('\ufeffname;amount\n"a; b";3\n"two\nlines";5\n', ';')
        self.assertEqual(2, result['row_count'])
        self.assertEqual('8', result['columns'][1]['sum'])

    def test_formulas_and_python_are_text_never_executed(self):
        result = analyze_csv('item\n=1+1\n__import__("os").system("false")\n@cmd\n')
        self.assertEqual('text', result['columns'][0]['type'])
        self.assertEqual(2, result['columns'][0]['formula_like_cells'])
        self.assertFalse(result['formula_execution'])

    def test_csv_boundaries_and_malformed_shapes_fail_closed(self):
        for value in ('', 'a,a\n1,2', 'a,b\n1', 'a\n"unterminated', 'a\n'+'x'*2049, 'a\n'+'1\n'*5001, 'a\n'+'x'*262144, 'a\n\x00'):
            with self.assertRaises(AssistanceError, msg=value[:20]):analyze_csv(value)
        with self.assertRaises(AssistanceError):analyze_csv(','.join('c'+str(i) for i in range(33))+'\n'+','.join('1' for _ in range(33)))

    def test_nonfinite_huge_exponents_and_literal_nan_are_not_numbers(self):
        result = analyze_csv('a\nNaN\nInfinity\n1e999\n1e308\n-1e308\n')
        column = result['columns'][0]
        self.assertEqual(2, column['numeric_count'])
        self.assertEqual(3, column['non_numeric_count'])
        json.dumps(result, allow_nan=False)


if __name__ == '__main__':unittest.main()
