"""Offline design reference only: no network, model, audio or tool execution."""
import json
from uuid import uuid4


class ContractError(ValueError):
    pass


def strict_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError('duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ContractError('non-finite JSON number')

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as exc:
        raise ContractError('invalid JSON object') from exc
    if not isinstance(value, dict):
        raise ContractError('object required')
    return value


class NDJSON:
    """Frame UTF-8 JSON objects on LF; bound bytes, reject incomplete EOF.

    HTTP chunks are not messages. Bytes stay buffered until a whole frame is
    available, so a UTF-8 codepoint can safely span chunks. Not an SSE parser.
    """
    def __init__(self, max_frame_bytes=65536):
        if max_frame_bytes < 1:
            raise ValueError('positive frame limit required')
        self.limit = max_frame_bytes
        self.buffer = b''
        self.closed = False

    def feed(self, chunk):
        if self.closed:
            raise ContractError('parser closed')
        if not isinstance(chunk, bytes):
            raise TypeError('bytes required')
        frames = []
        # Never copy the entire untrusted chunk into the pending-frame buffer.
        start = 0
        try:
            while start < len(chunk):
                end = chunk.find(b'\n', start)
                stop = len(chunk) if end < 0 else end
                if len(self.buffer) + stop - start > self.limit:
                    raise ContractError('frame too large')
                self.buffer += chunk[start:stop]
                if end < 0:
                    break
                line, self.buffer = self.buffer, b''
                if line.strip():
                    frames.append(strict_object(line))
                start = end + 1
        except ContractError:
            self.closed, self.buffer = True, b''
            raise
        return frames

    def finish(self):
        if self.closed:
            raise ContractError('parser closed')
        self.closed = True
        if self.buffer:
            self.buffer = b''
            raise ContractError('unterminated frame at EOF')


def llm_query(text, history):
    """Caller must provide already-authorized, channel-specific history.

    Allocate id explicitly; never trust upstream class defaults for uniqueness.
    This function deliberately does not accept a public/private event envelope.
    """
    if not isinstance(text, str) or not isinstance(history, list):
        raise ContractError('text and history required')
    sanitized = []
    for item in history:
        if (not isinstance(item, dict) or set(item) != {'role', 'content'}
                or item['role'] not in {'system', 'user', 'assistant'}
                or not isinstance(item['content'], str)):
            raise ContractError('unsupported conversation')
        sanitized.append(dict(item))
    return {'id': str(uuid4()), 'text': text, 'history': sanitized}


def llm_prediction(value):
    # Keep response opaque: delta versus cumulative semantics need a real model
    # baseline. Prediction id is not assumed equal to query id.
    if (not isinstance(value, dict) or not isinstance(value.get('id'), str)
            or not value['id'] or not isinstance(value.get('response'), str)
            or not isinstance(value.get('history'), list)):
        raise ContractError('invalid LLM prediction')
    return value['response']


def mc_hello(raw):
    """Validate a synthetic hello only. This does not authenticate an MC peer."""
    value = strict_object(raw)
    if set(value) != {'protocol', 'version', 'message', 'action', 'code', 'data'}:
        raise ContractError('unexpected envelope fields')
    if (value['protocol'] != 'ZerolanProtocol' or value['version'] != '1.1'
            or value['action'] != 'koneko.client.hello'
            or not isinstance(value['message'], str)
            or type(value['code']) is not int or value['code'] != 0
            or value['data'] != {}):
        raise ContractError('unsupported hello')
    return value
