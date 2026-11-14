'use strict';
(()=>{
 const app=window.CompanionApp;if(!app)return;const $=id=>document.getElementById(id),S=window.StudySession;
 let state=S.fresh(),role='',timer=null,disposed=false,storageWarning=false,draftNotice='';
 const labels={idle:'准备开始',running:'正在专注',paused:'已暂停',review:'本轮复盘',break:'休息一下'};
 function save(){if(!role)return;try{sessionStorage.setItem('study-room:'+role,JSON.stringify(state));}catch{storageWarning=true;}}
 function dispatch(event){if(event.type!=='tick')draftNotice='';state=S.reduce(state,event,performance.now());save();render();}
 function switchRole(){const next=app.core.scope().character_id;if(next===role)return;save();role=next;draftNotice='';try{state=S.restore(JSON.parse(sessionStorage.getItem('study-room:'+role)||'null'));}catch{state=S.fresh();}render();}
 function render(){
  const phase=state.phase,quiet=phase==='running',snapshot=app.core.get();document.body.dataset.studyPhase=phase;
  $('study-state').textContent=labels[phase];$('study-timer').textContent=`${String(Math.floor(Math.ceil(state.remaining/1000)/60)).padStart(2,'0')}:${String(Math.ceil(state.remaining/1000)%60).padStart(2,'0')}`;
  $('study-progress').value=phase==='break'?300000-state.remaining:state.elapsed;$('study-progress').max=phase==='break'?300000:state.minutes*60000;
  $('study-goal').disabled=phase!=='idle';if(document.activeElement!==$('study-goal'))$('study-goal').value=state.goal;
  $('study-kind').disabled=phase!=='idle';$('study-kind').value=state.kind;
  for(const b of document.querySelectorAll('[data-study-duration]')){b.disabled=phase!=='idle';b.setAttribute('aria-pressed',String(Number(b.dataset.studyDuration)===state.minutes));}
  const main=$('study-main');main.textContent=({idle:'开始专注',running:'暂停计时',paused:'继续专注',review:'保存本轮 · 休息 5 分钟',break:'结束休息 · 下一轮'})[phase];main.disabled=!role||phase==='idle'&&!state.goal.trim();
  $('study-finish').hidden=!['running','paused'].includes(phase);
  $('study-summary').textContent=`${state.rounds} 轮完成 · ${Math.floor(state.total/60000)} 分钟已记录`;
  $('study-guidance').textContent=storageWarning?'当前浏览器无法保存进度，请勿关闭此页。':snapshot.failed?'本次请求失败。材料已保留，可检查连接或重试。':draftNotice||({idle:'填写目标后开始计时。',running:'自动朗读已暂停。',paused:'计时已暂停。',review:`实际专注 ${Math.floor(state.elapsed/60000)} 分钟。勾选已完成的步骤，再决定下一轮。`,break:'休息结束后可开始下一轮。'})[phase];
  $('study-quiet').hidden=!quiet;$('study-quiet').textContent=quiet?'计时中':'';
  const texts=S.steps(state.kind);for(let i=0;i<3;i++){$('study-step-'+i).checked=state.checked[i];$('study-step-label-'+i).textContent=texts[i];}
  const st=snapshot.state;const ready=st&&(st.settings.engine==='api'?Boolean(st.settings.api_model):st.model_installed&&st.runtime_installed);
  $('study-ai-state').textContent=snapshot.failed?'本次请求失败，可检查连接或重试':ready?'':'配置模型后可准备问题';
  $('study-ai-plan').disabled=!role||!state.goal.trim()||Boolean(snapshot.chat)||Boolean(st?.model_busy);
  $('study-ai-review').disabled=!role||!state.goal.trim()||state.elapsed===0||Boolean(snapshot.chat)||Boolean(st?.model_busy);
  $('study-ai-state').hidden=!$('study-ai-state').textContent;
  $('study-live-state').textContent='本地';
 }
 function ask(mode){
  if(!state.goal.trim()){$('study-goal').focus();return;}
  const st=app.core.get().state,ready=st&&(st.settings.engine==='api'?Boolean(st.settings.api_model):st.model_installed&&st.runtime_installed);
  if(!ready){$('conversation-connection').click();return;}
  app.speech.stop();
  const input=$('compose-text'),result=S.draft(input.value,S.prompt(state,mode),input.maxLength);
  if(result.status==='added'){
   app.core.setDraft(result.text);input.value=result.text;input.dispatchEvent(new Event('input',{bubbles:true}));
  }
  draftNotice=result.status==='full'?'输入框已满，原有材料已保留。请先整理内容，再添加问题。':result.status==='unchanged'?'问题已在输入框中，原有材料已保留；检查后由你发送。':'原有材料已保留，问题已补在末尾；检查后由你发送。';
  input.focus();render();
 }
 $('compose-text').addEventListener('input',()=>{draftNotice='';});
 $('study-goal').addEventListener('input',e=>dispatch({type:'goal',value:e.target.value}));
 $('study-kind').addEventListener('change',e=>dispatch({type:'kind',value:e.target.value}));
 for(const b of document.querySelectorAll('[data-study-duration]'))b.onclick=()=>dispatch({type:'duration',value:Number(b.dataset.studyDuration)});
 $('study-main').onclick=()=>{if(['idle','paused'].includes(state.phase))app.speech.stop();dispatch({type:({idle:'start',running:'pause',paused:'resume',review:'save',break:'skip'})[state.phase]});};
 $('study-finish').onclick=()=>dispatch({type:'finish'});
 $('study-ai-plan').onclick=()=>ask('plan');$('study-ai-review').onclick=()=>ask('review');
 for(let i=0;i<3;i++)$('study-step-'+i).onchange=()=>dispatch({type:'check',index:i});
 $('study-clear').onclick=()=>{dispatch({type:'clear'});$('study-goal').focus();};
 $('study-connect').onclick=()=>app.openConnections();
 $('study-view').onclick=()=>{const on=!document.body.classList.contains('study-immersive');document.body.classList.toggle('study-immersive',on);$('study-view').setAttribute('aria-pressed',String(on));$('study-view').textContent=on?'展开学习台':'收起学习台';};
 const offChange=app.core.on('change',()=>{switchRole();render();});const offInvalidate=app.core.on('invalidate',()=>{if(state.phase==='running')dispatch({type:'pause'});save();});
 timer=setInterval(()=>{if(!disposed&&['running','break'].includes(state.phase))dispatch({type:'tick'});},250);
 const close=()=>{disposed=true;clearInterval(timer);offChange();offInvalidate();if(state.phase==='running')state=S.reduce(state,{type:'pause'},performance.now());save();};
 window.addEventListener('pagehide',close,{once:true});document.body.classList.add('study-room');switchRole();render();
 window.CompanionStudy=Object.freeze({isQuiet:()=>state.phase==='running',snapshot:()=>({...state,checked:[...state.checked]}),dispose:close});
})();
