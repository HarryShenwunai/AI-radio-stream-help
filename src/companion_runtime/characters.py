"""Local character catalog with a separate SQLite file for each identity.

The application owns conversation/renderer locks. This module never copies a
character's conversations or personality to a newly created identity. Legacy
migration reads the old database through SQLite's read-only backup API and
leaves the source in place, so the old application must not keep writing it.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
from uuid import UUID, uuid4


class CharacterError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _uuid(value: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise CharacterError('角色或资产标识格式不正确。')
    try:
        normalized = str(UUID(value))
    except ValueError as error:
        raise CharacterError('角色或资产标识格式不正确。') from error
    if normalized != value:
        raise CharacterError('角色或资产标识格式不正确。')
    return value


def _name(value: str) -> str:
    if not isinstance(value, str):
        raise CharacterError('请输入角色名称。')
    value = value.strip()
    if not value or len(value) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise CharacterError('角色名称需为1–80字，不能包含控制字符。')
    try:
        value.encode('utf-8', 'strict')
    except UnicodeEncodeError as error:
        raise CharacterError('角色名称包含无效字符。') from error
    return value


def validate_name(value: str) -> str:
    """Validate before the caller changes profile settings or catalog metadata."""
    return _name(value)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


class CharacterStore:
    """Persist identity metadata; private settings/history stay in profile DBs.

    One store instance is safe across threads. SQLite write transactions also
    serialize separate instances using the same root. Calling code must stop
    the active generation before switching or changing its appearance.
    """

    def __init__(self, root: Path, max_profiles: int = 50) -> None:
        if isinstance(max_profiles, bool) or not isinstance(max_profiles, int) or max_profiles < 1:
            raise ValueError('max_profiles must be a positive integer')
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.profiles = self.root / 'profiles'
        self.trash = self.root / '.character-trash'
        self.catalog = self.root / 'characters.sqlite3'
        self._lock = threading.RLock()
        self._bootstrapped = False
        self._limit = max_profiles
        for directory in (self.profiles, self.trash):
            if directory.is_symlink():
                raise CharacterError('角色目录不能使用符号链接。', 409)
            directory.mkdir(exist_ok=True, mode=0o700)
        if self.catalog.is_symlink():
            raise CharacterError('角色目录数据库不能使用符号链接。', 409)
        with self._connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL,
                    avatar_revision TEXT, archived INTEGER NOT NULL DEFAULT 0
                    CHECK(archived IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deletions (
                    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, created TEXT NOT NULL
                );
            ''')
        os.chmod(self.catalog, 0o600)

    @contextmanager
    def _connection(self):
        if self.catalog.is_symlink():
            raise CharacterError('角色目录数据库不能使用符号链接。', 409)
        conn = sqlite3.connect(self.catalog, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _row(row) -> dict:
        value = dict(row)
        value['archived'] = bool(value['archived'])
        return value

    @staticmethod
    def _find(conn, character_id: str):
        row = conn.execute('SELECT * FROM characters WHERE id=?', (_uuid(character_id),)).fetchone()
        if row is None:
            raise CharacterError('这个角色已经不存在。', 404)
        return row

    @staticmethod
    def _active_id(conn) -> str:
        row = conn.execute("SELECT value FROM metadata WHERE key='active_character_id'").fetchone()
        if row is None:
            raise CharacterError('角色目录状态不完整，请保留数据并恢复备份。', 503)
        return _uuid(row['value'])

    def _directory(self, character_id: str) -> Path:
        if self.profiles.is_symlink():
            raise CharacterError('角色目录不可用。', 409)
        directory = self.profiles / _uuid(character_id)
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise CharacterError('角色目录不可用。', 409)
        return directory

    def _database(self, character_id: str) -> Path:
        directory = self._directory(character_id)
        database = directory / 'companion.db'
        if not directory.is_dir() or database.is_symlink() or not database.is_file():
            raise CharacterError('角色数据库不可用，请保留数据并检查备份。', 409)
        return database

    def _copy_legacy(self, source: Path, destination: Path) -> None:
        if source.is_symlink() or not source.is_file():
            raise CharacterError('旧数据库不可用，原文件已保留。', 503)
        temporary = destination.with_suffix('.migration')
        started = time.monotonic()
        def progress(_status: int, _remaining: int, _total: int) -> None:
            if time.monotonic() - started > 10:
                raise CharacterError('迁移等待超时，旧数据库未更改。', 503)
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as old:
                if old.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise CharacterError('旧数据库检查失败，原文件已保留。', 503)
                with closing(sqlite3.connect(temporary)) as new:
                    old.backup(new, pages=128, progress=progress, sleep=0.01)
                    new.commit()
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        except sqlite3.Error as error:
            raise CharacterError('迁移失败，旧数据库未更改。', 503) from error
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _legacy_name(database: Path) -> str:
        # Read user-visible identity only; do not import provider credentials.
        try:
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as conn:
                row = conn.execute("SELECT value FROM settings WHERE key='name'").fetchone()
            return _name(json.loads(row[0])) if row else '陪伴角色'
        except (sqlite3.Error, ValueError, TypeError):
            return '陪伴角色'

    def bootstrap(self) -> dict:
        """Create exactly one initial identity, migrating the legacy DB once."""
        with self._lock:
            directory = None
            committed = False
            try:
                with self._connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    count = conn.execute('SELECT count(*) FROM characters').fetchone()[0]
                    if count:
                        row = self._find(conn, self._active_id(conn))
                        if row['archived']:
                            raise CharacterError('当前角色已归档，请恢复目录备份。', 503)
                        self._database(row['id'])
                        result = self._row(row)
                    else:
                        character_id = str(uuid4())
                        directory = self._directory(character_id)
                        directory.mkdir(mode=0o700)
                        database = directory / 'companion.db'
                        legacy = self.root / 'companion.db'
                        name = '陪伴角色'
                        if legacy.exists() or legacy.is_symlink():
                            self._copy_legacy(legacy, database)
                            name = self._legacy_name(database)
                        else:
                            database.touch(mode=0o600)
                        conn.execute('INSERT INTO characters(id,name,created) VALUES(?,?,?)',
                                     (character_id, name, _now()))
                        conn.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                                     ('active_character_id', character_id))
                        result = self._row(self._find(conn, character_id))
                committed = True
                self._bootstrapped = True
            finally:
                if directory is not None and not committed:
                    shutil.rmtree(directory, ignore_errors=True)
            self.cleanup_pending_deletions()
            return result

    def _ready(self) -> None:
        if not self._bootstrapped:
            self.bootstrap()

    def active(self) -> dict:
        with self._lock:
            self._ready()
            with self._connection() as conn:
                row = self._find(conn, self._active_id(conn))
                if row['archived']:
                    raise CharacterError('当前角色不可用。', 503)
                return self._row(row)

    def get(self, character_id: str) -> dict:
        with self._lock:
            self._ready()
            with self._connection() as conn:
                return self._row(self._find(conn, character_id))

    def list(self, include_archived: bool = True) -> list[dict]:
        if not isinstance(include_archived, bool):
            raise CharacterError('角色列表参数不正确。')
        with self._lock:
            self._ready()
            with self._connection() as conn:
                query = 'SELECT * FROM characters'
                if not include_archived:
                    query += ' WHERE archived=0'
                return [self._row(row) for row in conn.execute(query + ' ORDER BY created,id')]

    def create(self, name: str) -> dict:
        name = _name(name)
        with self._lock:
            self._ready()
            self.cleanup_pending_deletions()
            directory = None
            committed = False
            try:
                with self._connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    count = conn.execute('SELECT count(*) FROM characters').fetchone()[0]
                    count += conn.execute('SELECT count(*) FROM deletions').fetchone()[0]
                    if count >= self._limit:
                        raise CharacterError(f'最多保留{self._limit}个角色，请先删除不需要的角色。', 409)
                    character_id = str(uuid4())
                    directory = self._directory(character_id)
                    directory.mkdir(mode=0o700)
                    (directory / 'companion.db').touch(mode=0o600)
                    conn.execute('INSERT INTO characters(id,name,created) VALUES(?,?,?)',
                                 (character_id, name, _now()))
                    result = self._row(self._find(conn, character_id))
                committed = True
                return result
            finally:
                if directory is not None and not committed:
                    shutil.rmtree(directory, ignore_errors=True)

    def select(self, character_id: str) -> dict:
        with self._lock:
            self._ready()
            with self._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                row = self._find(conn, character_id)
                if row['archived']:
                    raise CharacterError('请先恢复已归档的角色。', 409)
                self._database(character_id)
                conn.execute('UPDATE metadata SET value=? WHERE key=?',
                             (character_id, 'active_character_id'))
                return self._row(row)

    def rename(self, character_id: str, name: str) -> dict:
        name = _name(name)
        with self._lock:
            self._ready()
            with self._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self._find(conn, character_id)
                conn.execute('UPDATE characters SET name=? WHERE id=?', (name, character_id))
                return self._row(self._find(conn, character_id))

    def set_appearance(self, character_id: str, asset_id: str | None) -> dict:
        if asset_id is not None:
            _uuid(asset_id)
        with self._lock:
            self._ready()
            with self._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                row = self._find(conn, character_id)
                if row['archived']:
                    raise CharacterError('已归档角色不能更换外观。', 409)
                conn.execute('UPDATE characters SET avatar_revision=? WHERE id=?',
                             (asset_id, character_id))
                return self._row(self._find(conn, character_id))

    def archive(self, character_id: str) -> dict:
        with self._lock:
            self._ready()
            with self._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                row = self._find(conn, character_id)
                if row['archived']:
                    return self._row(row)
                if conn.execute('SELECT count(*) FROM characters WHERE archived=0').fetchone()[0] <= 1:
                    raise CharacterError('请至少保留一个可用角色。', 409)
                if self._active_id(conn) == character_id:
                    raise CharacterError('请先切换到另一个角色，再归档此角色。', 409)
                conn.execute('UPDATE characters SET archived=1 WHERE id=?', (character_id,))
                return self._row(self._find(conn, character_id))

    def restore(self, character_id: str) -> dict:
        with self._lock:
            self._ready()
            with self._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self._find(conn, character_id)
                self._database(character_id)
                conn.execute('UPDATE characters SET archived=0 WHERE id=?', (character_id,))
                return self._row(self._find(conn, character_id))

    def delete(self, character_id: str) -> dict:
        """Remove an inactive identity; disclose any pending disk cleanup."""
        with self._lock:
            self._ready()
            deletion_id = str(uuid4())
            original = self._directory(character_id)
            retired = self.trash / deletion_id
            moved = False
            committed = False
            try:
                with self._connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    row = self._find(conn, character_id)
                    if not row['archived'] and conn.execute('SELECT count(*) FROM characters WHERE archived=0').fetchone()[0] <= 1:
                        raise CharacterError('请至少保留一个可用角色。', 409)
                    if self._active_id(conn) == character_id:
                        raise CharacterError('请先切换到另一个角色，再删除此角色。', 409)
                    if original.exists():
                        original.rename(retired)
                        moved = True
                    conn.execute('DELETE FROM characters WHERE id=?', (character_id,))
                    conn.execute('INSERT INTO deletions VALUES(?,?,?)', (deletion_id, character_id, _now()))
                committed = True
            finally:
                if moved and not committed:
                    retired.rename(original)
            cleaned = self._cleanup_one(deletion_id)
            return {'id': character_id, 'deleted': True, 'cleanup_pending': not cleaned}

    def _cleanup_one(self, deletion_id: str) -> bool:
        path = self.trash / _uuid(deletion_id)
        try:
            if self.trash.is_symlink() or path.is_symlink():
                raise OSError('trash directory must not be a symlink')
            if path.exists():
                shutil.rmtree(path)
            with self._connection() as conn:
                conn.execute('DELETE FROM deletions WHERE id=?', (deletion_id,))
            return True
        except (OSError, sqlite3.Error):
            return False

    def cleanup_pending_deletions(self) -> dict:
        with self._lock:
            with self._connection() as conn:
                ids = [row['id'] for row in conn.execute('SELECT id FROM deletions')]
            cleaned = sum(self._cleanup_one(value) for value in ids)
            return {'cleaned': cleaned, 'pending': len(ids) - cleaned}

    def db_path(self, character_id: str) -> Path:
        with self._lock:
            self.get(character_id)
            return self._database(character_id)
