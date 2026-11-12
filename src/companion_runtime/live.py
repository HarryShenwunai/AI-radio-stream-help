"""Bounded, offline public ingress. No account clients, private storage or tools.

Input is our explicit normalized envelope, not a Bilibili or danmuji SDK shape.
The binding must be supplied by a trusted pairing/configuration layer.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
import hashlib
import json
import math
import re
import threading
import time
from typing import Callable, Mapping

SOURCES = frozenset({'bilibili-open-live', 'danmuji-bridge'})
FIELDS = frozenset({'room_id', 'event_id', 'text', 'actor_key', 'event_at', 'type'})


class LiveEventError(ValueError):
    """Validation error with a fixed code; never includes viewer content."""

    def __init__(self, code: str = 'invalid') -> None:
        self.code = code
        super().__init__(code)


def _valid_utf8(value: str) -> bool:
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeEncodeError:
        return False
    return True


def _identifier(value: object, limit: int) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= limit
            and value == value.strip() and _valid_utf8(value)
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def _finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class LiveBinding:
    source: str
    room_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or self.source not in SOURCES:
            raise ValueError('unsupported source')
        if not isinstance(self.room_id, str) or not re.fullmatch(r'[0-9]{1,32}', self.room_id):
            raise ValueError('room_id must be a bounded decimal string')


@dataclass(frozen=True)
class PublicEvent:
    source: str
    room_id: str
    event_id: str
    text: str
    actor_key: str | None
    received_at: float
    event_at: float | None
    expires_at: float
    type: str = 'danmaku'

    @property
    def dedupe_key(self) -> str:
        material = '\0'.join((self.source, self.room_id, self.event_id))
        return hashlib.sha256(material.encode('utf-8')).hexdigest()


def normalize_event(
    binding: LiveBinding,
    payload: Mapping[str, object],
    *,
    received_at: float,
    wall_now: float,
    ttl_seconds: float = 8.0,
    max_text_chars: int = 300,
) -> PublicEvent:
    """Validate an already-mapped public message with no privilege fields.

    event_at, when supplied, is a Unix timestamp. It can shorten the deadline;
    it cannot extend it. Missing timestamps use receipt TTL and remain a known
    source-staleness limitation. Unknown fields are rejected, not forwarded.
    """
    if not isinstance(payload, Mapping) or set(payload) - FIELDS:
        raise LiveEventError()
    if not {'room_id', 'event_id', 'text'} <= set(payload):
        raise LiveEventError()
    if not isinstance(payload['room_id'], str) or not re.fullmatch(r'[0-9]{1,32}', payload['room_id']):
        raise LiveEventError()
    if payload['room_id'] != binding.room_id:
        raise LiveEventError('wrong_room')
    if not _identifier(payload['event_id'], 160):
        raise LiveEventError()
    if payload.get('type', 'danmaku') != 'danmaku':
        raise LiveEventError()
    text = payload['text']
    if not isinstance(text, str) or not 1 <= len(text) <= max_text_chars or not text.strip():
        raise LiveEventError()
    if not _valid_utf8(text):
        raise LiveEventError()
    if any((ord(char) < 32 and char not in '\n\t') or ord(char) == 127 for char in text):
        raise LiveEventError()
    actor = payload.get('actor_key')
    if actor in ('', '0', None):
        actor = None  # Anonymous viewers are not a shared authenticated identity.
    elif not _identifier(actor, 160):
        raise LiveEventError()
    event_at = payload.get('event_at')
    age = 0.0
    if event_at is not None:
        if not _finite_number(event_at) or event_at < 0 or event_at > wall_now + 5.0:
            raise LiveEventError()
        age = max(0.0, wall_now - event_at)
    return PublicEvent(
        source=binding.source, room_id=binding.room_id,
        event_id=payload['event_id'], text=text.strip(), actor_key=actor,
        received_at=received_at, event_at=event_at,
        expires_at=received_at + ttl_seconds - age,
    )


class LiveIngress:
    """Single trusted source/room, FIFO drop-new policy, bounded deduplication.

    Dedup IDs are retained only for admitted events. If the ID cache is full,
    new events are rejected rather than evicting unexpired IDs and admitting
    duplicates. pop() never waits for an event, model, or network operation.
    """

    def __init__(
        self,
        binding: LiveBinding,
        *,
        capacity: int = 200,
        ttl_seconds: float = 8.0,
        dedupe_capacity: int = 4096,
        dedupe_seconds: float = 60.0,
        max_text_chars: int = 300,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(binding, LiveBinding):
            raise TypeError('trusted binding required')
        for value in (capacity, dedupe_capacity, max_text_chars):
            if type(value) is not int or not 1 <= value <= 100_000:
                raise ValueError('invalid capacity')
        if not _finite_number(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError('invalid ttl')
        if not _finite_number(dedupe_seconds) or dedupe_seconds < ttl_seconds:
            raise ValueError('dedupe_seconds must cover receipt ttl')
        self.binding = binding
        self.capacity = capacity
        self.ttl_seconds = float(ttl_seconds)
        self.dedupe_capacity = dedupe_capacity
        self.dedupe_seconds = float(dedupe_seconds)
        self.max_text_chars = max_text_chars
        self._clock = clock
        self._wall_clock = wall_clock
        self._queue: deque[PublicEvent] = deque()
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._counts: Counter[str] = Counter()
        self._lock = threading.Lock()

    def _purge(self, current: float) -> None:
        # Source timestamp ages can differ, so expired events need not form a
        # prefix. Work is bounded by configured queue capacity, not total input.
        retained = deque(event for event in self._queue if event.expires_at > current)
        self._counts['expired_queued'] += len(self._queue) - len(retained)
        self._queue = retained
        while self._seen and next(iter(self._seen.values())) <= current:
            self._seen.popitem(last=False)

    def submit(self, payload: Mapping[str, object]) -> str:
        with self._lock:
            current = self._clock()
            self._purge(current)
            self._counts['submitted'] += 1
            try:
                event = normalize_event(
                    self.binding, payload, received_at=current,
                    wall_now=self._wall_clock(), ttl_seconds=self.ttl_seconds,
                    max_text_chars=self.max_text_chars,
                )
            except LiveEventError as error:
                self._counts[error.code] += 1
                return error.code
            if event.expires_at <= current:
                status = 'expired'
            elif event.dedupe_key in self._seen:
                status = 'duplicate'
            elif len(self._queue) >= self.capacity:
                status = 'full'
            elif len(self._seen) >= self.dedupe_capacity:
                status = 'dedupe_full'
            else:
                self._queue.append(event)
                self._seen[event.dedupe_key] = current + self.dedupe_seconds
                self._counts['max_queue_depth'] = max(
                    self._counts['max_queue_depth'], len(self._queue))
                status = 'accepted'
            self._counts[status] += 1
            return status

    def pop(self) -> PublicEvent | None:
        with self._lock:
            self._purge(self._clock())
            if not self._queue:
                return None
            self._counts['dequeued'] += 1
            return self._queue.popleft()

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            self._purge(self._clock())
            keys = ('submitted', 'accepted', 'dequeued', 'duplicate', 'expired',
                    'expired_queued', 'full', 'dedupe_full', 'invalid',
                    'wrong_room', 'max_queue_depth')
            result: dict[str, int | float] = {key: self._counts[key] for key in keys}
            denominator = self._counts['submitted']
            result.update(
                queue_depth=len(self._queue), dedupe_entries=len(self._seen),
                admission_coverage=self._counts['accepted'] / denominator if denominator else 0.0,
                dequeue_coverage=self._counts['dequeued'] / denominator if denominator else 0.0,
            )
            return result


def synthetic_replay(rate: int = 200, seconds: int = 60) -> dict[str, object]:
    """Advance synthetic time without sleeping or sending platform traffic."""
    if type(rate) is not int or type(seconds) is not int or not 1 <= rate <= 1000 or not 1 <= seconds <= 3600:
        raise ValueError('replay rate/seconds outside local bounds')
    tick = [0.0]
    ingress = LiveIngress(
        LiveBinding('danmuji-bridge', '1'),
        clock=lambda: tick[0], wall_clock=lambda: 1_800_000_000.0 + tick[0],
    )
    for index in range(rate * seconds):
        tick[0] = index / rate
        ingress.submit({'room_id': '1', 'event_id': f'fixture-{index}', 'text': '合成弹幕'})
        if index % rate == 0:
            ingress.pop()  # Simulated consumer selects at most one event/s.
    return {
        'mode': 'offline_synthetic', 'platform_connected': False,
        'rate_per_second': rate, 'simulated_seconds': seconds,
        'consumer': 'at most one dequeued event per synthetic second; no inference or playback',
        'stats': ingress.snapshot(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Offline bounded public-event replay')
    parser.add_argument('--rate', type=int, default=200)
    parser.add_argument('--seconds', type=int, default=60)
    arguments = parser.parse_args()
    print(json.dumps(synthetic_replay(arguments.rate, arguments.seconds), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
