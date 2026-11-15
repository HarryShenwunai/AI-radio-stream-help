'use strict';
(()=>{
 const $=id=>document.getElementById(id),S=window.StudySession;
 let focus=S.fresh(),mode='focus',breakRemaining=300000,breakLast=null,timer=0,disposed=false;
 async function api(path){const r=await fetch('/api/'+path,{headers:{'X-Companion':'local-app'},cache:'no-store'});const data=await r.json();if(!r.ok)throw Error(data.error||'请先打开助手首页。');return data;}
 const scene=CompanionScene.create({container:$('character-canvas'),image:$('character-image'),api,onState:s=>{$('character-status').hidden=s.ready&&!s.placeholder;$('character-status').textContent=s.error||(s.placeholder?'尚未启用角色，请回助手选择Live2D。':'正在加载角色');}});
 const format=ms=>{const seconds=Math.ceil(ms/1000);return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`;};
 function accrue(){const now=performance.now();focus=S.reduce(focus,{type:'tick'},now);if(breakLast!==null){breakRemaining=Math.max(0,breakRemaining-(now-breakLast));breakLast=breakRemaining?now:null;}}
 function draw(){accrue();$('clock').textContent=format(focus.remaining);$('timer-state').textContent=({idle:'未开始',running:'计时中',paused:'已暂停',review:'本轮计时结束',break:'休息中'})[focus.phase];$('timer-toggle').textContent=focus.phase==='running'?'暂停专注':focus.phase==='paused'?'继续专注':'开始专注';$('break-toggle').textContent=breakLast!==null?'暂停休息':'开始休息';$('break-status').textContent=breakRemaining===0?'休息计时结束':breakLast!==null?format(breakRemaining):'休息计时已暂停';clearTimeout(timer);timer=0;if(!disposed&&!document.hidden&&(focus.phase==='running'||breakLast!==null))timer=setTimeout(draw,250);}
 function changeMode(next){accrue();if(focus.phase==='running')focus=S.reduce(focus,{type:'pause'},performance.now());breakLast=null;mode=next;$('room').dataset.mode=mode;$('room-state').textContent={focus:'专注',question:'回应提问',break:'短暂休息'}[mode];for(const name of ['focus','question','break'])$(name+'-widget').hidden=name!==mode;for(const b of document.querySelectorAll('button[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===mode));draw();}
 document.querySelectorAll('button[data-mode]').forEach(b=>b.onclick=()=>changeMode(b.dataset.mode));
 $('apply-topic').onclick=()=>{$('topic').textContent=$('topic-input').value.trim()||'本场主题尚未填写';};
 $('apply-question').onclick=()=>{$('question').textContent=$('question-input').value.trim()||'尚未置顶提问';changeMode('question');};
 $('apply-caption').onclick=()=>{$('caption').textContent=$('caption-input').value.trim();$('caption').hidden=!$('caption').textContent;};
 $('timer-toggle').onclick=()=>{if(mode!=='focus')changeMode('focus');const goal=$('topic-input').value.trim();if(!goal){$('issue').textContent='先填写本场主题，再开始计时。';return;}$('issue').textContent='';const now=performance.now();if(focus.phase==='running')focus=S.reduce(focus,{type:'pause'},now);else if(focus.phase==='paused')focus=S.reduce(focus,{type:'resume'},now);else{focus=S.fresh();focus=S.reduce(focus,{type:'goal',value:goal});focus=S.reduce(focus,{type:'duration',value:Number($('duration').value)});focus=S.reduce(focus,{type:'start'},now);}draw();};
 $('timer-reset').onclick=()=>{focus=S.fresh();draw();};
 $('break-duration').onchange=()=>{breakLast=null;breakRemaining=Number($('break-duration').value)*60000;draw();};
 $('break-toggle').onclick=()=>{if(mode!=='break')changeMode('break');accrue();if(breakLast!==null)breakLast=null;else{if(!breakRemaining)breakRemaining=Number($('break-duration').value)*60000;breakLast=performance.now();}draw();};
 $('hide-controls').onclick=()=>{$('controls').hidden=true;};$('show-controls').onclick=()=>{$('controls').hidden=false;};
 document.addEventListener('visibilitychange',()=>{scene.setVisible(!document.hidden);if(document.hidden){clearTimeout(timer);timer=0;}else draw();});
 window.addEventListener('pagehide',()=>{disposed=true;clearTimeout(timer);scene.dispose();});
 window.RoomPreview={scene,snapshot:()=>({focus:{...focus},mode,breakRemaining,breakRunning:breakLast!==null})};
 scene.setExpanded(false);
 api('room').then(data=>scene.sync({character_id:data.character.id,epoch:0,asset:data.character.appearance,scale:100})).catch(e=>{$('character-status').textContent=e.message;$('character-status').hidden=false;});draw();
})();
