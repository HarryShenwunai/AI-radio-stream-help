"""On-demand, source-bound preference proposals; no implicit memory learning.

A model may select an exact explicit user line, never invent or rewrite a fact.
Only a separate owner confirmation can persist that line as role memory.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
import builtins
from contextlib import contextmanager
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import TypeAlias
from uuid import UUID, uuid4

from companion_runtime.http_payload import JsonValue

Record: TypeAlias = dict[str, JsonValue]
_ACTIVE_LOCK = threading.RLock()
_ACTIVE: dict[tuple[str, str], threading.Event] = {}
_RUNTIME = str(uuid4())
_EXPLICIT = re.compile(r'^(?:我(?:更|最|比较|不|不太|很|特别|非常|一直|通常|一般|只)?(?:喜欢|讨厌|偏好|习惯)|我(?:希望|不希望|想让|不想让)你|请(?:叫我|称呼我)|(?:请)?不要(?:叫我|称呼我))')


class PreferenceLearningError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True)
class PreferenceSource:
    source_message_id: int
    text: str
    source_digest: str


@dataclass(frozen=True)
class PreferenceRequest:
    request_id: str
    role_scope: str
    sources: tuple[PreferenceSource, ...]


@dataclass(frozen=True)
class PreferenceSuggestion:
    source_message_id: int
    exact_quote: str


@dataclass(frozen=True)
class PreferenceProviderReply:
    candidates: tuple[PreferenceSuggestion, ...]
    provider_id: str


PreferenceProvider: TypeAlias = Callable[[PreferenceRequest, threading.Event], PreferenceProviderReply]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise PreferenceLearningError('invalid_identifier')
    return value


def _quote(value: object, source: PreferenceSource) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 300 or value != value.strip():
        raise PreferenceLearningError('invalid_preference_quote')
    if not _EXPLICIT.match(value) or value not in (line.strip() for line in source.text.splitlines()):
        raise PreferenceLearningError('preference_not_explicit_user_line')
    if any(ord(character) < 32 for character in value):
        raise PreferenceLearningError('invalid_preference_quote')
    return value


class PreferenceLearningStore:
    """Single-backend role ledger. Parent must authorize owner and active role.

    No background observer exists. collect() is an explicit bounded operation.
    is_scope_current must consult current host state, not a captured role value.
    Parent must cancel and drain collect() before deleting its role database.
    """

    def __init__(self, database: Path, role_scope: str, *, provider: PreferenceProvider | None = None,
                 clock: Callable[[], float] = time.time,
                 is_scope_current: Callable[[], bool] = lambda: True,
                 runtime_session: str | None = None) -> None:
        if not isinstance(role_scope, str):
            raise PreferenceLearningError('invalid_role_scope')
        try:
            if str(UUID(role_scope)) != role_scope:
                raise ValueError()
        except ValueError:
            raise PreferenceLearningError('invalid_role_scope') from None
        if Path(database).is_symlink():
            raise PreferenceLearningError('invalid_database_path', 409)
        self.database = Path(database).resolve()
        self.role_scope, self.provider, self.clock = role_scope, provider, clock
        self.is_scope_current = is_scope_current
        self.runtime_session = _identifier(runtime_session or _RUNTIME)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            schema = '''
                CREATE TABLE IF NOT EXISTS preference_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preference_requests(request_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,status TEXT NOT NULL,error TEXT,
                    candidate_ids TEXT NOT NULL,provider_id TEXT NOT NULL,
                    runtime_session TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preference_candidates(candidate_id TEXT PRIMARY KEY,
                    source_message_id INTEGER NOT NULL,source_digest TEXT NOT NULL,
                    text TEXT NOT NULL,text_digest TEXT NOT NULL,status TEXT NOT NULL,
                    memory_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    UNIQUE(source_message_id,source_digest,text_digest));
            '''
            for statement in schema.split(';'):
                if statement.strip():
                    connection.execute(statement)
            bound = connection.execute("SELECT value FROM preference_metadata WHERE key='role_scope'").fetchone()
            if bound and bound[0] != role_scope:
                raise PreferenceLearningError('role_scope_mismatch', 409)
            connection.execute("INSERT OR IGNORE INTO preference_metadata VALUES('role_scope',?)", (role_scope,))
            connection.execute("UPDATE preference_requests SET status='failed',error='interrupted_on_restart' WHERE status='generating' AND runtime_session!=?", (self.runtime_session,))

    def _now(self) -> str:
        return dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).isoformat(timespec='seconds')

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # This is an existing role database, never a request to create a role.
        # A stale cached store must not recreate a deleted profile on disk.
        if self.database.is_symlink():
            raise PreferenceLearningError('invalid_database_path', 409)
        try:
            connection = sqlite3.connect(self.database.as_uri() + '?mode=rw', uri=True, timeout=5)
        except sqlite3.OperationalError:
            raise PreferenceLearningError('role_database_unavailable', 409) from None
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _enabled(self, connection: sqlite3.Connection) -> None:
        if not self.is_scope_current():
            raise PreferenceLearningError('scope_changed', 409)
        value = connection.execute("SELECT value FROM settings WHERE key='memory_mode'").fetchone()
        if value is None or value[0] != '"relevant"':
            raise PreferenceLearningError('memory_disabled', 409)

    def _source(self, connection: sqlite3.Connection, message_id: object) -> PreferenceSource:
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id < 1:
            raise PreferenceLearningError('invalid_source_message_id')
        row = connection.execute("SELECT text FROM messages WHERE id=? AND role='user' AND kind='chat'", (message_id,)).fetchone()
        if row is None:
            raise PreferenceLearningError('source_unavailable', 409)
        text = row[0]
        if not isinstance(text, str) or not 1 <= len(text) <= 3000:
            raise PreferenceLearningError('source_size_limit')
        source = PreferenceSource(message_id, text, _digest(text))
        if connection.execute('SELECT 1 FROM forgotten WHERE digest=?', (_digest(text.strip()),)).fetchone():
            raise PreferenceLearningError('source_forgotten', 409)
        return source

    def _verify(self, connection: sqlite3.Connection, row: sqlite3.Row) -> None:
        source = self._source(connection, row['source_message_id'])
        if source.source_digest != row['source_digest']:
            raise PreferenceLearningError('source_changed', 409)
        _quote(row['text'], source)
        if connection.execute('SELECT 1 FROM forgotten WHERE digest=?', (row['text_digest'],)).fetchone():
            raise PreferenceLearningError('source_forgotten', 409)

    def _candidate(self, row: sqlite3.Row) -> Record:
        return {'candidate_id': row['candidate_id'], 'role_scope': self.role_scope,
                'source_message_id': row['source_message_id'], 'source_digest': row['source_digest'],
                'text': row['text'], 'status': row['status'], 'memory_id': row['memory_id'],
                'created_at': row['created_at'], 'updated_at': row['updated_at'],
                'basis': 'exact_explicit_user_line; owner_confirmation_required'}

    def _reconcile(self, connection: sqlite3.Connection) -> int:
        """Redact forgotten or invalidated material before returning any ledger.

        A confirmed memory can outlive cleared chat, but cannot outlive deletion
        or editing of that actual memory. Never reconstruct it from the ledger.
        """
        changed = 0
        rows = connection.execute("SELECT * FROM preference_candidates WHERE text!=''").fetchall()
        for row in rows:
            target = None
            forgotten = connection.execute('SELECT 1 FROM forgotten WHERE digest=?', (row['text_digest'],)).fetchone()
            if forgotten:
                target = 'forgotten'
                if row['memory_id'] is not None:
                    connection.execute('DELETE FROM memories WHERE id=? AND source=?', (row['memory_id'], 'confirmed-preference:' + row['candidate_id']))
            elif row['status'] == 'confirmed':
                memory = connection.execute('SELECT text,source FROM memories WHERE id=?', (row['memory_id'],)).fetchone()
                if (memory is None or memory['source'] != 'confirmed-preference:' + row['candidate_id']
                        or _digest(memory['text'].strip()) != row['text_digest']):
                    target = 'stale'
            elif row['status'] in ('pending', 'rejected'):
                try:
                    self._verify(connection, row)
                except PreferenceLearningError:
                    target = 'stale'
            if target is not None:
                connection.execute('UPDATE preference_candidates SET status=?,text=?,memory_id=NULL,updated_at=? WHERE candidate_id=?', (target, '', self._now(), row['candidate_id']))
                changed += 1
        return changed

    def reconcile(self) -> int:
        """Host may invoke after forgetting/updating memories, before exporting."""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if not self.is_scope_current():
                raise PreferenceLearningError('scope_changed', 409)
            return self._reconcile(connection)

    def _request(self, connection: sqlite3.Connection, request_id: str) -> Record:
        self._reconcile(connection)
        row = connection.execute('SELECT * FROM preference_requests WHERE request_id=?', (request_id,)).fetchone()
        if row is None:
            raise PreferenceLearningError('request_not_found', 404)
        ids = json.loads(row['candidate_ids'])
        candidates: list[JsonValue] = []
        for candidate_id in ids:
            item = connection.execute('SELECT * FROM preference_candidates WHERE candidate_id=?', (candidate_id,)).fetchone()
            if item:
                candidates.append(self._candidate(item))
        return {'request_id': request_id, 'role_scope': self.role_scope, 'status': row['status'],
                'error': row['error'], 'provider_id': row['provider_id'], 'candidates': candidates,
                'automatic_learning': False, 'external_actions': False}

    def list(self, limit: int = 50) -> list[Record]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise PreferenceLearningError('invalid_limit')
        with self._connection() as connection:
            if not self.is_scope_current():
                raise PreferenceLearningError('scope_changed', 409)
            self._reconcile(connection)
            rows = connection.execute('SELECT * FROM preference_candidates ORDER BY created_at DESC,candidate_id LIMIT ?', (limit,)).fetchall()
            return [self._candidate(row) for row in rows]

    def collect(self, request_id: str, source_message_ids: builtins.list[int]) -> Record:
        request_id = _identifier(request_id)
        if (not isinstance(source_message_ids, list) or not 1 <= len(source_message_ids) <= 12
                or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in source_message_ids)
                or len(set(source_message_ids)) != len(source_message_ids)):
            raise PreferenceLearningError('invalid_source_message_ids')
        fingerprint = _digest(json.dumps(source_message_ids))
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._enabled(connection)
            old = connection.execute('SELECT * FROM preference_requests WHERE request_id=?', (request_id,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise PreferenceLearningError('request_id_conflict', 409)
                return self._request(connection, request_id)
            sources = tuple(self._source(connection, value) for value in source_message_ids)
            if sum(len(source.text) for source in sources) > 12000:
                raise PreferenceLearningError('source_size_limit')
            if connection.execute('SELECT count(*) FROM preference_candidates').fetchone()[0] >= 200:
                raise PreferenceLearningError('candidate_limit_reached', 429)
            if connection.execute('SELECT count(*) FROM preference_requests').fetchone()[0] >= 1000:
                raise PreferenceLearningError('request_limit_reached', 429)
            status = 'generating' if self.provider is not None else 'unavailable'
            error = None if self.provider is not None else 'provider_not_configured'
            connection.execute('INSERT INTO preference_requests VALUES(?,?,?,?,?,?,?,?)',
                               (request_id, fingerprint, status, error, '[]', '', self.runtime_session, self._now()))
        if self.provider is None:
            with self._connection() as connection:
                return self._request(connection, request_id)
        cancelled = threading.Event()
        key = (str(self.database), request_id)
        with _ACTIVE_LOCK:
            _ACTIVE[key] = cancelled
        try:
            with self._connection() as connection:
                if connection.execute('SELECT status FROM preference_requests WHERE request_id=?', (request_id,)).fetchone()[0] != 'generating':
                    return self._request(connection, request_id)
            reply = self.provider(PreferenceRequest(request_id, self.role_scope, sources), cancelled)
            if (not isinstance(reply, PreferenceProviderReply) or not isinstance(reply.candidates, tuple)
                    or len(reply.candidates) > 10 or not isinstance(reply.provider_id, str)
                    or not 1 <= len(reply.provider_id) <= 120):
                raise PreferenceLearningError('invalid_provider_reply')
            selected: list[tuple[PreferenceSource, str]] = []
            by_id = {source.source_message_id: source for source in sources}
            for suggestion in reply.candidates:
                if (not isinstance(suggestion, PreferenceSuggestion)
                        or isinstance(suggestion.source_message_id, bool)
                        or suggestion.source_message_id not in by_id):
                    raise PreferenceLearningError('invalid_provider_source')
                source = by_id[suggestion.source_message_id]
                selected.append((source, _quote(suggestion.exact_quote, source)))
            with self._connection() as connection:
                connection.execute('BEGIN IMMEDIATE')
                self._enabled(connection)
                current = connection.execute('SELECT status FROM preference_requests WHERE request_id=?', (request_id,)).fetchone()[0]
                if current == 'generating' and not cancelled.is_set():
                    candidate_ids = []
                    for source, quote in selected:
                        actual = self._source(connection, source.source_message_id)
                        if actual.source_digest != source.source_digest:
                            raise PreferenceLearningError('source_changed', 409)
                        text_digest = _digest(quote)
                        if connection.execute('SELECT 1 FROM forgotten WHERE digest=?', (text_digest,)).fetchone():
                            raise PreferenceLearningError('source_forgotten', 409)
                        candidate_id = str(uuid4())
                        connection.execute('INSERT OR IGNORE INTO preference_candidates VALUES(?,?,?,?,?,?,?,?,?)',
                            (candidate_id, source.source_message_id, source.source_digest, quote, text_digest,
                             'pending', None, self._now(), self._now()))
                        actual_id = connection.execute('SELECT candidate_id FROM preference_candidates WHERE source_message_id=? AND source_digest=? AND text_digest=?',
                            (source.source_message_id, source.source_digest, text_digest)).fetchone()[0]
                        if actual_id not in candidate_ids:
                            candidate_ids.append(actual_id)
                    connection.execute("UPDATE preference_requests SET status=?,candidate_ids=?,provider_id=? WHERE request_id=?", ('proposed' if candidate_ids else 'no_candidates', json.dumps(candidate_ids), reply.provider_id, request_id))
        except Exception:
            with self._connection() as connection:
                connection.execute("UPDATE preference_requests SET status='failed',error='provider_or_source_failed' WHERE request_id=? AND status='generating'", (request_id,))
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.pop(key, None)
        with self._connection() as connection:
            return self._request(connection, request_id)

    def cancel_generating(self) -> int:
        with self._connection() as connection:
            ids = [row[0] for row in connection.execute("SELECT request_id FROM preference_requests WHERE status='generating'")]
            connection.execute("UPDATE preference_requests SET status='cancelled',error='cancelled' WHERE status='generating'")
        with _ACTIVE_LOCK:
            for request_id in ids:
                event = _ACTIVE.get((str(self.database), request_id))
                if event:
                    event.set()
        return len(ids)

    def decide(self, candidate_id: str, decision: str) -> Record:
        candidate_id = _identifier(candidate_id)
        if decision not in ('confirm', 'reject', 'delete'):
            raise PreferenceLearningError('invalid_decision')
        self.reconcile()  # Redaction survives a later rejected decision.
        pending_error: PreferenceLearningError | None = None
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if not self.is_scope_current():
                raise PreferenceLearningError('scope_changed', 409)
            self._reconcile(connection)
            row = connection.execute('SELECT * FROM preference_candidates WHERE candidate_id=?', (candidate_id,)).fetchone()
            if row is None:
                raise PreferenceLearningError('candidate_not_found', 404)
            if decision == 'delete':
                if row['memory_id'] is not None:
                    connection.execute('DELETE FROM memories WHERE id=? AND source=?', (row['memory_id'], 'confirmed-preference:' + candidate_id))
                connection.execute('INSERT OR IGNORE INTO forgotten VALUES(?,?)', (row['text_digest'], self._now()))
                connection.execute("UPDATE preference_candidates SET status='deleted',text='',memory_id=NULL,updated_at=? WHERE candidate_id=?", (self._now(), candidate_id))
            elif decision == 'reject':
                if row['status'] not in ('pending', 'rejected'):
                    raise PreferenceLearningError('candidate_already_terminal', 409)
                connection.execute("UPDATE preference_candidates SET status='rejected',updated_at=? WHERE candidate_id=?", (self._now(), candidate_id))
            else:
                self._enabled(connection)
                if row['status'] != 'pending':
                    if row['status'] != 'confirmed':
                        raise PreferenceLearningError('candidate_already_terminal', 409)
                else:
                    try:
                        self._verify(connection, row)
                    except PreferenceLearningError as error:
                        pending_error = error
                        connection.execute("UPDATE preference_candidates SET status='stale',text='',updated_at=? WHERE candidate_id=?", (self._now(), candidate_id))
                    if pending_error is None:
                        if connection.execute('SELECT count(*) FROM memories').fetchone()[0] >= 60:
                            raise PreferenceLearningError('memory_limit_reached', 409)
                        cursor = connection.execute('INSERT INTO memories(text,created,source) VALUES(?,?,?)', (row['text'], self._now(), 'confirmed-preference:' + candidate_id))
                        connection.execute("UPDATE preference_candidates SET status='confirmed',memory_id=?,updated_at=? WHERE candidate_id=?", (cursor.lastrowid, self._now(), candidate_id))
            result = self._candidate(connection.execute('SELECT * FROM preference_candidates WHERE candidate_id=?', (candidate_id,)).fetchone())
        if pending_error is not None:
            raise pending_error
        return result

    def correct(self, candidate_id: str, source_message_id: int, exact_quote: str) -> Record:
        """Remove the old confirmed line; replacement always awaits confirmation."""
        candidate_id = _identifier(candidate_id)
        self.reconcile()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._enabled(connection)
            self._reconcile(connection)
            old = connection.execute('SELECT * FROM preference_candidates WHERE candidate_id=?', (candidate_id,)).fetchone()
            if old is None:
                raise PreferenceLearningError('candidate_not_found', 404)
            if old['status'] not in ('pending', 'confirmed'):
                raise PreferenceLearningError('candidate_already_terminal', 409)
            source = self._source(connection, source_message_id)
            quote = _quote(exact_quote, source)
            if source_message_id == old['source_message_id'] or _digest(quote) == old['text_digest']:
                raise PreferenceLearningError('correction_requires_new_source')
            if connection.execute('SELECT 1 FROM forgotten WHERE digest=?', (_digest(quote),)).fetchone():
                raise PreferenceLearningError('source_forgotten', 409)
            existing = connection.execute('SELECT status FROM preference_candidates WHERE source_message_id=? AND source_digest=? AND text_digest=?', (source.source_message_id, source.source_digest, _digest(quote))).fetchone()
            if existing is not None and existing['status'] != 'pending':
                raise PreferenceLearningError('replacement_already_terminal', 409)
            if old['memory_id'] is not None:
                connection.execute('DELETE FROM memories WHERE id=? AND source=?', (old['memory_id'], 'confirmed-preference:' + candidate_id))
            connection.execute('INSERT OR IGNORE INTO forgotten VALUES(?,?)', (old['text_digest'], self._now()))
            connection.execute("UPDATE preference_candidates SET status='corrected',text='',memory_id=NULL,updated_at=? WHERE candidate_id=?", (self._now(), candidate_id))
            replacement = str(uuid4())
            connection.execute('INSERT OR IGNORE INTO preference_candidates VALUES(?,?,?,?,?,?,?,?,?)',
                (replacement, source.source_message_id, source.source_digest, quote, _digest(quote), 'pending', None, self._now(), self._now()))
            result = self._candidate(connection.execute('SELECT * FROM preference_candidates WHERE source_message_id=? AND source_digest=? AND text_digest=?', (source.source_message_id, source.source_digest, _digest(quote))).fetchone())
            result['previous_source_message_id'] = old['source_message_id']
            return result
