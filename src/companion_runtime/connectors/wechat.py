"""Owner-bound private AstrBot bridge; distinct from public LiveIngress.

No account SDK, credentials, network destinations or recipient selection reach
models. The app's owner-authenticated HTTP layer alone may call approve(). A
separate random plugin token authenticates ingress/poll/audio/ack, never approval.
"""
from __future__ import annotations
from collections import OrderedDict, deque
import hashlib
import hmac
import io
import math
import os
import stat
import re
from pathlib import Path
import secrets
import threading
import time
from uuid import UUID, uuid4
import wave

from .bilibili import ConnectorError, _text


def _message(value, limit):
    if not isinstance(value,str) or not 1 <= len(value) <= limit or not value.strip():
        raise ConnectorError('invalid_text')
    try:value.encode('utf-8')
    except UnicodeError:raise ConnectorError('invalid_text') from None
    if any((ord(c)<32 and c not in '\n\t') or ord(c)==127 for c in value):
        raise ConnectorError('invalid_text')
    return value


def canonical_id(value):
    if not isinstance(value, str):
        raise ConnectorError('invalid_id')
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ConnectorError('invalid_id') from None
    return value


class WechatBridge:
    def __init__(self, owner_origin: str, character_id: str, audio_root: Path, *,
                 token: str | None = None, capacity=64, ttl_seconds=120.0,
                 clock=time.monotonic, wall_clock=time.time):
        self._origin = _text(owner_origin, 512)
        # Actual weixin_oc adapter IDs may be owner-chosen; require a private
        # FriendMessage origin, not GroupMessage or an inferred recipient.
        if ':FriendMessage:' not in owner_origin or owner_origin.count(':FriendMessage:') != 1:
            raise ConnectorError('private_origin_required')
        self.character_id = canonical_id(character_id)
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ConnectorError('invalid_capacity')
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int,float)) or not math.isfinite(ttl_seconds) or not 1 <= ttl_seconds <= 3600:
            raise ConnectorError('invalid_ttl')
        self._token = secrets.token_urlsafe(32) if token is None else token
        if not isinstance(self._token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', self._token):
            raise ConnectorError('invalid_token')
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._clock, self._wall = clock, wall_clock
        self._incoming = deque()
        self._seen = OrderedDict()
        self._outgoing = OrderedDict()
        self._audio = OrderedDict()
        self._audio_root = Path(audio_root)
        self._lock = threading.RLock()
        self._counts = {'accepted': 0, 'duplicate': 0, 'full': 0, 'expired': 0, 'orphan_audio_removed': 0}
        self._closed = False
        self._last_orphan_sweep = float('-inf')
        self._orphan_limit_hit = False

    @property
    def pairing_token(self):
        """Owner-only pairing API; never include this property in normal state."""
        return self._token

    def _ensure_open(self):
        if self._closed:raise ConnectorError('bridge_closed')

    def authenticate(self, authorization):
        self._ensure_open()
        if not isinstance(authorization, str) or not authorization.isascii() or not hmac.compare_digest(authorization, 'Bearer ' + self._token):
            raise ConnectorError('unauthorized_bridge')

    def _purge(self):
        if self._closed:return
        now = self._clock()
        self._incoming = deque(x for x in self._incoming if x['expires_at'] > now)
        for collection in (self._seen, self._outgoing, self._audio):
            for key, value in list(collection.items()):
                until = value if collection is self._seen else value['expires_at']
                if until <= now:
                    del collection[key]
                    if collection is self._audio:
                        self._secure_audio_root()
                        self._audio_path(key).unlink(missing_ok=True)
        if now-self._last_orphan_sweep >= min(self._ttl,30):
            self._sweep_orphans()
            self._last_orphan_sweep = now

    def _sweep_orphans(self):
        if not self._audio_root.exists():return
        self._secure_audio_root()
        self._orphan_limit_hit=False
        with os.scandir(self._audio_root) as entries:
            for index,entry in enumerate(entries):
                if index >= 4096:
                    self._orphan_limit_hit=True
                    break
                if not entry.name.endswith('.wav'):continue
                ident=entry.name[:-4]
                try:canonical_id(ident)
                except ConnectorError:continue
                if ident in self._audio or not entry.is_file(follow_symlinks=False):continue
                if entry.stat(follow_symlinks=False).st_mtime <= self._wall()-self._ttl:
                    Path(entry.path).unlink(missing_ok=True)
                    self._counts['orphan_audio_removed'] += 1

    def close(self):
        """Revoke this bridge and remove local assets; cannot recall external sends."""
        with self._lock:
            if self._closed:return
            if self._audio:
                self._secure_audio_root()
                for ident in list(self._audio):self._audio_path(ident).unlink(missing_ok=True)
            self._audio.clear();self._incoming.clear();self._outgoing.clear();self._seen.clear()
            self._closed=True

    def ingest(self, payload, authorization):
        self.authenticate(authorization)
        if not isinstance(payload, dict) or set(payload) != {'platform', 'origin', 'event_id', 'text', 'timestamp'}:
            raise ConnectorError('invalid_inbound')
        if payload['platform'] != 'weixin_oc' or payload['origin'] != self._origin:
            raise ConnectorError('wrong_origin')
        event_id = _text(payload['event_id'], 160)
        text = _message(payload['text'], 1200)
        if not text.strip():
            raise ConnectorError('empty_text')
        at = payload['timestamp']
        if isinstance(at, bool) or not isinstance(at, (int,float)):
            raise ConnectorError('invalid_timestamp')
        try:
            valid = math.isfinite(at) and 0 <= at <= self._wall()+5
        except (OverflowError,ValueError):
            valid = False
        if not valid:
            raise ConnectorError('invalid_timestamp')
        with self._lock:
            self._purge()
            if self._wall()-at >= self._ttl:
                self._counts['expired'] += 1
                return 'expired'
            key = hashlib.sha256((self._origin+'\0'+event_id).encode()).hexdigest()
            if key in self._seen:
                self._counts['duplicate'] += 1
                return 'duplicate'
            if len(self._incoming) >= self._capacity or len(self._seen) >= self._capacity*16:
                self._counts['full'] += 1
                return 'full'
            now = self._clock()
            self._incoming.append({'event_id': event_id, 'text': text, 'character_id': self.character_id,
                                   'source': 'weixin_oc', 'received_at': now,
                                   'expires_at': now+self._ttl-max(0,self._wall()-at)})
            self._seen[key] = now+self._ttl
            self._counts['accepted'] += 1
            return 'accepted'

    def pop_inbound(self):
        with self._lock:
            self._purge()
            return dict(self._incoming.popleft()) if self._incoming else None

    @staticmethod
    def _validate_audio(audio):
        if not isinstance(audio, bytes) or not 44 <= len(audio) <= 8*1024*1024:
            raise ConnectorError('invalid_audio')
        try:
            with wave.open(io.BytesIO(audio)) as wav:
                if wav.getcomptype() != 'NONE' or wav.getnchannels() not in (1,2) or wav.getsampwidth() != 2 or not 8000 <= wav.getframerate() <= 48000:
                    raise ConnectorError('invalid_audio')
                if wav.getnframes()/wav.getframerate() > 120:
                    raise ConnectorError('audio_too_long')
                if len(wav.readframes(wav.getnframes())) != wav.getnframes()*wav.getnchannels()*2:
                    raise ConnectorError('truncated_audio')
        except (wave.Error, EOFError):
            raise ConnectorError('invalid_audio') from None

    def _secure_audio_root(self):
        # Do not resolve first: that would erase evidence of a symlink supplied
        # as the storage directory or one of its existing parent components.
        for path in (self._audio_root, *self._audio_root.parents):
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise ConnectorError('unsafe_audio_directory')
        self._audio_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=self._audio_root.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ConnectorError('unsafe_audio_directory')
        if os.name=='posix':
            os.chmod(self._audio_root,0o700,follow_symlinks=False)

    def stage_audio(self, audio: bytes):
        """Accept generated PCM WAV bytes, never a URL/path; private local files."""
        self._validate_audio(audio)
        with self._lock:
            self._ensure_open()
            self._purge()
            if self._orphan_limit_hit:raise ConnectorError('audio_directory_limit')
            if len(self._audio) >= self._capacity:
                raise ConnectorError('full')
            self._secure_audio_root()
            ident = str(uuid4())
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
            descriptor=os.open(self._audio_path(ident),flags,0o600)
            try:
                if os.name=='posix':os.fchmod(descriptor,0o600)
                with os.fdopen(descriptor,'wb') as output:
                    descriptor=None
                    output.write(audio)
            finally:
                if descriptor is not None:os.close(descriptor)
            self._audio[ident] = {'expires_at': self._clock()+self._ttl,
                                  'sha256':hashlib.sha256(audio).hexdigest(),'size':len(audio)}
            return ident

    def _delete_unreferenced_audio(self, candidates):
        retained={x['audio_id'] for x in self._outgoing.values() if x['state'] in {'preview','approved','claimed'}}
        for ident in candidates:
            if ident in self._audio and ident not in retained:
                self._secure_audio_root()
                self._audio_path(ident).unlink(missing_ok=True)
                del self._audio[ident]

    def _audio_path(self, ident):
        return self._audio_root / (canonical_id(ident)+'.wav')

    def preview_reply(self, text, *, character_id, generation_id, audio_id=None):
        if canonical_id(character_id) != self.character_id:
            raise ConnectorError('wrong_character')
        canonical_id(generation_id)
        if not isinstance(text,str):
            raise ConnectorError('invalid_text')
        if text:
            _message(text, 1600)
        elif audio_id is None:
            raise ConnectorError('empty_reply')
        with self._lock:
            self._ensure_open()
            self._purge()
            if audio_id is not None and canonical_id(audio_id) not in self._audio:
                raise ConnectorError('unknown_audio')
            if len(self._outgoing) >= self._capacity:
                raise ConnectorError('full')
            ident = str(uuid4())
            item = {'id': ident, 'character_id': self.character_id, 'generation_id': generation_id,
                    'text': text, 'audio_id': audio_id, 'audio_kind': 'file' if audio_id else None,
                    'state': 'preview', 'expires_at': self._clock()+self._ttl}
            self._outgoing[ident] = item
            return dict(item)

    def approve(self, ident):
        """Trusted owner UI only. Plugin transport token must NOT expose this."""
        with self._lock:
            self._ensure_open()
            self._purge()
            item = self._outgoing.get(canonical_id(ident))
            if item is None or item['state'] != 'preview':
                raise ConnectorError('not_approvable')
            item['state'] = 'approved'
            return dict(item)

    def cancel(self, *, generation_id=None):
        with self._lock:
            candidates=set()
            for item in self._outgoing.values():
                if (generation_id is None or item['generation_id'] == generation_id) and item['state'] in {'preview','approved'}:
                    item['state'] = 'cancelled'
                    candidates.add(item['audio_id'])
            self._delete_unreferenced_audio(candidates)

    def claim(self, authorization):
        self.authenticate(authorization)
        with self._lock:
            self._purge()
            for item in self._outgoing.values():
                if item['state'] == 'approved':
                    item['state'] = 'claimed'  # No automatic replay after an ambiguous network/send result.
                    return dict(item)
            return None

    def audio_bytes(self, ident, authorization):
        self.authenticate(authorization)
        with self._lock:
            self._purge()
            canonical_id(ident)
            if ident not in self._audio or not any(x['audio_id']==ident and x['state']=='claimed' for x in self._outgoing.values()):
                raise ConnectorError('audio_not_claimed')
            self._secure_audio_root()
            flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
            try:
                path=self._audio_path(ident)
                if path.is_symlink():raise ConnectorError('unsafe_audio_file')
                descriptor=os.open(path,flags)
                with os.fdopen(descriptor,'rb') as file:
                    info=os.fstat(file.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size != self._audio[ident]['size']:
                        raise ConnectorError('unsafe_audio_file')
                    if os.name=='posix':os.fchmod(file.fileno(),0o600)
                    audio=file.read(8*1024*1024+1)
            except OSError:
                raise ConnectorError('unsafe_audio_file') from None
            if hashlib.sha256(audio).hexdigest() != self._audio[ident]['sha256']:
                raise ConnectorError('audio_changed')
            self._validate_audio(audio)
            return audio

    def acknowledge(self, ident, status, authorization):
        self.authenticate(authorization)
        if status not in {'handed_to_adapter','failed_or_uncertain'}:
            raise ConnectorError('invalid_ack')
        with self._lock:
            self._ensure_open()
            self._purge()
            item = self._outgoing.get(canonical_id(ident))
            if item is None or item['state'] != 'claimed':
                raise ConnectorError('not_claimed')
            item['state'] = status
            self._delete_unreferenced_audio({item['audio_id']})
            return {'id': ident, 'state': status, 'delivered_verified': False}

    def status(self, *, include_previews=False):
        with self._lock:
            self._purge()
            result = {'platform': 'weixin_oc', 'closed': self._closed, 'orphan_directory_limit': self._orphan_limit_hit, 'character_id': self.character_id,
                      'inbound_text': True, 'inbound_native_audio': False,
                      'outbound_text': True, 'outbound_native_voice': False,
                      'outbound_audio_file': True, 'default_mode': 'preview',
                      'account_verified': False, 'delivered_verified': False,
                      'queue_depth': len(self._incoming), 'outbound_depth': len(self._outgoing),
                      'counts': dict(self._counts)}
            if include_previews:
                result['previews'] = [dict(x) for x in self._outgoing.values()]
            return result
