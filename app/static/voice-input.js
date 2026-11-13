'use strict';
// Explicit push-to-record, local HTTP transcription. No auto-send or online ASR fallback.
window.CompanionVoiceInput=(()=>{
 function pcm16Wav(samples,rate=16000){
  const result=new ArrayBuffer(44+samples.length*2),view=new DataView(result);
  const ascii=(offset,value)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
  ascii(0,'RIFF');view.setUint32(4,result.byteLength-8,true);ascii(8,'WAVE');ascii(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);ascii(36,'data');view.setUint32(40,samples.length*2,true);
  for(let i=0;i<samples.length;i++){const value=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,value<0?Math.round(value*32768):Math.round(value*32767),true);}return result;
 }
 function base64(buffer){const bytes=new Uint8Array(buffer);let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(text);}
 function create({getCharacterId,isHidden,onDraft,onStatus=()=>{},onError=()=>{}}){
  let ticket=0,stream=null,recorder=null,chunks=[],timer=0,request=null,operation='',owner='',phase='idle',decoder=null;
  const publish=value=>{phase=value;onStatus(value);};
  function stopTracks(){for(const track of stream?.getTracks()||[])track.stop();stream=null;}
  function cancel(){
   ticket++;clearTimeout(timer);timer=0;request?.abort();request=null;stopTracks();
   if(recorder){const old=recorder;recorder=null;old.onstop=null;old.ondataavailable=null;if(old.state!=='inactive'){try{old.stop();}catch{}}}
   chunks=[];decoder?.close().catch(()=>{});decoder=null;const stale=operation,character=owner;operation='';owner='';publish('idle');
   if(stale)fetch('/api/transcribe/stop',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify({operation_id:stale,expected_character_id:character}),keepalive:true}).catch(()=>{});
  }
  async function wav(blob){
   const Audio=window.AudioContext||window.webkitAudioContext,Offline=window.OfflineAudioContext||window.webkitOfflineAudioContext;
   if(!Audio||!Offline)throw new Error('当前浏览器无法处理本地录音，请换用 Chrome。');
   const context=new Audio();decoder=context;
   try{
    const decoded=await context.decodeAudioData(await blob.arrayBuffer());
    if(!decoded.length||!Number.isFinite(decoded.duration)||decoded.duration<=0)throw new Error('没有录到声音，请重试。');
    const duration=Math.min(60,decoded.duration),length=Math.max(1,Math.floor(duration*16000)),offline=new Offline(1,length,16000),source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start(0,0,duration);
    const rendered=await offline.startRendering();return pcm16Wav(rendered.getChannelData(0));
   }finally{context.close().catch(()=>{});if(decoder===context)decoder=null;}
  }
  async function finish(localTicket,id){
   if(localTicket!==ticket)return;
   clearTimeout(timer);timer=0;stopTracks();recorder=null;
   if(localTicket!==ticket)return;if(id!==getCharacterId()||isHidden()){cancel();return;}
   publish('processing');const captured=chunks;chunks=[];
   try{
    const blob=new Blob(captured,{type:captured[0]?.type||'audio/webm'});if(blob.size>16*1024*1024)throw new Error('录音过大，请缩短后重试。');
    const audio=await wav(blob);if(localTicket!==ticket||id!==getCharacterId()||isHidden())return;
    request=new AbortController();const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json','X-Companion':'local-app'},body:JSON.stringify({audio_base64:base64(audio),operation_id:operation,expected_character_id:id}),signal:request.signal});
    const result=await response.json();if(localTicket!==ticket||id!==getCharacterId()||isHidden())return;
    if(!response.ok)throw new Error(result.error||'本地识别失败，请稍后重试。');
    if(result.character_id!==id||result.operation_id!==operation)throw new Error('录音结果已过期，请重试。');
    if(typeof result.text==='string'&&result.text.trim())onDraft(result.text);else onError('没有识别到文字，请再试一次。');
   }catch(error){if(localTicket===ticket&&error.name!=='AbortError')onError(error.message||'本地识别失败。');}
   finally{if(localTicket===ticket){request=null;operation='';owner='';publish('idle');}}
  }
  async function start(){
   if(phase!=='idle'||isHidden())return;
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){onError('当前浏览器不支持本地录音，请使用 Chrome。');return;}
   const localTicket=++ticket,id=getCharacterId();if(!id)return;publish('starting');
   try{
    const check=await fetch('/api/voice/status'),status=await check.json();if(localTicket!==ticket)return;if(isHidden()||id!==getCharacterId()){cancel();return;}
    if(!check.ok||!status.asr?.ready)throw new Error(status.asr?.reason||'本地语音识别尚未准备好，请先完成安装。');
    const opened=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    if(localTicket!==ticket||isHidden()||id!==getCharacterId()){opened.getTracks().forEach(track=>track.stop());return;}
    stream=opened;owner=id;operation=crypto.randomUUID();chunks=[];
    const mime=window.MediaRecorder.isTypeSupported?.('audio/webm;codecs=opus')?'audio/webm;codecs=opus':'';
    const current=new window.MediaRecorder(opened,mime?{mimeType:mime}:{});recorder=current;
    current.ondataavailable=event=>{if(localTicket===ticket&&event.data.size)chunks.push(event.data);};
    current.onstop=()=>finish(localTicket,id);current.onerror=()=>{if(localTicket===ticket){cancel();onError('录音已中断，请检查麦克风。');}};
    current.start(250);publish('recording');timer=setTimeout(()=>{if(localTicket===ticket&&current.state==='recording'){publish('processing');current.stop();}},60000);
   }catch(error){if(localTicket===ticket){cancel();onError(error.name==='NotAllowedError'?'麦克风权限未开启。':error.message||'无法开始录音。');}}
  }
  function stop(){if(phase==='recording'&&recorder?.state==='recording'){publish('processing');clearTimeout(timer);timer=0;recorder.stop();}else if(phase!=='idle')cancel();}
  return {start,stop,cancel,get phase(){return phase;}};
 }
 return Object.freeze({create,pcm16Wav});
})();
