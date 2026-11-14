"""Implementation property regressions, separate from the finite TLA+ models.

These tests force the real application to pause at mutex admission/cleanup,
then run a private turn. In-memory negative controls remove only the relevant
DISPATCH critical section; no production file is changed. Playback checks use
the real tracker/merge implementation over every action word of bounded length.
"""
from __future__ import annotations

import ast
from collections import deque
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from companion_runtime.playback import PlaybackError, PlaybackTracker, context_for, merge_receipts

ACTION_ALPHABET = ('playing', 'completed', 'stopped', 'new', 'switch', 'old_end',
                   'bad_nonce', 'bad_scope', 'bad_owner', 'bad_appearance', 'wrong_message')
PROPERTY_RESULT = {'traces': 0, 'operations': 0, 'max_depth': 0}
SCHEDULER_RESULT = []


def _app_without_boundary(edge=None):
    source = (ROOT/'app/server.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    removed = []
    class RemoveOneBoundary(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name != 'connector_request':return node
            return self.generic_visit(node)
        def visit_With(self, node):
            node = self.generic_visit(node)
            if edge is None or not any(isinstance(item.context_expr, ast.Name) and item.context_expr.id == 'DISPATCH_LOCK' for item in node.items):
                return node
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and isinstance(n.func.value, ast.Name) and n.func.value.id == 'MODEL_LOCK']
            methods = {n.func.attr for n in calls}
            matches = ('acquire' in methods) if edge == 'admission' else ('release' in methods and 'acquire' not in methods)
            if matches:
                removed.append(node.lineno)
                return node.body
            return node
    tree = RemoveOneBoundary().visit(tree)
    ast.fix_missing_locations(tree)
    if edge is not None and len(removed) != 1:
        raise AssertionError(f'Expected exactly one {edge} source boundary, found {removed}')
    module = types.ModuleType('formal_app_' + uuid4().hex)
    module.__file__ = str(ROOT/'app/server.py')
    exec(compile(tree, module.__file__, 'exec'), module.__dict__)
    return module, hashlib.sha256(source.encode()).hexdigest(), removed


class _DispatchProbe:
    def __init__(self):
        self.lock = threading.RLock()
        self.private_attempt = threading.Event()
        self.private_entered = threading.Event()
    def __enter__(self):
        private = threading.current_thread().name == 'formal-private'
        if private:self.private_attempt.set()
        self.lock.acquire()
        if private:self.private_entered.set()
        return self
    def __exit__(self,*_):self.lock.release()


class _ModelProbe:
    def __init__(self, edge):
        self.lock = threading.Lock()
        self.edge = edge
        self.checkpoint = threading.Event()
        self.proceed = threading.Event()
        self.used = False
    def acquire(self, blocking=True, timeout=-1):
        ok = self.lock.acquire(blocking, timeout)
        if ok and self.edge == 'admission' and threading.current_thread().name == 'formal-public' and not self.used:
            self.used = True;self.checkpoint.set()
            if not self.proceed.wait(4):raise AssertionError('Test did not release public admission checkpoint')
        return ok
    def release(self):
        if self.edge == 'cleanup' and threading.current_thread().name == 'formal-public' and not self.used:
            self.used = True;self.checkpoint.set()
            if not self.proceed.wait(4):raise AssertionError('Test did not release public cleanup checkpoint')
        self.lock.release()
    def locked(self):return self.lock.locked()


class FormalSourceInterleavingTests(unittest.TestCase):
    def _run(self, edge, mutate):
        app, source_sha, removed = _app_without_boundary(edge if mutate else None)
        with tempfile.TemporaryDirectory(prefix='formal-app-') as temporary:
            app.DATA = Path(temporary)
            app.init()
            app.MODEL_LOCK = model = _ModelProbe(edge)
            app.DISPATCH_LOCK = dispatch = _DispatchProbe()
            event = {'source':'bilibili-open-live','room_id':'1','event_id':'formal-event',
                     'text':'public fixture','expires_at':time.monotonic()+60}
            service = types.SimpleNamespace(lock=threading.RLock(), public_generation=None,
                public_persona='public-only fixture', public_replies=deque(), public_events=lambda:[event])
            from companion_runtime.live_output import LiveOutput
            service.output = LiveOutput()
            service.output.set_material('public-only fixture', True)
            app.integrations = lambda:service
            app.INTEGRATIONS[str(app.DATA.resolve())] = service
            app.generate_once = lambda *_args,**_kwargs:'public fixture reply'
            app.generate = lambda *_args,**_kwargs:'private fixture reply'
            outcomes = {}
            def public():
                try:outcomes['public']=app.connector_request('bili/reply',{'event_id':'formal-event'})
                except Exception as error:outcomes['public_error']={'type':type(error).__name__,'status':getattr(error,'status',None)}
            def private():
                try:outcomes['private']=app.chat({'text':'private fixture','request_id':'formal-private-'+uuid4().hex})
                except Exception as error:outcomes['private_error']={'type':type(error).__name__,'status':getattr(error,'status',None)}
            pub = threading.Thread(target=public,name='formal-public')
            priv = threading.Thread(target=private,name='formal-private')
            try:
                pub.start();self.assertTrue(model.checkpoint.wait(4),'Public path missed targeted actual mutex operation')
                priv.start();self.assertTrue(dispatch.private_attempt.wait(4))
                if mutate:
                    self.assertTrue(dispatch.private_entered.wait(4),'Negative control failed to expose private entry')
                    priv.join(4)
                    self.assertEqual(outcomes.get('private_error',{}).get('status'),409,outcomes)
                else:
                    self.assertFalse(dispatch.private_entered.wait(.1),'Private entered the supposedly atomic public boundary')
                model.proceed.set();pub.join(4);priv.join(4)
                self.assertFalse(pub.is_alive() or priv.is_alive(),'A model mutex remained held')
                if not mutate:
                    self.assertIn('private',outcomes,outcomes)
                    self.assertEqual(outcomes['private']['message']['text'],'private fixture reply')
                SCHEDULER_RESULT.append({'edge':edge,'negative_control':mutate,'source_sha256':source_sha,
                    'removed_dispatch_lines':removed,'private_status':outcomes.get('private_error',{}).get('status',200),
                    'observed_public_error':outcomes.get('public_error'),'passed':True})
            finally:
                model.proceed.set();pub.join(5)
                if priv.ident is not None:priv.join(5)
                app.INTEGRATIONS.clear()
    def test_actual_admission_is_atomic_for_private_request(self):self._run('admission',False)
    def test_legacy_admission_negative_control_exposes_409(self):self._run('admission',True)
    def test_actual_cleanup_is_atomic_for_private_request(self):self._run('cleanup',False)
    def test_legacy_cleanup_negative_control_exposes_409(self):self._run('cleanup',True)


def check_action_word(word):
    tracker = PlaybackTracker(max_entries=4)
    role, appearance = 'A','skin-0'
    texts = {'A':'甲乙尾','B':'不同角色'}
    ledger, longest, terminal, attempts = {}, {}, {}, []
    def persist(receipt):
        if not receipt.get('should_persist',True):return
        key=(receipt['character_id'],str(receipt['message_id']),receipt['text_sha'])
        before=ledger.get(key)
        previous=len(before.get('confirmed_text','')) if before else 0
        ledger[key]=merge_receipts(before,receipt)
        text=texts[receipt['character_id']]
        confirmed=ledger[key].get('confirmed_text','')
        assert text.startswith(confirmed)
        assert len(confirmed)>=previous
        longest[key]=max(longest.get(key,0),len(receipt.get('confirmed_text','')))
        assert len(confirmed)==longest[key]
        if ledger[key]['status'] in {'completed','stopped'}:
            view=context_for(text,ledger[key],message_id=1)
            assert view['text']==confirmed
    def begin():
        text=texts[role]
        audible=text[:2] if not attempts else text
        item=tracker.begin(role,appearance,1,text,duration_seconds=1,audible_text=audible)
        for stopped in item.pop('stopped_receipts'):persist(stopped)
        attempts.append(item)
        return item
    current=begin()
    for action in word:
        assert tracker.size()<=4
        PROPERTY_RESULT['operations']+=1
        if action=='new':
            current=begin();continue
        if action=='switch':
            for receipt in tracker.invalidate(reason='switch'):persist(receipt)
            role='B' if role=='A' else 'A';appearance='skin-1' if appearance=='skin-0' else 'skin-0'
            current=begin();continue
        item=attempts[0] if action=='old_end' else current
        nonce=item['nonce']
        target_role=item['character_id']
        if action=='bad_nonce':nonce=('A' if nonce[0]!='A' else 'B')+nonce[1:]
        if action=='bad_scope':target_role='forged-other-owner-role'
        target_appearance='forged-skin' if action=='bad_appearance' else item['appearance_id']
        target_owner='other-owner' if action=='bad_owner' else 'local'
        status={'playing':'playing','stopped':'stopped'}.get(action,'completed')
        position=.5 if status=='playing' else (0 if status=='stopped' else 1)
        try:
            receipt=tracker.receipt(item['playback_id'],nonce,character_id=target_role,
                appearance_id=target_appearance,position_seconds=position,duration_seconds=1,status=status,
                owner_id=target_owner,message_id=2 if action=='wrong_message' else 1)
        except PlaybackError:
            assert action in {'bad_nonce','bad_scope','bad_owner','bad_appearance','wrong_message'} or item['playback_id'] in terminal or action=='old_end' or action=='stopped'
            continue
        assert action not in {'bad_nonce','bad_scope','bad_owner','bad_appearance','wrong_message'}
        if not receipt['accepted']:
            assert receipt['stale'] and not receipt['should_persist'] and receipt['confirmed_text']==''
            continue
        assert item['playback_id']==current['playback_id']
        assert item['character_id']==role and item['appearance_id']==appearance
        prior=terminal.get(item['playback_id'])
        if prior is not None:assert status==prior
        if status in {'completed','stopped'}:terminal[item['playback_id']]=status
        if status=='completed':assert receipt['position_seconds']==receipt['duration_seconds']==1
        persist(receipt)
        assert tracker.size()<=4
    assert tracker.size()<=4


class FormalPlaybackImplementationTests(unittest.TestCase):
    def test_all_action_words_up_to_five_steps_preserve_scope_and_confirmation(self):
        # Exact finite test domain: 11 actions^5 words. Every shorter word is a
        # prefix of a length-five word and each prefix is checked after each step.
        for word in itertools.product(ACTION_ALPHABET,repeat=5):
            try:check_action_word(word)
            except Exception as error:
                raise AssertionError('Replayable action word: '+repr(word)) from error
            PROPERTY_RESULT['traces']+=1
        PROPERTY_RESULT['max_depth']=5

    def test_all_persistence_orders_keep_prior_full_confirmation(self):
        tracker=PlaybackTracker()
        first=tracker.begin('A','skin',1,'正文尾部',duration_seconds=1)
        pending={**first,'should_persist':True}
        complete=tracker.receipt(first['playback_id'],first['nonce'],character_id='A',appearance_id='skin',
            position_seconds=1,duration_seconds=1,status='completed')
        second=tracker.begin('A','skin',1,'正文尾部',duration_seconds=1)
        stopped=tracker.receipt(second['playback_id'],second['nonce'],character_id='A',appearance_id='skin',
            position_seconds=.5,duration_seconds=1,status='stopped')
        for order in itertools.permutations([pending,complete,stopped]):
            merged=None
            for receipt in order:merged=merge_receipts(merged,receipt)
            self.assertEqual(context_for('正文尾部',merged,message_id=1)['text'],'正文尾部')

    def test_sqlite_persistence_orders_keep_completed_prefix_after_scope_switch(self):
        # Exercise the application's actual transaction/read/merge/write, with
        # another identity active while old server receipts arrive out of order.
        for order in itertools.permutations(range(3)):
            app, _, _ = _app_without_boundary()
            with tempfile.TemporaryDirectory(prefix='formal-sqlite-') as temporary:
                app.DATA = Path(temporary)
                app.init()
                original_id = app.profile_id()
                with app.db() as connection:
                    inserted = connection.execute('INSERT INTO messages(role,text,created) VALUES(?,?,?)',
                                                  ('assistant','正文尾部',app.now()))
                    message_id = inserted.lastrowid
                tracker = PlaybackTracker()
                first = tracker.begin(original_id,'skin',message_id,'正文尾部',duration_seconds=1)
                pending = {**first,'should_persist':True}
                complete = tracker.receipt(first['playback_id'],first['nonce'],character_id=original_id,
                    appearance_id='skin',position_seconds=1,duration_seconds=1,status='completed')
                second = tracker.begin(original_id,'skin',message_id,'正文尾部',duration_seconds=1)
                tracker.receipt(second['playback_id'],second['nonce'],character_id=original_id,
                    appearance_id='skin',position_seconds=.5,duration_seconds=1,status='playing')
                stopped, = tracker.invalidate(reason='switch')
                other = app.catalog().create('test other identity')
                app.init_profile(other['id'])
                app.catalog().select(other['id'])
                receipts = [pending,complete,stopped]
                for index in order:
                    app.persist_playback(receipts[index])
                    self.assertEqual(app.profile_id(),other['id'])
                with app.db() as connection:
                    self.assertEqual(connection.execute('SELECT count(*) FROM playback_context').fetchone()[0],0)
                with app.profile_context(original_id):
                    with app.db() as connection:
                        row = connection.execute('SELECT receipt FROM playback_context WHERE message_id=?',
                                                 (message_id,)).fetchone()
                    persisted = json.loads(row['receipt'])
                    self.assertEqual(persisted['status'],'stopped')
                    self.assertEqual(persisted['confirmed_text'],'正文尾部')
                    self.assertEqual(context_for('正文尾部',persisted,message_id=message_id)['text'],'正文尾部')
                    self.assertNotIn('nonce',persisted)


if __name__=='__main__':unittest.main()
