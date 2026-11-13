'use strict';
// Playback evidence is a local player's report, not proof that a human heard words.
window.CompanionPlayback=(()=>{
 function valid(meta){return meta&&typeof meta.playback_id==='string'&&typeof meta.nonce==='string'&&meta.nonce.length>=20&&typeof meta.character_id==='string'&&(meta.appearance_id===null||typeof meta.appearance_id==='string')&&Number.isSafeInteger(meta.message_id)&&meta.message_id>0;}
 function fromHeader(value){if(!value)return null;const meta=JSON.parse(atob(value));if(!valid(meta))throw new Error('播放回执信息无效，请重试。');return meta;}
 function create(meta,{onState=()=>{},onLimit=()=>{}}={}){
  if(!valid(meta))throw new Error('播放回执信息无效，请重试。');
  let audio=null,startedAt=null,terminal=false,lastSent=-Infinity,lastPosition=0,chain=Promise.resolve(),limitTimer=0;
  const known=Number.isFinite(meta.duration_seconds)&&meta.duration_seconds>0&&meta.duration_seconds<=180?meta.duration_seconds:null;
  const notify=(status,result={})=>onState(status,result);
  function seconds(){const raw=audio?audio.currentTime:startedAt===null?0:(performance.now()-startedAt)/1000;return Number.isFinite(raw)?Math.max(lastPosition,Math.min(known||180,Math.max(0,raw))):lastPosition;}
  function duration(status,position){if(known!==null)return known;const measured=audio?.duration;if(Number.isFinite(measured)&&measured>0&&measured<=180)return measured;return position>0?position:null;}
  function payload(status,position,total){return {playback_id:meta.playback_id,nonce:meta.nonce,character_id:meta.character_id,appearance_id:meta.appearance_id,message_id:meta.message_id,expected_character_id:meta.character_id,position_seconds:position,duration_seconds:total,status};}
  async function send(body){
   try{const response=await fetch('/api/playback/receipt',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify(body),keepalive:body.status!=='playing'});const result=await response.json();if(!response.ok)throw new Error(result.error||'播放回执未确认。');if(body.status==='playing'&&terminal)return result;notify(result.accepted&&!result.stale?body.status:'stale',result);return result;}
   catch{if(body.status!=='playing'||!terminal)notify('unconfirmed');return null;}
  }
  function progress(force=false){if(terminal||(!audio&&known===null))return;const now=performance.now();if(!force&&now-lastSent<1000)return;lastSent=now;const position=seconds(),total=duration('playing',position);if(!(total>0))return;lastPosition=position;const body=payload('playing',position,total);chain=chain.then(()=>terminal?null:send(body),()=>terminal?null:send(body));return chain;}
  function finish(status){
   if(terminal)return Promise.resolve(null);
   const observed=seconds();let position=observed,total=duration(status,position);
   if(status==='completed'){
    const elapsed=startedAt===null?0:(performance.now()-startedAt)/1000;
    if(audio){if(!(total>0)||!Number.isFinite(audio.currentTime)||Math.abs(audio.currentTime-total)>.05||audio.ended===false)status='stopped';else position=total;}
    else if(startedAt===null||elapsed<=0||elapsed>180)status='stopped';
   }
   terminal=true;clearTimeout(limitTimer);limitTimer=0;lastPosition=position;
   // Terminal reports start immediately, including pagehide. Late queued progress
   // is dropped; the server seals a terminal nonce and rejects in-flight older progress.
   const body=payload(status,position,total);notify(status==='stopped'?'stopping':'finishing');return send(body);
  }
  notify('pending');
  return {attachAudio(value){audio=value;},startSystem(){if(terminal)return;startedAt=performance.now();notify('playing');limitTimer=setTimeout(()=>{if(!terminal){finish('stopped');onLimit();}},180000);},progress,complete:()=>finish('completed'),stop:()=>finish('stopped'),get terminal(){return terminal;}};
 }
 return Object.freeze({fromHeader,create});
})();
