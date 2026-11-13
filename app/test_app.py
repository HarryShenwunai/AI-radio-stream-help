import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import time
import threading
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('companion_server',Path(__file__).with_name('server.py'))
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DATA=Path(self.tmp.name);app.init();app.set_settings({'quiet_start':0,'quiet_end':0})
    def tearDown(self):self.tmp.cleanup()
    def count(self,table):
        with app.db() as c:return c.execute('SELECT count(*) FROM '+table).fetchone()[0]
    def user(self,text):
        with app.db() as c:c.execute("INSERT INTO messages(role,text,created) VALUES('user',?,?)",(text,app.now()))
    def test_explicit_memory_is_persisted_and_repeated_request_is_idempotent(self):
        a=app.chat({'text':'记住：我喜欢桂花乌龙茶','request_id':'once'})
        b=app.chat({'text':'记住：我喜欢桂花乌龙茶','request_id':'once'})
        self.assertEqual(a['message']['id'],b['message']['id']);self.assertEqual(self.count('memories'),1)
        app.init();self.assertIn('桂花乌龙',app.state()['memories'][0]['text'])
    def test_memory_search_can_recall_older_fact(self):
        app.add_memory('我的爱好是天文摄影')
        for i in range(20):app.add_memory(f'第{i}条：周末读书')
        with app.db() as c:c.execute("INSERT INTO messages(role,text,created) VALUES('user','我的爱好是什么？',?)",(app.now(),))
        self.assertIn('天文摄影',app.build_prompt(app.settings())[0]['content'])
    def test_memory_length_and_count_limits(self):
        with self.assertRaises(app.AppError):app.add_memory('a'*301)
        for i in range(60):app.add_memory(str(i))
        with self.assertRaises(app.AppError):app.add_memory('overflow')
    def test_api_validation_does_not_allow_insecure_remote_or_metadata(self):
        for url in ['http://example.com/v1','https://user:secret@example.com/v1','http://169.254.169.254/v1','file:///etc/passwd']:
            with self.subTest(url=url),self.assertRaises(app.AppError):app.validate_base(url)
        self.assertEqual(app.validate_base('http://127.0.0.1:9999/v1'),'http://127.0.0.1:9999/v1')
    def test_reminder_is_shown_once(self):
        app.schedule({'title':'喝水','minutes':1/60});app.scheduler_tick(time.time()+2);app.scheduler_tick(time.time()+3)
        self.assertEqual(app.state()['tasks'][0]['status'],'done')
        self.assertEqual(sum(m['kind']=='reminder' for m in app.state()['messages']),1)
    def test_cancelled_reminder_does_not_fire(self):
        app.schedule({'title':'不应提醒','minutes':1/60})
        with app.DISPATCH_LOCK:
            with app.db() as c:c.execute("UPDATE tasks SET status='cancelled'")
        app.scheduler_tick(time.time()+5)
        self.assertFalse(any(m['kind']=='reminder' for m in app.state()['messages']))
    def test_quiet_window_skips_due_reminder(self):
        hour=app.dt.datetime.now().hour;app.set_settings({'quiet_start':hour,'quiet_end':(hour+1)%24})
        app.schedule({'title':'安静测试','minutes':1/60});app.scheduler_tick(time.time()+2)
        self.assertEqual(app.state()['tasks'][0]['status'],'quiet')
        self.assertFalse(any(m['kind']=='reminder' for m in app.state()['messages']))
    def test_expired_reminder_not_replayed_after_long_offline(self):
        app.schedule({'title':'过期任务','minutes':1/60});app.scheduler_tick(time.time()+4000)
        self.assertEqual(app.state()['tasks'][0]['status'],'expired')
    def test_study_requires_enable_and_disable_pauses_existing(self):
        with self.assertRaises(app.AppError):app.schedule({'title':'学习','minutes':1,'kind':'study'})
        app.set_settings({'study':True});app.schedule({'title':'学习','minutes':1,'kind':'study'})
        app.set_settings({'study':False});self.assertEqual(app.state()['tasks'][0]['status'],'paused')
    def test_restore_old_backup_does_not_resurrect_forgotten_memory(self):
        app.add_memory('我的秘密测试事实')
        backup=app.state()
        with app.db() as c:c.execute('INSERT INTO forgotten VALUES(?,?)',(app.forget_digest('我的秘密测试事实'),app.now()))
        result=app.restore({'backup':backup})
        self.assertTrue(result['chat_skipped']);self.assertEqual(self.count('memories'),0);self.assertEqual(self.count('messages'),0)
    def test_restore_pauses_outstanding_tasks_and_keeps_model_settings(self):
        app.schedule({'title':'将来任务','minutes':5});backup=app.state();backup['settings']['api_base']='https://different.example/v1'
        before=app.settings()['api_base'];app.restore({'backup':backup})
        self.assertEqual(app.state()['tasks'][0]['status'],'paused');self.assertEqual(app.settings()['api_base'],before)
    def test_invalid_restore_leaves_existing_data(self):
        app.add_memory('有效记忆');before=app.state()
        with self.assertRaises(app.AppError):app.restore({'backup':{'messages':[{'role':'system','text':'bad'}]}})
        self.assertEqual(app.state()['memories'],before['memories'])
    def test_secret_is_not_returned_in_state_and_has_private_permissions(self):
        app.set_settings({'api_key':'fixture-secret-do-not-leak'})
        import json,stat
        self.assertNotIn('fixture-secret-do-not-leak',json.dumps(app.state()))
        self.assertEqual((app.DATA/'api-key').read_text(),'fixture-secret-do-not-leak')
        if os.name=='posix':self.assertEqual(stat.S_IMODE((app.DATA/'api-key').stat().st_mode),0o600)
    def test_prompt_separates_fiction_and_user_facts(self):
        app.add_memory('我喜欢花茶');self.user('我喜欢什么花茶？');prompt=app.build_prompt(app.settings())[0]['content']
        self.assertIn('不要编造共同经历',prompt);self.assertIn('用户喜欢花茶',prompt)
    def test_no_wechat_success_claim(self):self.assertIs(app.state()['wechat_available'],False)
    def test_saved_user_fact_cannot_be_rendered_as_role_favorite(self):
        app.add_memory('我最喜欢的饮品是桂花乌龙茶')
        self.user('我最喜欢喝什么？');messages=app.build_prompt(app.settings())
        self.assertEqual(app.ground_memory_owner('我的最爱是桂花乌龙茶。',messages),'你的最爱是桂花乌龙茶。')
        self.assertEqual(app.ground_memory_owner('我最喜欢喝桂花乌龙茶。',messages),'你最喜欢喝桂花乌龙茶。')
    def test_owner_guard_does_not_rewrite_normal_role_expression(self):
        app.add_memory('我喜欢花茶')
        messages=app.build_prompt(app.settings())+[{'role':'user','content':'你喜欢做什么？'}]
        self.assertEqual(app.ground_memory_owner('我喜欢听音乐。',messages),'我喜欢听音乐。')
        messages[-1]['content']='我最喜欢喝什么？'
        self.assertEqual(app.ground_memory_owner('我不知道，你还没告诉我。',messages),'我不知道，你还没告诉我。')
    def test_unrelated_memory_has_no_fallback_injection(self):
        app.add_memory('我喜欢桂花乌龙茶');self.user('刚才看见月亮特别亮，突然想告诉你。')
        self.assertNotIn('桂花乌龙',app.build_prompt(app.settings())[0]['content'])
        self.assertEqual(app.select_memories(app.settings(),'今天好累'),[])
    def test_memory_off_uses_current_dialogue_without_saved_facts(self):
        app.add_memory('我喜欢桂花乌龙茶');app.set_settings({'memory_mode':'off'})
        self.user('今天想喝热可可。');self.user('我喜欢喝什么？')
        prompt=app.build_prompt(app.settings())
        self.assertNotIn('桂花乌龙',str(prompt));self.assertIn('热可可',str(prompt))
        self.assertEqual(self.count('memories'),1)
    def test_current_correction_and_role_preferences_do_not_retrieve_old_facts(self):
        app.add_memory('我最喜欢的饮品是桂花乌龙茶')
        for query in ['你喜欢喝什么？','以前喜欢茶，现在已经不喜欢了，想喝可可']:
            self.assertEqual(app.select_memories(app.settings(),query),[])
    def test_relevant_memory_is_capped_and_model_does_not_need_it(self):
        for i in range(10):app.add_memory(f'我喜欢天文摄影，第{i}种相机')
        self.assertLessEqual(len(app.select_memories(app.settings(),'我的天文摄影爱好是什么？')),3)
        with patch.object(app,'generate',return_value='月亮很亮，听起来是个不错的晚上。') as gen:
            result=app.chat({'text':'今晚月亮很亮','request_id':'no-facts'})
        self.assertIn('月亮',result['message']['text']);self.assertEqual(gen.call_count,1)
        self.assertNotIn('相机',str(gen.call_args.args[1]))
    def test_modes_and_profile_persist_without_adding_memories(self):
        app.set_settings({'conversation_mode':'listen','character_notes':'喜欢旧书店','memory_mode':'off'})
        app.init();self.user('你喜欢什么？');prompt=app.build_prompt(app.settings())[0]['content']
        self.assertIn('倾听',prompt);self.assertIn('喜欢旧书店',prompt);self.assertEqual(self.count('memories'),0)
    def test_shared_word_in_casual_chat_does_not_trigger_old_preference(self):
        app.add_memory('我最喜欢桂花乌龙茶')
        self.assertEqual(app.select_memories(app.settings(),'刚打开窗户闻到桂花香，心情好了点。'),[])
    def test_retry_replaces_only_answer_without_duplicating_user(self):
        with patch.object(app,'generate',return_value='第一次回答'):
            original=app.chat({'text':'随便聊两句','request_id':'first'})
        user=next(m for m in app.state()['messages'] if m['role']=='user')
        with patch.object(app,'generate',return_value='换一种说法'):
            result=app.chat({'retry_message_id':user['id'],'request_id':'retry'})
        self.assertEqual(sum(m['role']=='user' for m in app.state()['messages']),1)
        self.assertFalse(any(m['id']==original['message']['id'] for m in app.state()['messages']))
        self.assertEqual(result['message']['text'],'换一种说法')
    def test_retry_failure_keeps_previous_answer(self):
        with patch.object(app,'generate',return_value='仍应保留的回答'):app.chat({'text':'你好','request_id':'original'})
        user=next(m for m in app.state()['messages'] if m['role']=='user')
        with patch.object(app,'generate',side_effect=app.AppError('provider failed',502)),self.assertRaises(app.AppError):
            app.chat({'retry_message_id':user['id'],'request_id':'failed-retry'})
        self.assertEqual(app.state()['messages'][-1]['text'],'仍应保留的回答')
    def test_cancellation_does_not_commit_partial_answer(self):
        ready=threading.Event();results=[]
        def slow(s,messages,on_delta,cancel,on_status=None):
            on_delta('未完成的半句话');ready.set();cancel.wait(2);app.check_cancel(cancel);return '不应保存'
        with patch.object(app,'generate',side_effect=slow):
            worker=threading.Thread(target=lambda:results.append(app.chat({'text':'说点什么','request_id':'stop'},on_delta=lambda x:None)))
            worker.start();self.assertTrue(ready.wait(2));self.assertTrue(app.cancel_chat({'request_id':'stop'})['stopping']);worker.join(3)
        self.assertFalse(worker.is_alive());self.assertEqual(len(results),1);self.assertTrue(results[0]['cancelled']);self.assertEqual(results[0]['request_id'],'stop');self.assertTrue(results[0]['generation_id']);self.assertFalse(app.MODEL_LOCK.locked())
        self.assertFalse(any(m['role']=='assistant' and m['kind']=='chat' for m in app.state()['messages']))
    def test_disconnect_during_meta_releases_model_lock(self):
        def disconnected(meta):raise app.Cancelled()
        result=app.chat({'text':'你好','request_id':'disconnect'},on_meta=disconnected)
        self.assertTrue(result['cancelled']);self.assertFalse(app.MODEL_LOCK.locked());self.assertFalse(app.ACTIVE)
    def test_stale_retry_and_request_id_collision_are_rejected(self):
        with patch.object(app,'generate',return_value='回答'):
            app.chat({'text':'第一句','request_id':'a'})
            first=next(m for m in app.state()['messages'] if m['role']=='user')
            app.chat({'text':'第二句','request_id':'b'})
            with self.assertRaises(app.AppError):app.chat({'retry_message_id':first['id'],'request_id':'stale'})
    def test_delay_then_complete_does_not_send_future_reminder(self):
        app.schedule({'title':'约好散步','minutes':1})
        task=app.state()['tasks'][0];app.change_task({'id':task['id'],'minutes':5},'delay')
        due=app.state()['tasks'][0]['due'];self.assertGreater(due,time.time()+290)
        app.change_task({'id':task['id']},'complete');app.scheduler_tick(due+1)
        self.assertEqual(app.state()['tasks'][0]['status'],'completed')
        self.assertFalse(any(m['kind']=='reminder' for m in app.state()['messages']))
    def test_cancelled_task_cannot_be_delayed_or_completed(self):
        app.schedule({'title':'已取消','minutes':1});task=app.state()['tasks'][0]
        app.change_task({'id':task['id']},'cancel')
        for action in ['delay','complete']:
            with self.assertRaises(app.AppError):app.change_task({'id':task['id'],'minutes':5},action)
    def test_clean_reply_uses_one_inference_pass(self):
        messages=[{'role':'system','content':'角色'},{'role':'user','content':'今晚看见月亮了'}]
        with patch.object(app,'generate_once',return_value='这样的瞬间，确实值得分享。') as once:
            self.assertEqual(app.generate(app.settings(),messages),'这样的瞬间，确实值得分享。')
        self.assertEqual(once.call_count,1)
    def test_unwanted_question_is_revised_once_and_emits_replace(self):
        messages=[{'role':'system','content':'角色'},{'role':'user','content':'别问我问题，陪我说两句'}];stages=[]
        with patch.object(app,'generate_once',side_effect=['你今天怎么样？','好，今天就慢慢来。']) as once:
            answer=app.generate(app.settings(),messages,on_status=stages.append)
        self.assertEqual(answer,'好，今天就慢慢来。');self.assertEqual(once.call_count,2);self.assertTrue(stages[0]['replace'])
    def test_failed_revision_does_not_commit_an_answer(self):
        with patch.object(app,'generate_once',side_effect=['你好吗？','还是想问你好吗？']),self.assertRaises(app.AppError):
            app.chat({'text':'不要问我问题','request_id':'invalid-revision'})
        self.assertFalse(any(m['role']=='assistant' and m['kind']=='chat' for m in app.state()['messages']))
        self.assertFalse(app.MODEL_LOCK.locked())
    def test_experience_checks_do_not_block_declared_fiction_or_preferences(self):
        def issues(query,text):return app.response_issues(app.settings(),[{'role':'user','content':query}],text)
        self.assertIn('unconfirmed_experience',issues('今晚好累','我刚去书店买了一本书。'))
        self.assertIn('unknown_environment',issues('今天不想学习','太阳快下山了。'))
        self.assertEqual(issues('写个虚构小故事','我刚去书店买了一本书。'),[])
        self.assertEqual(issues('你喜欢什么音乐','我喜欢轻快的音乐。'),[])
    def test_negative_request_for_advice_is_not_misread_as_asking_for_advice(self):
        messages=[{'role':'user','content':'别急着给我建议，我只想吐槽。'}]
        self.assertIn('unsolicited_advice',app.response_issues(app.settings(),messages,'你先深呼吸。'))
    @unittest.skipUnless(hasattr(time,'tzset'),'timezone environment switch is POSIX-specific')
    def test_daily_message_limit_uses_local_calendar_day(self):
        import os
        previous=os.environ.get('TZ')
        try:
            os.environ['TZ']='Asia/Shanghai';time.tzset()
            stamp=app.dt.datetime(2026,11,20,16,30,tzinfo=app.dt.timezone.utc).timestamp()
            self.assertEqual(app.local_day_start_utc(stamp),'2026-11-20T16:00:00+00:00')
        finally:
            if previous is None:os.environ.pop('TZ',None)
            else:os.environ['TZ']=previous
            time.tzset()

if __name__=='__main__':unittest.main(verbosity=2)
