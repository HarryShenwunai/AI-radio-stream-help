"""Read-only Bilibili OpenLive client; no chat-send or model/tool access.

Wire contract: official OpenLive C# sample and previously inspected blivedm.
Credentials are owner configuration, never model arguments. aiohttp is optional.
"""
from __future__ import annotations
import asyncio
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import hmac
import ipaddress
import json
import math
import struct
import time
from urllib.parse import urlsplit
from uuid import uuid4
import zlib

from ..live import LiveBinding, LiveIngress

API = 'https://live-open.biliapi.com'
HEADER = struct.Struct('>IHHII')
MAX_FRAME = 262144
MAX_EVENTS = 256

class ConnectorError(ValueError):
    """Fixed diagnostic codes never include credentials or upstream bodies."""


def _text(value, limit=256):
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise ConnectorError('invalid_config')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ConnectorError('invalid_config') from None
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConnectorError('invalid_config')
    return value


def _loopback(parts):
    try:
        return ipaddress.ip_address(parts.hostname or '').is_loopback
    except ValueError:
        return False


def validate_url(value, *, websocket=False, test_mode=False):
    p = urlsplit(_text(value, 2048))
    if p.username or p.password or p.fragment:
        raise ConnectorError('untrusted_endpoint')
    try:
        port = p.port
    except ValueError:
        raise ConnectorError('untrusted_endpoint') from None
    if test_mode and _loopback(p) and p.scheme == ('ws' if websocket else 'http'):
        return value
    if port not in (None, 443):
        raise ConnectorError('untrusted_endpoint')
    if websocket:
        host = (p.hostname or '').lower()
        if p.scheme != 'wss' or not (host == 'chat.bilibili.com' or host.endswith('.chat.bilibili.com')):
            raise ConnectorError('untrusted_endpoint')
    elif value != API:
        raise ConnectorError('untrusted_endpoint')
    return value


@dataclass(frozen=True)
class OpenLiveCredentials:
    access_key_id: str = field(repr=False)
    access_key_secret: str = field(repr=False)
    app_id: int
    anchor_code: str = field(repr=False)

    def __post_init__(self):
        for value in (self.access_key_id, self.access_key_secret, self.anchor_code):
            _text(value)
        if type(self.app_id) is not int or not 1 <= self.app_id <= 2**63 - 1:
            raise ConnectorError('invalid_app_id')


def signed_request(credentials, body, *, timestamp=None, nonce=None):
    """Sign exactly the bytes sent; header order is the official sorted order."""
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    headers = {
        'x-bili-accesskeyid': credentials.access_key_id,
        'x-bili-content-md5': hashlib.md5(raw).hexdigest(),
        'x-bili-signature-method': 'HMAC-SHA256',
        'x-bili-signature-nonce': nonce or uuid4().hex,
        'x-bili-signature-version': '1.0',
        'x-bili-timestamp': str(int(time.time()) if timestamp is None else timestamp),
    }
    material = '\n'.join(f'{k}:{v}' for k, v in sorted(headers.items()))
    headers['Authorization'] = hmac.new(credentials.access_key_secret.encode(), material.encode(), hashlib.sha256).hexdigest()
    headers['Content-Type'] = 'application/json'
    return raw, headers


def packet(body, operation):
    body = body.encode() if isinstance(body, str) else body
    if len(body) > MAX_FRAME - HEADER.size:
        raise ConnectorError('oversized_packet')
    return HEADER.pack(HEADER.size + len(body), HEADER.size, 1, operation, 1) + body


def decode_packets(raw, *, depth=0):
    """Bounded Bili binary frames, concatenation and zlib nesting.

    Brotli uses the official 1.2+ bounded streaming API. No unbounded decoder
    fallback is permitted; missing/old optional dependencies fail closed.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_FRAME or depth > 2:
        raise ConnectorError('invalid_frame')
    result = []
    offset = 0
    while offset < len(raw):
        if len(raw) - offset < HEADER.size:
            raise ConnectorError('truncated_frame')
        size, head, version, op, _ = HEADER.unpack_from(raw, offset)
        if head != HEADER.size or size < head or size > len(raw) - offset:
            raise ConnectorError('invalid_frame')
        body = raw[offset + head:offset + size]
        if version == 2:
            decoder = zlib.decompressobj()
            try:
                unpacked = decoder.decompress(body, MAX_FRAME + 1)
            except zlib.error:
                raise ConnectorError('invalid_compression') from None
            if len(unpacked) > MAX_FRAME or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
                raise ConnectorError('compression_limit')
            result.extend(decode_packets(unpacked, depth=depth+1))
        elif version == 3:
            try:
                import brotli
                decoder = brotli.Decompressor()
                unpacked = decoder.process(body, output_buffer_limit=MAX_FRAME+1)
            except ImportError:
                raise ConnectorError('brotli_dependency_missing') from None
            except TypeError:
                raise ConnectorError('bounded_brotli_required') from None
            except Exception:
                raise ConnectorError('invalid_compression') from None
            if len(unpacked) > MAX_FRAME or not decoder.is_finished() or not decoder.can_accept_more_data():
                raise ConnectorError('compression_limit')
            result.extend(decode_packets(unpacked, depth=depth+1))
        elif version in (0, 1):
            result.append((op, body))
        else:
            raise ConnectorError('unsupported_compression')
        if len(result) > MAX_EVENTS:
            raise ConnectorError('event_limit')
        offset += size
    return result


class BiliOpenLive:
    """One explicitly configured room. Output is PublicEvent only.

    run() owns its networking; stop via asyncio.Event. No account login, public
    posting, OBS output, private conversation callbacks or arbitrary URLs exist.
    test_mode only permits literal loopback mock endpoints, never remote HTTP.
    """
    def __init__(self, credentials: OpenLiveCredentials, room_id: str, *,
                 ingress: LiveIngress | None = None, api_base=API, test_mode=False,
                 heartbeat_seconds=20.0, websocket_heartbeat_seconds=30.0,
                 reconnect_initial=1.0, reconnect_max=30.0):
        if not isinstance(credentials, OpenLiveCredentials):
            raise ConnectorError('trusted_credentials_required')
        binding = LiveBinding('bilibili-open-live', room_id)
        if ingress is not None and ingress.binding != binding:
            raise ConnectorError('wrong_ingress_binding')
        for n in (heartbeat_seconds, websocket_heartbeat_seconds, reconnect_initial, reconnect_max):
            if isinstance(n, bool) or not isinstance(n, (int,float)) or not math.isfinite(n) or n <= 0:
                raise ConnectorError('invalid_interval')
        self.ingress = ingress or LiveIngress(binding)
        self._credentials = credentials
        self._api = validate_url(api_base, test_mode=test_mode)
        self._test = test_mode
        self._heartbeat = heartbeat_seconds
        self._ws_heartbeat = websocket_heartbeat_seconds
        self._retry_initial = reconnect_initial
        self._retry_max = reconnect_max
        self._running = False
        self._state = 'stopped'
        self._error = None
        self._counts = Counter()

    def status(self):
        return {'state': self._state, 'last_error': self._error,
                'room_id': self.ingress.binding.room_id, 'source': 'bilibili-open-live',
                'mode': 'local_preview_only', 'outbound_supported': False,
                'compression': 'raw/zlib/bounded Brotli1.2; auth body preserved',
                'account_verified': False, 'counts': dict(self._counts), 'queue': self.ingress.snapshot()}

    async def _request(self, session, action, data):
        raw, headers = signed_request(self._credentials, data)
        async with session.post(self._api + '/v2/app/' + action, data=raw, headers=headers,
                                allow_redirects=False) as response:
            if response.status != 200:
                raise ConnectorError('upstream_http_error')
            chunks = []; length = 0
            async for chunk in response.content.iter_chunked(16384):
                length += len(chunk)
                if length > MAX_FRAME:
                    raise ConnectorError('oversized_response')
                chunks.append(chunk)
            body = b''.join(chunks)
            try:
                result = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                raise ConnectorError('invalid_response') from None
            if not isinstance(result, dict) or type(result.get('code')) is not int or result['code'] != 0:
                raise ConnectorError('upstream_rejected')
            return result.get('data')

    def _ingest(self, body):
        try:
            value = json.loads(body)
            if not isinstance(value, dict) or value.get('cmd') != 'LIVE_OPEN_PLATFORM_DM':
                self._counts['ignored'] += 1
                return
            data = value['data']
            payload = {'room_id': str(data['room_id']), 'event_id': data['msg_id'],
                       'text': data['msg'], 'event_at': data['timestamp'],
                       'actor_key': data.get('open_id')}
            state = self.ingress.submit(payload)
            self._counts[state] += 1
        except (ValueError, TypeError, KeyError, RecursionError):
            self._counts['invalid_event'] += 1

    async def _connection(self, session, stop):
        game = None
        try:
            self._state = 'starting'
            data = await self._request(session, 'start', {'code': self._credentials.anchor_code, 'app_id': self._credentials.app_id})
            game = _text(data['game_info']['game_id'])
            if str(data['anchor_info']['room_id']) != self.ingress.binding.room_id:
                raise ConnectorError('wrong_room')
            links = data['websocket_info']['wss_link']
            if not isinstance(links, list) or not 1 <= len(links) <= 8:
                raise ConnectorError('invalid_ws_links')
            url = validate_url(links[self._counts['connections'] % len(links)], websocket=True, test_mode=self._test)
            auth = data['websocket_info']['auth_body']
            if not isinstance(auth, str) or not 1 <= len(auth.encode('utf-8')) <= 65536 or not isinstance(json.loads(auth),dict):
                raise ConnectorError('invalid_auth_body')
            self._state = 'authenticating'
            async with session.ws_connect(url, max_msg_size=MAX_FRAME, autoping=True) as ws:
                self._counts['connections'] += 1
                await ws.send_bytes(packet(auth, 7))
                message = await ws.receive(timeout=10)
                if not isinstance(message.data, bytes):
                    raise ConnectorError('auth_failed')
                frames = decode_packets(message.data)
                if not frames or frames[0][0] != 8:
                    raise ConnectorError('auth_failed')
                auth_reply = json.loads(frames[0][1])
                if not isinstance(auth_reply,dict) or type(auth_reply.get('code')) is not int or auth_reply['code'] != 0:
                    raise ConnectorError('auth_failed')
                for operation, content in frames[1:]:
                    if operation == 5:
                        self._ingest(content)
                self._state = 'connected'
                self._error = None
                now = time.monotonic(); project_due = now + self._heartbeat; ws_due = now
                last_received = now
                while not stop.is_set():
                    now = time.monotonic()
                    if now >= project_due:
                        await self._request(session, 'heartbeat', {'game_id': game})
                        self._counts['project_heartbeats'] += 1
                        project_due = time.monotonic() + self._heartbeat
                    if now >= ws_due:
                        await ws.send_bytes(packet(b'', 2))
                        self._counts['ws_heartbeats'] += 1
                        ws_due = time.monotonic() + self._ws_heartbeat
                    if now - last_received > max(90, self._ws_heartbeat * 3):
                        raise ConnectorError('heartbeat_timeout')
                    try:
                        message = await ws.receive(timeout=min(.5, max(.01, project_due-now), max(.01, ws_due-now)))
                    except asyncio.TimeoutError:
                        continue
                    if not isinstance(message.data, bytes):
                        raise ConnectorError('ws_closed')
                    last_received = time.monotonic()
                    for operation, content in decode_packets(message.data):
                        if operation == 5:
                            self._ingest(content)
        finally:
            if game is not None:
                try:
                    await self._request(session, 'end', {'app_id': self._credentials.app_id, 'game_id': game})
                    self._counts['ended'] += 1
                except Exception:
                    self._counts['end_failed'] += 1

    async def run(self, stop: asyncio.Event):
        if self._running:
            raise ConnectorError('already_running')
        self._running = True
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), trust_env=False) as session:
                attempt = 0
                while not stop.is_set():
                    try:
                        await self._connection(session, stop)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        self._state = 'reconnecting'
                        self._error = str(error) if isinstance(error, ConnectorError) else 'connection_failed'
                        self._counts['reconnects'] += 1
                    if stop.is_set():
                        break
                    delay = min(self._retry_max, self._retry_initial * 2 ** min(attempt, 10))
                    attempt += 1
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
        finally:
            self._running = False
            self._state = 'stopped'
