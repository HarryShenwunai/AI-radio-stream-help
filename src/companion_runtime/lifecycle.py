"""Bounded, in-process ownership of generation and media lifetimes.

The HTTP layer must derive ``Scope`` from authenticated server-side context.
Neither a request's role field nor this registry establishes authorization.
Setting an event signals cooperative cancellation; it does not guarantee that
an external provider has stopped computing. Consumers must also reject results
for handles which are no longer current.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import math
import threading
import time
from typing import Callable, Iterable, Literal
from uuid import uuid4


CancelStatus = Literal["accepted", "already_done", "not_found"]


class GenerationCapacityError(RuntimeError):
    """All registry slots belong to still-valid generations."""


@dataclass(frozen=True)
class Scope:
    channel: Literal["private", "live"]
    session_id: str

    def __post_init__(self) -> None:
        if self.channel not in {"private", "live"}:
            raise ValueError("unsupported channel")
        _identifier(self.session_id, "session_id")


@dataclass(frozen=True)
class GenerationHandle:
    generation_id: str
    request_id: str
    scope: Scope
    cancel_event: threading.Event = field(default_factory=threading.Event, compare=False)

    @property
    def id(self) -> str:
        return self.generation_id


@dataclass
class _Entry:
    handle: GenerationHandle
    completed_at: float | None = None
    invalidated_at: float | None = None


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError(f"{name} must be a non-empty string of at most 160 characters")


class GenerationRegistry:
    """Serialize transitions while keeping storage within ``max_entries``.

    Completed generations remain eligible for speech/playback until cancelled,
    superseded, or ``retention_seconds`` after completion. Running generations
    do not expire merely to free cache space. Invalidated tombstones can be
    evicted early under capacity pressure; cancellation of an evicted ID then
    returns ``not_found``. Callers must treat every non-current ID as unusable.
    A new generation may replace the current generation in its own scope even
    when full, but may never evict a still-valid generation in another scope.
    """

    def __init__(
        self,
        max_entries: int = 256,
        retention_seconds: float = 600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        if isinstance(retention_seconds, bool) or not isinstance(retention_seconds, (int, float)):
            raise ValueError("retention_seconds must be positive and finite")
        if not math.isfinite(retention_seconds) or retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive and finite")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._limit = max_entries
        self._retention = retention_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._current: dict[Scope, str] = {}

    def _remove(self, generation_id: str) -> None:
        entry = self._entries.pop(generation_id)
        entry.handle.cancel_event.set()
        if self._current.get(entry.handle.scope) == generation_id:
            del self._current[entry.handle.scope]

    def _prune(self, stamp: float) -> None:
        for generation_id, entry in list(self._entries.items()):
            # Respect a cooperative event set by a consumer as invalidation.
            if entry.handle.cancel_event.is_set() and entry.invalidated_at is None:
                entry.invalidated_at = stamp
                if self._current.get(entry.handle.scope) == generation_id:
                    del self._current[entry.handle.scope]
            retired_at = entry.invalidated_at if entry.invalidated_at is not None else entry.completed_at
            if retired_at is not None and stamp - retired_at >= self._retention:
                self._remove(generation_id)

    @staticmethod
    def _scope(scope: Scope) -> None:
        if not isinstance(scope, Scope):
            raise TypeError("scope must be a server-derived Scope")

    def begin(self, scope: Scope, request_id: str) -> GenerationHandle:
        """Begin an attempt; the same request ID may have a new generation."""
        self._scope(scope)
        _identifier(request_id, "request_id")
        with self._lock:
            stamp = self._clock()
            self._prune(stamp)
            previous_id = self._current.get(scope)
            if len(self._entries) >= self._limit:
                # Failed admission must not cancel any existing valid result.
                victim = next((key for key, item in self._entries.items()
                               if item.invalidated_at is not None), previous_id)
                if victim is None:
                    raise GenerationCapacityError("generation registry is full")
                self._remove(victim)
            if previous_id is not None and previous_id in self._entries:
                previous = self._entries[previous_id]
                previous.handle.cancel_event.set()
                previous.invalidated_at = stamp
            handle = GenerationHandle(str(uuid4()), request_id, scope)
            self._entries[handle.id] = _Entry(handle)
            self._current[scope] = handle.id
            return handle

    def current(self, scope: Scope) -> GenerationHandle | None:
        return self.resolve(scope)

    def resolve(
        self,
        scope: Scope,
        *,
        generation_id: str | None = None,
        request_id: str | None = None,
    ) -> GenerationHandle | None:
        """Return only the current usable handle matching every supplied ID."""
        self._scope(scope)
        if generation_id is not None:
            _identifier(generation_id, "generation_id")
        if request_id is not None:
            _identifier(request_id, "request_id")
        with self._lock:
            self._prune(self._clock())
            entry = self._entries.get(self._current.get(scope, ""))
            if entry is None or entry.handle.cancel_event.is_set():
                return None
            handle = entry.handle
            if generation_id is not None and handle.id != generation_id:
                return None
            if request_id is not None and handle.request_id != request_id:
                return None
            return handle

    def is_current(self, handle: GenerationHandle) -> bool:
        if not isinstance(handle, GenerationHandle):
            return False
        with self._lock:
            return self.current(handle.scope) is handle

    def complete(self, handle: GenerationHandle) -> bool:
        """Keep a successful result usable for media, without reviving old work."""
        if not isinstance(handle, GenerationHandle):
            return False
        with self._lock:
            if not self.is_current(handle):
                return False
            entry = self._entries[handle.id]
            if entry.completed_at is None:
                entry.completed_at = self._clock()
            return True

    def cancel(
        self,
        scope: Scope,
        *,
        generation_id: str | None = None,
        request_id: str | None = None,
    ) -> CancelStatus:
        """Invalidate only a matching generation in the authenticated scope.

        ``accepted`` acknowledges local invalidation, not provider termination.
        ``already_done`` means this retained generation was already invalidated.
        ``not_found`` covers an unknown/expired ID and an ID in another scope.
        Completed but still-usable media is invalidated and returns ``accepted``.
        """
        self._scope(scope)
        if generation_id is None and request_id is None:
            raise ValueError("cancellation requires a generation_id or request_id")
        if generation_id is not None:
            _identifier(generation_id, "generation_id")
        if request_id is not None:
            _identifier(request_id, "request_id")
        with self._lock:
            stamp = self._clock()
            self._prune(stamp)
            candidates: Iterable[_Entry | None]
            if generation_id is not None:
                candidates = [self._entries.get(generation_id)]
            else:
                candidates = reversed(self._entries.values())
            for entry in candidates:
                if entry is None:
                    continue
                handle = entry.handle
                if handle.scope != scope or (request_id is not None and handle.request_id != request_id):
                    continue
                if entry.invalidated_at is not None or handle.cancel_event.is_set():
                    return "already_done"
                handle.cancel_event.set()
                entry.invalidated_at = stamp
                if self._current.get(scope) == handle.id:
                    del self._current[scope]
                return "accepted"
            return "not_found"

    def __len__(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._entries)
