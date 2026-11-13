"""Explicit real local-model conversation observations; no quality score."""
from pathlib import Path
import json
import os
import time
from llama_cpp import Llama
from companion_runtime.conversation import build_messages, generate_reply, response_issues

root=Path(__file__).resolve().parents[1]
model_dir=Path(os.environ.get('COMPANION_MODELS','/workspace/companion/models'))
model=model_dir/'qwen3-4b-instruct-2507-q4_k_m.gguf'
llm=Llama(model_path=str(model),n_ctx=4096,n_threads=4,n_batch=256,verbose=False)
s={'name':'用户自建角色','personality':'温柔但有自己的主见，偶尔俏皮，喜欢自然简短的聊天。','user_name':'你','memory_mode':'relevant','conversation_mode':'daily','character_notes':'偏爱轻快的民谣。'}
cases=[
 ('memory_admin_does_not_become_current_topic',[{'role':'user','text':'记住：我的合成口令是蓝纸风筝'},{'role':'assistant','text':'好，我记住了。'},{'role':'user','text':'我今天有点累，只想安静聊一句，不要提问。'}],['我的合成口令是蓝纸风筝']),
 ('no_old_facts',[{'role':'user','text':'别总提旧事实和以前的偏好，今天只聊当下。我想看一部轻松的电影，不用问我问题。'}],['我喜欢桂花乌龙茶']),
 ('study_is_optional',[{'role':'user','text':'今天不想学习了，只想歇一会儿。先别劝我，也不要问问题。'}],[]),
 ('character_preferences_belong_to_character',[{'role':'user','text':'你自己喜欢什么音乐？'}],['我喜欢电子音乐'])]
records=[]
for name,history,memories in cases:
 messages=build_messages(s,history,memories);started=time.monotonic();first=[];calls=[];deltas=[];stages=[]
 def provider(settings,msgs,on_delta,cancel,max_tokens=180):
  calls.append({'max_tokens':max_tokens})
  chunks=llm.create_chat_completion(messages=msgs,max_tokens=max_tokens,temperature=.65,top_p=.9,repeat_penalty=1.1,seed=42,stream=True)
  text=[]
  try:
   for chunk in chunks:
    token=chunk['choices'][0].get('delta',{}).get('content')
    if token:
     if not first:first.append(time.monotonic()-started)
     text.append(token)
     if on_delta:on_delta(token)
  finally:
   if hasattr(chunks,'close'):chunks.close()
  return ''.join(text).strip()
 try:
  reply=generate_reply(s,messages,provider,on_delta=deltas.append,on_status=stages.append)
  record={'case':name,'reply':reply,'observable_issues':response_issues(s,messages,reply),'elapsed_seconds':round(time.monotonic()-started,3),'first_text_seconds':round(first[0],3),'generation_passes':len(calls),'completed':True}
  if name=='memory_admin_does_not_become_current_topic':record['stale_passphrase_present']='蓝纸风筝' in reply
 except Exception as error:record={'case':name,'completed':False,'error_type':type(error).__name__,'error':str(error),'generation_passes':len(calls)}
 records.append(record)
 print(json.dumps(record,ensure_ascii=False),flush=True)
result={'date':'2026-11-12','scope':'four real local Qwen3-4B observations on synthetic dialogue; no human quality acceptance','model':model.name,'backend':'llama-cpp-python CPU 4 threads','cases':records,'human_naturalness_accepted':False,'windows_or_rtx4060_tested':False,'failed_observations_retained':True}
(root/'review/conversation-real-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
