"""Actual HTTP/SQLite playback receipt and prompt-context integration.

The player reports synthetic observations here; this is not human attention or
actual audio playback proof. Browser end-to-end checks cover real Audio events.
"""
import base64
import io
import json
import unittest
import uuid
import threading
import wave

import test_character_http as character_http


class PlaybackIntegrationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=character_http.CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
        self.fixture.setUp()
        stream=io.BytesIO()
        with wave.open(stream,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16000)
        self.audio=stream.getvalue()
        self.fixture.app.synthesize=lambda text:self.audio

    def tearDown(self):self.fixture.tearDown()

    def reply(self,text='UNHEARD_ASSISTANT_ONLY_CANARY'):
        f=self.fixture;original=f.app.generate
        def generate(settings,messages,on_delta=None,cancel=None,on_status=None):
            if on_delta:on_delta(text)
            return text
        f.app.generate=generate
        try:return f.chat('这是一条合成用户输入')
        finally:f.app.generate=original

    def speech(self,reply):
        f=self.fixture
        status,headers,body=f.request('POST','/api/speech',{'message_id':reply['message']['id'],'expected_character_id':f.state()['active_character_id']})
        self.assertEqual(status,200,body);self.assertTrue(body.startswith(b'RIFF'))
        self.assertIn('X-Companion-Playback',headers)
        return json.loads(base64.b64decode(headers['X-Companion-Playback']))

    def receipt(self,playback,status='stopped',position=0,duration=1,**extra):
        f=self.fixture
        return f.post('playback/receipt',{'playback_id':playback['playback_id'],'nonce':playback['nonce'],
            'character_id':playback['character_id'],'appearance_id':playback['appearance_id'],
            'position_seconds':position,'duration_seconds':duration,'status':status,
            'expected_character_id':playback['character_id'],**extra})

    def persisted(self,message_id):
        with self.fixture.app.db() as connection:
            row=connection.execute('SELECT receipt FROM playback_context WHERE message_id=?',(message_id,)).fetchone()
            return json.loads(row['receipt']) if row else None

    def test_nonce_is_only_in_authenticated_playback_header_not_db_state_or_export(self):
        f=self.fixture;reply=self.reply();playback=self.speech(reply)
        self.assertTrue(playback['nonce']);saved=self.persisted(reply['message']['id'])
        self.assertEqual(saved['status'],'pending');self.assertNotIn('nonce',saved)
        self.assertNotIn(playback['nonce'],json.dumps(f.state()))
        status,_,body=f.request('GET','/api/export');self.assertEqual(status,200)
        self.assertNotIn(playback['nonce'].encode(),body)
        self.assertNotIn('confirmed_text',playback)

    def test_partial_stop_preserves_visible_text_but_does_not_invent_heard_prefix(self):
        f=self.fixture;reply=self.reply();playback=self.speech(reply)
        result=self.receipt(playback,position=.5)
        self.assertEqual(result['confirmed_characters'],0)
        self.assertEqual(self.persisted(reply['message']['id'])['confirmed_text'],'')
        self.assertIn(reply['message']['text'],str(f.state()['messages']))
        f.chat('继续说现在的事情')
        self.assertNotIn('UNHEARD_ASSISTANT_ONLY_CANARY',json.dumps(f.model_calls[-1]))

    def test_full_completion_then_interrupted_replay_does_not_downgrade_heard_context(self):
        f=self.fixture;reply=self.reply('COMPLETED_ASSISTANT_CANARY');first=self.speech(reply)
        self.receipt(first,'completed',1)
        second=self.speech(reply);self.receipt(second,'stopped',.2)
        self.assertEqual(self.persisted(reply['message']['id'])['confirmed_text'],'COMPLETED_ASSISTANT_CANARY')
        f.chat('继续当前对话')
        self.assertIn('COMPLETED_ASSISTANT_CANARY',json.dumps(f.model_calls[-1]))

    def test_complete_truncated_tts_confirms_only_server_synthesized_700_character_prefix(self):
        f=self.fixture;text='PREFIX_VOICE_'*60+'UNSYNTHESIZED_TAIL_CANARY';reply=self.reply(text);playback=self.speech(reply)
        self.receipt(playback,'completed',1)
        self.assertEqual(self.persisted(reply['message']['id'])['confirmed_text'],text[:700])
        f.chat('接着聊一句')
        history=json.dumps(f.model_calls[-1])
        self.assertNotIn('UNSYNTHESIZED_TAIL_CANARY',history)
        self.assertIn(text[:700],history)

    def test_client_confirmed_text_and_owner_claim_cannot_replace_server_text(self):
        f=self.fixture;reply=self.reply('SERVER_BOUND_TEXT');playback=self.speech(reply)
        self.receipt(playback,'completed',1,confirmed_text='FORGED_CLIENT_TEXT')
        self.assertEqual(self.persisted(reply['message']['id'])['confirmed_text'],'SERVER_BOUND_TEXT')
        status,_,_=f.request('POST','/api/playback/receipt',{'owner':True,'playback_id':playback['playback_id']})
        self.assertEqual(status,403)

    def test_wrong_nonce_character_and_early_completed_position_are_rejected(self):
        f=self.fixture;reply=self.reply();playback=self.speech(reply)
        base={'playback_id':playback['playback_id'],'nonce':playback['nonce'],'character_id':playback['character_id'],
              'appearance_id':playback['appearance_id'],'position_seconds':.5,'duration_seconds':1,'status':'completed'}
        for changes,expected in [({},409),({'nonce':'x'*43},404),({'character_id':'wrong-character'},404),({'position_seconds':float('nan')},400)]:
            with self.subTest(changes=changes):f.post('playback/receipt',{**base,**changes},expected=expected)
        self.assertEqual(self.persisted(reply['message']['id'])['confirmed_text'],'')

    def test_role_or_appearance_switch_invalidates_old_completed_callback(self):
        f=self.fixture;reply=self.reply();playback=self.speech(reply)
        f.create('回执隔离身份')
        result=self.receipt(playback,'completed',1)
        self.assertFalse(result['accepted']);self.assertTrue(result['stale'])
        with f.app.db() as connection:self.assertEqual(connection.execute('SELECT count(*) FROM playback_context').fetchone()[0],0)
        f.select(f.initial_id);fresh=self.speech(reply);asset=f.import_asset();f.activate(f.initial_id,asset['id'])
        self.assertFalse(self.receipt(fresh,'completed',1)['accepted'])

    def test_clear_cascades_receipts_without_resurrecting_plaintext(self):
        f=self.fixture;reply=self.reply('DELETE_WITH_CONTEXT_CANARY');playback=self.speech(reply)
        self.receipt(playback,'completed',1)
        f.post('conversation/clear',{'expected_character_id':f.initial_id})
        self.assertIsNone(self.persisted(reply['message']['id']))
        self.receipt(playback,'completed',1)
        with f.app.db() as connection:self.assertEqual(connection.execute('SELECT count(*) FROM playback_context').fetchone()[0],0)
        self.assertNotIn('DELETE_WITH_CONTEXT_CANARY',str(f.state()['messages']))

    def test_forget_and_old_backup_cannot_restore_confirmed_plaintext(self):
        f=self.fixture
        f.post('memories',{'text':'FORGOTTEN_MEMORY_CANARY','expected_character_id':f.initial_id})
        memory_id=f.state()['memories'][0]['id']
        reply=self.reply('FORGOTTEN_AUDIO_CONTEXT_CANARY');playback=self.speech(reply)
        self.receipt(playback,'completed',1);backup=f.state()
        f.post('memories/delete',{'id':memory_id,'clear_context':True,'expected_character_id':f.initial_id})
        self.assertIsNone(self.persisted(reply['message']['id']))
        restored=f.post('restore',{'backup':backup,'expected_character_id':f.initial_id})
        self.assertTrue(restored['chat_skipped'])
        self.assertNotIn('FORGOTTEN_AUDIO_CONTEXT_CANARY',str(f.state()['messages']))
        self.assertNotIn('FORGOTTEN_MEMORY_CANARY',str(f.state()['memories']))
        with f.app.db() as connection:self.assertEqual(connection.execute('SELECT count(*) FROM playback_context').fetchone()[0],0)

    def test_retry_deletes_old_assistant_receipt_instead_of_reusing_confirmed_text(self):
        f=self.fixture;reply=self.reply('RETRIED_OLD_AUDIO_CANARY');playback=self.speech(reply)
        self.receipt(playback,'completed',1)
        user=next(message for message in f.state()['messages'] if message['role']=='user' and message['kind']=='chat')
        f.post('chat',{'text':user['text'],'retry_message_id':user['id'],'request_id':str(uuid.uuid4()),'expected_character_id':f.initial_id})
        self.assertIsNone(self.persisted(reply['message']['id']))
        self.assertNotIn('RETRIED_OLD_AUDIO_CANARY',str(f.state()['messages']))
        self.assertNotIn('RETRIED_OLD_AUDIO_CANARY',json.dumps(f.model_calls[-1]))

    def test_pending_playback_after_tracker_restart_is_conservatively_excluded(self):
        f=self.fixture;reply=self.reply('PENDING_RESTART_CANARY');self.speech(reply)
        f.app.PLAYBACK_TRACKERS.clear();f.app.init()
        f.chat('重启后继续一句')
        self.assertNotIn('PENDING_RESTART_CANARY',json.dumps(f.model_calls[-1]))

    def test_late_historical_tts_cannot_supersede_newer_playback_receipt(self):
        f=self.fixture;old=self.reply('HISTORICAL_SLOW_A');new=self.reply('HISTORICAL_FAST_B')
        entered,release=threading.Event(),threading.Event();f.pending_releases.append(release)
        def provider(text):
            if text=='HISTORICAL_SLOW_A':entered.set();self.assertTrue(release.wait(8))
            return self.audio
        f.app.synthesize=provider;late=[]
        worker=threading.Thread(target=lambda:late.append(f.request('POST','/api/speech',
            {'message_id':old['message']['id'],'expected_character_id':f.initial_id})))
        f.pending_threads.append(worker);worker.start();self.assertTrue(entered.wait(3))
        current=self.speech(new);self.receipt(current,'playing',.2)
        release.set();worker.join(4);self.assertFalse(worker.is_alive())
        completed=self.receipt(current,'completed',1)
        self.assertEqual((late[0][0],completed['accepted']),(409,True),
                         {'old_response_status':late[0][0],'new_completion':completed})
        self.assertEqual(self.persisted(new['message']['id'])['confirmed_text'],'HISTORICAL_FAST_B')

    def test_historical_tts_does_not_revive_after_role_aba_switch(self):
        f=self.fixture;reply=self.reply('OLD_ABA_SPEECH');entered,release=threading.Event(),threading.Event()
        f.pending_releases.append(release)
        def provider(text):entered.set();self.assertTrue(release.wait(8));return self.audio
        f.app.synthesize=provider;late=[]
        worker=threading.Thread(target=lambda:late.append(f.request('POST','/api/speech',
            {'message_id':reply['message']['id'],'expected_character_id':f.initial_id})))
        f.pending_threads.append(worker);worker.start();self.assertTrue(entered.wait(3))
        f.create('ABA中间身份');f.select(f.initial_id);release.set();worker.join(4)
        self.assertEqual(late[0][0],409,{'status':late[0][0]})

    def test_invalid_speech_request_does_not_take_current_playback_ownership(self):
        f=self.fixture;reply=self.reply('CURRENT_VALID_SPEECH');playback=self.speech(reply)
        f.post('speech',{'message_id':999999,'expected_character_id':f.initial_id},expected=404)
        self.assertTrue(self.receipt(playback,'completed',1)['accepted'])

    def test_stale_generation_stop_does_not_invalidate_newer_playback(self):
        f=self.fixture;old=self.reply('OLD_GENERATION_REPLY');new=self.reply('NEW_GENERATION_REPLY')
        current=self.speech(new);self.receipt(current,'playing',.2)
        stopped=f.post('chat/stop',{'request_id':old['request_id'],'generation_id':old['generation_id'],
                                  'expected_character_id':f.initial_id})
        completed=self.receipt(current,'completed',1)
        self.assertTrue(completed['accepted'],{'old_stop':stopped,'current_completion':completed})


if __name__=='__main__':unittest.main(verbosity=2)
