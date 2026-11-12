'use strict';
// One audio owner and one playback-receipt chain. Presentation is injected.
window.CompanionSpeech=(()=>{
 function create({core,scene,isHidden,onState=()=>{},onReceipt=()=>{},onError=()=>{}}){
  let serial=0,audio=null,url=null,request=null,cleanup=null,receipt=null,context=null,state='idle';
  const status=value=>{state=value;onState(value);};
  function stop(){
   receipt?.stop();receipt=null;serial++;if('speechSynthesis'in window)speechSynthesis.cancel();cleanup?.();request?.abort();request=null;context=null;scene?.setSpeaking(false);status('idle');
  }
  function tracked(meta,ticket){return meta?window.CompanionPlayback.create(meta,{onState:(phase,result)=>onReceipt(meta,phase,result),onLimit:()=>{if(ticket===serial){stop();onError('朗读达到时长上限，完整文字仍可回看。');}}}):null;}
  async function systemStart(ctx,ticket,stamp){
   if(!ctx.message_id&&!(ctx.generation_id&&ctx.request_id))return null;
   const payload=ctx.generation_id&&ctx.request_id?{generation_id:ctx.generation_id,request_id:ctx.request_id}:{message_id:ctx.message_id};
   const response=await fetch('/api/playback/start',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify({...payload,expected_character_id:stamp.character_id})});
   const result=await response.json();if(!response.ok)throw new Error(result.error||'这条朗读已失效。');return tracked(result.playback,ticket);
  }
  async function speak(text,ctx={}){
   if(isHidden()){stop();return;}stop();core.claimMedia();const ticket=serial,stamp=core.scope(),settings=core.get().state?.settings||{};context={...ctx};
   const live=()=>ticket===serial&&core.current(stamp)&&core.scope().appearance_id===stamp.appearance_id&&!isHidden();
   if(ctx.character_id&&ctx.character_id!==stamp.character_id)return;
   status('preparing');
   if(settings.voice_backend!=='system'){
    if(!core.get().state?.local_voice_available){status('idle');onError('声音还未准备好，请先连接声音。');return;}
    const controller=new AbortController();request=controller;let clean=null,proof=null;
    try{
     const payload=ctx.generation_id&&ctx.request_id?{text:String(text).slice(0,700),generation_id:ctx.generation_id,request_id:ctx.request_id}:ctx.message_id!==undefined?{message_id:ctx.message_id}:{text:String(text).slice(0,700)};
     const response=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify({...payload,expected_character_id:stamp.character_id}),signal:controller.signal});
     if(!response.ok){const error=await response.json();throw new Error(error.error||'语音合成失败。');}
     const header=response.headers?.get('X-Companion-Playback');
     if(header){const meta=window.CompanionPlayback.fromHeader(header);proof=tracked(meta,ticket);if(!live()){proof?.stop();return;}if(meta.character_id!==stamp.character_id||meta.appearance_id!==stamp.appearance_id){proof?.stop();throw new Error('角色已变化，旧声音已停止。');}receipt=proof;}
     const blob=await response.blob();if(!live()){proof?.stop();return;}
     const objectUrl=URL.createObjectURL(blob),element=new Audio(objectUrl);proof?.attachAudio(element);let released=false;
     const current=()=>live()&&audio===element;
     clean=()=>{if(released)return;released=true;proof?.stop();if(receipt===proof)receipt=null;element.onplay=null;element.onended=null;element.onerror=null;element.onpause=null;element.ontimeupdate=null;element.pause();element.src='';URL.revokeObjectURL(objectUrl);if(audio===element)audio=null;if(url===objectUrl)url=null;if(cleanup===clean)cleanup=null;};
     audio=element;url=objectUrl;cleanup=clean;
     element.onplay=()=>{if(!current()){clean();return;}proof?.progress(true);scene?.setSpeaking(true);scene?.setAudio(element);status('playing');};
     element.ontimeupdate=()=>{if(current())proof?.progress();};
     element.onpause=()=>{if(current()&&!element.ended){proof?.stop();scene?.setSpeaking(false);context=null;clean();status('idle');}};
     element.onended=()=>{if(!current())return;proof?.complete();scene?.setSpeaking(false);context=null;clean();status('idle');};
     element.onerror=()=>{if(!current())return;proof?.stop();scene?.setSpeaking(false);context=null;clean();status('idle');onError('声音无法播放，可以重试。');};
     await element.play();if(!current())clean();
    }catch(error){proof?.stop();clean?.();if(ticket===serial){if(receipt===proof)receipt=null;scene?.setSpeaking(false);context=null;status('idle');if(error.name!=='AbortError')onError(error.name==='NotAllowedError'?'请点按朗读按钮播放声音。':error.message);}}
    finally{if(request===controller)request=null;}
   }else{
    const voices=window.speechSynthesis?.getVoices()||[];if(!voices.length){status('idle');onError('系统没有提供音色，请在声音流程选择其他方式。');return;}
    let proof=null;
    try{proof=await systemStart(ctx,ticket,stamp);if(!live()){proof?.stop();return;}receipt=proof;
     const utterance=new SpeechSynthesisUtterance(proof?String(text):String(text).replace(/https?:\/\/\S+/g,'链接').replace(/[*#_`]/g,''));
     utterance.lang='zh-CN';utterance.rate=settings.voice_rate||1;utterance.pitch=1.04;
     const preferred=localStorage.getItem('character-voice:'+stamp.character_id);utterance.voice=voices.find(v=>v.voiceURI===preferred)||voices.find(v=>v.lang.startsWith('zh'))||voices[0];
     utterance.onstart=()=>{if(!live()){proof?.stop();return;}proof?.startSystem();scene?.setSpeaking(true);status('playing');};
     utterance.onboundary=()=>{if(live())scene?.systemBoundary?.();};utterance.onend=()=>{if(!live())return;proof?.complete();if(receipt===proof)receipt=null;scene?.setSpeaking(false);context=null;status('idle');};
     utterance.onerror=event=>{proof?.stop();if(!live())return;if(receipt===proof)receipt=null;scene?.setSpeaking(false);context=null;status('idle');if(!['canceled','interrupted'].includes(event.error))onError('系统朗读中断，可以重试。');};
     speechSynthesis.speak(utterance);
    }catch(error){proof?.stop();if(ticket===serial){status('idle');onError(error.message);}}
   }
  }
  const unsubscribe=[core.on('invalidate',stop),core.on('media-stop',stop)];
  return {speak,stop,get state(){return state;},get context(){return context;},get audio(){return audio;},dispose(){stop();unsubscribe.forEach(off=>off());}};
 }
 return Object.freeze({create});
})();
