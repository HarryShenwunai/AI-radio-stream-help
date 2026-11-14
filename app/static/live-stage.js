'use strict';
// This scoped token grants public-output access only. Never acquire a private cookie.
const token=location.hash.slice(1),client=crypto.randomUUID();
history.replaceState(null,'',location.pathname);
const caption=document.querySelector('#caption'),status=document.querySelector('#status'),enable=document.querySelector('#enable');
let active=null,enabled=false,lastContact=performance.now(),busy=false;
function clear(){if(active){active.audio.pause();active.audio.removeAttribute('src');URL.revokeObjectURL(active.url);}active=null;caption.textContent='';}
async function call(action,data={},binary=false){
 const response=await fetch('/api/live-output',{method:'POST',credentials:'omit',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({action,client,...data}),signal:AbortSignal.timeout(1000)});
 if(!response.ok)throw new Error('输出失效或已停止');
 return binary?response.blob():response.json();
}
async function receipt(item,state){return call('receipt',{id:item.id,state});}
async function poll(){
 if(!enabled||busy)return;busy=true;
 try{
  const {item}=await call('poll');lastContact=performance.now();
  if(!item){clear();status.textContent='等待主播逐条批准 · 观众接收未验证';return;}
  if(active?.id===item.id)return;
  clear();
  // A refreshed page must not resume an earlier client's claimed item.
  if(item.state!=='claimed')return;
  const blob=await call('audio',{id:item.id},true);
  const url=URL.createObjectURL(blob),audio=new Audio(url),entry={id:item.id,url,audio};active=entry;
  audio.addEventListener('ended',async()=>{if(active!==entry)return;clear();try{await receipt(item,'completed');status.textContent='本页播放结束 · 观众接收未验证';}catch{status.textContent='播放回执未确认';}});
  audio.addEventListener('error',()=>{if(active===entry){clear();receipt(item,'failed').catch(()=>{});}});
  try{
   await receipt(item,'playing');
   if(active!==entry)return;
   await audio.play();
   if(active!==entry){audio.pause();return;}
   caption.textContent=item.text;status.textContent='本页正在输出 · 观众接收未验证';
  }catch{clear();await receipt(item,'failed').catch(()=>{});status.textContent='音频未播放，请检查浏览器音频权限';}
 }catch{clear();enabled=false;enable.hidden=false;status.hidden=false;status.textContent='输出已停止或连接失效；请从主播端重新打开';}
 finally{busy=false;}
}
enable.addEventListener('click',()=>{enabled=true;enable.hidden=true;status.hidden=true;lastContact=performance.now();poll();});
setInterval(poll,250);
setInterval(()=>{if(active&&performance.now()-lastContact>1250){clear();status.textContent='输出连接超时，已停止本页音频';}},100);
window.addEventListener('pagehide',()=>{enabled=false;clear();});

// OBS/source URL edits can be same-document fragment navigation. Rebind explicitly.
window.addEventListener('hashchange',()=>{if(location.hash){enabled=false;clear();location.reload();}});
