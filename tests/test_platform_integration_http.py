"""Actual application HTTP/generation/database boundaries with local adapters.

No Bilibili account, AstrBot server, WeChat account or actual message sending.
Plugin claims/ACK are local protocol checks and never delivery evidence.
"""
import http.client
import json
import time
import threading
from types import SimpleNamespace
import unittest

import test_character_http as character_http
from companion_runtime.live import LiveBinding, LiveIngress


class PlatformIntegrationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=character_http.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
        self.fixture.setUp();self.origin='qa:FriendMessage:owned-test-conversation';self.token=None

    def tearDown(self):
        f=self.fixture;f.app.STOP.set()
        for service in list(f.app.INTEGRATIONS.values()):service.close()
        self.fixture.tearDown()

    def plugin(self,route,payload=None,*,method='POST',token=None):
        f=self.fixture;connection=http.client.HTTPConnection('127.0.0.1',f.server.server_port,timeout=10)
        headers={'Authorization':'Bearer '+(token or self.token or 'invalid-token'),'Content-Type':'application/json'}
        body=json.dumps(payload or {}).encode() if method=='POST' else None
        try:
            connection.request(method,'/api/'+route,body=body,headers=headers)
            response=connection.getresponse();return response.status,response.read()
        finally:connection.close()

    def configure(self,auto=False,voice=True):
        f=self.fixture
        result=f.post('connectors/wechat/configure',{'owner_origin':self.origin,'auto_approve':auto,
            'confirm_owner_auto_reply':auto,'voice':voice,'expected_character_id':f.initial_id})
        self.token=result['pairing_token'];return result

    def inbound(self,event='event-1',**changes):
        return self.plugin('connectors/wechat/inbound',{'platform':'weixin_oc','origin':self.origin,
            'event_id':event,'text':'PRIVATE_WECHAT_CANARY','timestamp':time.time(),**changes})

    def status(self):
        status,_,body=self.fixture.request('GET','/api/connectors/status');self.assertEqual(status,200,body)
        return json.loads(body)

    def preview(self):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            items=self.status()['wechat'].get('previews',[])
            if items:return items[0]
            time.sleep(.02)
        self.fail('Private application worker did not create a bounded local preview: '+str(self.status()))

    def test_pairing_token_cannot_configure_approve_read_state_or_change_role(self):
        f=self.fixture;self.configure()
        self.assertNotIn(self.token,json.dumps(self.status()))
        for route,payload in [('settings',{'personality':'unauthorized'}),('characters/create',{'name':'unauthorized'}),
            ('connectors/wechat/approve',{'id':'anything'}),('connectors/wechat/configure',{'owner_origin':self.origin})]:
            with self.subTest(route=route):self.assertIn(self.plugin(route,payload)[0],(401,403))
        self.assertIn(self.plugin('state',method='GET')[0],(401,403))
        self.assertEqual(len(f.state()['characters']),1)

    def test_private_inbound_preview_requires_owner_approval_and_ack_is_not_delivery(self):
        f=self.fixture;self.configure()
        self.assertEqual(self.inbound()[0],200);preview=self.preview()
        self.assertEqual(preview['state'],'preview');self.assertEqual(preview['audio_kind'],'file')
        self.assertIsNone(json.loads(self.plugin('connectors/wechat/claim')[1])['item'])
        f.post('connectors/wechat/approve',{'id':preview['id'],'expected_character_id':f.initial_id})
        status,body=self.plugin('connectors/wechat/claim');self.assertEqual(status,200)
        item=json.loads(body)['item'];self.assertEqual(item['id'],preview['id'])
        status,audio=self.plugin('connectors/wechat/audio/'+item['audio_id'],method='GET')
        self.assertEqual(status,200);self.assertTrue(audio.startswith(b'RIFF'))
        status,body=self.plugin('connectors/wechat/ack',{'id':item['id'],'status':'handed_to_adapter'})
        self.assertEqual(status,200);self.assertFalse(json.loads(body)['delivered_verified'])
        self.assertIsNone(json.loads(self.plugin('connectors/wechat/claim')[1])['item'])
        self.assertEqual(self.plugin('connectors/wechat/audio/'+item['audio_id'],method='GET')[0],403)
        self.assertFalse(self.status()['wechat']['outbound_native_voice'])

    def test_duplicate_or_wrong_origin_cannot_add_private_turns_or_privileges(self):
        f=self.fixture;self.configure(voice=False)
        self.assertEqual(self.inbound()[0],200);self.preview()
        code,body=self.inbound();self.assertEqual(code,200);self.assertEqual(json.loads(body)['status'],'duplicate')
        self.assertEqual(self.inbound('wrong-origin',origin='qa:FriendMessage:someone-else')[0],403)
        self.assertEqual(self.inbound('public-injection',platform='bilibili-open-live')[0],403)
        self.assertEqual(self.inbound('privilege-injection',character_id=f.initial_id)[0],403)
        self.assertEqual(len(f.model_calls),1)
        self.assertEqual(sum(m['role']=='user' and m['text']=='PRIVATE_WECHAT_CANARY' for m in f.state()['messages']),1)

    def test_switching_identity_cancels_approved_bridge_output(self):
        f=self.fixture;self.configure();self.inbound();preview=self.preview()
        f.post('connectors/wechat/approve',{'id':preview['id'],'expected_character_id':f.initial_id})
        f.create('切换后的私有身份')
        self.assertIsNone(json.loads(self.plugin('connectors/wechat/claim')[1])['item'])
        self.assertNotIn('PRIVATE_WECHAT_CANARY',str(f.state()['messages']))
        self.assertEqual(self.plugin('connectors/wechat/audio/'+preview['audio_id'],method='GET')[0],403)

    def test_repairing_revokes_old_token_and_restart_returns_to_preview(self):
        f=self.fixture;self.configure(auto=True,voice=False);old=self.token
        self.configure(auto=True,voice=False)
        self.assertNotEqual(old,self.token)
        self.assertEqual(self.plugin('connectors/wechat/claim',token=old)[0],403)
        service=f.app.integrations();service.close();f.app.INTEGRATIONS.clear()
        restored=self.status()['wechat']
        self.assertTrue(restored['configured']);self.assertFalse(restored['automatic_reply_enabled'])
        self.assertEqual(restored['previews'],[])

    def test_auto_reply_needs_explicit_confirmation_and_bili_needs_explicit_connect(self):
        f=self.fixture
        f.post('connectors/wechat/configure',{'owner_origin':self.origin,'auto_approve':True,'voice':False,
            'expected_character_id':f.initial_id},expected=400)
        f.post('connectors/bili/configure',{'access_key_id':'fake-id','access_key_secret':'fake-secret','app_id':1,
            'anchor_code':'fake-code','room_id':'123','connect':False,'expected_character_id':f.initial_id},expected=400)
        self.assertEqual(self.status()['bili']['state'],'not_connected')
        self.assertFalse(self.status()['wechat']['configured'])

    def test_public_reply_context_excludes_private_chat_memories_and_personality(self):
        f=self.fixture
        f.post('memories',{'text':'PRIVATE_MEMORY_CANARY','expected_character_id':f.initial_id})
        f.post('settings',{'personality':'PRIVATE_PERSONALITY_CANARY','expected_character_id':f.initial_id})
        f.chat('PRIVATE_CHAT_CANARY');before=len(f.state()['messages'])
        service=f.app.integrations();ingress=LiveIngress(LiveBinding('bilibili-open-live','123'))
        ingress.submit({'room_id':'123','event_id':'public-1','text':'PUBLIC_DANMAKU_CANARY'})
        service.bili=SimpleNamespace(ingress=ingress,status=lambda:{'state':'local-test-fixture','account_verified':False})
        calls=[]
        def generate_once(settings,messages,*args,**kwargs):calls.append(messages);return '公开回复夹具'
        f.app.generate_once=generate_once
        result=f.post('connectors/bili/reply',{'event_id':'public-1','expected_character_id':f.initial_id})
        serialized=json.dumps(calls,ensure_ascii=False)
        self.assertIn('PUBLIC_DANMAKU_CANARY',serialized)
        for canary in ['PRIVATE_MEMORY_CANARY','PRIVATE_PERSONALITY_CANARY','PRIVATE_CHAT_CANARY']:self.assertNotIn(canary,serialized)
        self.assertFalse(result['delivered']);self.assertEqual(result['mode'],'local_preview')
        self.assertEqual(len(f.state()['messages']),before)

    def prepare_public(self):
        f=self.fixture;service=f.app.integrations();ingress=LiveIngress(LiveBinding('bilibili-open-live','123'))
        ingress.submit({'room_id':'123','event_id':'public-blocking','text':'PUBLIC_ONLY_BLOCKING_CANARY'})
        service.bili=SimpleNamespace(ingress=ingress,status=lambda:{'state':'local-test-fixture','account_verified':False})
        return service

    def start_public_request(self):
        f=self.fixture;result=[]
        worker=threading.Thread(target=lambda:result.append(f.request('POST','/api/connectors/bili/reply',
            {'event_id':'public-blocking','expected_character_id':f.initial_id})))
        f.pending_threads.append(worker);worker.start();return worker,result

    def test_stop_rejects_uncooperative_late_public_output(self):
        f=self.fixture;service=self.prepare_public();entered,release=threading.Event(),threading.Event()
        f.pending_releases.append(release)
        def public_provider(*args,**kwargs):
            entered.set();self.assertTrue(release.wait(8));return 'LATE_PUBLIC_CANARY'
        f.app.generate_once=public_provider;worker,result=self.start_public_request();self.assertTrue(entered.wait(3))
        f.post('connectors/bili/stop',{'expected_character_id':f.initial_id})
        release.set();worker.join(4);self.assertFalse(worker.is_alive())
        self.assertEqual(result[0][0],409,result);self.assertEqual(list(service.public_replies),[])
        self.assertNotIn('LATE_PUBLIC_CANARY',str(f.state()['messages']))

    def test_private_turn_cancels_public_and_takes_over_shared_model(self):
        f=self.fixture;service=self.prepare_public();entered,cancelled=threading.Event(),threading.Event()
        def public_provider(settings,messages,cancel=None,**kwargs):
            entered.set()
            if not cancel.wait(5):raise AssertionError('private turn did not cancel public generation')
            cancelled.set();f.app.check_cancel(cancel)
        f.app.generate_once=public_provider;worker,result=self.start_public_request();self.assertTrue(entered.wait(3))
        reply=f.chat('PRIVATE_TAKEOVER_CANARY')
        worker.join(4);self.assertFalse(worker.is_alive());self.assertTrue(cancelled.is_set())
        self.assertEqual(result[0][0],409,result);self.assertEqual(list(service.public_replies),[])
        self.assertEqual(reply['message']['role'],'assistant')
        self.assertNotIn('PUBLIC_ONLY_BLOCKING_CANARY',json.dumps(f.model_calls,ensure_ascii=False))

    def test_uncooperative_public_provider_times_out_private_takeover_without_fake_completion(self):
        f=self.fixture;service=self.prepare_public();entered,release=threading.Event(),threading.Event()
        f.pending_releases.append(release)
        def public_provider(*args,**kwargs):
            entered.set();self.assertTrue(release.wait(9));return 'UNCANCELLABLE_PUBLIC_CANARY'
        f.app.generate_once=public_provider;worker,result=self.start_public_request();self.assertTrue(entered.wait(3))
        status,_,_=f.request('POST','/api/chat',{'text':'PRIVATE_WAITING_CANARY','request_id':'private-timeout',
                                             'expected_character_id':f.initial_id})
        self.assertEqual(status,409)
        self.assertTrue(worker.is_alive(),'test native provider should still be running; do not claim forced cancellation')
        release.set();worker.join(3);self.assertEqual(result[0][0],409,result)
        self.assertEqual(list(service.public_replies),[])


if __name__=='__main__':unittest.main(verbosity=2)
