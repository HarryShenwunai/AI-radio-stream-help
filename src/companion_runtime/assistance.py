"""Scoped, durable proposals. No external action executor or arbitrary code runner.

The HTTP owner supplies an already-authorized profile database and, optionally,
a real advice provider. Advice never reads chat history or saved memories here.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
import csv
from dataclasses import dataclass
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Literal, TypeAlias, cast
from uuid import UUID, uuid4

from .http_payload import JsonValue

JsonObject: TypeAlias = dict[str, JsonValue]
Kind: TypeAlias = Literal['schedule', 'outfit', 'dinner', 'brainstorm', 'data_analysis', 'game']
Decision: TypeAlias = Literal['confirm', 'reject', 'cancel']
KINDS = frozenset({'schedule', 'outfit', 'dinner', 'brainstorm', 'data_analysis', 'game'})
ADVICE_KINDS = KINDS - {'schedule', 'data_analysis'}
MAX_CSV_BYTES = 262144
MAX_CSV_ROWS = 5000
MAX_CSV_COLUMNS = 32
# Pending decisions are bounded; accepting/declining one must free capacity.
MAX_PROPOSALS = 200
_RUNTIME = str(uuid4())
_ACTIVE_LOCK = threading.RLock()
_ACTIVE: dict[tuple[str, str], threading.Event] = {}


class AssistanceError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class AdviceRequest:
    request_id: str
    role_scope: str
    kind: Kind
    inputs: JsonObject
    source_evidence: tuple[JsonObject, ...] = ()


@dataclass(frozen=True)
class ProviderReply:
    summary: str
    provider_id: str


@dataclass(frozen=True)
class TrustedObservation:
    """Server-only conversion of a live perception manager record.

    This object is not an HTTP credential. Host must first resolve the opaque
    observation id through the owner/role/appearance/epoch permission manager.
    """
    observation_id: str
    role_scope: str
    session_id: str
    request_id: str
    source_sha256: str
    captured_at_ms: int
    description: str
    kind: str
    processing: str


AdviceProvider: TypeAlias = Callable[[AdviceRequest, threading.Event], ProviderReply]


def _text(value: object, limit: int, *, empty: bool = False, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise AssistanceError('invalid_text')
    value = value.strip()
    if (not empty and not value) or len(value) > limit:
        raise AssistanceError('invalid_text')
    if any(ord(char) < 32 and not (multiline and char in '\n\t\r') for char in value) or '\x7f' in value:
        raise AssistanceError('invalid_text')
    try:value.encode('utf-8', 'strict')
    except UnicodeEncodeError as error:raise AssistanceError('invalid_text') from error
    return value


def _identifier(value: object) -> str:
    result = _text(value, 128)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', result):
        raise AssistanceError('invalid_identifier')
    return result


def _role(value: object) -> str:
    result = _text(value, 36)
    try:normalized = str(UUID(result))
    except ValueError as error:raise AssistanceError('invalid_role_scope') from error
    if result != normalized:
        raise AssistanceError('invalid_role_scope')
    return result


def _dump(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True)


def _object(value: str) -> JsonObject:
    loaded: object = json.loads(value)
    if not isinstance(loaded, dict):
        raise AssistanceError('stored_proposal_invalid', 409)
    return cast(JsonObject, loaded)


def _now(stamp: float) -> str:
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat(timespec='seconds')


def migrate_connection(connection: sqlite3.Connection) -> None:
    """Additive migration: preserve old rows and never guess message provenance."""
    schema = '''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,
            due REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'reminder');
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,role TEXT NOT NULL,
            text TEXT NOT NULL,created TEXT NOT NULL,request_id TEXT,kind TEXT DEFAULT 'chat');
        CREATE TABLE IF NOT EXISTS assistance_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assistance_proposals(
            action_id TEXT PRIMARY KEY,request_id TEXT NOT NULL UNIQUE,role_scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,kind TEXT NOT NULL,summary TEXT NOT NULL,inputs TEXT NOT NULL,
            permission_scope TEXT NOT NULL,status TEXT NOT NULL,source_evidence TEXT NOT NULL,
            result TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            runtime_session TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assistance_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT NOT NULL REFERENCES assistance_proposals(action_id) ON DELETE CASCADE,
            event TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS assistance_status ON assistance_proposals(status,created_at);
        CREATE TABLE IF NOT EXISTS assistance_controls(id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,target TEXT NOT NULL,created_at TEXT NOT NULL);
    '''
    # executescript implicitly commits an existing caller transaction. These
    # fixed schema statements must instead participate in that transaction.
    for statement in schema.split(';'):
        if statement.strip():connection.execute(statement)
    task_columns = {row[1] for row in connection.execute('PRAGMA table_info(tasks)')}
    if 'assistance_action_id' not in task_columns:
        connection.execute('ALTER TABLE tasks ADD COLUMN assistance_action_id TEXT')
    message_columns = {row[1] for row in connection.execute('PRAGMA table_info(messages)')}
    if 'task_id' not in message_columns:
        connection.execute('ALTER TABLE messages ADD COLUMN task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL')
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS assistance_task_once ON tasks(assistance_action_id) WHERE assistance_action_id IS NOT NULL')


def analyze_csv(text: str, delimiter: str = ',') -> JsonObject:
    """Bounded CSV parsing and Decimal statistics; cells are never evaluated."""
    if not isinstance(text, str) or not isinstance(delimiter, str) or delimiter not in {',', ';', '\t'}:
        raise AssistanceError('invalid_csv')
    try:encoded = text.encode('utf-8', 'strict')
    except UnicodeEncodeError as error:raise AssistanceError('invalid_csv') from error
    if not encoded or len(encoded) > MAX_CSV_BYTES or '\x00' in text:
        raise AssistanceError('csv_size_limit')
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff'), newline=''), delimiter=delimiter, strict=True)
    try:
        headers = next(reader)
        if (not headers or len(headers) > MAX_CSV_COLUMNS or any(not cell.strip() or len(cell) > 120 for cell in headers)
                or len(set(headers)) != len(headers)):
            raise AssistanceError('invalid_csv_header')
        values: list[list[str]] = [[] for _ in headers]
        row_count = 0
        for row in reader:
            if not row:continue
            row_count += 1
            if row_count > MAX_CSV_ROWS or len(row) != len(headers) or any(len(cell) > 2048 for cell in row):
                raise AssistanceError('csv_shape_limit')
            for index, cell in enumerate(row):values[index].append(cell.strip())
    except (csv.Error, StopIteration) as error:raise AssistanceError('invalid_csv') from error
    if not row_count:
        raise AssistanceError('csv_no_data')
    columns: list[JsonValue] = []
    with localcontext() as context:
        context.prec = 34
        for name, cells in zip(headers, values):
            numeric: list[Decimal] = []
            invalid = missing = formulas = 0
            for cell in cells:
                if not cell:
                    missing += 1;continue
                if cell.startswith(('=', '+', '@')):formulas += 1
                if len(cell) > 64 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?', cell):
                    invalid += 1;continue
                try:number = Decimal(cell)
                except InvalidOperation:
                    invalid += 1;continue
                if not number.is_finite() or number and abs(number.adjusted()) > 308:
                    invalid += 1;continue
                numeric.append(number)
            column: JsonObject = {'name':name, 'missing':missing, 'numeric_count':len(numeric),
                                  'non_numeric_count':invalid, 'formula_like_cells':formulas,
                                  'type':'numeric' if numeric and not invalid else 'mixed' if numeric else 'text'}
            if numeric:
                total = sum(numeric, Decimal(0))
                column.update({'min':str(min(numeric)), 'max':str(max(numeric)), 'sum':str(total), 'mean':str(total / len(numeric))})
            columns.append(column)
    return {'row_count':row_count, 'column_count':len(headers), 'columns':columns,
            'csv_sha256':hashlib.sha256(encoded).hexdigest(), 'bytes':len(encoded),
            'method':'csv.reader + Decimal, 34 significant digits; numeric aggregates ignore missing/non-numeric cells',
            'formula_execution':False, 'external_actions':False}


class AssistanceStore:
    """A single-owner backend's per-role durable action ledger.

    Separate instances in one backend share cancellation events. A new backend
    session fails old in-flight generation rather than silently re-executing it.
    Host must enforce active-role ownership before invoking any method.
    """
    def __init__(self, database: Path, role_scope: str, *, provider: AdviceProvider | None = None,
                 provider_kinds: Iterable[str] = (), clock: Callable[[], float] = time.time,
                 runtime_session: str | None = None) -> None:
        self.database = Path(database).resolve()
        if Path(database).is_symlink():raise AssistanceError('invalid_database_path', 409)
        self.role_scope = _role(role_scope)
        self.provider = provider
        self.provider_kinds = frozenset(provider_kinds)
        if self.provider_kinds - ADVICE_KINDS:raise AssistanceError('invalid_provider_capability')
        self.clock = clock
        self.runtime_session = _identifier(runtime_session or _RUNTIME)
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            migrate_connection(connection)
            bound = connection.execute("SELECT value FROM assistance_metadata WHERE key='role_scope'").fetchone()
            if bound and bound[0] != self.role_scope:raise AssistanceError('role_scope_mismatch', 409)
            connection.execute("INSERT OR IGNORE INTO assistance_metadata VALUES('role_scope',?)", (self.role_scope,))
            interrupted = connection.execute("SELECT action_id FROM assistance_proposals WHERE status='generating' AND runtime_session!=?", (self.runtime_session,)).fetchall()
            for row in interrupted:
                connection.execute("UPDATE assistance_proposals SET status='failed',error='interrupted_on_restart',updated_at=? WHERE action_id=?", (self._now(), row[0]))
                self._event(connection, row[0], 'interrupted_on_restart')
        try:os.chmod(self.database, 0o600)
        except OSError:pass

    def _now(self) -> str:
        return _now(self.clock())

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback();raise
        finally:connection.close()

    def _event(self, connection: sqlite3.Connection, action_id: str, event: str) -> None:
        connection.execute('INSERT INTO assistance_events(action_id,event,created_at) VALUES(?,?,?)', (action_id, event, self._now()))

    def _record(self, row: sqlite3.Row) -> JsonObject:
        return {'request_id':row['request_id'], 'action_id':row['action_id'], 'role_scope':row['role_scope'],
                'kind':row['kind'], 'summary':row['summary'], 'inputs':_object(row['inputs']),
                'permission_scope':row['permission_scope'], 'status':row['status'],
                'source_evidence':cast(JsonValue, json.loads(row['source_evidence'])), 'result':_object(row['result']),
                'error':row['error'], 'created_at':row['created_at'], 'updated_at':row['updated_at']}

    def _read(self, connection: sqlite3.Connection, action_id: str) -> sqlite3.Row:
        row: sqlite3.Row | None = connection.execute('SELECT * FROM assistance_proposals WHERE action_id=? AND role_scope=?', (action_id, self.role_scope)).fetchone()
        if row is None:raise AssistanceError('proposal_not_found', 404)
        return row

    def get(self, action_id: str) -> JsonObject:
        with self._connection() as connection:return self._record(self._read(connection, _identifier(action_id)))

    def list(self, limit: int = 50) -> list[JsonObject]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise AssistanceError('invalid_limit')
        with self._connection() as connection:
            return [self._record(row) for row in connection.execute('SELECT * FROM assistance_proposals WHERE role_scope=? ORDER BY rowid DESC LIMIT ?', (self.role_scope, limit))]

    def _inputs(self, kind: str, raw: object, *, has_observation: bool = False) -> JsonObject:
        if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):raise AssistanceError('invalid_inputs')
        if kind == 'schedule':
            if set(raw) - {'title', 'due_at', 'notes'}:raise AssistanceError('invalid_inputs')
            title = _text(raw.get('title'), 100)
            due_at = _text(raw.get('due_at'), 64)
            try:due = dt.datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            except ValueError as error:raise AssistanceError('invalid_due_at') from error
            if due.tzinfo is None:raise AssistanceError('timezone_required')
            try:
                stamp = due.timestamp()
                normalized_due = due.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
            except (ValueError, OverflowError, OSError) as error:raise AssistanceError('invalid_due_at') from error
            if not math.isfinite(stamp):raise AssistanceError('invalid_due_at')
            return {'title':title, 'due_at':normalized_due,
                    'notes':_text(raw.get('notes', ''), 2000, empty=True, multiline=True)}
        if kind == 'data_analysis':
            if set(raw) - {'csv_text', 'delimiter', 'filename'}:raise AssistanceError('invalid_inputs')
            text = raw.get('csv_text')
            delimiter = raw.get('delimiter', ',')
            if not isinstance(text, str) or not isinstance(delimiter, str):raise AssistanceError('invalid_csv')
            try:encoded = text.encode('utf-8', 'strict')
            except UnicodeEncodeError as error:raise AssistanceError('invalid_csv') from error
            if not encoded or len(encoded) > MAX_CSV_BYTES:raise AssistanceError('csv_size_limit')
            # Preserve exactly the uploaded bytes for a stable source digest.
            return {'csv_text':text, 'delimiter':delimiter, 'filename':_text(raw.get('filename', 'data.csv'), 120)}
        permitted = {'query', 'context', 'game', 'mode'} if kind == 'game' else {'query', 'context'}
        if set(raw) - permitted:raise AssistanceError('invalid_inputs')
        result: JsonObject = {'query':_text(raw.get('query'), 2000, multiline=True),
                              'context':_text(raw.get('context', ''), 6000, empty=True, multiline=True)}
        if kind == 'game':
            result.update({'game':_text(raw.get('game'), 120), 'mode':_text(raw.get('mode', ''), 120, empty=True)})
            if not result['context'] and not has_observation:raise AssistanceError('game_context_required')
        return result

    def _observation(self, value: TrustedObservation) -> tuple[JsonObject, str]:
        if not isinstance(value, TrustedObservation):raise AssistanceError('untrusted_observation')
        if value.role_scope != self.role_scope:raise AssistanceError('observation_role_mismatch', 409)
        if (value.kind not in {'camera', 'screen'} or value.processing not in {'local', 'remote'}
                or not isinstance(value.source_sha256, str) or not re.fullmatch('[0-9a-f]{64}', value.source_sha256)
                or isinstance(value.captured_at_ms, bool) or not isinstance(value.captured_at_ms, int)
                or not 0 <= value.captured_at_ms <= 100000000000000):
            raise AssistanceError('invalid_observation')
        description = _text(value.description, 6000, multiline=True)
        metadata: JsonObject = {'source':'vision_model_observation', 'observation_id':_identifier(value.observation_id),
                                'session_id':_identifier(value.session_id), 'request_id':_identifier(value.request_id),
                                'role_scope':self.role_scope, 'capture_kind':value.kind, 'processing':value.processing,
                                'captured_at_ms':value.captured_at_ms, 'source_sha256':value.source_sha256,
                                'description_sha256':hashlib.sha256(description.encode('utf-8')).hexdigest(),
                                'inference_verified':False, 'untrusted_context':True}
        return metadata, description

    def create(self, request_id: str, kind: str, inputs: object, *, observation: TrustedObservation | None = None) -> JsonObject:
        request_id = _identifier(request_id)
        if not isinstance(kind, str) or kind not in KINDS:raise AssistanceError('invalid_kind')
        observation_metadata: JsonObject | None = None
        description = ''
        if observation is not None:
            if kind not in ADVICE_KINDS:raise AssistanceError('observation_not_supported_for_kind')
            observation_metadata, description = self._observation(observation)
        normalized = self._inputs(kind, inputs, has_observation=observation is not None)
        identity: JsonObject = {'kind':kind, 'inputs':normalized}
        if observation_metadata is not None:identity['observation'] = observation_metadata
        fingerprint = hashlib.sha256(_dump(identity).encode('utf-8')).hexdigest()
        action_id = str(uuid4())
        summary, error, status = '', None, 'generating'
        result: JsonObject = {'external_actions':False}
        persisted = normalized
        evidence: list[JsonValue] = [{'source':'user_input', 'observed_at':self._now(), 'sha256':fingerprint,
                                     'scope':'explicit_request_only; no saved memory or unrequested screen capture'}]
        if observation_metadata is not None:evidence.append(observation_metadata)
        if kind == 'schedule':
            summary = cast(str, normalized['title']);status = 'proposed'
        elif kind == 'data_analysis':
            result = analyze_csv(cast(str, normalized['csv_text']), cast(str, normalized['delimiter']))
            persisted = {key:value for key, value in normalized.items() if key != 'csv_text'}
            persisted.update({'csv_sha256':result['csv_sha256'], 'bytes':result['bytes']})
            summary = f"已解析 {result['row_count']} 行、{result['column_count']} 列；数值统计可查看结果。"
            evidence.append({'source':'csv_upload', 'sha256':result['csv_sha256'], 'observed_at':self._now(), 'bytes':result['bytes']})
            status = 'proposed'
        elif self.provider is None or kind not in self.provider_kinds:
            status, error = 'unavailable', 'provider_not_configured_for_kind'
        if kind in {'game', 'outfit'}:
            evidence.append({'source':'capability_limit', 'scope':'explicit text and any authorized unverified model observation; no implicit capture, live telemetry or game control; expertise not benchmarked'})
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            old = connection.execute('SELECT * FROM assistance_proposals WHERE request_id=?', (request_id,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:raise AssistanceError('request_id_conflict', 409)
                return self._record(old)
            if observation is not None and not -2000 <= self.clock() * 1000 - observation.captured_at_ms <= 30000:
                raise AssistanceError('observation_expired', 409)
            if kind == 'schedule':
                due = dt.datetime.fromisoformat(cast(str, normalized['due_at'])).timestamp()
                if not 1 <= due - self.clock() <= 604800:raise AssistanceError('due_out_of_range')
            count = connection.execute("SELECT count(*) FROM assistance_proposals WHERE status IN ('generating','proposed')").fetchone()[0]
            if count >= MAX_PROPOSALS:raise AssistanceError('proposal_limit_reached', 429)
            connection.execute('INSERT INTO assistance_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (action_id, request_id, self.role_scope, fingerprint, kind, summary, _dump(persisted),
                 'local_schedule' if kind == 'schedule' else 'read_only', status, _dump(evidence), _dump(result), error,
                 self._now(), self._now(), self.runtime_session))
            self._event(connection, action_id, 'created_' + status)
        if status != 'generating':return self.get(action_id)
        cancelled = threading.Event()
        key = (str(self.database), action_id)
        with _ACTIVE_LOCK:_ACTIVE[key] = cancelled
        try:
            # A cancellation between insertion and event registration still wins.
            if self.get(action_id)['status'] != 'generating':return self.get(action_id)
            if self.provider is None:raise AssistanceError('provider_unavailable', 503)
            provider_inputs = dict(normalized)
            if observation_metadata is not None:
                provider_inputs['observation'] = {**observation_metadata, 'description':description}
            reply = self.provider(AdviceRequest(request_id, self.role_scope, cast(Kind, kind), provider_inputs,
                                               tuple(cast(JsonObject, item) for item in evidence)), cancelled)
            if not isinstance(reply, ProviderReply):raise AssistanceError('invalid_provider_reply')
            summary = _text(reply.summary, 6000, multiline=True)
            provider_id = _text(reply.provider_id, 120)
            evidence.append({'source':'model_provider', 'provider_id':provider_id, 'observed_at':self._now(),
                             'scope':'generated suggestion, not verified facts or executed actions'})
            with self._connection() as connection:
                connection.execute('BEGIN IMMEDIATE')
                current = self._read(connection, action_id)
                if current['status'] == 'generating' and not cancelled.is_set():
                    connection.execute("UPDATE assistance_proposals SET summary=?,source_evidence=?,status='proposed',updated_at=? WHERE action_id=?", (summary, _dump(evidence), self._now(), action_id))
                    self._event(connection, action_id, 'provider_completed')
        except Exception:
            with self._connection() as connection:
                connection.execute('BEGIN IMMEDIATE')
                if self._read(connection, action_id)['status'] == 'generating':
                    connection.execute("UPDATE assistance_proposals SET status='failed',error='provider_failed',updated_at=? WHERE action_id=?", (self._now(), action_id))
                    self._event(connection, action_id, 'provider_failed')
        finally:
            with _ACTIVE_LOCK:_ACTIVE.pop(key, None)
        return self.get(action_id)

    def decide(self, action_id: str, decision: str) -> JsonObject:
        action_id = _identifier(action_id)
        if not isinstance(decision, str) or decision not in {'confirm', 'reject', 'cancel'}:raise AssistanceError('invalid_decision')
        target = {'confirm':'confirmed', 'reject':'rejected', 'cancel':'cancelled'}[decision]
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._read(connection, action_id)
            if row['status'] == target:return self._record(row)
            allowed = {'proposed'} if decision != 'cancel' else {'generating', 'proposed', 'confirmed', 'unavailable', 'failed'}
            if row['status'] not in allowed:raise AssistanceError('proposal_already_terminal', 409)
            result = _object(row['result'])
            if decision == 'confirm' and row['kind'] == 'schedule':
                inputs = _object(row['inputs'])
                due = dt.datetime.fromisoformat(cast(str, inputs['due_at'])).timestamp()
                if not 1 <= due - self.clock() <= 604800:raise AssistanceError('due_out_of_range', 409)
                connection.execute("INSERT INTO tasks(title,due,status,created,kind,assistance_action_id) VALUES(?,?,'pending',?,'reminder',?)", (inputs['title'], due, self._now(), action_id))
                task = connection.execute('SELECT id FROM tasks WHERE assistance_action_id=?', (action_id,)).fetchone()
                result = {'external_actions':False, 'task_id':task[0], 'local_schedule_created':True}
            elif decision == 'cancel' and row['kind'] == 'schedule':
                task = connection.execute('SELECT status FROM tasks WHERE assistance_action_id=?', (action_id,)).fetchone()
                if task and task[0] == 'completed':raise AssistanceError('task_already_completed', 409)
                connection.execute("UPDATE tasks SET status='cancelled' WHERE assistance_action_id=? AND status!='completed'", (action_id,))
                result['local_schedule_cancelled'] = True
            connection.execute('UPDATE assistance_proposals SET status=?,result=?,updated_at=? WHERE action_id=?', (target, _dump(result), self._now(), action_id))
            self._event(connection, action_id, target)
        if decision == 'cancel':
            with _ACTIVE_LOCK:
                event = _ACTIVE.get((str(self.database), action_id))
                if event:event.set()
        return self.get(action_id)

    def cancel_generating(self) -> int:
        """Host calls on role switch/stop; late provider replies cannot revive it."""
        count = 0
        with self._connection() as connection:
            actions = [row[0] for row in connection.execute("SELECT action_id FROM assistance_proposals WHERE status='generating' AND role_scope=?", (self.role_scope,))]
        for action_id in actions:
            try:self.decide(action_id, 'cancel');count += 1
            except AssistanceError as error:
                if error.status != 409:raise
        return count

    def set_proactive_paused(self, paused: bool) -> JsonObject:
        if not isinstance(paused, bool):raise AssistanceError('invalid_paused')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT OR REPLACE INTO settings VALUES('proactive',?)", (json.dumps(not paused),))
            if paused:connection.execute("UPDATE tasks SET status='paused' WHERE status IN ('pending','quiet')")
            connection.execute('INSERT INTO assistance_controls(event,target,created_at) VALUES(?,?,?)',
                               ('proactive_paused' if paused else 'proactive_resumed', 'role', self._now()))
        return self.snapshot()

    def cancel_legacy_task(self, task_id: int) -> JsonObject:
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:raise AssistanceError('invalid_task_id')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:raise AssistanceError('task_not_found', 404)
            if row['status'] == 'completed':raise AssistanceError('task_already_completed', 409)
            if row['status'] == 'cancelled':return {'ok':True, 'task_id':task_id, 'status':'cancelled'}
            connection.execute("UPDATE tasks SET status='cancelled' WHERE id=?", (task_id,))
            if row['assistance_action_id']:
                connection.execute("UPDATE assistance_proposals SET status='cancelled',updated_at=? WHERE action_id=?", (self._now(), row['assistance_action_id']))
                self._event(connection, row['assistance_action_id'], 'legacy_task_cancelled')
            connection.execute('INSERT INTO assistance_controls(event,target,created_at) VALUES(?,?,?)', ('legacy_task_cancelled', str(task_id), self._now()))
        return {'ok':True, 'task_id':task_id, 'status':'cancelled'}

    def snapshot(self) -> JsonObject:
        with self._connection() as connection:
            setting = connection.execute("SELECT value FROM settings WHERE key='proactive'").fetchone()
            proactive = bool(setting and setting[0] == 'true')
            tasks: list[JsonValue] = [{'id':row['id'], 'title':row['title'], 'due':row['due'], 'status':row['status'],
                                      'kind':row['kind'], 'action_id':row['assistance_action_id']}
                                     for row in connection.execute('SELECT * FROM tasks ORDER BY id DESC LIMIT 60')]
        return {'proposals':cast(JsonValue, self.list()), 'proactive_paused':not proactive, 'legacy_tasks':tasks,
                'capabilities':{'schedule':True, 'data_analysis':True,
                                **{kind:self.provider is not None and kind in self.provider_kinds for kind in sorted(ADVICE_KINDS)}},
                'external_execution_enabled':False}
