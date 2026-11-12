"""Bounded server-owned audio playback receipts, never human-attention proof.

No character positions are inferred from seconds. A complete unaligned WAV
confirms only the exact text prefix the server actually synthesized. HTTP must
derive owner/scope and message text itself; persisted receipts are server data,
not arbitrary request JSON. This module performs no I/O.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import math
import secrets
import threading
import time
from typing import Callable
from uuid import uuid4

MAX_ENTRIES = 64
MAX_TTL_SECONDS = 600
MAX_DURATION_SECONDS = 180
MAX_TEXT_BYTES = 64 * 1024
_ANY = object()
_EPSILON = 0.000001
EVIDENCE = "client_owner_reported_playback_not_human_attention"


class PlaybackError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _identifier(value, name, *, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 160 or any(not c.isprintable() for c in value):
        raise PlaybackError(f"{name} 无效。")
    return value


def _message_key(value):
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 2**63 - 1:
        return str(value)
    return _identifier(value, "message_id")


def _text_sha(value):
    if not isinstance(value, str):
        raise PlaybackError("播放文字必须是字符串。")
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        raise PlaybackError("播放文字编码无效。") from None
    if len(raw) > MAX_TEXT_BYTES:
        raise PlaybackError("播放文字超过64 KiB预算。", 413)
    return hashlib.sha256(raw).hexdigest()


def _seconds(value, name, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= MAX_DURATION_SECONDS or not math.isfinite(value)):
        raise PlaybackError(f"{name} 必须是有限秒数。")
    value = float(value)
    if not (0 < value <= MAX_DURATION_SECONDS if positive else 0 <= value <= MAX_DURATION_SECONDS):
        raise PlaybackError(f"{name} 超过0–180秒范围。")
    return value


@dataclass
class _Entry:
    playback_id: str
    nonce_hash: bytes
    owner_id: str
    character_id: str
    appearance_id: str | None
    message_id: str | int
    message_key: str
    text_sha: str
    text_length: int
    audible_text: str
    created_at: float
    sequence: int
    status: str = "pending"
    position: float = 0
    duration: float | None = None
    confirmed_text: str = ""
    invalidated: bool = False
    reason: str = ""


class PlaybackTracker:
    """One tracker per data root; one current playback per trusted owner.

    TTL runs from begin and cannot be extended by traffic. Capacity never evicts
    another owner's valid active playback; begin may reclaim its own previous
    attempt or a terminal record. Scope changes must call invalidate even if a
    browser never reports its stop. Nonces establish possession plus server
    binding, not authentication; HTTP authentication remains mandatory.
    """
    def __init__(self, max_entries: int = 64, ttl_seconds: float = 600,
                 clock: Callable[[], float] = time.monotonic):
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or not 1 <= max_entries <= MAX_ENTRIES:
            raise ValueError("max_entries must be 1–64")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError("ttl_seconds must be positive and at most 600")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._limit, self._ttl, self._clock = max_entries, float(ttl_seconds), clock
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._current: dict[str, str] = {}
        self._tracker_id = str(uuid4())
        self._sequence = 0

    def _next(self):
        self._sequence += 1
        return self._sequence

    def _remove(self, playback_id):
        entry = self._entries.pop(playback_id)
        if self._current.get(entry.owner_id) == playback_id:
            self._current.pop(entry.owner_id, None)
        entry.audible_text = entry.confirmed_text = ""

    def _prune(self, now):
        for key, entry in list(self._entries.items()):
            if now - entry.created_at >= self._ttl:
                self._remove(key)

    def _snapshot(self, entry, *, accepted=True, stale=False, should_persist=True, include_text=True):
        confirmed = entry.confirmed_text if include_text else ""
        return {"playback_id": entry.playback_id, "character_id": entry.character_id,
                "appearance_id": entry.appearance_id, "message_id": entry.message_id,
                "text_sha": entry.text_sha, "text_length": entry.text_length,
                "status": entry.status, "position_seconds": entry.position,
                "duration_seconds": entry.duration, "confirmed_text": confirmed,
                "truncated": len(confirmed) < entry.text_length,
                "evidence": EVIDENCE, "accepted": accepted, "stale": stale,
                "should_persist": should_persist, "reason": entry.reason,
                "tracker_id": self._tracker_id, "sequence": entry.sequence}

    def _retire(self, entry, reason):
        stopped = None
        if entry.status not in {"completed", "stopped"}:
            entry.status, entry.confirmed_text, entry.reason = "stopped", "", reason
            entry.sequence = self._next()
            stopped = self._snapshot(entry)
        entry.invalidated = True
        entry.audible_text = entry.confirmed_text = ""
        if self._current.get(entry.owner_id) == entry.playback_id:
            self._current.pop(entry.owner_id, None)
        return stopped

    def begin(self, character_id: str, appearance_id: str | None, message_id: str | int,
              text: str, *, owner_id: str = "local", duration_seconds: float | None = None,
              audible_text: str | None = None) -> dict:
        owner_id = _identifier(owner_id, "owner_id")
        character_id = _identifier(character_id, "character_id")
        appearance_id = _identifier(appearance_id, "appearance_id", nullable=True)
        message_key, text_sha = _message_key(message_id), _text_sha(text)
        audible = text if audible_text is None else audible_text
        if not text or not isinstance(audible, str) or not audible or not text.startswith(audible):
            raise PlaybackError("合成文字必须是完整消息的非空前缀。")
        _text_sha(audible)
        duration = None if duration_seconds is None else _seconds(duration_seconds, "duration_seconds", positive=True)
        with self._lock:
            now = self._clock()
            self._prune(now)
            previous_id = self._current.get(owner_id)
            if len(self._entries) >= self._limit:
                victim = next((key for key, e in self._entries.items() if e.invalidated or e.status in {"completed", "stopped"}), previous_id)
                if victim is None:
                    raise PlaybackError("播放追踪器已满，请稍后重试。", 429)
            else:
                victim = None
            stopped = []
            if previous_id is not None:
                receipt = self._retire(self._entries[previous_id], "superseded")
                if receipt is not None:
                    stopped.append(receipt)
            if victim is not None:
                self._remove(victim)
            playback_id, nonce = str(uuid4()), secrets.token_urlsafe(32)
            entry = _Entry(playback_id, hashlib.sha256(nonce.encode("ascii")).digest(), owner_id,
                           character_id, appearance_id, message_id, message_key, text_sha,
                           len(text), audible, now, self._next(), duration=duration)
            self._entries[playback_id] = entry
            self._current[owner_id] = playback_id
            result = self._snapshot(entry, should_persist=False, include_text=False)
            result.update(nonce=nonce, expires_in_seconds=self._ttl,
                          audible_text_sha=_text_sha(audible), audible_text_length=len(audible),
                          stopped_receipts=stopped)
            return result

    def receipt(self, playback_id: str, nonce: str, *, character_id: str,
                appearance_id: str | None, position_seconds: float,
                duration_seconds: float | None, status: str, owner_id: str = "local",
                message_id: str | int | None = None) -> dict:
        owner_id = _identifier(owner_id, "owner_id")
        character_id = _identifier(character_id, "character_id")
        appearance_id = _identifier(appearance_id, "appearance_id", nullable=True)
        _identifier(playback_id, "playback_id")
        if not isinstance(nonce, str) or not 20 <= len(nonce) <= 128 or not nonce.isascii():
            raise PlaybackError("播放凭证无效。", 404)
        if not isinstance(status, str) or status not in {"playing", "completed", "stopped"}:
            raise PlaybackError("播放状态无效。")
        position = _seconds(position_seconds, "position_seconds")
        if isinstance(duration_seconds, bool):
            raise PlaybackError("duration_seconds 必须是有限秒数。")
        if status == "stopped" and position == 0 and (duration_seconds is None or duration_seconds == 0):
            duration = None
        else:
            duration = _seconds(duration_seconds, "duration_seconds", positive=True)
        with self._lock:
            self._prune(self._clock())
            entry = self._entries.get(playback_id)
            proof = hashlib.sha256(nonce.encode("ascii")).digest()
            if (entry is None or not hmac.compare_digest(proof, entry.nonce_hash)
                    or entry.owner_id != owner_id or entry.character_id != character_id
                    or entry.appearance_id != appearance_id
                    or (message_id is not None and _message_key(message_id) != entry.message_key)):
                raise PlaybackError("播放凭证或所属消息不匹配。", 404)
            if entry.invalidated or self._current.get(owner_id) != playback_id:
                # Do not return old text, update a new scope, or permit a late
                # onended callback to confirm a cancelled attempt.
                return self._snapshot(entry, accepted=False, stale=True,
                                      should_persist=False, include_text=False)
            if duration is not None and entry.duration is not None and abs(duration - entry.duration) > .05:
                raise PlaybackError("播放时长与已绑定的音频不一致。", 409)
            effective_duration = entry.duration if entry.duration is not None else duration
            if ((effective_duration is not None and position > effective_duration + _EPSILON)
                    or (duration is not None and position > duration + _EPSILON)
                    or position + _EPSILON < entry.position):
                raise PlaybackError("播放位置越界或倒退。", 409)
            if status == "completed" and (effective_duration is None or duration is None
                    or abs(position - effective_duration) > _EPSILON
                    or abs(position - duration) > _EPSILON):
                raise PlaybackError("只有播放位置到达音频末尾才能报告完成。", 409)
            if entry.status in {"completed", "stopped"}:
                if status == entry.status and abs(position - entry.position) <= _EPSILON:
                    return self._snapshot(entry, should_persist=False)
                raise PlaybackError("此播放回执已结束，不能恢复或改写。", 409)
            entry.position = min(position, effective_duration) if effective_duration is not None else position
            entry.duration, entry.status = effective_duration, status
            entry.confirmed_text = entry.audible_text if status == "completed" else ""
            entry.reason = "client_stopped" if status == "stopped" else ""
            entry.sequence = self._next()
            return self._snapshot(entry)

    report = receipt

    def invalidate(self, *, character_id: str | None = None, appearance_id=_ANY,
                   owner_id: str = "local", reason: str = "switch") -> list[dict]:
        owner_id = _identifier(owner_id, "owner_id")
        if character_id is not None:
            _identifier(character_id, "character_id")
        if appearance_id is not _ANY:
            _identifier(appearance_id, "appearance_id", nullable=True)
        _identifier(reason, "reason")
        with self._lock:
            result = []
            for entry in self._entries.values():
                if (entry.owner_id == owner_id and not entry.invalidated
                        and (character_id is None or entry.character_id == character_id)
                        and (appearance_id is _ANY or entry.appearance_id == appearance_id)):
                    stopped = self._retire(entry, reason)
                    if stopped is not None:
                        result.append(stopped)
            self._prune(self._clock())
            return result

    def size(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._entries)


def merge_receipts(previous: dict | None, incoming: dict) -> dict:
    """Merge trusted server receipts without erasing earlier playback evidence.

    The latest attempt's status may be stopped while an earlier attempt already
    confirmed the entire message. This function preserves the longest compatible
    confirmed prefix, never derives a prefix from seconds, and performs no DB I/O.
    Caller must transactionally read/merge/write the correct profile/message row.
    """
    if not isinstance(incoming, dict):
        raise PlaybackError("播放回执格式无效。")
    result = dict(incoming)
    length = result.get("text_length")
    if (not isinstance(length, int) or isinstance(length, bool) or not 0 <= length <= MAX_TEXT_BYTES
            or not isinstance(result.get("text_sha"), str)
            or len(result["text_sha"]) != 64 or not isinstance(result.get("status"), str)
            or result["status"] not in {"pending", "playing", "stopped", "completed"}):
        raise PlaybackError("播放回执字段无效。")
    new = result.get("confirmed_text", "")
    if not isinstance(new, str) or len(new) > length:
        raise PlaybackError("确认文字格式无效。")
    if previous is None:
        return result
    if not isinstance(previous, dict) or any(previous.get(k) != result.get(k) for k in ("character_id", "message_id", "text_sha")):
        raise PlaybackError("不能合并不同角色、消息或文字的播放回执。", 409)
    old = previous.get("confirmed_text", "")
    if not isinstance(old, str) or len(old) > length or not (old.startswith(new) or new.startswith(old)):
        raise PlaybackError("确认文字不是同一个消息的兼容前缀。", 409)
    if (previous.get("tracker_id") == result.get("tracker_id")
            and isinstance(previous.get("sequence"), int) and isinstance(result.get("sequence"), int)
            and previous["sequence"] > result["sequence"]):
        result = dict(previous)
    confirmed = old if len(old) > len(new) else new
    result["confirmed_text"] = confirmed
    result["truncated"] = len(confirmed) < result.get("text_length", len(confirmed))
    result["evidence"] = EVIDENCE
    return result


def context_for(message_text: str, receipt: dict | None, *, message_id=None) -> dict:
    """Return prompt-only text from a trusted matching completed/stopped receipt.

    `truncated` means some full message characters are deliberately withheld from
    model context; it says nothing about human attention. DB/chat display text is
    untouched. A SHA mismatch or malformed/unrecognized receipt leaves the text
    unchanged and `applied=False`; callers must never pass client JSON directly.
    """
    digest = _text_sha(message_text)
    unchanged = {"text": message_text, "truncated": False, "applied": False,
                 "interrupted": False, "evidence": None}
    try:
        message_matches = message_id is None or (isinstance(receipt, dict)
            and _message_key(receipt.get("message_id")) == _message_key(message_id))
    except PlaybackError:
        return unchanged
    if (not isinstance(receipt, dict) or receipt.get("text_sha") != digest
            or not isinstance(receipt.get("status"), str) or receipt["status"] not in {"completed", "stopped"}
            or not message_matches):
        return unchanged
    confirmed = receipt.get("confirmed_text")
    if not isinstance(confirmed, str) or not message_text.startswith(confirmed):
        return unchanged
    return {"text": confirmed, "truncated": confirmed != message_text,
            "applied": True, "interrupted": receipt["status"] == "stopped", "evidence": EVIDENCE}
