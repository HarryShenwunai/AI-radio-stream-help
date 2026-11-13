'use strict';
window.CompanionConversation=(()=>{
 function recordReceipt(notes,meta,phase){const key=meta.character_id+':'+meta.message_id;notes.delete(key);notes.set(key,({completed:'播放完成',stopped:'播放已停止',unconfirmed:'播放记录未确认',playing:'正在播放',stale:'旧播放记录已失效'})[phase]||'');while(notes.size>256)notes.delete(notes.keys().next().value);}
 function create({core,ui,speech,assistance,notes}){
  const {el,button,hint}=CompanionUI;let panel=null,list=null,lastKey='',bottom=true,observer=null;
  function render(){if(!list)return;const snapshot=core.get(),state=snapshot.state;if(!state)return;const key=JSON.stringify([snapshot.scope.character_id,state.messages,snapshot.chat?.text,snapshot.chat?.status,[...notes]]);if(key===lastKey)return;lastKey=key;const atBottom=bottom;list.replaceChildren();
   if(!state.messages.length&&!snapshot.chat)list.append(el('p','empty-copy','新的对话，从你想说的话开始。'));
   for(const message of state.messages){const item=el('article','conversation-message '+(message.role==='user'?'from-you':'from-character'));item.dataset.messageId=message.id;item.append(el('span','message-author',message.role==='user'?state.settings.user_name||'你':state.settings.name),el('p','message-text',message.text));
    if(message.role==='assistant'){const actions=el('footer','message-actions'),speak=button('朗读',{icon:'volume',action:()=>speech.speak(message.text,{message_id:message.id})});actions.append(speak);const note=notes.get(snapshot.scope.character_id+':'+message.id);if(note)actions.append(el('span','playback-note',note));item.append(actions);const card=assistance.associated(message);if(card)item.append(card);}list.append(item);}
   if(snapshot.chat){const streaming=el('article','conversation-message from-character streaming');streaming.append(el('span','message-author',state.settings.name),el('p','message-text',snapshot.chat.text||'正在准备回复…'));list.append(streaming);}if(!snapshot.chat&&state.messages.some(item=>item.role==='user'&&item.kind==='chat'))list.append(button('重新回答最近一句',{icon:'reset',action:()=>core.retry()}));if(atBottom)queueMicrotask(()=>{if(list)list.scrollTop=list.scrollHeight;});
  }
  function open(){const frame=ui.panel('对话回看',{id:'history',className:'history-panel',modal:false});panel=frame.node;list=el('div','conversation-scroll');list.id='conversation-log';list.setAttribute('role','log');frame.body.append(list);lastKey='';bottom=true;list.addEventListener('scroll',()=>{bottom=list.scrollHeight-list.scrollTop-list.clientHeight<64;},{passive:true});ui.open(frame.node,{id:'history',modal:false,onClose:()=>{observer?.disconnect();observer=null;panel=null;list=null;lastKey='';}});if(window.ResizeObserver){observer=new ResizeObserver(()=>{if(bottom&&list)list.scrollTop=list.scrollHeight;});observer.observe(list);}render();}
  core.on('change',render);return {open,render,get node(){return panel;}};
 }
 return Object.freeze({create,recordReceipt});
})();
