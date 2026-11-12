"""Real temporary SQLite/filesystem checks for character identity isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from companion_runtime.characters import CharacterError, CharacterStore, validate_name


class CharacterStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='characters-test-')
        self.root = Path(self.tmp.name) / 'data'
        self.store = CharacterStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def legacy(self, name='自定义旧角色'):
        old = self.root / 'companion.db'
        with closing(sqlite3.connect(old)) as conn, conn:
            conn.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);'
                               'CREATE TABLE messages(text TEXT);'
                               'CREATE TABLE forgotten(digest TEXT PRIMARY KEY);')
            conn.execute('INSERT INTO settings VALUES(?,?)', ('name', json.dumps(name)))
            conn.execute('INSERT INTO messages VALUES(?)', ('private canary from old identity',))
            conn.execute('INSERT INTO forgotten VALUES(?)', ('forget-canary',))
        return old

    def test_bootstrap_is_idempotent_and_persists_the_active_identity(self):
        first = self.store.bootstrap()
        self.assertEqual(first['name'], '陪伴角色')
        self.assertEqual(str(UUID(first['id'])), first['id'])
        self.assertFalse(first['archived'])
        self.assertIsNone(first['avatar_revision'])
        second = CharacterStore(self.root).bootstrap()
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.store.db_path(first['id']), self.root / 'profiles' / first['id'] / 'companion.db')

    def test_migration_copies_committed_sqlite_data_but_never_rewrites_legacy(self):
        old = self.legacy()
        original = old.read_bytes()
        key = self.root / 'api-key'
        key.write_text('synthetic-local-secret')
        profile = self.store.bootstrap()
        self.assertEqual(profile['name'], '自定义旧角色')
        with closing(sqlite3.connect(self.store.db_path(profile['id']))) as conn, conn:
            self.assertEqual(conn.execute('SELECT text FROM messages').fetchone()[0], 'private canary from old identity')
            self.assertEqual(conn.execute('SELECT digest FROM forgotten').fetchone()[0], 'forget-canary')
            conn.execute('INSERT INTO messages VALUES(?)', ('only in migrated identity',))
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(key.read_text(), 'synthetic-local-secret')
        self.assertFalse((self.root / 'profiles' / profile['id'] / 'api-key').exists())

    def test_migration_does_not_recopy_after_old_database_changes(self):
        old = self.legacy()
        profile = self.store.bootstrap()
        with closing(sqlite3.connect(old)) as conn, conn:
            conn.execute('INSERT INTO messages VALUES(?)', ('later old application event',))
        self.assertEqual(CharacterStore(self.root).bootstrap()['id'], profile['id'])
        with closing(sqlite3.connect(self.store.db_path(profile['id']))) as conn, conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM messages').fetchone()[0], 1)

    def test_backup_reads_committed_wal_without_requiring_checkpoint(self):
        old = self.legacy()
        conn = sqlite3.connect(old)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('INSERT INTO messages VALUES(?)', ('committed WAL canary',))
            conn.commit()
            profile = self.store.bootstrap()
            with closing(sqlite3.connect(self.store.db_path(profile['id']))) as result, result:
                self.assertEqual(result.execute('SELECT count(*) FROM messages').fetchone()[0], 2)
        finally:
            conn.close()

    def test_new_character_has_its_own_empty_database_not_a_private_copy(self):
        self.legacy()
        original = self.store.bootstrap()
        new = self.store.create('另一个角色')
        self.assertNotEqual(original['id'], new['id'])
        self.assertEqual(self.store.active()['id'], original['id'])
        with closing(sqlite3.connect(self.store.db_path(new['id']))) as conn, conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0], 0)
        with closing(sqlite3.connect(self.store.db_path(original['id']))) as conn, conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM messages').fetchone()[0], 1)

    def test_identical_names_are_allowed_but_ids_and_database_files_are_distinct(self):
        self.store.bootstrap()
        a, b = self.store.create('重复名字'), self.store.create('重复名字')
        self.assertNotEqual(a['id'], b['id'])
        self.assertNotEqual(self.store.db_path(a['id']), self.store.db_path(b['id']))

    def test_select_is_explicit_and_survives_restart(self):
        initial = self.store.bootstrap()
        other = self.store.create('第二位')
        self.assertEqual(self.store.active()['id'], initial['id'])
        self.store.select(other['id'])
        self.assertEqual(CharacterStore(self.root).active()['id'], other['id'])

    def test_appearance_and_name_changes_do_not_change_identity_or_database(self):
        old = self.legacy()
        profile = self.store.bootstrap()
        path = self.store.db_path(profile['id'])
        before = path.read_bytes()
        appearance = str(uuid4())
        self.assertEqual(self.store.set_appearance(profile['id'], appearance)['avatar_revision'], appearance)
        self.assertEqual(self.store.rename(profile['id'], ' 新名字 ')['name'], '新名字')
        self.assertEqual(self.store.active()['id'], profile['id'])
        self.assertEqual(path.read_bytes(), before)
        self.store.set_appearance(profile['id'], None)
        self.assertIsNone(self.store.active()['avatar_revision'])
        self.assertTrue(old.exists())

    def test_archive_restore_preserve_data_and_do_not_switch_implicitly(self):
        active = self.store.bootstrap()
        other = self.store.create('收起的角色')
        database = self.store.db_path(other['id'])
        database.write_bytes(b'private relationship bytes for archive preservation')
        self.assertTrue(self.store.archive(other['id'])['archived'])
        self.assertEqual(len(self.store.list(False)), 1)
        self.assertEqual(len(self.store.list()), 2)
        for method in [lambda: self.store.select(other['id']),
                       lambda: self.store.set_appearance(other['id'], str(uuid4()))]:
            with self.assertRaises(CharacterError) as raised:
                method()
            self.assertEqual(raised.exception.status, 409)
        self.assertFalse(self.store.restore(other['id'])['archived'])
        self.assertEqual(database.read_bytes(), b'private relationship bytes for archive preservation')
        self.assertEqual(self.store.active()['id'], active['id'])

    def test_active_or_last_available_identity_cannot_be_archived_or_deleted(self):
        active = self.store.bootstrap()
        for method in [self.store.archive, self.store.delete]:
            with self.assertRaises(CharacterError) as raised:
                method(active['id'])
            self.assertEqual(raised.exception.status, 409)
        other = self.store.create('另一位')
        for method in [self.store.archive, self.store.delete]:
            with self.assertRaises(CharacterError):
                method(active['id'])
        self.store.archive(other['id'])
        self.store.delete(other['id'])
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.store.active()['id'], active['id'])

    def test_delete_removes_only_inactive_character_data(self):
        active = self.store.bootstrap()
        other = self.store.create('可删除')
        path = self.store.db_path(other['id'])
        path.write_bytes(b'only the removed identity')
        result = self.store.delete(other['id'])
        self.assertEqual(result, {'id': other['id'], 'deleted': True, 'cleanup_pending': False})
        self.assertFalse(path.parent.exists())
        self.assertTrue(self.store.db_path(active['id']).exists())
        with self.assertRaises(CharacterError) as raised:
            self.store.get(other['id'])
        self.assertEqual(raised.exception.status, 404)

    def test_failed_disk_cleanup_is_disclosed_and_can_be_retried(self):
        active = self.store.bootstrap()
        other = self.store.create('稍后清理')
        with patch('companion_runtime.characters.shutil.rmtree', side_effect=PermissionError('test fault')):
            result = self.store.delete(other['id'])
        self.assertTrue(result['cleanup_pending'])
        self.assertEqual(self.store.active()['id'], active['id'])
        self.assertEqual(len(list(self.store.trash.iterdir())), 1)
        self.assertEqual(self.store.cleanup_pending_deletions(), {'cleaned': 1, 'pending': 0})
        self.assertEqual(list(self.store.trash.iterdir()), [])

    def test_catalog_transaction_failure_restores_retired_directory(self):
        self.store.bootstrap()
        other = self.store.create('不能丢失')
        path = self.store.db_path(other['id'])
        path.write_bytes(b'rollback canary')
        connection = self.store._connection
        @contextmanager
        def fail_after_work():
            with connection() as conn:
                yield conn
                raise sqlite3.OperationalError('injected commit failure')
        with patch.object(self.store, '_connection', fail_after_work):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.delete(other['id'])
        self.assertEqual(self.store.get(other['id'])['name'], '不能丢失')
        self.assertEqual(path.read_bytes(), b'rollback canary')
        self.assertEqual(list(self.store.trash.iterdir()), [])

    def test_corrupt_legacy_does_not_create_an_active_or_half_migrated_profile(self):
        old = self.root / 'companion.db'
        old.write_bytes(b'not sqlite; keep this source unchanged')
        before = old.read_bytes()
        with self.assertRaises(CharacterError) as raised:
            self.store.bootstrap()
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(list(self.store.profiles.iterdir()), [])
        with closing(sqlite3.connect(self.store.catalog)) as conn, conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM characters').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM metadata').fetchone()[0], 0)
        old.unlink()
        self.assertEqual(self.store.bootstrap()['name'], '陪伴角色')

    def test_migration_failure_after_copy_leaves_source_and_catalog_unchanged(self):
        old = self.legacy()
        before = hashlib.sha256(old.read_bytes()).hexdigest()
        find = self.store._find
        with patch.object(self.store, '_find', side_effect=CharacterError('injected registry fault')):
            with self.assertRaises(CharacterError):
                self.store.bootstrap()
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(), before)
        self.assertEqual(list(self.store.profiles.iterdir()), [])
        with closing(sqlite3.connect(self.store.catalog)) as conn, conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM characters').fetchone()[0], 0)
        self.assertEqual(self.store.bootstrap()['name'], '自定义旧角色')

    def test_quota_and_invalid_names_fail_without_orphan_directories(self):
        store = CharacterStore(self.root, max_profiles=2)
        store.bootstrap()
        for name in ['', ' ', 'a'*81, 'x\x00y', 'x\ny', '\ud800', None]:
            with self.subTest(name=repr(name)), self.assertRaises(CharacterError):
                store.create(name)
        second = store.create('第二位')
        with self.assertRaises(CharacterError) as raised:
            store.create('第三位')
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(len(list(store.profiles.iterdir())), 2)
        store.delete(second['id'])
        self.assertEqual(store.create('新一位')['name'], '新一位')

    def test_concurrent_bootstrap_and_admission_across_store_instances(self):
        stores = [CharacterStore(self.root, max_profiles=8) for _ in range(4)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            initial = list(pool.map(lambda store: store.bootstrap()['id'], stores))
        self.assertEqual(len(set(initial)), 1)
        def create(i):
            try:
                return stores[i % 4].create(f'角色{i}')['id']
            except CharacterError as error:
                self.assertEqual(error.status, 409)
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(16)))
        self.assertEqual(sum(value is not None for value in results), 7)
        self.assertEqual(len(self.store.list()), 8)
        self.assertEqual(len(list(self.store.profiles.iterdir())), 8)
        self.assertEqual(self.store.active()['id'], initial[0])

    def test_invalid_identifiers_never_resolve_outside_profile_root(self):
        current = self.store.bootstrap()
        for value in ['../elsewhere', '/tmp/file', '', 'file://x', current['id'].upper(), '{'+current['id']+'}', None]:
            with self.subTest(value=value), self.assertRaises(CharacterError):
                self.store.db_path(value)
        with self.assertRaises(CharacterError):
            self.store.set_appearance(current['id'], '../outside')
        self.assertIsNone(self.store.active()['avatar_revision'])

    def test_symlinked_profile_or_database_is_rejected(self):
        current = self.store.bootstrap()
        database = self.store.db_path(current['id'])
        target = self.root / 'outside-private'
        target.write_text('outside canary')
        database.unlink()
        try:
            database.symlink_to(target)
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows account lacks the privilege to create test symlinks')
            raise
        with self.assertRaises(CharacterError):
            self.store.db_path(current['id'])
        with self.assertRaises(CharacterError):
            self.store.select(current['id'])
        self.assertEqual(target.read_text(), 'outside canary')

    def test_missing_profile_database_is_not_silently_recreated(self):
        current = self.store.bootstrap()
        self.store.db_path(current['id']).unlink()
        with self.assertRaises(CharacterError):
            CharacterStore(self.root).bootstrap()
        self.assertFalse((self.root/'profiles'/current['id']/'companion.db').exists())

    def test_catalog_contains_no_conversations_personality_or_secret(self):
        self.legacy()
        self.store.bootstrap()
        with closing(sqlite3.connect(self.store.catalog)) as conn, conn:
            dump = '\n'.join(conn.iterdump())
        self.assertNotIn('private canary', dump)
        self.assertNotIn('forget-canary', dump)
        self.assertNotIn('api-key', dump)
        self.assertNotIn('personality', dump)

    def test_registry_and_new_database_permissions_are_private_on_posix(self):
        current = self.store.bootstrap()
        if os.name == 'posix':
            self.assertEqual(self.store.catalog.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.store.db_path(current['id']).stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.store.db_path(current['id']).parent.stat().st_mode & 0o777, 0o700)

    def test_public_name_validation_matches_catalog_rules(self):
        self.assertEqual(validate_name('  新角色  '), '新角色')
        for value in ['', 'a'*81, 'x\x00y', '\ud800']:
            with self.assertRaises(CharacterError):
                validate_name(value)

    def test_invalid_limit_and_list_argument_are_rejected(self):
        for limit in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                CharacterStore(self.root, max_profiles=limit)
        with self.assertRaises(CharacterError):
            self.store.list(include_archived=1)


if __name__ == '__main__':
    unittest.main()
