'use strict';
const $=s=>document.querySelector(s);
let app=null,view='chat',busy=false,lastSeen=0,selectedVoice=localStorage.getItem('lan-voice')||'',polling=false;
let recognition=null,recording=false,localAudio=null,voiceRequest=null,audioUrl=null,voiceSerial=0;
let voiceCleanup=null,voiceContext=null,activeGeneration='';
let streamDraft=null,activeRequest="",stopping=false,failedSend=null;
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,3800);}
async function api(path,data){
 const opts=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(data)};
 const response=await fetch('/api/'+path,opts);
 const result=await response.json();
 if(!response.ok)throw new Error(result.error||'请求失败，请稍后再试。');
 return result;
}
function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function localTime(text){return new Date(text).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}
function showView(name){view=name;document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!=='view-'+name);document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('#view-title').textContent=({chat:'和'+(app?.settings.name||'小岚')+'聊天',memory:'记忆',tasks:'约定',settings:'设置'})[name];if(name==='settings')fillSettings();}
function voices(){if(!('speechSynthesis'in window))return [];return speechSynthesis.getVoices();}
async function speak(text,context={}){
 stopVoice();const serial=voiceSerial;voiceContext={...context};
 if((!selectedVoice||selectedVoice==='__local__'||!voices().length)&&app?.local_voice_available){await localSpeak(text,context);return;}
 if(!('speechSynthesis'in window)){toast('当前浏览器不支持朗读。试试 Chrome 或系统浏览器。');return;}
 const all=voices();
 if(!all.length){toast('浏览器暂未提供语音。请检查系统中文语音包，或稍后重试。');return;}
 speechSynthesis.cancel();
 const u=new SpeechSynthesisUtterance(text.replace(/https?:\/\/\S+/g,'链接').replace(/[*#_`]/g,''));
 u.lang='zh-CN';u.rate=app?.settings.voice_rate||1;u.pitch=1.04;
 u.voice=all.find(v=>v.voiceURI===selectedVoice)||all.find(v=>v.lang.startsWith('zh')&&/female|xiaoxiao|ting|hui|女/i.test(v.name))||all.find(v=>v.lang.startsWith('zh'))||all[0];
 u.onerror=e=>{if(serial!==voiceSerial)return;document.body.classList.remove('is-speaking');voiceContext=null;if(!['canceled','interrupted'].includes(e.error))toast('朗读没有成功，请检查系统音色。');};
 u.onstart=()=>{if(serial===voiceSerial)document.body.classList.add('is-speaking');};u.onend=()=>{if(serial===voiceSerial){document.body.classList.remove('is-speaking');voiceContext=null;}};
 speechSynthesis.speak(u);
}
function fillVoices(){const select=$('#voice-select');select.replaceChildren(element('option','', '自动选择中文音色'));select.firstChild.value='';if(app?.local_voice_available){const option=element('option','','本地中文合成');option.value='__local__';select.append(option);}for(const v of voices()){const op=element('option','',v.name+' · '+v.lang);op.value=v.voiceURI;select.append(op);}select.value=selectedVoice;}
function messageNode(m){
 const row=element('article','message '+m.role);row.dataset.messageId=m.id;
 const avatar=element('div','mini-avatar',m.role==='user'?'你':app.settings.name.slice(0,1));
 const wrap=element('div','bubble-wrap');wrap.append(element('div','bubble'+(['reminder','proactive'].includes(m.kind)?' reminder':''),m.text));
 const foot=element('div','message-foot');foot.append(element('span','',localTime(m.created)));
 if(m.role==='assistant'){const b=element('button','read-button','朗读');b.type='button';b.setAttribute('aria-label','朗读这条消息');b.addEventListener('click',()=>speak(m.text,{message_id:m.id}));foot.append(b);}
 wrap.append(foot);row.append(avatar,wrap);return row;
}
function renderMessages(){
 const root=$('#messages'),nearBottom=root.scrollHeight-root.scrollTop-root.clientHeight<110;
 const ids=app.settings.name+':'+app.messages.map(m=>m.id).join(',');
 if(root.dataset.ids!==ids){
  root.dataset.ids=ids;root.replaceChildren(element('div','day-divider','我们的对话'));
  let day='';for(const m of app.messages){
   const date=new Date(m.created).toLocaleDateString('zh-CN');
   if(day&&date!==day)root.append(element('div','day-divider',date));
   day=date;root.append(messageNode(m));
  }
 }
 let draft=root.querySelector('[data-stream]');
 const show=streamDraft?.text&&!app.messages.some(m=>m.role==='assistant'&&m.request_id===streamDraft.rid);
 if(show){
  if(!draft){draft=messageNode({id:'draft',role:'assistant',text:'',created:new Date().toISOString()});draft.dataset.stream='true';draft.classList.add('streaming');draft.querySelector('.message-foot').replaceChildren(element('span','','正在回复'));root.append(draft);}
  draft.querySelector('.bubble').textContent=streamDraft.text;
 }else if(draft)draft.remove();
 if(nearBottom)root.scrollTop=root.scrollHeight;
 updateRetry();
}
function updateRetry(){
 if(!app)return;const last=app.messages.filter(m=>m.kind==='chat'&&m.role==='user').at(-1);
 $('#retry-answer').hidden=busy||Boolean(app.model_busy)||!last||last.text.startsWith('记住：')||last.text.startsWith('记住:');
 $('#retry-answer').textContent=app.messages.at(-1)?.role==='user'?'继续回答':'换个回答';
}
function renderMemories(){
 $('#memory-count').textContent=app.memories.length+' / 60';const list=$('#memory-list');list.replaceChildren();
 if(!app.memories.length)list.append(element('div','empty','我们还没有保存特别的记忆。\n想让我记住的事，可以慢慢告诉我。'));
 for(const m of app.memories){
  const card=element('article','list-card');card.append(element('p','',m.text));const foot=element('footer');foot.append(element('span','',new Date(m.created).toLocaleDateString('zh-CN')));
  const edit=element('button','text-button','修改');edit.onclick=async()=>{const value=prompt('修改记忆。为避免旧事实留在上下文，保存时会清空当前聊天；其他记忆保留。',m.text);if(value===null)return;try{$('#stop-voice').click();await api('memories/update',{id:m.id,text:value});await refresh();toast('记忆已更新，旧对话上下文已清空。');}catch(e){toast(e.message);}};
  const del=element('button','text-button','忘记');del.onclick=async()=>{if(!confirm('忘记这条记忆，并清空当前聊天上下文？其他记忆和约定会保留。已经导出的备份不会自动删除。'))return;try{$('#stop-voice').click();await api('memories/delete',{id:m.id,clear_context:true});await refresh();toast('已经忘记，当前对话上下文已清空。');}catch(e){toast(e.message);}};
  foot.append(edit,del);card.append(foot);list.append(card);
 }
}
function renderTasks(){
 const pending=app.tasks.filter(t=>t.status==='pending').length;$('#task-count').textContent=pending+' 个进行中';const list=$('#task-list');list.replaceChildren();
 if(!app.tasks.length)list.append(element('div','empty','留一个小小的约定吧。\n记得让应用保持运行。'));
 const labels={pending:'等待提醒',done:'已提醒',completed:'你已完成',cancelled:'已取消',quiet:'安静时段，已跳过',expired:'已过期，未补发',paused:'已暂停'};
 for(const t of app.tasks){
  const card=element('article','list-card');card.append(element('p','',t.title));const foot=element('footer');
  foot.append(element('span','',new Date(t.due*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})),element('span','',labels[t.status]||t.status));
  if(!['completed','cancelled'].includes(t.status)){
   for(const [action,label] of [['complete','做完了'],['delay','5 分钟后'],['cancel','取消']]){
    const button=element('button','text-button',label);button.onclick=async()=>{try{await api('tasks/'+action,{id:t.id,minutes:5});await refresh();toast(({complete:'完成啦。',delay:'好，改到 5 分钟后。',cancel:'约定已取消。'})[action]);}catch(e){toast(e.message);}};foot.append(button);
   }
  }
  card.append(foot);list.append(card);
 }
}
function fillSettings(){
 if(!app)return;const f=$('#settings-form');
 for(const [k,value]of Object.entries(app.settings)){const input=f.elements.namedItem(k);if(!input)continue;if(input.type==='checkbox')input.checked=value;else input.value=value;}
 f.elements.api_key.value='';f.elements.api_key.placeholder=app.has_api_key?'已保存 · 留空不修改':'填写模型提供方的 API 密钥';
 engineFields();fillVoices();
 $('#timezone').textContent='时间按应用所在电脑：'+app.timezone+'。开始和结束相同表示不设安静时段。';
 $('#local-model-note').textContent=!app.runtime_installed?'还没有本地推理组件。运行「安装本地模型」或选择 API。':!app.model_installed?'本地模型还未下载完成。运行安装脚本后再开始聊天。':'本地模型已安装。首次聊天需要加载，回复质量受小模型能力限制。';
}
function engineFields(){const isApi=$('#engine').value==='api';$('#api-fields').hidden=!isApi;$('#local-model-note').hidden=isApi;}
function render(){
 document.querySelectorAll('[data-mode]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.mode===app.settings.conversation_mode));b.disabled=busy||app.model_busy;});
 $('#memory-toggle').textContent=app.settings.memory_mode==='off'?'只聊当下':'记忆按需';$('#memory-toggle').setAttribute('aria-pressed',String(app.settings.memory_mode!=='off'));$('#memory-toggle').disabled=busy||app.model_busy;
 $('#mobile-voice').setAttribute('aria-pressed',String(app.settings.voice));
 $('#portrait-line').textContent=({daily:'一点小事，也想听你说。',listen:'慢慢说，我在听。',playful:'今天也找点小小的快乐吧。'})[app.settings.conversation_mode];
 if(!busy){$('#thinking').hidden=!app.model_busy;if(app.model_busy)$('#thinking span').textContent='还有一条回复正在进行…';}
 $('#portrait-name').textContent=app.settings.name;document.title=app.settings.name+' · 陪你慢慢聊';
 if(view==='chat')$('#view-title').textContent='和'+app.settings.name+'聊天';
 $('#voice-toggle').textContent=app.settings.voice?'♪ 语音开启':'♪ 语音关闭';$('#voice-toggle').setAttribute('aria-pressed',String(app.settings.voice));
 let status=app.settings.engine==='api'?'模型 API · '+app.settings.api_model:app.model_status==='loading'?'正在加载本地模型…':!app.model_installed?'本地模型未安装 · 请打开设置':'本地模型 · '+app.model_label+' · '+(app.model_status==='ready'?'已就绪':'首次聊天时加载');
 $('#connection').textContent=status;$('#task-hint').textContent='应用运行时在这里提醒，时间按 '+app.timezone+'。尚未接入微信。';
 renderMessages();renderMemories();renderTasks();
}
async function refresh(){
 if(polling)return;polling=true;
 try{
  const fresh=await api('state');const incoming=fresh.messages.filter(m=>m.id>lastSeen&&m.role==='assistant'&&['reminder','proactive'].includes(m.kind));
  app=fresh;render();
  if(lastSeen&&incoming.length){for(const m of incoming){toast(m.text);if(app.settings.voice&&!busy&&!stopping)speak(m.text,{message_id:m.id});if('Notification'in window&&Notification.permission==='granted'&&document.hidden)new Notification(app.settings.name,{body:m.text});}}
  lastSeen=Math.max(lastSeen,...app.messages.map(m=>m.id));
 }catch(e){$('#connection').textContent='连接中断 · 请确认应用仍在运行';}
 finally{polling=false;}
}
function setBusy(value){
 busy=value;$('#send').disabled=value;$('#thinking').hidden=!value;document.body.classList.toggle('is-thinking',value);
 $('#thinking span').textContent=value?(app?.settings.engine==='local'&&app?.model_status!=='ready'?'正在加载本地模型…':'正在回复…'):'';
 if(!value){stopping=false;$('#stop-generation').disabled=false;}
 if(app){document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=value);$('#memory-toggle').disabled=value;updateRetry();}
}
async function runChat(text,retryId=null){
 if(busy||app?.model_busy){toast('先等上一条回复结束，或点击停止。');return;}
 stopVoice();$('#error').hidden=true;setBusy(true);activeRequest=retryId===null&&failedSend?.text===text?failedSend.rid:crypto.randomUUID();
 const rid=activeRequest;activeGeneration='';streamDraft={rid,text:''};let finished=false,failed=false;
 try{
  const payload={text,request_id:rid};if(retryId!==null)payload.retry_message_id=retryId;
  const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(payload)});
  if(!response.ok){const error=await response.json();throw new Error(error.error||'连接失败。');}
  if(!response.body)throw new Error('浏览器不支持流式回复，请更新浏览器。');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  async function event(data){
   if(activeRequest!==rid)return;
   if(data.type==='meta'){
    if(typeof data.generation_id==='string')activeGeneration=data.generation_id;
    if(!app.messages.some(m=>m.id===data.user.id))app.messages.push(data.user);
    renderMessages();if(stopping)await api('chat/stop',cancelPayload(rid,activeGeneration));
   }else if(data.type==='status'){
    if(data.replace){streamDraft.text='';renderMessages();}$('#thinking span').textContent='正在调整表达…';
   }else if(data.type==='delta'){
    streamDraft.text+=data.text;$('#thinking span').textContent='正在回复…';renderMessages();
   }else if(data.type==='done'){
    finished=true;streamDraft=null;failedSend=null;if(typeof data.generation_id==='string')activeGeneration=data.generation_id;
    if(data.cancelled){toast('已停止，未完成的回复不会保存。');}
    else if(data.message){app.messages=app.messages.filter(m=>!(retryId!==null&&m.id>retryId&&m.role==='assistant'&&m.kind==='chat'));if(!app.messages.some(m=>m.id===data.message.id))app.messages.push(data.message);renderMessages();if(app.settings.voice&&!stopping)speak(data.message.text,activeGeneration?{generation_id:activeGeneration,request_id:rid}:{message_id:data.message.id});}
   }else if(data.type==='error'){throw new Error(data.error);}
  }
  try{
   while(true){
    const part=await reader.read();buffer+=decoder.decode(part.value||new Uint8Array(),{stream:!part.done});
    let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);for(const line of block.split('\n'))if(line.startsWith('data:'))await event(JSON.parse(line.slice(5)));}
    if(part.done)break;
   }
   if(!finished)throw new Error('连接中断，消息已保留，可以继续回答。');
  }finally{reader.releaseLock();}
 }catch(e){failed=true;if(retryId===null)failedSend={rid,text};$('#error').textContent=e.message;$('#error').hidden=false;}
 finally{streamDraft=null;activeRequest='';activeGeneration='';await refresh();renderMessages();setBusy(false);if(failed&&retryId===null&&!app.messages.some(m=>m.role==='user'&&m.request_id===rid)&&!$('#message-input').value)$('#message-input').value=text;$('#message-input').focus();}
}
async function send(){
 const input=$('#message-input'),text=input.value.trim();if(!text||busy||app?.model_busy)return;
 input.value='';input.style.height='auto';await runChat(text);
}
function cancelPayload(requestId,generationId){
 const payload={request_id:requestId};if(generationId)payload.generation_id=generationId;return payload;
}
$('#stop-generation').onclick=async()=>{
 const context=voiceContext,rid=activeRequest||app?.active_request_id||context?.request_id,generation=activeGeneration||context?.generation_id;
 stopVoice();if(!rid)return;stopping=true;$('#stop-generation').disabled=true;$('#thinking span').textContent='正在停止…';
 try{await api('chat/stop',cancelPayload(rid,generation));}catch(e){toast(e.message);$('#stop-generation').disabled=false;}
};
$('#retry-answer').onclick=()=>{const last=app?.messages.filter(m=>m.role==='user'&&m.kind==='chat').at(-1);if(last)runChat(last.text,last.id);};
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=async()=>{try{await api('settings',{conversation_mode:button.dataset.mode});await refresh();}catch(e){toast(e.message);}});
$('#memory-toggle').onclick=async()=>{try{await api('settings',{memory_mode:app.settings.memory_mode==='off'?'relevant':'off'});await refresh();toast(app.settings.memory_mode==='off'?'这次只参考当前对话，长期记忆保留。':'只在相关时参考少量记忆。');}catch(e){toast(e.message);}};
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>showView(b.dataset.view));
$('#composer').onsubmit=e=>{e.preventDefault();send();};
$('#message-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send();}};
$('#message-input').oninput=e=>{e.target.style.height='auto';e.target.style.height=Math.min(130,e.target.scrollHeight)+'px';};
$('#memory-form').onsubmit=async e=>{e.preventDefault();try{await api('memories',{text:$('#memory-input').value});$('#memory-input').value='';await refresh();toast('记住了。');}catch(e){toast(e.message);}};
$('#task-form').onsubmit=async e=>{e.preventDefault();try{await api('tasks',{title:$('#task-title').value,minutes:Number($('#task-minutes').value),kind:$('#task-kind').value});$('#task-title').value='';await refresh();toast('约好了。');}catch(e){toast(e.message);}};
$('#settings-form').onsubmit=async e=>{e.preventDefault();const f=e.target,data={};for(const input of f.elements){if(!input.name)continue;data[input.name]=input.type==='checkbox'?input.checked:['quiet_start','quiet_end','voice_rate'].includes(input.name)?Number(input.value):input.value;}try{await api('settings',data);selectedVoice=$('#voice-select').value;localStorage.setItem('lan-voice',selectedVoice);await refresh();toast('设置已保存。');}catch(e){toast(e.message);}};
$('#engine').onchange=engineFields;
$('#voice-toggle').onclick=async()=>{if(!app)return;const enabled=!app.settings.voice;if(!enabled)$('#stop-voice').click();try{await api('settings',{voice:enabled});await refresh();}catch(e){toast(e.message);}};
$('#stop-voice').onclick=()=>{const context=voiceContext;stopVoice();if(context?.generation_id&&context?.request_id)api('chat/stop',cancelPayload(context.request_id,context.generation_id)).catch(e=>toast(e.message));};
$('#mobile-voice').onclick=()=>$('#voice-toggle').click();
$('#test-voice').onclick=()=>{selectedVoice=$('#voice-select').value;speak('你好，我是'+(app?.settings.name||'小岚')+'。今天过得怎么样？');};
$('#notify-permission').onclick=async()=>{if(!('Notification'in window)){toast('此浏览器不支持通知。');return;}const p=await Notification.requestPermission();toast(p==='granted'?'已开启。应用运行时可通知你。':'没有开启通知，仍会在应用里提醒。');};
$('#clear-chat').onclick=async()=>{if(!confirm('清空聊天记录？已保存的记忆和约定会保留。'))return;try{$('#stop-voice').click();await api('conversation/clear',{});await refresh();toast('对话已清空。');}catch(e){toast(e.message);}};
$('#export').onclick=async()=>{try{const data=await api('export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='小岚-聊天与记忆-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出，请妥善保管个人聊天。');}catch(e){toast(e.message);}};
for(const id of ['quiet-start','quiet-end'])for(let h=0;h<24;h++){const o=element('option','',String(h).padStart(2,'0')+':00');o.value=h;$('#'+id).append(o);}
const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SpeechRecognition){recognition=new SpeechRecognition();recognition.lang='zh-CN';recognition.interimResults=false;recognition.onresult=e=>{const t=e.results[0][0].transcript;$('#message-input').value+=t;$('#message-input').focus();};recognition.onend=()=>{recording=false;$('#mic').textContent='🎙';};recognition.onerror=()=>toast('没能识别声音。请检查麦克风权限或改用文字。');}
$('#mic').onclick=()=>{if(!recognition){toast('此浏览器不支持语音输入，请用 Chrome 并允许麦克风。');return;}if(recording){recognition.stop();return;}if(!localStorage.getItem('lan-mic-consent')){if(!confirm('语音输入由浏览器提供，部分浏览器会将录音发送到在线识别服务。是否继续？'))return;localStorage.setItem('lan-mic-consent','yes');}try{recognition.start();recording=true;$('#mic').textContent='■';toast('正在听，识别后会填入输入框，不自动发送。');}catch(e){toast('无法开始录音，请稍后重试。');}};
if('speechSynthesis'in window)speechSynthesis.onvoiceschanged=fillVoices;
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
refresh();setInterval(()=>{if(!document.hidden)refresh();},5000);

$('#restore-backup').onclick=()=>$('#backup-file').click();
$('#backup-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>900000){toast('备份文件过大。');return;}if(!confirm('恢复将替换聊天、记忆、约定与角色；API设置和密钥不变。未完成约定会暂停。如果曾删除记忆，旧对话不会导入，以免忘记的事实重新出现。')){e.target.value='';return;}try{const backup=JSON.parse(await file.text());const result=await api('restore',{backup});await refresh();fillSettings();toast(result.chat_skipped?'已恢复，旧对话因遗忘记录未导入。':'备份已恢复，未完成约定已暂停。');}catch(err){toast(err.message);}e.target.value='';};

function stopVoice(){
 // Invalidate callbacks before cancel/pause, which can dispatch old events.
 voiceSerial++;if('speechSynthesis'in window)speechSynthesis.cancel();
 if(voiceCleanup)voiceCleanup();
 if(voiceRequest){voiceRequest.abort();voiceRequest=null;}
 voiceContext=null;document.body.classList.remove('is-speaking');
}
async function localSpeak(text,context={}){
 const serial=voiceSerial,controller=new AbortController();voiceRequest=controller;
 // Historical messages are resolved by ID on the server, never by client text.
 const payload=context.generation_id&&context.request_id?{text:text.slice(0,700),generation_id:context.generation_id,request_id:context.request_id}:context.message_id!==undefined?{message_id:context.message_id}:{text:text.slice(0,700)};
 let cleanup=null;
 try{
  const r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(payload),signal:controller.signal});
  if(!r.ok){const body=await r.json();throw new Error(body.error||'语音合成失败。');}
  const blob=await r.blob();if(serial!==voiceSerial)return;
  const url=URL.createObjectURL(blob),audio=new Audio(url);let disposed=false;
  const current=()=>serial===voiceSerial&&localAudio===audio;
  cleanup=()=>{
   if(disposed)return;disposed=true;
   audio.onerror=null;audio.onended=null;audio.onplay=null;audio.pause();audio.src='';URL.revokeObjectURL(url);
   if(localAudio===audio)localAudio=null;if(audioUrl===url)audioUrl=null;if(voiceCleanup===cleanup)voiceCleanup=null;
  };
  audioUrl=url;localAudio=audio;voiceCleanup=cleanup;
  audio.onplay=()=>{if(current())document.body.classList.add('is-speaking');else cleanup();};
  audio.onended=()=>{if(!current())return;document.body.classList.remove('is-speaking');voiceContext=null;cleanup();};
  audio.onerror=()=>{if(!current())return;document.body.classList.remove('is-speaking');voiceContext=null;cleanup();toast('声音无法播放，请重试。');};
  await audio.play();if(!current())cleanup();
 }catch(e){
  if(cleanup)cleanup();
  if(serial===voiceSerial){document.body.classList.remove('is-speaking');voiceContext=null;if(e.name!=='AbortError')toast(e.name==='NotAllowedError'?'点击消息下的「朗读」即可播放。':e.message);}
 }finally{if(voiceRequest===controller)voiceRequest=null;}
}
window.addEventListener('pagehide',stopVoice);
