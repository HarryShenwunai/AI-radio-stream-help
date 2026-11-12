"""Real loopback HTTP/WebSocket protocol tests; no platform accounts or sends."""
import asyncio
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import struct
import sys
import tempfile
import time
import types
import unittest
from uuid import uuid4
import wave
import zlib

from companion_runtime.connectors import BiliOpenLive, OpenLiveCredentials, WechatBridge, ConnectorError
from companion_runtime.connectors.bilibili import HEADER, MAX_FRAME, decode_packets, packet, signed_request, validate_url
from companion_runtime.live import LiveBinding, LiveIngress


def wav_bytes():
    data=io.BytesIO()
    with wave.open(data,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\0\0'*240)
    return data.getvalue()


def plugin_module():
    """AstrBot API shim is explicit; no real SDK/account is loaded."""
    names=['astrbot','astrbot.api','astrbot.api.event','astrbot.api.star','astrbot.api.message_components']
    modules={name:types.ModuleType(name) for name in names}
    class Star:
        def __init__(self,context):self.context=context
    class Chain:
        def __init__(self,chain):self.chain=chain
    class Plain:
        def __init__(self,text):self.text=text
    class File:
        def __init__(self,**kwargs):self.__dict__.update(kwargs)
    event=modules['astrbot.api.event'];event.AstrMessageEvent=object;event.MessageChain=Chain
    event.filter=types.SimpleNamespace(event_message_type=lambda *_:lambda x:x,EventMessageType=types.SimpleNamespace(PRIVATE_MESSAGE=1))
    star=modules['astrbot.api.star'];star.Context=object;star.Star=Star;star.register=lambda *_:lambda x:x
    comp=modules['astrbot.api.message_components'];comp.Plain=Plain;comp.File=File
    modules['astrbot.api'].message_components=comp
    old={name:sys.modules.get(name) for name in names}
    try:
        sys.modules.update(modules)
        path=Path(__file__).resolve().parents[1]/'plugins/astrbot_companion_bridge/main.py'
        spec=importlib.util.spec_from_file_location('tested_astrbot_plugin',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    finally:
        for name,value in old.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value


class BinaryProtocolTests(unittest.TestCase):
    def test_split_concatenated_and_compressed_packets(self):
        raw=packet(b'{"code":0}',8)+packet('你好',5)
        self.assertEqual(decode_packets(raw),[(8,b'{"code":0}'),(5,'你好'.encode())])
        encoded=HEADER.pack(16+len(zlib.compress(raw)),16,2,5,1)+zlib.compress(raw)
        self.assertEqual(decode_packets(encoded),decode_packets(raw))

    def test_bad_length_and_truncation(self):
        for data in [b'123',HEADER.pack(15,16,1,5,1),HEADER.pack(100,16,1,5,1)+b'x']:
            with self.assertRaises(ConnectorError):decode_packets(data)

    def test_decompression_bomb_is_bounded(self):
        compressed=zlib.compress(b'x'*(MAX_FRAME+1))
        with self.assertRaisesRegex(ConnectorError,'compression_limit'):
            decode_packets(HEADER.pack(16+len(compressed),16,2,5,1)+compressed)

    def test_unsupported_version_fails_closed(self):
        with self.assertRaisesRegex(ConnectorError,'unsupported_compression'):
            decode_packets(HEADER.pack(17,16,9,5,1)+b'x')

    @unittest.skipUnless(importlib.util.find_spec('brotli'), 'optional Brotli1.2 dependency not installed')
    def test_brotli_packet_and_bomb_bounded(self):
        import brotli
        raw=packet('你好',5)
        body=brotli.compress(raw)
        self.assertEqual(decode_packets(HEADER.pack(16+len(body),16,3,5,1)+body),[(5,'你好'.encode())])
        bomb=brotli.compress(b'x'*(MAX_FRAME*8))
        with self.assertRaisesRegex(ConnectorError,'compression_limit'):
            decode_packets(HEADER.pack(16+len(bomb),16,3,5,1)+bomb)

    def test_event_count_bound(self):
        with self.assertRaisesRegex(ConnectorError,'event_limit'):
            decode_packets(packet(b'',3)*257)

    def test_credentials_not_repr(self):
        value=OpenLiveCredentials('access-secret','actual-private-secret',1,'anchor-private')
        self.assertNotIn('secret',repr(value));self.assertNotIn('anchor-private',repr(value))

    def test_ssrf_redirect_hosts_and_userinfo_rejected(self):
        for value in ['http://169.254.169.254','https://evil.example','https://live-open.biliapi.com/redirect','https://u:p@live-open.biliapi.com']:
            with self.assertRaises(ConnectorError):validate_url(value)
        for value in ['wss://chat.bilibili.com.evil.example/sub','ws://127.0.0.1:3','wss://169.254.169.254/sub']:
            with self.assertRaises(ConnectorError):validate_url(value,websocket=True)
        self.assertEqual(validate_url('wss://broadcastlv.chat.bilibili.com/sub',websocket=True),'wss://broadcastlv.chat.bilibili.com/sub')

    def test_test_override_only_literal_loopback(self):
        self.assertEqual(validate_url('http://127.0.0.1:1234',test_mode=True),'http://127.0.0.1:1234')
        with self.assertRaises(ConnectorError):validate_url('http://remote.example',test_mode=True)

    def test_public_ingress_binding_cannot_be_replaced(self):
        credentials=OpenLiveCredentials('a','b',1,'c')
        with self.assertRaises(ConnectorError):BiliOpenLive(credentials,'1',ingress=LiveIngress(LiveBinding('danmuji-bridge','1')))


class WechatPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.tick=[0.0];self.wall=[time.time()]
        self.id=str(uuid4());self.auth='Bearer '+'t'*40
        self.bridge=WechatBridge('wx:FriendMessage:owner',self.id,Path(self.temp.name),token='t'*40,capacity=2,clock=lambda:self.tick[0],wall_clock=lambda:self.wall[0])
    def tearDown(self):self.temp.cleanup()
    def payload(self,ident='a',**changes):
        return {'platform':'weixin_oc','origin':'wx:FriendMessage:owner','event_id':ident,'text':'合成消息','timestamp':self.wall[0],**changes}
    def preview(self,**changes):
        return self.bridge.preview_reply('合成回复',character_id=self.id,generation_id=str(uuid4()),**changes)
    def test_authentication_required(self):
        for auth in [None,'','Bearer '+'x'*40,'Bearer é']:
            with self.assertRaises(ConnectorError):self.bridge.ingest(self.payload(),auth)
    def test_owner_origin_and_platform_fixed(self):
        for changes in [{'origin':'wx:FriendMessage:other'},{'platform':'bilibili-open-live'}]:
            with self.assertRaises(ConnectorError):self.bridge.ingest(self.payload(**changes),self.auth)
    def test_group_origin_not_supported(self):
        with self.assertRaises(ConnectorError):WechatBridge('wx:GroupMessage:group',self.id,Path(self.temp.name))
    def test_injection_privilege_fields_rejected(self):
        payload=self.payload();payload['character_id']=str(uuid4())
        with self.assertRaises(ConnectorError):self.bridge.ingest(payload,self.auth)
    def test_dedup_capacity_and_private_binding(self):
        self.assertEqual(self.bridge.ingest(self.payload(),self.auth),'accepted')
        self.assertEqual(self.bridge.ingest(self.payload(),self.auth),'duplicate')
        self.assertEqual(self.bridge.ingest(self.payload('b'),self.auth),'accepted')
        self.assertEqual(self.bridge.ingest(self.payload('c'),self.auth),'full')
        item=self.bridge.pop_inbound();self.assertEqual(item['character_id'],self.id);self.assertNotIn('origin',item)
    def test_stale_and_nonfinite_events(self):
        self.assertEqual(self.bridge.ingest(self.payload(timestamp=self.wall[0]-121),self.auth),'expired')
        for at in [float('nan'),True,10**500]:
            with self.assertRaises(ConnectorError):self.bridge.ingest(self.payload(timestamp=at),self.auth)
    def test_multiline_text_and_control_rejection(self):
        self.assertEqual(self.bridge.ingest(self.payload(text='你好\n今天好吗'),self.auth),'accepted')
        self.assertEqual(self.bridge.pop_inbound()['text'],'你好\n今天好吗')
        for text in ['a\x00b','a\ud800b']:
            with self.assertRaises(ConnectorError):self.bridge.ingest(self.payload(text=text),self.auth)

    def test_default_preview_never_claimed(self):
        item=self.preview();self.assertEqual(item['state'],'preview');self.assertIsNone(self.bridge.claim(self.auth))
        self.assertNotIn('t'*40,json.dumps(self.bridge.status(include_previews=True)))
    def test_approve_single_claim_ack_not_delivery(self):
        item=self.preview();self.bridge.approve(item['id']);claimed=self.bridge.claim(self.auth)
        self.assertEqual(claimed['id'],item['id']);self.assertIsNone(self.bridge.claim(self.auth))
        result=self.bridge.acknowledge(item['id'],'handed_to_adapter',self.auth)
        self.assertFalse(result['delivered_verified'])
        with self.assertRaises(ConnectorError):self.bridge.approve(item['id'])
    def test_invalid_auth_token_and_empty_inbound(self):
        for token in ['',False,'x'*40+'\n']:
            with self.assertRaises(ConnectorError):WechatBridge('wx:FriendMessage:owner',self.id,Path(self.temp.name),token=token)
        with self.assertRaises(ConnectorError):self.bridge.ingest(self.payload(text='   '),self.auth)

    def test_cancel_and_expiry(self):
        item=self.preview();self.bridge.approve(item['id']);self.bridge.cancel();self.assertIsNone(self.bridge.claim(self.auth))
        self.tick[0]=121;self.assertEqual(self.bridge.status()['outbound_depth'],0)
    def test_wrong_character_and_path_id_rejected(self):
        with self.assertRaises(ConnectorError):self.bridge.preview_reply('x',character_id=str(uuid4()),generation_id=str(uuid4()))
        with self.assertRaises(ConnectorError):self.bridge.audio_bytes('../secret',self.auth)
    def test_audio_requires_claim_and_expires(self):
        ident=self.bridge.stage_audio(wav_bytes());item=self.preview(audio_id=ident)
        with self.assertRaises(ConnectorError):self.bridge.audio_bytes(ident,self.auth)
        self.bridge.approve(item['id']);self.bridge.claim(self.auth)
        self.assertEqual(self.bridge.audio_bytes(ident,self.auth),wav_bytes())
        self.tick[0]=121;self.bridge.status();self.assertFalse((Path(self.temp.name)/(ident+'.wav')).exists())
    @unittest.skipUnless(os.name=='posix','POSIX mode assertion; Windows ACL needs actual target checks')
    def test_private_audio_permissions(self):
        root=Path(self.temp.name)/'private';bridge=WechatBridge('wx:FriendMessage:owner',self.id,root,token='t'*40)
        ident=bridge.stage_audio(wav_bytes())
        self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((root/(ident+'.wav')).stat().st_mode),0o600)

    @unittest.skipUnless(os.name=='posix','symlink fixture')
    def test_audio_root_and_parent_symlink_rejected(self):
        link=Path(self.temp.name)/'link';real=Path(self.temp.name)/'real';real.mkdir();link.symlink_to(real,target_is_directory=True)
        for root in [link,link/'nested']:
            bridge=WechatBridge('wx:FriendMessage:owner',self.id,root,token='t'*40)
            with self.assertRaisesRegex(ConnectorError,'unsafe_audio_directory'):bridge.stage_audio(wav_bytes())

    def test_audio_content_tampering_rejected(self):
        ident=self.bridge.stage_audio(wav_bytes());item=self.preview(audio_id=ident);self.bridge.approve(item['id']);self.bridge.claim(self.auth)
        path=Path(self.temp.name)/(ident+'.wav');data=bytearray(path.read_bytes());data[-1]=1;path.write_bytes(data)
        with self.assertRaisesRegex(ConnectorError,'audio_changed'):self.bridge.audio_bytes(ident,self.auth)

    @unittest.skipUnless(os.name=='posix','symlink fixture')
    def test_audio_symlink_replacement_rejected(self):
        ident=self.bridge.stage_audio(wav_bytes());item=self.preview(audio_id=ident);self.bridge.approve(item['id']);self.bridge.claim(self.auth)
        path=Path(self.temp.name)/(ident+'.wav');target=Path(self.temp.name)/'other.wav';target.write_bytes(wav_bytes());path.unlink();path.symlink_to(target)
        with self.assertRaisesRegex(ConnectorError,'unsafe_audio_file'):self.bridge.audio_bytes(ident,self.auth)

    def test_cancel_cleans_pending_audio_but_keeps_claimed_until_ack(self):
        pending=self.bridge.stage_audio(wav_bytes());self.preview(audio_id=pending)
        claimed=self.bridge.stage_audio(wav_bytes());item=self.preview(audio_id=claimed);self.bridge.approve(item['id']);self.bridge.claim(self.auth)
        self.bridge.cancel()
        self.assertFalse((Path(self.temp.name)/(pending+'.wav')).exists())
        self.assertTrue((Path(self.temp.name)/(claimed+'.wav')).exists())
        self.bridge.acknowledge(item['id'],'failed_or_uncertain',self.auth)
        self.assertFalse((Path(self.temp.name)/(claimed+'.wav')).exists())

    def test_close_revokes_bridge_and_removes_local_claimed_assets(self):
        ident=self.bridge.stage_audio(wav_bytes());item=self.preview(audio_id=ident);self.bridge.approve(item['id']);self.bridge.claim(self.auth)
        self.bridge.close();self.bridge.close()
        self.assertFalse((Path(self.temp.name)/(ident+'.wav')).exists())
        self.assertTrue(self.bridge.status()['closed'])
        with self.assertRaisesRegex(ConnectorError,'bridge_closed'):self.bridge.claim(self.auth)
        with self.assertRaisesRegex(ConnectorError,'bridge_closed'):self.preview()

    def test_restart_sweeps_only_old_uuid_wav_orphans(self):
        old=Path(self.temp.name)/(str(uuid4())+'.wav');old.write_bytes(wav_bytes());os.utime(old,(self.wall[0]-130,self.wall[0]-130))
        young=Path(self.temp.name)/(str(uuid4())+'.wav');young.write_bytes(wav_bytes())
        unrelated=Path(self.temp.name)/'keep.txt';unrelated.write_text('keep')
        self.assertEqual(self.bridge.status()['counts']['orphan_audio_removed'],1)
        self.assertFalse(old.exists());self.assertTrue(young.exists());self.assertTrue(unrelated.exists())

    def test_invalid_audio_and_bounded_previews(self):
        with self.assertRaises(ConnectorError):self.bridge.stage_audio(b'http://evil.example/audio.wav')
        self.preview();self.preview()
        with self.assertRaisesRegex(ConnectorError,'full'):self.preview()


@unittest.skipUnless(importlib.util.find_spec('aiohttp'), 'optional aiohttp connector dependency is not installed')
class ConnectorLoopbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import web
        self.web=web;self.runners=[]
    async def asyncTearDown(self):
        for runner in self.runners:await runner.cleanup()
    async def serve(self,app):
        runner=self.web.AppRunner(app);await runner.setup();self.runners.append(runner)
        site=self.web.TCPSite(runner,'127.0.0.1',0);await site.start();return 'http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])

    async def test_openlive_actual_http_hmac_ws_auth_reconnect_dedup_heartbeats(self):
        app=self.web.Application();calls=[];ws_count=[0];base=[''];stop=asyncio.Event()
        cred=OpenLiveCredentials('local-key','local-secret',1,'local-code')
        async def api(request):
            body=await request.read();headers=request.headers
            material='\n'.join(f'{k}:{headers[k]}' for k in sorted(k for k in headers if k.lower().startswith('x-bili-')))
            # Header dictionary case differs in HTTP; canonical keys are lowercase.
            material='\n'.join(f'{k.lower()}:{headers[k]}' for k in sorted((k for k in headers if k.lower().startswith('x-bili-')),key=str.lower))
            self.assertEqual(headers['Authorization'],hmac.new(b'local-secret',material.encode(),hashlib.sha256).hexdigest())
            self.assertEqual(headers['x-bili-content-md5'],hashlib.md5(body).hexdigest())
            calls.append(request.match_info['action'])
            data={'game_info':{'game_id':'test-game'},'anchor_info':{'room_id':7},'websocket_info':{'wss_link':[base[0].replace('http:','ws:')+'/ws'],'auth_body':'{"key":"local-token","protover":3}'}} if calls[-1]=='start' else {}
            return self.web.json_response({'code':0,'data':data})
        async def websocket(request):
            ws=self.web.WebSocketResponse();await ws.prepare(request);ws_count[0]+=1
            auth=decode_packets((await ws.receive()).data);self.assertEqual(auth[0][0],7)
            self.assertEqual(auth[0][1], b'{"key":"local-token","protover":3}')
            await ws.send_bytes(packet('{"code":0}',8))
            def event(ident,room=7):return packet(json.dumps({'cmd':'LIVE_OPEN_PLATFORM_DM','data':{'room_id':room,'msg_id':ident,'msg':'合成弹幕','timestamp':int(time.time()),'open_id':'viewer'}}),5)
            await ws.send_bytes(event('same'))
            if ws_count[0]==1:
                await ws.close();return ws
            packed=zlib.compress(event('same')+event('second')+event('wrong',8))
            await ws.send_bytes(HEADER.pack(16+len(packed),16,2,5,1)+packed)
            async for message in ws:
                if message.type.name=='BINARY':self.assertEqual(decode_packets(message.data)[0][0],2)
            return ws
        app.router.add_post('/v2/app/{action}',api);app.router.add_get('/ws',websocket);base[0]=await self.serve(app)
        client=BiliOpenLive(cred,'7',api_base=base[0],test_mode=True,heartbeat_seconds=.05,websocket_heartbeat_seconds=.05,reconnect_initial=.01,reconnect_max=.02)
        task=asyncio.create_task(client.run(stop))
        try:
            for _ in range(200):
                if client.status()['counts'].get('project_heartbeats',0)>0 and client.status()['counts'].get('accepted',0)==2:break
                await asyncio.sleep(.01)
            else:self.fail(client.status())
        finally:
            stop.set();await asyncio.wait_for(task,3)
        status=client.status();self.assertGreaterEqual(ws_count[0],2);self.assertGreaterEqual(status['counts']['duplicate'],1)
        self.assertEqual(status['counts']['wrong_room'],1);self.assertIn('heartbeat',calls);self.assertEqual(calls.count('start'),calls.count('end'))
        self.assertEqual([client.ingress.pop().event_id,client.ingress.pop().event_id],['same','second'])
        self.assertNotIn('local-secret',json.dumps(status));self.assertFalse(status['outbound_supported'])

    async def test_astrbot_bridge_actual_http_owner_bound_preview_audio_file(self):
        module=plugin_module();temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        bridge=WechatBridge('wx:FriendMessage:owner',str(uuid4()),Path(temp.name),token='t'*40)
        app=self.web.Application()
        async def route(request):
            auth=request.headers.get('Authorization');action=request.match_info['action']
            if action=='inbound':return self.web.json_response({'status':bridge.ingest(await request.json(),auth)})
            if action=='claim':return self.web.json_response({'item':bridge.claim(auth)})
            if action=='ack':
                d=await request.json();return self.web.json_response(bridge.acknowledge(d['id'],d['status'],auth))
        async def audio(request):return self.web.Response(body=bridge.audio_bytes(request.match_info['id'],request.headers.get('Authorization')),content_type='audio/wav')
        app.router.add_post('/api/connectors/wechat/{action}',route);app.router.add_get('/api/connectors/wechat/audio/{id}',audio)
        base=await self.serve(app);client=module.LocalBridgeClient(base,'t'*40)
        result=await client.inbound({'platform':'weixin_oc','origin':'wx:FriendMessage:owner','event_id':'evt','text':'合成输入','timestamp':time.time()})
        self.assertEqual(result['status'],'accepted');self.assertEqual(bridge.pop_inbound()['text'],'合成输入')
        ident=bridge.stage_audio(wav_bytes());preview=bridge.preview_reply('合成回复',character_id=bridge.character_id,generation_id=str(uuid4()),audio_id=ident)
        self.assertIsNone((await client.claim())['item']);bridge.approve(preview['id'])
        item=(await client.claim())['item'];captured=[]
        class Context:
            async def send_message(self,origin,chain):
                captured.append((origin,chain));self.assertion=None
                self.audio=Path(chain.chain[-1].file).read_bytes()
        context=Context();plugin=module.CompanionOwnerBridge(context,{'owner_origin':'wx:FriendMessage:owner','bridge_url':base,'bridge_token':'t'*40})
        await plugin.initialize();self.assertIsNone(plugin.worker) # default sends disabled
        await plugin._send_one(item) # synthetic Context only, no platform network
        self.assertEqual(captured[0][0],'wx:FriendMessage:owner');self.assertEqual(context.audio,wav_bytes())
        self.assertEqual(captured[0][1].chain[-1].name,'陪伴语音.wav')
        self.assertEqual(bridge.status(include_previews=True)['previews'][0]['state'],'handed_to_adapter')
        self.assertFalse(bridge.status()['outbound_native_voice']);self.assertIsNone((await client.claim())['item'])

    async def test_plugin_rejects_remote_endpoints(self):
        module=plugin_module()
        for url in ['https://example.com','http://localhost:80','http://127.0.0.1:80/evil','http://u:p@127.0.0.1:80']:
            with self.assertRaises(ValueError):module.LocalBridgeClient(url,'t'*40)
