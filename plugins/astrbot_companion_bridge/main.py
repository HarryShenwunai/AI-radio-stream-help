"""AstrBot weixin_oc owner-only bridge. Disabled sends by default.

No login/token handling for WeChat is implemented here: AstrBot owns the adapter.
Comp.File is an audio-file fallback; Comp.Record/native voice is never emitted.
"""
from __future__ import annotations
import asyncio
import json
import re
from pathlib import Path
import tempfile
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID

from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.api import message_components as Comp


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalBridgeClient:
    def __init__(self, base, token):
        p = urlsplit(base)
        if p.scheme != 'http' or p.hostname != '127.0.0.1' or p.username or p.password or p.path not in ('','/') or p.query or p.fragment or not p.port:
            raise ValueError('bridge_url must be http://127.0.0.1:PORT')
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
            raise ValueError('invalid bridge token')
        self.base, self.token = base.rstrip('/'), token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _request(self, path, payload=None, audio=False):
        # path is constructed exclusively by methods below; never model/event data.
        req = urllib.request.Request(self.base+'/api/connectors/wechat/'+path,
              data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),
              headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(req,timeout=8) as response:
            raw=response.read((8*1024*1024 if audio else 65536)+1)
        if len(raw) > (8*1024*1024 if audio else 65536):
            raise ValueError('oversized bridge response')
        return raw if audio else json.loads(raw)

    async def inbound(self, data):
        return await asyncio.to_thread(self._request,'inbound',data)

    async def claim(self):
        return await asyncio.to_thread(self._request,'claim',{})

    async def ack(self, ident, state):
        return await asyncio.to_thread(self._request,'ack',{'id':ident,'status':state})

    async def audio(self, ident):
        if not isinstance(ident,str) or str(UUID(ident)) != ident:
            raise ValueError('invalid audio id')
        return await asyncio.to_thread(self._request,'audio/'+ident,None,True)


@register('companion_owner_bridge', 'project-contributors', 'Owner-bound local companion bridge', '0.1.0')
class CompanionOwnerBridge(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.origin = self.config.get('owner_origin','')
        self.client = None
        self.worker = None
        self.last_error = None
        if self.origin and ':FriendMessage:' in self.origin:
            self.client = LocalBridgeClient(self.config.get('bridge_url','http://127.0.0.1:8765'), self.config.get('bridge_token',''))

    async def initialize(self):
        if self.client is not None and self.config.get('enable_send',False) is True:
            self.worker = asyncio.create_task(self._outbound_loop())

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def receive_owner(self, event: AstrMessageEvent):
        if self.client is None or event.get_platform_name() != 'weixin_oc' or event.unified_msg_origin != self.origin:
            return
        # Stop AstrBot's normal model pipeline for this explicitly bound owner,
        # including during a backend outage; never fall back to an unapproved send.
        event.stop_event()
        text=event.get_message_str()
        if not isinstance(text,str) or not text.strip():
            return  # Attachment URLs/paths are not fetched or passed to the model.
        try:
            await self.client.inbound({'platform':'weixin_oc','origin':self.origin,
                  'event_id':str(event.message_obj.message_id),'text':text,
                  'timestamp':event.message_obj.timestamp})
            self.last_error = None
        except Exception:
            self.last_error = 'local_bridge_unavailable'

    async def _send_one(self, item):
        path = None
        try:
            text = item.get('text','')
            if not isinstance(text,str) or len(text)>1600:
                raise ValueError('invalid reply')
            parts = [Comp.Plain(text)] if text else []
            if item.get('audio_id'):
                if item.get('audio_kind') != 'file':
                    raise ValueError('native voice unsupported')
                audio = await self.client.audio(item['audio_id'])
                if not audio.startswith(b'RIFF') or audio[8:12] != b'WAVE':
                    raise ValueError('invalid WAV')
                with tempfile.NamedTemporaryFile(suffix='.wav',delete=False) as f:
                    path=Path(f.name);f.write(audio)
                parts.append(Comp.File(file=str(path),name='陪伴语音.wav'))
            if not parts:
                raise ValueError('empty reply')
            await self.context.send_message(self.origin, MessageChain(parts))
            # This is NOT a delivery receipt. Missing/expired context can reject sending.
            await self.client.ack(item['id'],'handed_to_adapter')
        except Exception:
            self.last_error='send_failed_or_uncertain'
            try:
                await self.client.ack(item['id'],'failed_or_uncertain')
            except Exception:
                pass
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    async def _outbound_loop(self):
        backoff = 1
        while True:
            try:
                response = await self.client.claim()
                item = response.get('item')
                if item:
                    await self._send_one(item)
                self.last_error = None
                backoff=1
            except asyncio.CancelledError:
                raise
            except Exception:
                self.last_error='local_bridge_unavailable'
                backoff=min(backoff*2,30)
            await asyncio.sleep(backoff)

    async def terminate(self):
        if self.worker is not None:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
