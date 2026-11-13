"""Typed serialization boundary shared by API values and opaque asset bytes."""
from __future__ import annotations

import json
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list['JsonValue'] | dict[str, 'JsonValue']
HttpPayload: TypeAlias = JsonValue | bytes | bytearray


def encode_http_body(value: HttpPayload, content_type: str) -> bytes:
    # Model JSON is already serialized and must remain byte-for-byte intact.
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if content_type.startswith('application/json'):
        return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if isinstance(value, str):
        return value.encode('utf-8')
    raise TypeError('A non-JSON response requires bytes or text')
