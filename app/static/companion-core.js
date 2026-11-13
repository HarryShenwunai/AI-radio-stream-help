'use strict';
// UI-independent identity, draft and transport boundary. No media or DOM is created here.
window.CompanionCore=(()=>{
 function create({fetcher=fetch,makeId=()=>crypto.randomUUID()}={}){
  let state=null,epoch=0,readSerial=0,refreshing=false,mutating=false,transitioning=false,chat=null,failed=null,lastSeen=0,disposed=false;
  const drafts=new Map(),listeners=new Map(),owner=makeId();let channel=null,clock=0,claimToken='';
  function on(type,callback){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(callback);return()=>listeners.get(type)?.delete(callback);}
  function emit(type,value){for(const fn of listeners.get(type)||[]){try{fn(value);}catch{}}}
  const role=()=>state?.active_character_id||'';
  const appearance=()=>state?.active_character?.appearance?.id||state?.active_character?.appearance_id||null;
  const scope=()=>({character_id:role(),appearance_id:appearance(),epoch});
  const current=stamp=>stamp.epoch===epoch&&stamp.character_id===role();
  function view(){return {state,scope:scope(),chat:chat?{...chat,controller:undefined}:null,mutating,transitioning,draft:drafts.get(role())||'',failed};}
  function change(){emit('change',view());}
  function invalidate(reason='role-change'){
   const previous=scope();transitioning=true;epoch++;readSerial++;refreshing=false;chat?.controller.abort();chat=null;failed=null;lastSeen=0;
   emit('invalidate',{reason,previous,current:scope()});change();
  }
  async function api(path,data,options={}){
   const stamp=scope(),character=options.character_id||stamp.character_id;
   let payload=data===undefined?undefined:{...data};
   if(payload&&!path.startsWith('characters/')&&character&&payload.expected_character_id===undefined)payload.expected_character_id=character;
   const response=await fetcher('/api/'+path,payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(payload),signal:options.signal});
   let result;try{result=await response.json();}catch{throw new Error('应用响应不可用，请稍后重试。');}
   if(!response.ok){const messages={due_out_of_range:'请选择未来7天内的提醒时间。',invalid_inputs:'请检查填写内容。',game_context_required:'请补充游戏情境，或先分享一次屏幕观察。',observation_expired:'这次观察已过期，请重新分享画面。',provider_not_configured_for_kind:'还未连接这项建议能力。',invalid_csv:'无法读取这份CSV，请检查分隔符与内容。',csv_size_limit:'这份数据太大，请缩小后重试。',vision_not_configured:'视觉模型尚未连接。',consent_required:'请先确认这次分享。',scope_changed:'角色或形象已切换，旧操作已停止。',cancelled:'操作已经取消。',session_expired:'分享已过期，请重新选择来源。',rate_limited:'请稍等两秒再分享画面。',frame_too_large:'画面过大，请缩小来源后重试。',invalid_frame:'未能读取这次画面，请重新预览。',provider_failed:'视觉服务没有完成分析，请检查连接。',owner_runtime_setup_required:'尚未安装已获授权的Live2D运行时。'};const error=new Error(messages[result.code]||messages[result.error]||result.error||'操作未完成，请重试。');error.status=response.status;error.code=result.code;throw error;}
   if(!options.allowStale&&!path.startsWith('characters/')&&!current(stamp))throw new Error('角色已切换，旧操作已停止。');
   return result;
  }
  function adopt(fresh){
   if(!fresh||!Array.isArray(fresh.messages)||typeof fresh.active_character_id!=='string')throw new Error('角色状态不可用。');
   const before=role(),revision=appearance(),changed=Boolean(before&&before!==fresh.active_character_id);
   if(changed)invalidate('role-change');else if(before&&revision!==(fresh.active_character?.appearance?.id||fresh.active_character?.appearance_id||null))emit('media-stop',{reason:'appearance-change'});
   const incoming=!changed&&lastSeen?fresh.messages.filter(item=>item.id>lastSeen&&item.role==='assistant'&&['reminder','proactive'].includes(item.kind)):[];
   state=fresh;transitioning=false;if(Array.isArray(fresh.characters)){const known=new Set(fresh.characters.map(item=>item.id));for(const id of drafts.keys())if(!known.has(id))drafts.delete(id);}lastSeen=Math.max(0,...fresh.messages.map(item=>Number(item.id)||0));change();
   for(const message of incoming)emit('incoming',message);
  }
  async function refresh(force=false){
   if(disposed||refreshing&&!force)return;refreshing=true;const serial=++readSerial,stamp=scope();
   try{const fresh=await api('state',undefined,{allowStale:true});if(serial===readSerial&&current(stamp))adopt(fresh);}
   catch(error){if(serial===readSerial)emit('error',error);}
   finally{if(serial===readSerial)refreshing=false;}
  }
  function claimMedia(){clock=Math.max(Date.now(),clock+1);claimToken=String(clock).padStart(20,'0')+'-'+owner;channel?.postMessage({type:'claim',owner,clock,token:claimToken});}
  function announceRole(){channel?.postMessage({type:'character-changed',owner});}
  try{if(typeof BroadcastChannel==='function'){channel=new BroadcastChannel('companion-media');channel.onmessage=event=>{const data=event.data;if(data?.owner===owner)return;if(data?.type==='claim'){if(Number.isSafeInteger(data.clock))clock=Math.max(clock,data.clock);if(typeof data.token!=='string'||data.token>claimToken){claimToken=data.token||claimToken;emit('media-stop',{reason:'another-player'});}}else if(data?.type==='character-changed'){invalidate('external-role-change');refresh(true);}};}}catch{}
  async function character(action,data){
   if(mutating)return;mutating=true;change();
   if(['create','select','archive','delete'].includes(action))invalidate('character-'+action);
   try{const result=await api('characters/'+action,data,{allowStale:true});if(result.active_character_id)adopt(result);else await refresh(true);if(action==='delete')drafts.delete(data.id);announceRole();return result;}
   catch(error){await refresh(true);throw error;}
   finally{mutating=false;change();}
  }
  async function send(text,{retryId=null}={}){
   text=String(text||'').trim();if(!text||chat||mutating||state?.model_busy)return false;
   emit('media-stop',{reason:'new-message'});const stamp=scope(),requestId=retryId===null&&failed?.text===text?failed.requestId:makeId(),controller=new AbortController();
   chat={requestId,generationId:'',text:'',sourceText:text,status:'sending',stopping:false,controller};failed=null;drafts.set(stamp.character_id,'');change();let finished=false;
   const live=()=>current(stamp)&&chat?.requestId===requestId;
   try{
    const payload={text,request_id:requestId,expected_character_id:stamp.character_id};if(retryId!==null)payload.retry_message_id=retryId;
    const response=await fetcher('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(payload),signal:controller.signal});
    if(!response.ok){const error=await response.json();throw new Error(error.error||'对话未能开始。');}if(!response.body)throw new Error('当前浏览器不支持流式回复。');
    const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let buffer='';
    async function event(data){
     if(!live()||finished)return;
     if(data.type==='meta'){chat.generationId=typeof data.generation_id==='string'?data.generation_id:'';if(data.user&&!state.messages.some(item=>item.id===data.user.id))state.messages.push(data.user);if(chat.stopping)await stopChat();}
     else if(data.type==='status'){if(data.replace)chat.text='';chat.status='adjusting';}
     else if(data.type==='delta'){if(typeof data.text!=='string')throw new Error('回复文本格式无效。');chat.text+=data.text;chat.status='replying';}
     else if(data.type==='done'){
      finished=true;failed=null;if(typeof data.generation_id==='string')chat.generationId=data.generation_id;
      if(!data.cancelled&&data.message){if(retryId!==null)state.messages=state.messages.filter(item=>!(item.role==='assistant'&&item.id>retryId&&item.kind==='chat'));if(!state.messages.some(item=>item.id===data.message.id))state.messages.push(data.message);emit('answer',{message:data.message,character_id:stamp.character_id,generation_id:chat.generationId,request_id:requestId,automatic:!chat.stopping&&state.settings.voice});}
      chat.status=data.cancelled?'stopped':'done';
     }else if(data.type==='error')throw new Error(data.error||'回复中断。');
     change();
    }
    try{while(true){const part=await reader.read();buffer+=decoder.decode(part.value||new Uint8Array(),{stream:!part.done});if(buffer.length>1048576)throw new Error('回复数据块过大，已停止读取。');let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);for(const line of block.split('\n'))if(line.startsWith('data:'))await event(JSON.parse(line.slice(5)));}if(part.done)break;}if(!finished&&live())throw new Error('连接中断。已保留消息，可以重试。');}
    finally{reader.releaseLock();}
   }catch(error){if(current(stamp)&&error.name!=='AbortError'){failed={requestId,text,retryId,error:error.message};if(!state.messages.some(item=>item.role==='user'&&item.request_id===requestId)&&!drafts.get(stamp.character_id))drafts.set(stamp.character_id,text);emit('error',error);}}
   finally{if(live())chat=null;if(current(stamp)){await refresh(true);change();}}
   return finished;
  }
  async function stopChat(context={}){
   emit('media-stop',{reason:'stop-request'});const requestId=chat?.requestId||state?.active_request_id||context.request_id,generationId=chat?.generationId||context.generation_id;if(!requestId)return;
   if(chat){chat.stopping=true;chat.status='stopping';change();}
   try{return await api('chat/stop',{request_id:requestId,...(generationId?{generation_id:generationId}:{})});}catch(error){emit('error',error);throw error;}
  }
  return {on,api,refresh,adopt,character,send,stopChat,invalidate,claimMedia,scope,current,get: view,
   setDraft(text){drafts.set(role(),String(text||''));},retry(){if(failed)return send(failed.text,{retryId:failed.retryId});const last=state?.messages.filter(item=>item.role==='user'&&item.kind==='chat').at(-1);if(last)return send(last.text,{retryId:last.id});},
   dispose(){disposed=true;invalidate('dispose');channel?.close();listeners.clear();drafts.clear();}};
 }
 return Object.freeze({create});
})();
