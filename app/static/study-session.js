'use strict';
// Deterministic session state: no network, media, DOM, or wall-clock assumptions.
(function(root){
 const LIMIT=120*60000, phases=new Set(['idle','running','paused','review','break']);
 const fresh=()=>({phase:'idle',goal:'',minutes:25,remaining:1500000,elapsed:0,last:null,kind:'read',checked:[false,false,false],rounds:0,total:0});
 function restore(raw){
  const s=fresh();if(!raw||typeof raw!=='object')return s;
  s.goal=typeof raw.goal==='string'?raw.goal.slice(0,180):'';
  s.minutes=[15,25,50].includes(raw.minutes)?raw.minutes:25;
  s.kind=['read','practice','write'].includes(raw.kind)?raw.kind:'read';
  s.phase=phases.has(raw.phase)?raw.phase:'idle';if(s.phase==='running')s.phase='paused';const wasBreak=s.phase==='break';if(wasBreak)s.phase='idle';
  const duration=s.minutes*60000;
  s.elapsed=Number.isFinite(raw.elapsed)?Math.max(0,Math.min(duration,raw.elapsed)):0;
  if(wasBreak)s.elapsed=0;s.remaining=duration-s.elapsed;
  s.checked=[0,1,2].map(i=>raw.checked?.[i]===true);
  s.rounds=Number.isSafeInteger(raw.rounds)?Math.max(0,Math.min(999,raw.rounds)):0;
  s.total=Number.isFinite(raw.total)?Math.max(0,Math.min(LIMIT*999,raw.total)):0;
  if(!s.goal.trim()&&s.phase!=='idle')s.phase='idle';
  return s;
 }
 function advance(s,now){
  if(!['running','break'].includes(s.phase)||!Number.isFinite(now))return s;
  const delta=s.last===null?0:Math.max(0,Math.min(s.remaining,now-s.last));
  const next={...s,remaining:Math.max(0,s.remaining-delta),last:Math.max(s.last??now,now)};
  if(s.phase==='running')next.elapsed+=delta;
  if(next.remaining===0){next.phase=s.phase==='running'?'review':'idle';next.last=null;if(s.phase==='break'){next.remaining=s.minutes*60000;next.elapsed=0;}}
  return next;
 }
 function reduce(state,event,now){
  let s=advance(state,now);const e=event||{};
  if(e.type==='tick')return s;
  if(e.type==='goal'&&s.phase==='idle')return {...s,goal:String(e.value||'').slice(0,180)};
  if(e.type==='kind'&&s.phase==='idle'&&['read','practice','write'].includes(e.value))return {...s,kind:e.value,checked:[false,false,false]};
  if(e.type==='duration'&&s.phase==='idle'&&[15,25,50].includes(e.value))return {...s,minutes:e.value,remaining:e.value*60000};
  if(e.type==='start'&&s.phase==='idle'&&s.goal.trim()&&Number.isFinite(now))return {...s,phase:'running',elapsed:0,remaining:s.minutes*60000,last:now,checked:[false,false,false]};
  if(e.type==='pause'&&s.phase==='running')return {...s,phase:'paused',last:null};
  if(e.type==='resume'&&s.phase==='paused'&&Number.isFinite(now))return {...s,phase:'running',last:now};
  if(e.type==='finish'&&['running','paused'].includes(s.phase))return {...s,phase:'review',last:null};
  if(e.type==='check'&&Number.isInteger(e.index)&&e.index>=0&&e.index<3)return {...s,checked:s.checked.map((v,i)=>i===e.index?!v:v)};
  if(e.type==='save'&&s.phase==='review'&&Number.isFinite(now))return {...s,phase:'break',remaining:300000,last:now,total:Math.min(LIMIT*999,s.total+s.elapsed),rounds:Math.min(999,s.rounds+1)};
  if(e.type==='skip'&&s.phase==='break')return {...s,phase:'idle',remaining:s.minutes*60000,elapsed:0,last:null};
  if(e.type==='clear')return fresh();
  return s;
 }
 function steps(kind){return ({read:['圈出本节的核心问题','用自己的话解释关键概念','不看资料，复述并标记疑点'],practice:['独立完成一组题目','对照思路，定位错误原因','重做错题，记录一个规律'],write:['写下论点与三个支撑点','完成一版连续草稿','检查逻辑、证据与表达']})[kind]||steps('read');}
 function prompt(s,mode){const goal=s.goal.trim();if(!goal)return '';return mode==='review'?`请协助我复盘学习目标「${goal}」。本轮实际计时 ${Math.floor(s.elapsed/60000)} 分钟，完成步骤 ${s.checked.filter(Boolean).length}/3。先问我学会了什么、哪里仍困惑，再给出下一轮建议；不要假设我已掌握。`:`我的本轮学习目标是「${goal}」，可用 ${s.minutes} 分钟。请给出三个具体可执行步骤和一个检验理解的问题。缺少教材或题目时请明确询问，不要编造材料内容。`;}
 const api=Object.freeze({fresh,restore,reduce,steps,prompt});if(typeof module==='object'&&module.exports)module.exports=api;else root.StudySession=api;
})(typeof window==='object'?window:globalThis);
