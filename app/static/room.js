'use strict';
(()=>{
 const $=id=>document.getElementById(id),S=window.StudySession,modes=['focus','question','break'];
 const fresh=()=>({version:1,mode:'focus',topic:'',question:'',caption:'',minutes:25,breakMinutes:5,applied:false});
 function configFrom(value){const c=fresh();if(!value||value.version!==1)return c;for(const [key,max] of [['topic',100],['question',220],['caption',300]])if(typeof value[key]==='string')c[key]=value[key].slice(0,max);if(modes.includes(value.mode))c.mode=value.mode;if([15,25,50].includes(value.minutes))c.minutes=value.minutes;if([3,5,10].includes(value.breakMinutes))c.breakMinutes=value.breakMinutes;c.applied=value.applied===true;return c;}
 let config=fresh(),draftMode='focus',focus=S.fresh(),breakRemaining=300000,breakStarted=false,breakLast=null,timer=0,disposed=false,loaded=false,key='',fitFrame=0;
 async function api(path){const response=await fetch('/api/'+path,{headers:{'X-Companion':'local-app'},cache:'no-store'}),data=await response.json();if(!response.ok)throw Error(data.error||'请先打开助手。');return data;}
 const scene=CompanionScene.create({container:$('character-canvas'),image:$('character-image'),api,onState:s=>{$('character-status').hidden=s.ready&&!s.placeholder;$('character-status').textContent=s.error||(s.placeholder?'未启用角色':'正在加载角色');}});
 const format=ms=>{const seconds=Math.ceil(ms/1000);return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`;};
 function accrue(){const now=performance.now();focus=S.reduce(focus,{type:'tick'},now);if(breakLast!==null){breakRemaining=Math.max(0,breakRemaining-(now-breakLast));breakLast=breakRemaining?now:null;}}
 function persist(){if(!key)return;try{localStorage.setItem(key,JSON.stringify({config,draft:readDraft(),focus,breakRemaining,breakStarted}));}catch{$('issue').textContent='无法保存设置。';}}
 function readDraft(){return {...config,mode:draftMode,topic:$('topic-input').value.trim(),question:$('question-input').value.trim(),caption:$('caption-input').value.trim(),minutes:Number($('duration').value),breakMinutes:Number($('break-duration').value),applied:true};}
 function dirty(){return !config.applied||JSON.stringify(readDraft())!==JSON.stringify(config);}
 function feedback(){for(const b of document.querySelectorAll('button[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===draftMode));$('settings-state').textContent=dirty()?'未应用':'已应用';$('applied-mode').textContent={focus:'专注',question:'提问',break:'休息'}[config.mode];}
 function inputs(value=config){draftMode=value.mode;$('topic-input').value=value.topic;$('question-input').value=value.question;$('caption-input').value=value.caption;$('duration').value=String(value.minutes);$('break-duration').value=String(value.breakMinutes);}
 function draw(){
  accrue();$('room').dataset.mode=config.mode;$('room-state').textContent={focus:'专注',question:'提问',break:'休息'}[config.mode];$('room-state').hidden=!config.applied;
  $('topic').textContent=config.topic;$('topic').hidden=!config.topic;document.querySelector('.paper-rule').hidden=!config.topic;
  $('question').textContent=config.question;$('question-widget').hidden=config.mode!=='question'||!config.question;
  $('caption').textContent=config.caption;$('caption').hidden=!config.caption;
  $('focus-widget').hidden=config.mode!=='focus'||focus.phase==='idle';$('clock').textContent=format(focus.remaining);$('timer-state').textContent=({idle:'未开始',running:'计时中',paused:'已暂停',review:'已结束',break:'休息中'})[focus.phase];
  $('break-widget').hidden=config.mode!=='break'||!breakStarted;$('break-status').textContent=breakStarted?(breakRemaining===0?'已结束':format(breakRemaining)):'';
  $('timer-toggle').textContent=focus.phase==='running'?'暂停':focus.phase==='paused'?'继续':'开始';$('timer-toggle').disabled=config.mode!=='focus';$('duration').disabled=focus.phase!=='idle';
  $('break-toggle').textContent=breakLast!==null?'暂停':breakStarted&&breakRemaining>0?'继续':'开始';$('break-toggle').disabled=config.mode!=='break';$('break-duration').disabled=breakStarted;
  feedback();clearTimeout(timer);timer=0;if(!disposed&&!document.hidden&&(focus.phase==='running'||breakLast!==null))timer=setTimeout(draw,250);
 }
 function fits(next){
  const source=$('room'),probe=source.cloneNode(true),box=source.getBoundingClientRect();probe.querySelector('.character-space').remove();Object.assign(probe.style,{position:'fixed',left:'-100000px',top:'0',width:box.width+'px',height:box.height+'px',visibility:'hidden',pointerEvents:'none'});probe.dataset.mode=next.mode;
  const put=(id,text)=>{const n=probe.querySelector('#'+id);n.textContent=text;n.hidden=!text;};put('topic',next.topic);put('question',next.question);put('caption',next.caption);probe.querySelector('.paper-rule').hidden=!next.topic;probe.querySelector('#question-widget').hidden=next.mode!=='question'||!next.question;probe.querySelector('#focus-widget').hidden=next.mode!=='focus'||focus.phase==='idle';probe.querySelector('#break-widget').hidden=next.mode!=='break'||!breakStarted;
  document.body.append(probe);let bad='';for(const [id,label] of [['topic','主题'],['question','提问'],['caption','字幕']]){const n=probe.querySelector('#'+id);if(n.getClientRects().length&&(n.scrollHeight>n.clientHeight+1||n.scrollWidth>n.clientWidth+1)){bad=label;break;}}
  if(!bad){const area=probe.querySelector('.page-space');if(area.scrollHeight>area.clientHeight+1)bad='内容';}probe.remove();if(bad){$('issue').textContent=bad+'超出画面，请缩短文本。';return false;}$('issue').textContent='';return true;
 }
 function pause(){accrue();if(focus.phase==='running')focus=S.reduce(focus,{type:'pause'},performance.now());breakLast=null;}
 $('apply-settings').onclick=()=>{const next=configFrom(readDraft()),topicChanged=next.topic!==config.topic;if(!fits(next))return;if(next.mode!==config.mode||topicChanged)pause();if(topicChanged){focus=S.fresh();breakStarted=false;breakRemaining=next.breakMinutes*60000;}else if(!breakStarted)breakRemaining=next.breakMinutes*60000;config=next;$('room').dataset.overflow='false';persist();draw();};
 $('clear-scene').onclick=()=>{pause();config={...fresh(),minutes:config.minutes,breakMinutes:config.breakMinutes};focus=S.fresh();breakRemaining=config.breakMinutes*60000;breakStarted=false;$('room').dataset.overflow='false';persist();draw();};
 document.querySelectorAll('button[data-mode]').forEach(b=>b.onclick=()=>{draftMode=b.dataset.mode;feedback();});
 for(const id of ['topic-input','question-input','caption-input','duration','break-duration'])$(id).addEventListener('input',feedback);
 $('timer-toggle').onclick=()=>{const now=performance.now();if(!config.topic){$('issue').textContent='请先应用主题。';return;}$('issue').textContent='';if(focus.phase==='running')focus=S.reduce(focus,{type:'pause'},now);else if(focus.phase==='paused')focus=S.reduce(focus,{type:'resume'},now);else{focus=S.fresh();focus=S.reduce(focus,{type:'goal',value:config.topic});focus=S.reduce(focus,{type:'duration',value:config.minutes});focus=S.reduce(focus,{type:'start'},now);}persist();draw();};
 $('timer-reset').onclick=()=>{focus=S.fresh();persist();draw();};
 $('break-toggle').onclick=()=>{accrue();if(breakLast!==null)breakLast=null;else{if(!breakRemaining)breakRemaining=config.breakMinutes*60000;breakStarted=true;breakLast=performance.now();}persist();draw();};
 $('break-reset').onclick=()=>{breakLast=null;breakStarted=false;breakRemaining=config.breakMinutes*60000;persist();draw();};
 $('hide-controls').onclick=()=>{$('controls').hidden=true;document.body.classList.add('settings-hidden');$('show-controls').hidden=false;};$('show-controls').onclick=()=>{$('controls').hidden=false;document.body.classList.remove('settings-hidden');$('show-controls').hidden=true;};
 $('fullscreen-preview').onclick=()=>{$('preview-shell').requestFullscreen().catch(()=>{$('issue').textContent='无法进入全屏。';});};
 function reflow(){if(!loaded||!config.applied)return;$('room').dataset.overflow=String(!fits(config));}
 const layoutObserver=new ResizeObserver(()=>{cancelAnimationFrame(fitFrame);if(!disposed&&!document.hidden)fitFrame=requestAnimationFrame(reflow);});layoutObserver.observe($('room'));
 document.addEventListener('visibilitychange',()=>{scene.setVisible(!document.hidden);if(document.hidden){accrue();persist();clearTimeout(timer);timer=0;}else{draw();reflow();}});
 window.addEventListener('pagehide',()=>{pause();persist();disposed=true;clearTimeout(timer);cancelAnimationFrame(fitFrame);layoutObserver.disconnect();scene.dispose();});
 window.RoomPreview={scene,get loaded(){return loaded;},snapshot:()=>({focus:{...focus},mode:config.mode,config:{...config},draftMode,breakRemaining,breakRunning:breakLast!==null})};
 scene.setExpanded(false);
 api('room').then(data=>{key='room-settings:'+data.character.id;let draft=null;try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){config=configFrom(saved.config);draft=configFrom(saved.draft||saved.config);focus=S.restore(saved.focus);if(focus.goal!==config.topic||focus.minutes!==config.minutes)focus=S.fresh();breakStarted=saved.breakStarted===true;breakRemaining=Number.isFinite(saved.breakRemaining)?Math.max(0,Math.min(config.breakMinutes*60000,saved.breakRemaining)):config.breakMinutes*60000;}}catch{$('issue').textContent='无法读取已保存设置。';}inputs(draft||config);loaded=true;$('room-settings').disabled=false;$('clear-scene').disabled=false;draw();reflow();return scene.sync({character_id:data.character.id,epoch:0,asset:data.character.appearance,scale:100});}).catch(e=>{$('character-status').textContent=e.message;$('character-status').hidden=false;});draw();
})();
