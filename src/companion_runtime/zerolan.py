"""Bounded, offline adapters for the inspected Zerolan 1.1/Core DTOs.

This module performs no networking or tool execution. Shape validation is not
identity verification. Callers must select history from their authorized channel.
"""
from __future__ import annotations

import codecs
import io
import json
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4


class ProtocolError(ValueError):
    """Malformed, unsupported or oversized input. Messages omit input content."""


PROTOCOL = "ZerolanProtocol"
VERSION = "1.1"
# P0 only permits discovery/metadata, never model-proposed instruction execution.
READ_ONLY_ACTIONS = frozenset({
    "client_hello", "server_hello", "query_gameobjects_info",
    "update_gameobjects_info", "koneko.client.hello", "koneko.server.hello",
    "koneko.server.fetch_instructions", "koneko.client.push_instructions",
})
_MAX_TEXT_CHARS = 16000
_MAX_HISTORY_CHARS = 64000
_MAX_HISTORY_ITEMS = 64
_MAX_CONTROL_BYTES = 65536


def _json_constant(_value: str) -> Any:
    raise ProtocolError("Non-finite JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ProtocolError("Non-finite JSON number")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("Duplicate JSON member")
        result[key] = value
    return result


def _loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_json_constant, parse_float=_finite_float)
    except ProtocolError:
        raise
    except (ValueError, TypeError, RecursionError) as error:
        raise ProtocolError("Invalid JSON frame") from error


class NDJSONDecoder:
    """Decode strict UTF-8 JSON objects independently of HTTP chunk boundaries.

    Limits count wire bytes, including whitespace; a frame excludes its LF.
    Blank lines are ignored. A complete final JSON object may omit its LF;
    incomplete JSON/UTF-8 at EOF fails. After failure or finish, make a new
    decoder rather than appending to a potentially corrupted stream.
    """

    def __init__(self, max_frame_bytes: int = 65536,
                 max_total_bytes: int = 2_000_000) -> None:
        if (type(max_frame_bytes) is not int or max_frame_bytes <= 0 or
                type(max_total_bytes) is not int or max_total_bytes <= 0):
            raise ValueError("Byte limits must be positive integers")
        self.max_frame_bytes = max_frame_bytes
        self.max_total_bytes = max_total_bytes
        self._total_bytes = 0
        self._frame_bytes = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._frame = io.StringIO()
        self._closed = False

    def _fail(self, message: str) -> None:
        self._closed = True
        self._frame.close()
        self._decoder.reset()
        raise ProtocolError(message)

    def _record(self) -> dict[str, Any] | None:
        text = self._frame.getvalue()
        self._frame.seek(0)
        self._frame.truncate()
        self._frame_bytes = 0
        if not text.strip():
            return None
        try:
            value = _loads(text)
        except ProtocolError:
            self._fail("Invalid JSON frame")
        if not isinstance(value, dict):
            self._fail("Expected JSON object frame")
        return value

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        if self._closed:
            raise ProtocolError("Decoder is closed")
        if not isinstance(chunk, bytes):
            self._fail("Stream chunks must be bytes")
        self._total_bytes += len(chunk)
        if self._total_bytes > self.max_total_bytes:
            self._fail("Stream byte limit exceeded")
        output: list[dict[str, Any]] = []
        parts = chunk.split(b"\n")
        for index, part in enumerate(parts):
            self._frame_bytes += len(part)
            if self._frame_bytes > self.max_frame_bytes:
                self._fail("Frame byte limit exceeded")
            try:
                self._frame.write(self._decoder.decode(part, final=False))
                if index < len(parts) - 1:
                    # LF also exposes an incomplete UTF-8 sequence in this line.
                    self._frame.write(self._decoder.decode(b"\n", final=False))
            except UnicodeError:
                self._fail("Invalid UTF-8 frame")
            if index < len(parts) - 1:
                value = self._record()
                if value is not None:
                    output.append(value)
        return output

    def finish(self) -> list[dict[str, Any]]:
        if self._closed:
            raise ProtocolError("Decoder is closed")
        try:
            self._frame.write(self._decoder.decode(b"", final=True))
        except UnicodeError:
            self._fail("Incomplete UTF-8 at end of stream")
        value = self._record()
        self._closed = True
        self._frame.close()
        return [] if value is None else [value]


def _text(value: Any, field: str, *, allow_empty: bool = False,
          max_chars: int = _MAX_TEXT_CHARS) -> str:
    if (not isinstance(value, str) or len(value) > max_chars or
            (not allow_empty and not value.strip())):
        raise ProtocolError(f"Invalid {field}")
    # Reject surrogate code points before later UTF-8 encoding/networking.
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as error:
        raise ProtocolError(f"Invalid {field}") from error
    return value


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise ProtocolError("Invalid request id")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise ProtocolError("Invalid request id") from error
    if str(parsed) != value:
        raise ProtocolError("Request id must be a canonical UUID")
    return value


def _history(value: Any) -> list[dict[str, Any]]:
    if (not isinstance(value, (list, tuple)) or
            len(value) > _MAX_HISTORY_ITEMS):
        raise ProtocolError("Invalid history")
    result: list[dict[str, Any]] = []
    chars = 0
    for item in value:
        if not isinstance(item, Mapping) or set(item) - {"role", "content", "metadata"}:
            raise ProtocolError("Invalid history item")
        role = item.get("role")
        if not isinstance(role, str) or role not in {"system", "user", "assistant", "function"}:
            raise ProtocolError("Invalid history role")
        content = _text(item.get("content"), "history content", allow_empty=True)
        copied: dict[str, Any] = {"role": role, "content": content}
        metadata = item.get("metadata")
        if metadata is not None:
            copied["metadata"] = _text(metadata, "history metadata", allow_empty=True)
        chars += len(content) + len(metadata or "")
        if chars > _MAX_HISTORY_CHARS:
            raise ProtocolError("History character limit exceeded")
        result.append(copied)
    return result


def build_llm_query(text: str, history: Sequence[Mapping[str, Any]] = (),
                    request_id: str | None = None) -> dict[str, Any]:
    """Build the inspected LLMQuery DTO, allocating a fresh UUID per call.

    Only a channel-authorized caller may supply history; this is not a privacy
    filter. No upstream default ID, global history or supplied role is inferred.
    """
    return {"id": str(uuid4()) if request_id is None else _uuid(request_id),
            "text": _text(text, "query text"), "history": _history(history)}


def validate_prediction(value: Any) -> dict[str, Any]:
    """Validate LLMPrediction shape, without assuming delta vs cumulative text."""
    if (not isinstance(value, Mapping) or
            set(value) - {"id", "response", "history"} or
            not {"id", "response"} <= set(value)):
        raise ProtocolError("Invalid prediction fields")
    return {"id": _uuid(value["id"]),
            "response": _text(value["response"], "prediction response", allow_empty=True),
            "history": _history(value.get("history", []))}


def decode_predictions(chunks: Iterable[bytes], *, max_frame_bytes: int = 65536,
                       max_total_bytes: int = 2_000_000) -> Iterator[dict[str, Any]]:
    """Decode fixture/network bytes supplied by a caller; never opens a socket."""
    decoder = NDJSONDecoder(max_frame_bytes, max_total_bytes)
    for chunk in chunks:
        for value in decoder.feed(chunk):
            yield validate_prediction(value)
    for value in decoder.finish():
        yield validate_prediction(value)


def _control_copy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError("Expected control object")
    try:
        raw = json.dumps(dict(value), ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > _MAX_CONTROL_BYTES:
            raise ProtocolError("Control byte limit exceeded")
        result = _loads(raw)
    except ProtocolError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ProtocolError("Invalid control JSON") from error
    return result


def validate_control(value: Any, *, allowed_actions: Iterable[str] | None = None
                     ) -> dict[str, Any]:
    """Validate a bounded 1.1 discovery/metadata envelope; does not authorize it.

    A narrower per-connection action set may be supplied. It can never enable
    instruction calls, play_speech, cancellation or other P0 unsupported actions.
    No data payload is passed to any executor by this module.
    """
    result = _control_copy(value)
    expected = {"protocol", "version", "message", "action", "code", "data"}
    if set(result) != expected:
        raise ProtocolError("Invalid control fields")
    if result["protocol"] != PROTOCOL or result["version"] != VERSION:
        raise ProtocolError("Unsupported control protocol or version")
    permitted = READ_ONLY_ACTIONS
    if allowed_actions is not None:
        try:
            permitted = permitted.intersection(allowed_actions)
        except TypeError as error:
            raise ProtocolError("Invalid allowed action set") from error
    action = result["action"]
    if not isinstance(action, str) or action not in permitted:
        raise ProtocolError("Unsupported control action")
    _text(result["message"], "control message", allow_empty=True, max_chars=1000)
    if type(result["code"]) is not int or not -2147483648 <= result["code"] <= 2147483647:
        raise ProtocolError("Invalid control status")
    if not isinstance(result["data"], (dict, list, type(None))):
        raise ProtocolError("Invalid metadata payload")
    return result


def build_control(action: str, data: Any = None, *, message: str = "",
                  code: int = 0) -> dict[str, Any]:
    return validate_control({"protocol": PROTOCOL, "version": VERSION,
                             "message": message, "action": action,
                             "code": code, "data": data})


def compatibility_report() -> dict[str, Any]:
    """Honest adapter capabilities, not an upstream deployment health check."""
    return {
        "transport_io": False,
        "core_llm_ndjson": "fixture-tested framing; provider semantics unverified",
        "control_protocol": VERSION,
        "control_actions": sorted(READ_ONLY_ACTIONS),
        "generation_cancel_relay": False,
        "tool_execution": False,
        "tts": "not implemented; requires author fork zerolan/zerolan_api.py",
        "upstream_runtime_tested": False,
    }
