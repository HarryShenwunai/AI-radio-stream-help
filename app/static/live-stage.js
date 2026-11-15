'use strict';
// Token is never put in an asset URL, broadcast, DOM label or private cookie.
const token=location.hash.slice(1),client=crypto.randomUUID();
history.replaceState(null,'',location.pathname);
const caption=document.querySelector('#caption'),status=document.querySelector('#status'),enable=document.querySelector('#enable');
let active=null,enabled=false,lastContact=performance.now(),busy=false,epoch=0,scenePromise=null,sceneHash='',playSerial=0,lastTerminal='';
const notices=typeof BroadcastChannel==='function'?new BroadcastChannel('companion-live-output'):null;
function changed(){notices?.postMessage({type:'changed'});}
async function call(action,data={},binary=false){
 const response=await fetch('/api/live-output',{method:'POST',credentials:'omit',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({action,client,...data}),signal:AbortSignal.timeout(1000)});
 if(!response.ok)throw new Error('输出失效或已停止');return binary?response.blob():response.json();
}
const program=ProgramScene.create({call,container:document.querySelector('#character-canvas'),image:document.querySelector('#character-image'),onState:s=>{const node=document.querySelector('#character-status');node.hidden=s.ready&&!s.placeholder;node.textContent=s.error||(s.placeholder?'未设置节目人物':'正在准备人物');}});
function clear(){const previous=active;active=null;program.setSpeaking(false);if(previous?.audio){previous.audio.pause();previous.audio.removeAttribute('src');URL.revokeObjectURL(previous.url);}caption.textContent='';}
function revoke(message){epoch++;enabled=false;clear();program.clear();sceneHash='';scenePromise=null;enable.hidden=false;status.hidden=false;status.textContent=message;changed();}
async function receipt(item,state){const result=await call('receipt',{id:item.id,state});changed();return result;}
function fitsCaption(text){
 caption.style.visibility='hidden';caption.textContent=text;let fits=false;
 for(let size=32;size>=20;size-=2){caption.style.fontSize=size+'px';const box=caption.getBoundingClientRect();if(box.top>=24&&box.bottom<=innerHeight-24&&box.right<=innerWidth-24&&caption.scrollWidth<=caption.clientWidth){fits=true;break;}}
 caption.textContent='';caption.style.visibility='';return fits;
}
async function playbackFailure(item,message){revoke(message);await receipt(item,'failed').catch(()=>{});}
function syncScene(snapshot){
 if(snapshot?.sha256===sceneHash)return scenePromise||Promise.resolve(program.ready);
 sceneHash=snapshot?.sha256||'';scenePromise=program.sync(snapshot);return scenePromise;
}
async function startPlayback(item,own,ready){
 lastTerminal='';status.hidden=true;const entry={id:item.id,audio:null,url:null,started:false,ended:false,serial:++playSerial};active=entry;
 const valid=()=>active===entry&&own===epoch&&enabled;
 try{
  if(!fitsCaption(item.text))throw Error('回答无法完整显示，请扩大输出窗口后重新选题。');
  if(!await ready){if(valid())throw Error('节目人物未能准备，已停止播放。');return;}if(!valid())return;
  if(item.scene_snapshot?.sha256!==program.snapshot?.sha256)throw Error('节目人物与批准记录不一致。');
  const blob=await call('audio',{id:item.id},true);if(!valid())return;
  const bytes=await blob.arrayBuffer(),sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  if(!valid())return;if(item.audio_sha256!==sha)throw Error('节目音频校验失败。');
  const url=URL.createObjectURL(blob),audio=new Audio(url);Object.assign(entry,{url,audio});
  const complete=async()=>{if(!valid())return;clear();try{await receipt(item,'completed');if(own!==epoch||!enabled||playSerial!==entry.serial)return;lastTerminal='本页播放结束 · 观众接收未验证';status.hidden=false;status.textContent=lastTerminal;}catch{if(own!==epoch||!enabled||playSerial!==entry.serial)return;lastTerminal='播放回执未确认';status.hidden=false;status.textContent=lastTerminal;}};
  audio.addEventListener('ended',()=>{entry.ended=true;if(entry.started)complete();});
  audio.addEventListener('error',()=>{if(valid())playbackFailure(item,'音频无法解码，已停止播放。');});
  audio.addEventListener('pause',()=>{if(valid()&&entry.mediaStarted&&!audio.ended)playbackFailure(item,'音频已中断，请从主播端重新选题。');});
  // Attach analysis before starting audio so no unobserved initial segment is
  // played; speaking remains false until the actual media play succeeds.
  const audioReady=await program.setAudio(audio);if(!valid())return;if(audioReady===false)throw Error('音频输出未就绪，请检查本页音频权限。');
  await audio.play();if(!valid()){audio.pause();return;}
  if(audio.paused)throw Error('音频未播放，请检查浏览器音频权限。');
  entry.mediaStarted=true;caption.textContent=item.text;program.setSpeaking(true);status.textContent='本页正在输出 · 观众接收未验证';
  await receipt(item,'playing');if(!valid()){audio.pause();return;}entry.started=true;if(entry.ended)await complete();
 }catch(error){if(valid())await playbackFailure(item,error.message==='输出失效或已停止'?'输出已停止或连接失效；请从主播端重新打开':error.message||'音频未播放，请检查浏览器音频权限。');}
}
async function poll(){
 if(!enabled||busy)return;busy=true;const own=epoch;
 try{
  const {item,scene_snapshot}=await call('poll');if(own!==epoch||!enabled)return;lastContact=performance.now();
  const ready=syncScene(scene_snapshot);ready.catch(()=>{});
  if(!item){clear();if(!lastTerminal)status.textContent='等待主播逐条批准 · 观众接收未验证';return;}
  if(active?.id===item.id)return;
  clear();if(item.state!=='claimed')return;
  // Do not await asset preparation/audio.play here: claimed jobs must keep
  // receiving the existing heartbeat while their resources are loaded.
  startPlayback(item,own,ready);
 }catch{if(own===epoch)revoke('输出已停止或连接失效；请从主播端重新打开');}
 finally{busy=false;}
}
enable.addEventListener('click',()=>{epoch++;enabled=true;lastTerminal='';enable.hidden=true;status.hidden=true;lastContact=performance.now();poll();});
setInterval(poll,250);
setInterval(()=>{if(active&&performance.now()-lastContact>1250)playbackFailure({id:active.id},'输出连接超时，已停止播放。');},100);
window.addEventListener('pagehide',()=>{epoch++;enabled=false;clear();program.dispose();notices?.close();});
window.addEventListener('hashchange',()=>{if(location.hash){revoke('输出已改变');location.reload();}});
// Warm only approved current character resources, never a candidate reply.
const bootEpoch=epoch;call('scene').then(({scene_snapshot})=>{if(bootEpoch===epoch)return syncScene(scene_snapshot);}).catch(()=>{if(bootEpoch===epoch)status.textContent='输出已停止或连接失效；请从主播端重新打开';});
window.ProgramOutput=Object.freeze({getStats:()=>program.getStats(),getDiagnostics:options=>program.getDiagnostics(options),snapshot:()=>({scene_sha256:program.snapshot?.sha256||null,active_id:active?.id||null,enabled})});
