'use strict';
// This scoped token grants public-output access only. Never acquire a private cookie.
const token=location.hash.slice(1),client=crypto.randomUUID();
history.replaceState(null,'',location.pathname);
const caption=document.querySelector('#caption'),status=document.querySelector('#status'),enable=document.querySelector('#enable');
let active=null,enabled=false,lastContact=performance.now(),busy=false,epoch=0;
function clear(){if(active){active.audio.pause();active.audio.removeAttribute('src');URL.revokeObjectURL(active.url);}active=null;caption.textContent='';}
async function call(action,data={},binary=false){
 const response=await fetch('/api/live-output',{method:'POST',credentials:'omit',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({action,client,...data}),signal:AbortSignal.timeout(1000)});
 if(!response.ok)throw new Error('输出失效或已停止');
 return binary?response.blob():response.json();
}
async function receipt(item,state){return call('receipt',{id:item.id,state});}
function fitsCaption(text){
 caption.style.visibility='hidden';caption.textContent=text;
 let fits=false;
 for(let size=32;size>=20;size-=2){caption.style.fontSize=size+'px';const box=caption.getBoundingClientRect();if(box.bottom<=innerHeight-24&&box.right<=innerWidth-24&&caption.scrollWidth<=caption.clientWidth){fits=true;break;}}
 caption.textContent='';caption.style.visibility='';return fits;
}
async function playbackFailure(item,message){
 epoch++;enabled=false;clear();enable.hidden=false;status.hidden=false;status.textContent=message;
 await receipt(item,'failed').catch(()=>{});
}
async function poll(){
 if(!enabled||busy)return;busy=true;const own=epoch;
 try{
  const {item}=await call('poll');if(own!==epoch||!enabled)return;lastContact=performance.now();
  if(!item){clear();status.textContent='等待主播逐条批准 · 观众接收未验证';return;}
  if(active?.id===item.id)return;
  clear();
  // A refreshed page must not resume an earlier client's claimed item.
  if(item.state!=='claimed')return;
  if(!fitsCaption(item.text)){await playbackFailure(item,'回答无法完整显示，请扩大输出窗口后重新选题。');return;}
  const blob=await call('audio',{id:item.id},true);if(own!==epoch||!enabled)return;
  const url=URL.createObjectURL(blob),audio=new Audio(url),entry={id:item.id,url,audio};active=entry;
  audio.addEventListener('ended',async()=>{if(active!==entry)return;clear();try{await receipt(item,'completed');status.textContent='本页播放结束 · 观众接收未验证';}catch{status.textContent='播放回执未确认';}});
  audio.addEventListener('error',()=>{if(active===entry)playbackFailure(item,'音频无法解码，已停止播放。');});
  try{
   await receipt(item,'playing');
   if(active!==entry)return;
   await audio.play();
   if(active!==entry){audio.pause();return;}
   caption.textContent=item.text;status.textContent='本页正在输出 · 观众接收未验证';
  }catch{if(own===epoch)await playbackFailure(item,'音频未播放，请检查浏览器音频权限。');}
 }catch{if(own!==epoch)return;epoch++;clear();enabled=false;enable.hidden=false;status.hidden=false;status.textContent='输出已停止或连接失效；请从主播端重新打开';}
 finally{busy=false;}
}
enable.addEventListener('click',()=>{epoch++;enabled=true;enable.hidden=true;status.hidden=true;lastContact=performance.now();poll();});
setInterval(poll,250);
setInterval(()=>{if(active&&performance.now()-lastContact>1250){playbackFailure({id:active.id},'输出连接超时，已停止播放。');}},100);
window.addEventListener('pagehide',()=>{epoch++;enabled=false;clear();});

// OBS/source URL edits can be same-document fragment navigation. Rebind explicitly.
window.addEventListener('hashchange',()=>{if(location.hash){epoch++;enabled=false;clear();location.reload();}});
