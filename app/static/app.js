'use strict';
const $=s=>document.querySelector(s);
let app=null,view='chat',busy=false,lastSeen=0,selectedVoice=localStorage.getItem('lan-voice')||'',polling=false;
let recognition=null,recording=false,localAudio=null,voiceRequest=null,audioUrl=null,voiceSerial=0;
let voiceCleanup=null,voiceContext=null,activeGeneration='',activePlayback=null;
const playbackNotes=new Map();
let streamDraft=null,activeRequest="",stopping=false,failedSend=null;
let contextEpoch=0,refreshSerial=0,chatController=null,charactersBusy=false,characterSpeaking=false,chatCollapsed=false,contextInvalidated=false;
let recognitionEpoch=0,recognitionCharacter='';
let inputMode=localStorage.getItem('voice-input-mode')==='browser'?'browser':'local';
const localInput=window.CompanionVoiceInput?.create({getCharacterId:()=>currentCharacterId(),isHidden:isViewHidden,onDraft:text=>{if(isViewHidden())return;$('#message-input').value+=text;$('#message-input').focus();},onStatus:phase=>{const mic=$('#mic');mic.textContent=phase==='recording'?'■':phase==='idle'?'🎙':'…';mic.setAttribute('aria-label',phase==='recording'?'结束录音':phase==='idle'?'语音输入':'取消识别');},onError:text=>toast(text)});
let pendingAsset=null,pendingAssetCharacter='',assetRequestSerial=0,assetLoadedFor='',appearanceAssets=[],characterListKey='';
let localPreviewUrls={};
let pngBlinkTimer=0,pngBlinkEndTimer=0,pngBlinkActive=false,pngBlinkKey='';
const characterDrafts=new Map();
const mediaChannel=typeof BroadcastChannel==='function'?new BroadcastChannel('companion-media'):null;
const mediaOwner=crypto.randomUUID();let mediaClaimToken='',mediaClock=0;
if(mediaChannel)mediaChannel.onmessage=event=>{
 const data=event.data;if(data?.owner===mediaOwner)return;
 if(data?.type==='claim'){
  if(Number.isSafeInteger(data.clock))mediaClock=Math.max(mediaClock,data.clock);
  if(typeof data.token!=='string'||data.token>mediaClaimToken){mediaClaimToken=typeof data.token==='string'?data.token:mediaClaimToken;stopVoice();}
 }
 if(data?.type==='character-changed'){stopVoice();refresh(true);}
};
function claimMedia(){mediaClock=Math.max(Date.now(),mediaClock+1);mediaClaimToken=String(mediaClock).padStart(20,'0')+'-'+mediaOwner;if(mediaChannel)mediaChannel.postMessage({type:'claim',owner:mediaOwner,clock:mediaClock,token:mediaClaimToken});}
function isViewHidden(){return document.hidden||window.companionDesktopHidden===true;}
function currentCharacterId(){return typeof app?.active_character_id==='string'?app.active_character_id:'';}
function scopedPayload(payload,characterId=currentCharacterId()){
 const data={...payload};if(characterId&&data.expected_character_id===undefined)data.expected_character_id=characterId;return data;
}
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,3800);}
async function api(path,data){
 const payload=data===undefined?undefined:path.startsWith('characters/')?data:scopedPayload(data);
 const opts=payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(payload)};
 const response=await fetch('/api/'+path,opts);
 const result=await response.json();
 if(!response.ok)throw new Error(result.error||'请求失败，请稍后再试。');
 if(!path.startsWith('characters/')&&payload?.expected_character_id&&payload.expected_character_id!==currentCharacterId())throw new Error('角色已切换，请在当前角色重试。');
 return result;
}

function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function localTime(text){return new Date(text).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}
function showView(name){view=name;document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!=='view-'+name);document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('#view-title').textContent=({chat:'聊天',memory:'记忆',tasks:'约定',settings:'设置',characters:'我的角色',connectors:'平台连接'})[name];if(name==='settings')fillSettings();if(name==='characters'){renderCharacters();loadAppearanceAssets();}if(name!=='characters'){disposePreviewVrm();if(['vrm','live2d'].includes(pendingAsset?.format))$('#activate-appearance').disabled=true;}else if(['vrm','live2d'].includes(pendingAsset?.format)&&!previewVrm){renderVrmPreview(pendingAsset);}}
function playbackNoteKey(meta){return meta.character_id+':'+meta.message_id;}
function recordPlaybackNote(meta,status,result={}){
 const key=playbackNoteKey(meta),previous=playbackNotes.get(key);if(previous&&previous.playback_id!==meta.playback_id&&status!=='pending')return;
 const label=({pending:'等待朗读',playing:'正在朗读',stopping:'朗读已停止',finishing:'正在确认播放',stopped:'朗读已停止',completed:Number(result.confirmed_characters)<Number(meta.text_length)?'已播放合成部分':'播放完成',stale:'播放回执已过期',unconfirmed:'播放回执未确认'})[status]||'';
 playbackNotes.delete(key);playbackNotes.set(key,{playback_id:meta.playback_id,label});while(playbackNotes.size>512)playbackNotes.delete(playbackNotes.keys().next().value);
 if(meta.character_id===currentCharacterId()){const note=document.querySelector('[data-message-id="'+meta.message_id+'"] .playback-status');if(note)note.textContent=label;}
}
function makePlayback(meta,serial){if(!meta)return null;if(!window.CompanionPlayback)throw new Error('播放回执组件未能读取，请重新打开应用。');return window.CompanionPlayback.create(meta,{onState:(status,result)=>recordPlaybackNote(meta,status,result),onLimit:()=>{if(serial===voiceSerial){stopVoice();toast('这段朗读已达到时长上限，请继续查看文字。');}}});}
async function systemPlayback(context,serial){
 if(!window.CompanionPlayback||(!context.message_id&&!(context.generation_id&&context.request_id)))return null;
 const payload=context.generation_id&&context.request_id?{generation_id:context.generation_id,request_id:context.request_id}:{message_id:context.message_id};
 const response=await fetch('/api/playback/start',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(scopedPayload(payload,context.character_id||currentCharacterId()))});
 const result=await response.json();if(!response.ok)throw new Error(result.error||'无法开始这条朗读。');return makePlayback(result.playback,serial);
}

function voices(){if(!('speechSynthesis'in window))return [];return speechSynthesis.getVoices();}
async function speak(text,context={}){
 if(isViewHidden()){stopVoice();return;}
 stopVoice();claimMedia();const serial=voiceSerial;voiceContext={...context};
 if(app?.settings?.voice_backend&&app.settings.voice_backend!=='system'){if(!app.local_voice_available){toast('本机语音尚未准备好，请完成安装或选择系统音色。');return;}await localSpeak(text,context);return;}
 if(!app?.settings?.voice_backend&&(!selectedVoice||selectedVoice==='__local__'||!voices().length)&&app?.local_voice_available){await localSpeak(text,context);return;}
 if(!('speechSynthesis'in window)){toast('当前浏览器不支持朗读。试试 Chrome 或系统浏览器。');return;}
 const all=voices();
 if(!all.length){toast('浏览器暂未提供语音。请检查系统中文语音包，或稍后重试。');return;}
 let receipt=null;try{receipt=await systemPlayback(context,serial);}catch(error){if(serial===voiceSerial)toast(error.message);return;}
 if(serial!==voiceSerial||isViewHidden()){receipt?.stop();return;}activePlayback=receipt;
 speechSynthesis.cancel();
 const u=new SpeechSynthesisUtterance(receipt?text:text.replace(/https?:\/\/\S+/g,'链接').replace(/[*#_`]/g,''));
 u.lang='zh-CN';u.rate=app?.settings.voice_rate||1;u.pitch=1.04;
 u.voice=all.find(v=>v.voiceURI===selectedVoice)||all.find(v=>v.lang.startsWith('zh')&&/female|xiaoxiao|ting|hui|女/i.test(v.name))||all.find(v=>v.lang.startsWith('zh'))||all[0];
 u.onerror=e=>{receipt?.stop();if(activePlayback===receipt)activePlayback=null;if(serial!==voiceSerial)return;document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;if(!['canceled','interrupted'].includes(e.error))toast('朗读没有成功，请检查系统音色。');};
 u.onstart=()=>{if(serial===voiceSerial&&!isViewHidden()){receipt?.startSystem();document.body.classList.add('is-speaking');setCharacterSpeaking(true);}};u.onend=()=>{if(serial===voiceSerial){receipt?.complete();if(activePlayback===receipt)activePlayback=null;document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;}};
 speechSynthesis.speak(u);
}
function fillVoices(){const select=$('#voice-select');select.replaceChildren(element('option','', '自动选择中文音色'));select.firstChild.value='';if(!app?.settings?.voice_backend&&app?.local_voice_available){const option=element('option','','本地中文合成');option.value='__local__';select.append(option);}for(const v of voices()){const op=element('option','',v.name+' · '+v.lang);op.value=v.voiceURI;select.append(op);}select.value=selectedVoice;}
function messageNode(m){
 const row=element('article','message '+m.role);row.dataset.messageId=m.id;
 const avatar=element('div','mini-avatar',m.role==='user'?'你':app.settings.name.slice(0,1));
 const wrap=element('div','bubble-wrap');wrap.append(element('div','bubble'+(['reminder','proactive'].includes(m.kind)?' reminder':''),m.text));
 const foot=element('div','message-foot');foot.append(element('span','',localTime(m.created)));
 if(m.role==='assistant'){const b=element('button','read-button','朗读');b.type='button';b.setAttribute('aria-label','朗读这条消息');const characterId=currentCharacterId();b.addEventListener('click',()=>{if(characterId&&characterId!==currentCharacterId())return;speak(m.text,{message_id:m.id,character_id:characterId});});foot.append(b);}
 if(m.role==='assistant'){const note=element('span','playback-status',playbackNotes.get(currentCharacterId()+':'+m.id)?.label||'');foot.append(note);}
 wrap.append(foot);row.append(avatar,wrap);return row;
}
function renderMessages(){
 const root=$('#messages'),nearBottom=root.scrollHeight-root.scrollTop-root.clientHeight<110;
 const ids=currentCharacterId()+':'+app.settings.name+':'+app.messages.map(m=>m.id).join(',');
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
 engineFields();voiceFields();fillVoices();refreshVoiceStatus();
 $('#timezone').textContent='时间按应用所在电脑：'+app.timezone+'。开始和结束相同表示不设安静时段。';
 $('#local-model-note').textContent=!app.runtime_installed?'还没有本地推理组件。运行「安装本地模型」或选择 API。':!app.model_installed?'本地模型还未下载完成。运行安装脚本后再开始聊天。':'本地模型已安装。首次聊天需要加载，回复质量受小模型能力限制。';
}
function engineFields(){const isApi=$('#engine').value==='api';$('#api-fields').hidden=!isApi;$('#local-model-note').hidden=isApi;$('#compute-fields').hidden=isApi;}
function voiceFields(){syncAsrPrecision();$('#external-tts-fields').hidden=$('#voice-backend').value!=='external';$('#voice-select').disabled=$('#voice-backend').value!=='system';$('#system-voice-field').hidden=$('#voice-backend').value!=='system';$('#asr-mode').value=inputMode;$('#local-asr-fields').hidden=inputMode!=='local';$('#browser-asr-notice').hidden=inputMode!=='browser';}
function syncAsrPrecision(){const device=$('#asr-device').value,precision=$('#asr-precision'),allowed=device==='cuda'?['float16','int8_float16','float32']:['int8','float32'];for(const option of precision.options||[])option.disabled=!allowed.includes(option.value);if(!allowed.includes(precision.value))precision.value=device==='cuda'?'float16':'int8';}
async function refreshVoiceStatus(){const epoch=contextEpoch;try{const status=await api('voice/status');if(epoch===contextEpoch)$('#local-asr-status').textContent=status.asr?.ready?'本机识别已准备好 · 最长60秒':status.asr?.reason||'本机识别尚未准备好。';}catch{if(epoch===contextEpoch)$('#local-asr-status').textContent='无法读取语音状态。';}}
function render(){
 document.querySelectorAll('[data-mode]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.mode===app.settings.conversation_mode));b.disabled=busy||app.model_busy;});
 $('#memory-toggle').textContent=app.settings.memory_mode==='off'?'只聊当下':'记忆按需';$('#memory-toggle').setAttribute('aria-pressed',String(app.settings.memory_mode!=='off'));$('#memory-toggle').disabled=busy||app.model_busy;
 $('#mobile-voice').setAttribute('aria-pressed',String(app.settings.voice));
 $('#portrait-line').textContent=({daily:'一点小事，也想听你说。',listen:'慢慢说，我在听。',playful:'今天也找点小小的快乐吧。'})[app.settings.conversation_mode];
 if(!busy){$('#thinking').hidden=!app.model_busy;if(app.model_busy)$('#thinking span').textContent='还有一条回复正在进行…';}
 $('#portrait-name').textContent=app.settings.name;document.title=app.settings.name+' · 陪你慢慢聊';
 if(view==='chat')$('#view-title').textContent='聊天';
 $('#voice-toggle').textContent=app.settings.voice?'♪ 语音开启':'♪ 语音关闭';$('#voice-toggle').setAttribute('aria-pressed',String(app.settings.voice));
 let status=app.settings.engine==='api'?'模型 API · '+app.settings.api_model:app.model_status==='loading'?'正在加载本地模型…':!app.model_installed?'本地模型未安装 · 请打开设置':'本地模型 · '+app.model_label+' · '+(app.model_status==='ready'?'已就绪':'首次聊天时加载');
 $('#connection').textContent=status;$('#task-hint').textContent='应用运行时在这里提醒，时间按 '+app.timezone+'。尚未接入微信。';
 renderMessages();renderMemories();renderTasks();renderCharacterPicker();renderCharacterImage();if(view==='characters')renderCharacters();
}
async function refresh(force=false){
 if(polling&&!force)return;polling=true;
 const serial=++refreshSerial,epoch=contextEpoch;
 try{
  const fresh=await api('state');if(serial!==refreshSerial||epoch!==contextEpoch)return;
  adoptState(fresh);
 }catch(e){if(serial===refreshSerial)$('#connection').textContent='连接中断 · 请确认应用仍在运行';}
 finally{if(serial===refreshSerial)polling=false;}
}
function adoptState(fresh){
 const previous=currentCharacterId(),next=typeof fresh.active_character_id==='string'?fresh.active_character_id:'';
 const changed=Boolean(previous&&next&&previous!==next);
 const previousAsset=activeAppearance()?.id||app?.active_character?.appearance_id||null,nextAsset=fresh.active_character?.appearance?.id||fresh.active_character?.appearance_id||null;
 if(previous&&previous===next&&previousAsset!==nextAsset)stopVoice();
 if(changed){invalidateCharacterContext();window.CompanionConnectorsUI?.resetCharacter();}
 const incoming=changed?[]:fresh.messages.filter(m=>m.id>lastSeen&&m.role==='assistant'&&['reminder','proactive'].includes(m.kind));
 app=fresh;contextInvalidated=false;if(next&&(changed||!previous))selectedVoice=localStorage.getItem('character-voice:'+next)||(!previous?selectedVoice:'');render();
 if(changed){$('#message-input').value=characterDrafts.get(next)||'';if(view==='settings')fillSettings();if(view==='characters')loadAppearanceAssets(true);}
 if(lastSeen&&incoming.length){for(const m of incoming){toast(m.text);if(app.settings.voice&&!busy&&!stopping)speak(m.text,{message_id:m.id});if('Notification'in window&&Notification.permission==='granted'&&document.hidden)new Notification(app.settings.name,{body:m.text});}}
 lastSeen=Math.max(lastSeen,...app.messages.map(m=>m.id));
}
function invalidateCharacterContext(){
 const id=currentCharacterId();if(id&&!contextInvalidated)characterDrafts.set(id,$('#message-input').value);contextInvalidated=true;
 contextEpoch++;assetRequestSerial++;stopVoice();disposeStageVrm();stopPngBlink();if(chatController)chatController.abort();chatController=null;
 if(recording&&recognition){recognition.abort();recording=false;}localInput?.cancel();
 streamDraft=null;activeRequest='';activeGeneration='';failedSend=null;stopping=false;lastSeen=0;assetLoadedFor='';appearanceAssets=[];
 $('#message-input').value='';$('#memory-input').value='';$('#task-title').value='';$('#error').hidden=true;
 const form=$('#settings-form');if(form.elements?.api_key)form.elements.api_key.value='';
 clearAppearancePreview();resetFileInputs();setBusy(false);
}

function setBusy(value){
 busy=value;$('#send').disabled=value||charactersBusy;$('#thinking').hidden=!value;document.body.classList.toggle('is-thinking',value);
 $('#thinking span').textContent=value?(app?.settings.engine==='local'&&app?.model_status!=='ready'?'正在加载本地模型…':'正在回复…'):'';
 if(!value){stopping=false;$('#stop-generation').disabled=false;}
 if(app){document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=value);$('#memory-toggle').disabled=value;updateRetry();}
}
async function runChat(text,retryId=null){
 if(busy||charactersBusy||app?.model_busy){toast('先等上一条回复结束，或点击停止。');return;}
 stopVoice();$('#error').hidden=true;setBusy(true);activeRequest=retryId===null&&failedSend?.text===text?failedSend.rid:crypto.randomUUID();
 const rid=activeRequest,characterId=currentCharacterId(),epoch=contextEpoch,controller=new AbortController();chatController=controller;activeGeneration='';streamDraft={rid,text:''};let finished=false,failed=false;
 try{
  const payload=scopedPayload({text,request_id:rid},characterId);if(retryId!==null)payload.retry_message_id=retryId;
  const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(scopedPayload(payload)),signal:controller.signal});
  if(!response.ok){const error=await response.json();throw new Error(error.error||'连接失败。');}
  if(!response.body)throw new Error('浏览器不支持流式回复，请更新浏览器。');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  async function event(data){
   if(activeRequest!==rid||epoch!==contextEpoch||currentCharacterId()!==characterId)return;
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
 }catch(e){if(epoch===contextEpoch&&e.name!=='AbortError'){failed=true;if(retryId===null)failedSend={rid,text};$('#error').textContent=e.message;$('#error').hidden=false;}}
 finally{if(chatController===controller)chatController=null;if(epoch===contextEpoch){streamDraft=null;activeRequest='';activeGeneration='';await refresh();if(epoch===contextEpoch){renderMessages();setBusy(false);if(failed&&retryId===null&&!app.messages.some(m=>m.role==='user'&&m.request_id===rid)&&!$('#message-input').value)$('#message-input').value=text;$('#message-input').focus();}}}
}
async function send(){
 const input=$('#message-input'),text=input.value.trim();if(!text||busy||charactersBusy||app?.model_busy)return;
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
$('#settings-form').onsubmit=async e=>{e.preventDefault();const f=e.target,data={};for(const input of f.elements){if(!input.name)continue;data[input.name]=input.type==='checkbox'?input.checked:['quiet_start','quiet_end','voice_rate','local_gpu_layers','local_context'].includes(input.name)?Number(input.value):input.value;}try{await api('settings',data);selectedVoice=$('#voice-select').value;localStorage.setItem('character-voice:'+currentCharacterId(),selectedVoice);await refresh();toast('设置已保存。');}catch(e){toast(e.message);}};
$('#engine').onchange=engineFields;
$('#voice-backend').onchange=voiceFields;
$('#asr-device').onchange=syncAsrPrecision;
$('#asr-mode').value=inputMode;$('#asr-mode').onchange=event=>{localInput?.cancel();if(recording&&recognition){recognition.abort();recording=false;}inputMode=event.target.value==='browser'?'browser':'local';localStorage.setItem('voice-input-mode',inputMode);voiceFields();};
$('#voice-toggle').onclick=async()=>{if(!app)return;const enabled=!app.settings.voice;if(!enabled)$('#stop-voice').click();try{await api('settings',{voice:enabled});await refresh();}catch(e){toast(e.message);}};
$('#stop-voice').onclick=()=>{const context=voiceContext;stopVoice();if(context?.generation_id&&context?.request_id)api('chat/stop',cancelPayload(context.request_id,context.generation_id)).catch(e=>toast(e.message));};
$('#mobile-voice').onclick=()=>$('#voice-toggle').click();
$('#test-voice').onclick=()=>{selectedVoice=$('#voice-select').value;speak('你好，我是'+(app?.settings.name||'陪伴角色')+'。今天过得怎么样？');};
$('#notify-permission').onclick=async()=>{if(!('Notification'in window)){toast('此浏览器不支持通知。');return;}const p=await Notification.requestPermission();toast(p==='granted'?'已开启。应用运行时可通知你。':'没有开启通知，仍会在应用里提醒。');};
$('#clear-chat').onclick=async()=>{if(!confirm('清空聊天记录？已保存的记忆和约定会保留。'))return;try{$('#stop-voice').click();await api('conversation/clear',{});await refresh();toast('对话已清空。');}catch(e){toast(e.message);}};
$('#export').onclick=async()=>{const epoch=contextEpoch;try{const data=await api('export');if(epoch!==contextEpoch)throw new Error('角色已切换，请重新导出。');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=(app?.settings.name||'角色')+'-聊天与记忆-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出，请妥善保管个人聊天。');}catch(e){toast(e.message);}};
for(const id of ['quiet-start','quiet-end'])for(let h=0;h<24;h++){const o=element('option','',String(h).padStart(2,'0')+':00');o.value=h;$('#'+id).append(o);}
const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SpeechRecognition){recognition=new SpeechRecognition();recognition.lang='zh-CN';recognition.interimResults=false;recognition.onresult=e=>{if(isViewHidden()||!recording||recognitionEpoch!==contextEpoch||recognitionCharacter!==currentCharacterId())return;const t=e.results[0][0].transcript;$('#message-input').value+=t;$('#message-input').focus();};recognition.onend=()=>{recording=false;$('#mic').textContent='🎙';};recognition.onerror=()=>toast('没能识别声音。请检查麦克风权限或改用文字。');}
$('#mic').onclick=()=>{if(inputMode==='local'){if(!localInput){toast('本地录音组件未能读取，请重新打开应用。');return;}if(localInput.phase==='idle')localInput.start();else localInput.stop();return;}if(!recognition){toast('此浏览器不支持语音输入，请用 Chrome 并允许麦克风。');return;}if(recording){recognition.stop();return;}if(!localStorage.getItem('lan-mic-consent')){if(!confirm('语音输入由浏览器提供，部分浏览器会将录音发送到在线识别服务。是否继续？'))return;localStorage.setItem('lan-mic-consent','yes');}try{recognitionEpoch=contextEpoch;recognitionCharacter=currentCharacterId();recognition.start();recording=true;$('#mic').textContent='■';toast('正在听，识别后会填入输入框，不自动发送。');}catch(e){toast('无法开始录音，请稍后重试。');}};
if('speechSynthesis'in window)speechSynthesis.onvoiceschanged=fillVoices;
document.addEventListener('visibilitychange',()=>{if(document.hidden){stopVoice();localInput?.cancel();if(recording&&recognition){recognition.abort();recording=false;}}else refresh();});
refresh();setInterval(()=>{if(!isViewHidden())refresh();},5000);

$('#restore-backup').onclick=()=>$('#backup-file').click();
$('#backup-file').onchange=async e=>{const epoch=contextEpoch,characterId=currentCharacterId();const file=e.target.files[0];if(!file)return;if(file.size>900000){toast('备份文件过大。');return;}if(!confirm('恢复将替换聊天、记忆、约定与角色；API设置和密钥不变。未完成约定会暂停。如果曾删除记忆，旧对话不会导入，以免忘记的事实重新出现。')){e.target.value='';return;}try{const backup=JSON.parse(await file.text());if(epoch!==contextEpoch||characterId!==currentCharacterId())throw new Error('角色已切换，请重新选择备份。');const result=await api('restore',scopedPayload({backup},characterId));await refresh();fillSettings();toast(result.chat_skipped?'已恢复，旧对话因遗忘记录未导入。':'备份已恢复，未完成约定已暂停。');}catch(err){toast(err.message);}e.target.value='';};

function stopVoice(){
 // Capture the original media position before cancellation clears it.
 activePlayback?.stop();activePlayback=null;
 // Invalidate callbacks before cancel/pause, which can dispatch old events.
 voiceSerial++;if('speechSynthesis'in window)speechSynthesis.cancel();
 if(voiceCleanup)voiceCleanup();
 if(voiceRequest){voiceRequest.abort();voiceRequest=null;}
 voiceContext=null;document.body.classList.remove('is-speaking');setCharacterSpeaking(false);
}
async function localSpeak(text,context={}){
 const serial=voiceSerial,controller=new AbortController(),requestedCharacter=context.character_id||currentCharacterId(),requestedAppearance=app?.active_character?.appearance_id||null;voiceRequest=controller;
 // Historical messages are resolved by ID on the server, never by client text.
 const payload=context.generation_id&&context.request_id?{text:text.slice(0,700),generation_id:context.generation_id,request_id:context.request_id}:context.message_id!==undefined?{message_id:context.message_id}:{text:text.slice(0,700)};
 let cleanup=null,receipt=null;
 try{
  const r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(scopedPayload(payload,context.character_id||currentCharacterId())),signal:controller.signal});
  if(!r.ok){const body=await r.json();throw new Error(body.error||'语音合成失败。');}
  const header=r.headers?.get?.('X-Companion-Playback');if(header){if(!window.CompanionPlayback)throw new Error('播放回执组件未能读取，请重新打开应用。');const meta=window.CompanionPlayback.fromHeader(header);receipt=makePlayback(meta,serial);if(serial!==voiceSerial||isViewHidden()){receipt?.stop();return;}if(meta.character_id!==requestedCharacter||meta.appearance_id!==requestedAppearance){receipt?.stop();throw new Error('声音所属角色已改变，请重试。');}activePlayback=receipt;}
  const blob=await r.blob();if(serial!==voiceSerial||isViewHidden()){receipt?.stop();return;}
  const url=URL.createObjectURL(blob),audio=new Audio(url);receipt?.attachAudio(audio);let disposed=false;
  const current=()=>serial===voiceSerial&&localAudio===audio;
  cleanup=()=>{
   if(disposed)return;disposed=true;receipt?.stop();if(activePlayback===receipt)activePlayback=null;
   audio.onerror=null;audio.onended=null;audio.onplay=null;audio.onpause=null;audio.ontimeupdate=null;audio.pause();audio.src='';URL.revokeObjectURL(url);
   if(localAudio===audio)localAudio=null;if(audioUrl===url)audioUrl=null;if(voiceCleanup===cleanup)voiceCleanup=null;
  };
  audioUrl=url;localAudio=audio;voiceCleanup=cleanup;
  audio.onplay=()=>{if(current()){receipt?.progress(true);document.body.classList.add('is-speaking');setCharacterSpeaking(true);}else cleanup();};
  audio.ontimeupdate=()=>{if(current())receipt?.progress();};
  audio.onpause=()=>{if(current()&&!audio.ended){receipt?.stop();document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;cleanup();}};
  audio.onended=()=>{if(!current())return;receipt?.complete();document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;cleanup();};
  audio.onerror=()=>{if(!current())return;document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;cleanup();toast('声音无法播放，请重试。');};
  await audio.play();if(!current())cleanup();
 }catch(e){
  receipt?.stop();if(activePlayback===receipt)activePlayback=null;if(cleanup)cleanup();
  if(serial===voiceSerial){document.body.classList.remove('is-speaking');setCharacterSpeaking(false);voiceContext=null;if(e.name!=='AbortError')toast(e.name==='NotAllowedError'?'点击消息下的「朗读」即可播放。':e.message);}
 }finally{if(voiceRequest===controller)voiceRequest=null;}
}
window.addEventListener('pagehide',()=>{stopVoice();localInput?.cancel();});


// VRM is loaded only from locally validated, authenticated character assets.
let live2dBundlePromise=null,live2dRuntimePromise=null;
let vrmBundlePromise=null,stageVrm=null,previewVrm=null,stageVrmKey='',stageVrmSerial=0,previewVrmSerial=0,pendingVrmReady=false;
function vrmFps(mode){const stored=Number(localStorage.getItem('vrm-fps-'+mode));return mode==='collapsed'?[20,30].includes(stored)?stored:30:[30,60].includes(stored)?stored:60;}
function ensureVrmBundle(){
 if(window.CompanionVrm?.create)return Promise.resolve(window.CompanionVrm);
 if(!vrmBundlePromise)vrmBundlePromise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/vrm-renderer.js';script.onload=()=>window.CompanionVrm?.create?resolve(window.CompanionVrm):reject(new Error('三维组件未能启动。'));script.onerror=()=>{script.remove();vrmBundlePromise=null;reject(new Error('三维组件读取失败，请重试。'));};document.head.append(script);});
 return vrmBundlePromise;
}
function loadTrustedScript(path){return new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=path;script.onload=resolve;script.onerror=()=>{script.remove();reject(new Error('运行时读取失败，请检查本机安装。'));};document.head.append(script);});}
function live2DStatusReason(status){if(typeof status.reason==='string'&&/[\u3400-\u9fff]/.test(status.reason))return status.reason;if(status.core_available&&!status.bundle_available)return 'Live2D Core 已安装，还需要完成显示框架的授权安装。';return 'Live2D 运行时尚未准备好，请先完成授权安装。';}
async function ensureLive2DRuntime(){
 const status=await api('live2d/runtime');
 if(!status.available||status.core_url!=='/live2d-core.js')throw new Error(live2DStatusReason(status));
 if(status.runtime_url!=='/live2d-runtime.js')throw new Error('Live2D 显示框架尚未安装；请先完成合法运行时安装。');
 if(!live2dRuntimePromise)live2dRuntimePromise=(async()=>{if(!window.Live2DCubismCore)await loadTrustedScript('/live2d-core.js');if(!window.CompanionLive2DRuntime)await loadTrustedScript('/live2d-runtime.js');if(!window.Live2DCubismCore||!window.CompanionLive2DRuntime?.Live2DModel)throw new Error('Live2D 运行时与显示框架不匹配。');})().catch(error=>{live2dRuntimePromise=null;throw error;});
 await live2dRuntimePromise;
 if(!live2dBundlePromise)live2dBundlePromise=loadTrustedScript('/live2d-renderer.js').then(()=>{if(!window.CompanionLive2D?.create)throw new Error('Live2D 显示组件未能启动。');return window.CompanionLive2D;}).catch(error=>{live2dBundlePromise=null;throw error;});
 return live2dBundlePromise;
}
async function refreshLive2DStatus(){try{const status=await api('live2d/runtime');$('#live2d-runtime-status').textContent=status.available&&status.runtime_url?'本机运行时已安装；模型兼容性在预览时检查。':live2DStatusReason(status);}catch{$('#live2d-runtime-status').textContent='无法读取本机运行时状态。';}}
function ensureCharacterRenderer(asset){return asset?.format==='live2d'?ensureLive2DRuntime():ensureVrmBundle();}
function disposeStageVrm(){stageVrmSerial++;stageVrm?.dispose();stageVrm=null;stageVrmKey='';const stage=$('#vrm-stage');if(stage)stage.hidden=true;}
function disposePreviewVrm(){previewVrmSerial++;previewVrm?.dispose();previewVrm=null;pendingVrmReady=false;const stage=$('#vrm-preview');if(stage){stage.hidden=true;stage.dataset.state='empty';}}
function showVrmStageError(text){const message=$('#vrm-stage-message');if(message){message.hidden=false;$('#vrm-stage-status').textContent=text;$('#vrm-retry').hidden=false;}$('#portrait-avatar').style.visibility='visible';}
function stageIsExpanded(){return !chatCollapsed&&!document.body.classList.contains?.('desktop-collapsed');}
async function renderVrmStage(asset,size){
 const container=$('#vrm-stage');if(!container)return;
 if(isViewHidden()){disposeStageVrm();return;}
 const key=currentCharacterId()+':'+asset.id,url=assetResource(asset,'model');
 if(stageVrmKey===key){stageVrm?.setSpeaking(characterSpeaking);if(characterSpeaking&&localAudio)stageVrm?.setAudio(localAudio);stageVrm?.setScale(size/100);stageVrm?.setExpanded(stageIsExpanded());return;}
 disposeStageVrm();stageVrmKey=key;const ticket=stageVrmSerial;
 $('#vrm-stage-message').hidden=false;$('#vrm-stage-status').textContent='正在准备三维角色…';$('#vrm-retry').hidden=true;
 try{
  const engine=await ensureCharacterRenderer(asset);if(ticket!==stageVrmSerial||isViewHidden())return;
  container.hidden=false;stageVrm=engine.create({container,collapsedFps:vrmFps('collapsed'),expandedFps:vrmFps('expanded'),onError:text=>{if(ticket===stageVrmSerial)showVrmStageError(text);},onStats:stats=>{container.dataset.state=stats.state;container.dataset.frames=String(stats.frames);container.dataset.mouth=String(stats.mouth);container.dataset.blinks=String(stats.blinkCount);}});
  const instance=stageVrm,ready=await instance.load(asset.format==='live2d'?asset:url);
  if(ticket!==stageVrmSerial||stageVrm!==instance)return;
  if(!ready)return;
  $('#vrm-stage-message').hidden=true;$('#portrait-avatar').style.visibility='hidden';instance.setScale(size/100);instance.setExpanded(stageIsExpanded());instance.setSpeaking(characterSpeaking);if(characterSpeaking&&localAudio)instance.setAudio(localAudio);
 }catch(error){if(ticket===stageVrmSerial)showVrmStageError(error.message);}
}
async function renderVrmPreview(asset,epoch=contextEpoch){
 disposePreviewVrm();const ticket=previewVrmSerial;$('#appearance-preview').hidden=false;$('#appearance-preview-image').hidden=true;$('#vrm-preview').hidden=false;$('#preview-states').replaceChildren();$('#vrm-preview-retry').hidden=true;
 const id=asset.id;pendingVrmReady=false;
 try{
  const engine=await ensureCharacterRenderer(asset);if(ticket!==previewVrmSerial||epoch!==contextEpoch||pendingAsset?.id!==id||isViewHidden())return false;
  const container=$('#vrm-preview');previewVrm=engine.create({container,collapsedFps:20,expandedFps:30,onError:text=>{if(pendingAsset?.id===id){pendingVrmReady=false;$('#appearance-status').textContent=text;$('#vrm-preview-retry').hidden=false;$('#activate-appearance').disabled=true;}},onStats:stats=>{container.dataset.state=stats.state;container.dataset.frames=String(stats.frames);}});
  const instance=previewVrm,ready=await instance.load(asset.format==='live2d'?asset:assetResource(asset,'model'));
  if(ticket!==previewVrmSerial||epoch!==contextEpoch||previewVrm!==instance||pendingAsset?.id!==id){instance.dispose();return false;}
  pendingVrmReady=ready;instance.setHidden(view!=='characters'||isViewHidden());
  $('#activate-appearance').disabled=charactersBusy||!ready;
  if(ready)$('#appearance-status').textContent='动态预览已准备好 · 尚未启用';
  return ready;
 }catch(error){if(epoch===contextEpoch){$('#appearance-status').textContent=error.message;$('#vrm-preview-retry').hidden=false;}return false;}
}
function setAppearanceFormat(){
 assetRequestSerial++;clearAppearancePreview();resetFileInputs();
 const format=$('#appearance-format').value;$('#png-upload-fields').hidden=format!=='png';$('#vrm-upload-fields').hidden=format!=='vrm';$('#live2d-upload-fields').hidden=format!=='live2d';$('#asset-idle').required=format==='png';$('#asset-vrm').required=format==='vrm';$('#asset-live2d').required=format==='live2d';if(format==='live2d')refreshLive2DStatus();
}
async function encodeVrmFile(file){
 if(!file||!/\.vrm$/i.test(file.name))throw new Error('请选择 VRM 模型。');
 if(!file.size||file.size>64*1024*1024)throw new Error('VRM 模型请控制在 64 MB 内。');
 const buffer=await file.arrayBuffer(),header=new DataView(buffer);
 if(buffer.byteLength<20||header.getUint32(0,true)!==0x46546c67||header.getUint32(4,true)!==2||header.getUint32(8,true)!==buffer.byteLength)throw new Error('文件不是完整的 VRM 模型。');
 const bytes=new Uint8Array(buffer);let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
 return {filename:file.name,data_base64:btoa(binary)};
}
async function encodeLive2DFile(file){
 if(!file||!/\.zip$/i.test(file.name))throw new Error('请选择 Live2D ZIP 运行包。');
 if(!file.size||file.size>64*1024*1024)throw new Error('运行包请控制在 64 MB 内。');
 const bytes=new Uint8Array(await file.arrayBuffer());if(bytes.length<4||bytes[0]!==0x50||bytes[1]!==0x4b||bytes[2]!==3||bytes[3]!==4)throw new Error('文件不是有效 ZIP 运行包。');
 let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));return {filename:file.name,data_base64:btoa(binary)};
}
async function previewExistingLive2D(asset){clearAppearancePreview();pendingAsset=asset;pendingAssetCharacter=currentCharacterId();$('#appearance-preview').hidden=false;$('#appearance-status').textContent='正在检查本机运行时…';await renderVrmPreview(asset);}
async function importVrmAppearance(format='vrm'){
 if(charactersBusy)return;const id=currentCharacterId(),file=$(format==='live2d'?'#asset-live2d':'#asset-vrm').files?.[0];if(!id)return;
 const serial=++assetRequestSerial,epoch=contextEpoch;setCharactersBusy(true);$('#character-error').hidden=true;
 try{
  const model=await (format==='live2d'?encodeLive2DFile(file):encodeVrmFile(file));if(epoch!==contextEpoch||serial!==assetRequestSerial)return;
  $('#appearance-preview').hidden=false;$('#appearance-status').textContent='正在检查模型…';
  const result=await api('characters/assets/import',{character_id:id,format,model});
  if(epoch!==contextEpoch||serial!==assetRequestSerial||id!==currentCharacterId()){if(result.asset?.id)api('characters/assets/delete',{character_id:id,asset_id:result.asset.id}).catch(()=>{});return;}
  clearAppearancePreview();pendingAsset=result.asset;pendingAssetCharacter=id;
  const meta=pendingAsset.metadata||{},credit=[meta.name,...(Array.isArray(meta.authors)?meta.authors:[])].filter(x=>typeof x==='string').join(' · ');
  $('#vrm-model-credit').textContent=credit;$('#vrm-model-credit').hidden=!credit;$('#appearance-status').textContent='检查通过，正在准备三维预览…';
  await renderVrmPreview(pendingAsset,epoch);await loadAppearanceAssets(true);
 }catch(error){if(epoch===contextEpoch){characterError(error);$('#appearance-status').textContent='检查未通过，当前形象保持原样。';}}
 finally{setCharactersBusy(false);}
}
function pauseVrmViews(){localInput?.cancel();stopPngBlink();disposeStageVrm();disposePreviewVrm();if(['vrm','live2d'].includes(pendingAsset?.format))$('#activate-appearance').disabled=true;}
function resumeVrmViews(){if(!isViewHidden()){renderCharacterImage();if(view==='characters'&&['vrm','live2d'].includes(pendingAsset?.format)&&!previewVrm)renderVrmPreview(pendingAsset);}}
window.addEventListener('companion:desktop-pause',pauseVrmViews);
document.addEventListener('visibilitychange',()=>document.hidden?pauseVrmViews():resumeVrmViews());
window.addEventListener('pagehide',()=>{stopPngBlink();disposeStageVrm();disposePreviewVrm();});
window.companionDesktop?.onState(state=>{window.companionDesktopHidden=state.visible===false;if(state.visible===false)pauseVrmViews();else{resumeVrmViews();stageVrm?.setExpanded(Boolean(state.expanded));}});

// Character management stays in the same authenticated application and session.
function activeAppearance(){return app?.active_character?.appearance||app?.appearance||null;}
function assetResource(asset,state='idle'){
 const item=state==='thumbnail'?asset?.thumbnail:state==='model'?asset?.model:asset?.states?.[state];
 if(!item)return '';
 if(typeof item.url==='string'&&item.url.startsWith('/api/assets/'))return item.url;
 const id=asset?.id||asset?.asset_id,resource=typeof item==='string'?item:item.resource;
 if(typeof id!=='string'||!/^[a-f0-9-]{36}$/i.test(id)||!['idle.png','talk.png','blink.png','talk_blink.png','thumbnail.png','model.vrm','model.model3.json'].includes(resource))return '';
 const query=currentCharacterId()?'?character_id='+encodeURIComponent(currentCharacterId()):'';
 return '/api/assets/'+id+'/'+resource+query;
}
function stopPngBlink(){clearTimeout(pngBlinkTimer);clearTimeout(pngBlinkEndTimer);pngBlinkTimer=0;pngBlinkEndTimer=0;pngBlinkActive=false;pngBlinkKey='';}
function configurePngBlink(asset){
 const canBlink=asset&&!['vrm','live2d'].includes(asset.format)&&(asset.states?.blink||(characterSpeaking&&asset.states?.talk_blink));
 if(!canBlink||isViewHidden()){stopPngBlink();return;}
 const key=currentCharacterId()+':'+asset.id;
 if(key!==pngBlinkKey){stopPngBlink();pngBlinkKey=key;}
 if(pngBlinkTimer||pngBlinkEndTimer||pngBlinkActive)return;
 const epoch=contextEpoch;pngBlinkTimer=setTimeout(()=>{
  pngBlinkTimer=0;if(epoch!==contextEpoch||pngBlinkKey!==key||isViewHidden()){stopPngBlink();return;}
  pngBlinkActive=true;renderCharacterImage();if(pngBlinkKey!==key)return;pngBlinkEndTimer=setTimeout(()=>{pngBlinkEndTimer=0;if(pngBlinkKey!==key||epoch!==contextEpoch)return;pngBlinkActive=false;renderCharacterImage();},120);
 },1500+Math.random()*4500);
}
function setCharacterSpeaking(value){characterSpeaking=Boolean(value);renderCharacterImage();}
function renderCharacterImage(){
 const image=$('#portrait-avatar');if(!image)return;
 const asset=activeAppearance();configurePngBlink(asset);const state=pngBlinkActive&&characterSpeaking&&asset?.states?.talk_blink?'talk_blink':pngBlinkActive&&asset?.states?.blink?'blink':characterSpeaking&&asset?.states?.talk?'talk':'idle';
 const isVrm=['vrm','live2d'].includes(asset?.format);
 if(!isVrm){disposeStageVrm();$('#vrm-stage-message').hidden=true;image.style.visibility='';}document.querySelector('.illustration')?.classList.toggle('vrm-active',isVrm);
 const src=isVrm?'/avatar.svg':assetResource(asset,state)||'/avatar.svg';
 if(image.dataset.source!==src){image.dataset.source=src;image.src=src;image.onerror=()=>{if(image.dataset.source===src&&src!=='/avatar.svg'){image.dataset.source='/avatar.svg';image.src='/avatar.svg';}};}
 image.alt=(app?.settings?.name||'角色')+'的形象';
 const saved=Number(localStorage.getItem('character-scale:'+currentCharacterId()));
 const size=Number.isFinite(saved)&&saved>=60&&saved<=130?saved:100;
 image.style.transform='scale('+(size/100)+')';$('#character-scale').value=size;
 if(isVrm)renderVrmStage(asset,size);
}
function renderCharacterPicker(){
 const selector=$('#character-select');if(!selector)return;
 const entries=(app?.characters||[]).filter(character=>!character.archived),id=currentCharacterId();
 const key=id+':'+entries.map(character=>character.id+':'+(character.id===id?app.settings.name:character.name)).join('|');
 if(selector.dataset.key!==key){
  selector.dataset.key=key;selector.replaceChildren();
  for(const character of entries){const option=element('option','',character.id===id?app.settings.name:character.name);option.value=character.id;selector.append(option);}
  if(!entries.length){const option=element('option','',app?.settings?.name||'陪伴角色');option.value=id;selector.append(option);}
  selector.value=id;
 }
 selector.disabled=charactersBusy;
}
function setCharactersBusy(value){
 charactersBusy=value;$('#send').disabled=value||busy;$('#character-select').disabled=value;
 $('#character-create-form button').disabled=value;$('#preview-appearance').disabled=value;
 $('#activate-appearance').disabled=value||!pendingAsset||(['vrm','live2d'].includes(pendingAsset.format)&&!pendingVrmReady);
 document.querySelectorAll('[data-character-action]').forEach(button=>button.disabled=value);
 if(assetLoadedFor===currentCharacterId()&&currentCharacterId())renderAppearanceAssets();
}
function characterError(error){const node=$('#character-error');node.textContent=error?.message||String(error);node.hidden=false;}
async function characterAction(path,payload){
 if(charactersBusy)return;
 setCharactersBusy(true);$('#character-error').hidden=true;
 const previous=currentCharacterId();
 // Stop locally before asking the backend to change the active identity.
 if(['create','select','archive','delete'].includes(path)){invalidateCharacterContext();}
 try{
  await api('characters/'+path,payload);if(mediaChannel)mediaChannel.postMessage({type:'character-changed',owner:mediaOwner});await refresh(true);
  if(currentCharacterId()===previous)$('#message-input').value=characterDrafts.get(previous)||'';
  renderCharacters();if(view==='characters')await loadAppearanceAssets(true);
 }catch(error){characterError(error);toast(error.message);await refresh(true);if(currentCharacterId()===previous)$('#message-input').value=characterDrafts.get(previous)||'';}
 finally{setCharactersBusy(false);renderCharacterPicker();}
}
function renderCharacters(){
 if(!app)return;
 const root=$('#character-list'),id=currentCharacterId();
 const key=(app.characters||[]).map(character=>[character.id,character.id===id?app.settings.name:character.name,character.archived,character.appearance_id].join(':')).join('|')+':'+id;
 if(characterListKey===key)return;characterListKey=key;root.replaceChildren();
 for(const character of app.characters||[]){
  const card=element('article','character-card'),heading=element('div','character-card-heading');
  heading.append(element('strong','',character.id===id?app.settings.name:character.name));
  if(character.id===id)heading.append(element('span','character-badge','当前'));else if(character.archived)heading.append(element('span','character-badge','已收起'));
  card.append(heading);const actions=element('div','character-card-actions');
  const add=(label,action,handler)=>{const button=element('button','text-button',label);button.type='button';button.dataset.characterAction=action;button.disabled=charactersBusy;button.onclick=handler;actions.append(button);};
  if(character.archived)add('恢复','restore',()=>characterAction('restore',{id:character.id}));
  else if(character.id!==id)add('切换','select',()=>characterAction('select',{id:character.id}));
  if(!character.archived)add('收起','archive',()=>{if(confirm('收起“'+character.name+'”？聊天与记忆保留，可随时恢复。'))characterAction('archive',{id:character.id});});
  add('删除','delete',()=>{if(confirm('永久删除“'+character.name+'”及其聊天、记忆和约定？此操作无法撤销。'))characterAction('delete',{id:character.id});});
  card.append(actions);root.append(card);
 }
}
function clearAppearancePreview(){
 disposePreviewVrm();$('#appearance-preview-image').hidden=false;$('#vrm-model-credit').hidden=true;$('#vrm-preview-retry').hidden=true;
 pendingAsset=null;pendingAssetCharacter='';
 for(const url of Object.values(localPreviewUrls))URL.revokeObjectURL(url);localPreviewUrls={};
 const image=$('#appearance-preview-image');if(image){image.removeAttribute?.('src');image.src='';}
 $('#appearance-preview').hidden=true;$('#preview-states').replaceChildren();$('#appearance-status').textContent='';$('#activate-appearance').disabled=true;
}
function resetFileInputs(){for(const id of ['asset-idle','asset-talk','asset-blink','asset-talk-blink','asset-vrm','asset-live2d'])$('#'+id).value='';}
function previewStateButtons(urls){
 const root=$('#preview-states');root.replaceChildren();const labels={idle:'静态',talk:'说话',blink:'眨眼',talk_blink:'说话眨眼'};
 for(const [state,url] of Object.entries(urls)){
  const button=element('button','context-toggle',labels[state]);button.type='button';button.onclick=()=>{$('#appearance-preview-image').src=url;};root.append(button);
 }
}
async function inspectPngHeader(file){
 if(!file||!(/\.png$/i.test(file.name)))throw new Error('请选择 PNG 图片。');
 if(file.size>4*1024*1024)throw new Error('每张 PNG 请控制在 4 MB 内。');
 const bytes=new Uint8Array(await file.slice(0,33).arrayBuffer()),signature=[137,80,78,71,13,10,26,10];
 if(bytes.length<33||signature.some((value,index)=>bytes[index]!==value)||String.fromCharCode(...bytes.slice(12,16))!=='IHDR')throw new Error('文件不是有效 PNG 图片。');
 const uint32=offset=>bytes[offset]*16777216+bytes[offset+1]*65536+bytes[offset+2]*256+bytes[offset+3];
 const width=uint32(16),height=uint32(20);
 if(!width||!height||width>4096||height>4096||width*height>8000000)throw new Error('图片尺寸过大，请缩小后上传。');
 return {width,height};
}
async function showLocalAppearancePreview(){
 const serial=++assetRequestSerial,epoch=contextEpoch;clearAppearancePreview();$('#character-error').hidden=true;
 const ids={idle:'asset-idle',talk:'asset-talk',blink:'asset-blink',talk_blink:'asset-talk-blink'},files={};let pixels=0,total=0,dimensions='';
 try{
  for(const [state,id]of Object.entries(ids)){
   const file=$('#'+id).files?.[0];if(!file)continue;
   const size=await inspectPngHeader(file);pixels+=size.width*size.height;total+=file.size;
   const key=size.width+'x'+size.height;if(dimensions&&dimensions!==key)throw new Error('所有状态图的尺寸须一致。');dimensions=key;files[state]=file;
  }
  if(pixels>8000000||total>8*1024*1024)throw new Error('这组图片过大，请缩小后上传。');
  if(serial!==assetRequestSerial||epoch!==contextEpoch||!files.idle)return;
  for(const [state,file]of Object.entries(files))localPreviewUrls[state]=URL.createObjectURL(file);
  $('#appearance-preview').hidden=false;$('#appearance-preview-image').src=localPreviewUrls.idle;previewStateButtons(localPreviewUrls);
  $('#appearance-status').textContent='本机预览；检查通过后可启用。';
 }catch(error){if(serial===assetRequestSerial&&epoch===contextEpoch)characterError(error);}
}

async function encodePngFile(file){
 if(!file||!(/\.png$/i.test(file.name)))throw new Error('请选择 PNG 图片。');
 if(file.size>4*1024*1024)throw new Error('每张 PNG 请控制在 4 MB 内。');
 const bytes=new Uint8Array(await file.arrayBuffer());
 const signature=[137,80,78,71,13,10,26,10];if(bytes.length<8||signature.some((value,index)=>bytes[index]!==value))throw new Error('文件不是有效 PNG 图片。');
 let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
 return {filename:file.name,data_base64:btoa(binary)};
}
async function importAppearance(){
 if(charactersBusy)return;
 const id=currentCharacterId();if(!id)return;
 const files={};let total=0;
 for(const [state,input]of Object.entries({idle:'asset-idle',talk:'asset-talk',blink:'asset-blink',talk_blink:'asset-talk-blink'})){
  const file=$('#'+input).files?.[0];if(file){files[state]=file;total+=file.size;}
 }
 if(!files.idle){characterError(new Error('先选择一张静态形象。'));return;}
 if(total>8*1024*1024){characterError(new Error('全部图片请控制在 8 MB 内。'));return;}
 const serial=++assetRequestSerial,epoch=contextEpoch;setCharactersBusy(true);$('#character-error').hidden=true;$('#appearance-status').textContent='正在检查图片…';
 try{
  const states={};for(const [state,file]of Object.entries(files))states[state]=await encodePngFile(file);
  if(serial!==assetRequestSerial||epoch!==contextEpoch)return;
  const result=await api('characters/assets/import',{character_id:id,states});
  if(serial!==assetRequestSerial||epoch!==contextEpoch||id!==currentCharacterId()){
   if(result.asset?.id)api('characters/assets/delete',{character_id:id,asset_id:result.asset.id}).catch(()=>{});return;
  }
  clearAppearancePreview();pendingAsset=result.asset;pendingAssetCharacter=id;
  $('#appearance-preview').hidden=false;const urls={};for(const state of Object.keys(pendingAsset.states||{}))urls[state]=assetResource(pendingAsset,state);
  $('#appearance-preview-image').src=urls.idle;previewStateButtons(urls);
  const idle=pendingAsset.states.idle;$('#appearance-status').textContent='已检查 · '+idle.width+' × '+idle.height+' · 尚未启用';
  await loadAppearanceAssets(true);
 }catch(error){if(epoch===contextEpoch){characterError(error);$('#appearance-status').textContent='检查未通过，当前形象保持原样。';}}
 finally{setCharactersBusy(false);}
}
async function activateAppearance(assetId){
 if(charactersBusy)return;const id=currentCharacterId(),epoch=contextEpoch;
 setCharactersBusy(true);stopVoice();$('#character-error').hidden=true;
 try{
  await api('characters/assets/activate',{character_id:id,asset_id:assetId});if(mediaChannel)mediaChannel.postMessage({type:'character-changed',owner:mediaOwner});
  if(epoch!==contextEpoch)return;
  clearAppearancePreview();resetFileInputs();await refresh(true);await loadAppearanceAssets(true);toast('形象已更新，聊天与记忆保留。');
 }catch(error){if(epoch===contextEpoch)characterError(error);}
 finally{setCharactersBusy(false);}
}
async function loadAppearanceAssets(force=false){
 const id=currentCharacterId();if(!id||(!force&&assetLoadedFor===id))return;
 const epoch=contextEpoch;
 try{
  const result=await api('characters/assets?character_id='+encodeURIComponent(id));
  if(id!==currentCharacterId()||epoch!==contextEpoch)return;
  appearanceAssets=result.assets||[];assetLoadedFor=id;renderAppearanceAssets();
 }catch(error){if(epoch===contextEpoch)characterError(error);}
}
function renderAppearanceAssets(){
 const root=$('#appearance-list');root.replaceChildren();const active=app?.active_character?.appearance_id||app?.active_character?.avatar_revision||null;
 const fallback=element('button','appearance-card'+(!active?' selected':''));fallback.type='button';fallback.disabled=charactersBusy||!active;const original=element('img');original.src='/avatar.svg';original.alt='默认占位形象';fallback.append(original,element('span','','默认占位'));fallback.onclick=()=>activateAppearance(null);root.append(fallback);
 for(const asset of appearanceAssets){
  const card=element('article','appearance-card'+(asset.id===active?' selected':''));
  const image=element('img');image.src=assetResource(asset,'thumbnail')||assetResource(asset,'idle');image.alt='已导入的角色形象';card.append(image);if(['vrm','live2d'].includes(asset.format))card.append(element('span','format-badge',asset.format==='vrm'?'3D':'Live2D'));
  const use=element('button','text-button',asset.id===active?'正在使用':'使用');use.type='button';use.disabled=asset.id===active||charactersBusy;use.onclick=()=>asset.format==='live2d'?previewExistingLive2D(asset):activateAppearance(asset.id);card.append(use);
  if(asset.id!==active){const remove=element('button','text-button','删除');remove.type='button';remove.disabled=charactersBusy;remove.onclick=async()=>{if(!confirm('删除这份形象？角色的聊天与记忆会保留。'))return;try{await api('characters/assets/delete',{character_id:currentCharacterId(),asset_id:asset.id});if(pendingAsset?.id===asset.id)clearAppearancePreview();await loadAppearanceAssets(true);}catch(error){characterError(error);}};card.append(remove);}
  root.append(card);
 }
}
function toggleChat(){
 chatCollapsed=!chatCollapsed;document.body.classList.toggle('chat-collapsed',chatCollapsed);
 $('#toggle-chat').textContent=chatCollapsed?'展开聊天':'收起聊天';$('#toggle-chat').setAttribute('aria-expanded',String(!chatCollapsed));
 stageVrm?.setExpanded(stageIsExpanded());if(!chatCollapsed)$('#message-input').focus();
}
$('#toggle-chat').onclick=toggleChat;$('#show-stage').onclick=()=>{if(!chatCollapsed)toggleChat();};
$('#manage-characters').onclick=()=>showView('characters');
$('#character-select').onchange=event=>characterAction('select',{id:event.target.value});
$('#character-create-form').onsubmit=async event=>{event.preventDefault();const name=$('#character-name').value.trim();if(!name)return;await characterAction('create',{name});$('#character-name').value='';};
$('#appearance-form').onsubmit=event=>{event.preventDefault();['vrm','live2d'].includes($('#appearance-format').value)?importVrmAppearance($('#appearance-format').value):importAppearance();};
$('#appearance-format').onchange=setAppearanceFormat;
for(const selector of ['#asset-vrm','#asset-live2d'])$(selector).onchange=()=>{assetRequestSerial++;clearAppearancePreview();const file=$(selector).files?.[0];if(file){$('#appearance-preview').hidden=false;$('#appearance-status').textContent=file.name+' · 点击预览形象进行检查';}};
$('#live2d-refresh-runtime').onclick=refreshLive2DStatus;
$('#vrm-retry').onclick=()=>{stopVoice();disposeStageVrm();renderCharacterImage();};
$('#vrm-preview-retry').onclick=()=>{if(['vrm','live2d'].includes(pendingAsset?.format))renderVrmPreview(pendingAsset);};
for(const mode of ['collapsed','expanded']){$('#vrm-fps-'+mode).value=String(vrmFps(mode));$('#vrm-fps-'+mode).onchange=event=>{localStorage.setItem('vrm-fps-'+mode,event.target.value);stopVoice();disposeStageVrm();renderCharacterImage();};}
for(const id of ['asset-idle','asset-talk','asset-blink','asset-talk-blink'])$('#'+id).onchange=showLocalAppearancePreview;
$('#activate-appearance').onclick=()=>{if(pendingAsset&&pendingAssetCharacter===currentCharacterId())activateAppearance(pendingAsset.id);};
$('#cancel-appearance').onclick=async()=>{
 const asset=pendingAsset,id=pendingAssetCharacter;assetRequestSerial++;clearAppearancePreview();resetFileInputs();
 if(asset&&id)try{await api('characters/assets/delete',{character_id:id,asset_id:asset.id});await loadAppearanceAssets(true);}catch(error){characterError(error);}
};
$('#character-scale').oninput=event=>{localStorage.setItem('character-scale:'+currentCharacterId(),event.target.value);renderCharacterImage();};
window.addEventListener('pagehide',()=>{for(const url of Object.values(localPreviewUrls))URL.revokeObjectURL(url);if(mediaChannel)mediaChannel.close();});
