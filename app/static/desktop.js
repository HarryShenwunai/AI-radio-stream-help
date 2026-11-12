'use strict';
(() => {
 const host = window.companionDesktop;
 if (!host) return;
 document.body.classList.add('desktop-host', 'desktop-collapsed');
 document.documentElement.classList.add('desktop-host','desktop-collapsed');
 const tools = document.createElement('div');tools.className = 'desktop-tools';tools.setAttribute('aria-label','桌面控制');
 const drag = document.createElement('span');drag.className = 'desktop-drag';drag.textContent='⠿';drag.title='拖动角色';tools.append(drag);
 const buttons={};
 for(const [key,label,title] of [['expand','聊天','展开聊天'],['collapse','收起','回到角落'],['stop','停声','停止当前声音与回复'],['passthrough','穿透','鼠标穿透60秒；Ctrl+Shift+Space立即恢复'],['hide','隐藏','隐藏角色；Ctrl+Shift+Space恢复'],['quit','退出','退出应用']]){
  const button=document.createElement('button');button.type='button';button.textContent=label;button.title=title;button.dataset.desktopAction=key;button.setAttribute('aria-label',title);tools.append(button);buttons[key]=button;
 }
 document.body.append(tools);
 function pauseMedia(){
  if(typeof stopVoice==='function')stopVoice();
  if(typeof recognition!=='undefined'&&recognition){try{recognition.stop();}catch{}}
  window.dispatchEvent(new CustomEvent('companion:desktop-pause'));
 }
 async function action(fn){try{apply(await fn());}catch(error){if(typeof toast==='function')toast(error.message);}}
 function apply(value){
  window.companionDesktopHidden=value.visible===false;
  document.body.classList.toggle('desktop-collapsed',!value.expanded);
  document.documentElement.classList.toggle('desktop-collapsed',!value.expanded);
  buttons.expand.hidden=value.expanded;buttons.collapse.hidden=!value.expanded;
  buttons.passthrough.hidden=value.expanded;buttons.passthrough.setAttribute('aria-pressed',String(value.clickThrough));
  buttons.hide.disabled=!value.recoveryShortcut;
  if(!value.recoveryShortcut)buttons.hide.title='此系统没有恢复快捷键，请用收起或退出';
  if(value.visible===false)pauseMedia();
 }
 buttons.expand.onclick=()=>action(()=>host.setExpanded(true));
 buttons.collapse.onclick=()=>action(()=>host.setExpanded(false));
 buttons.stop.onclick=()=>{pauseMedia();document.querySelector('#stop-generation')?.click();};
 buttons.passthrough.onclick=()=>action(()=>host.setClickThrough(true));
 buttons.hide.onclick=()=>{pauseMedia();action(()=>host.hide());};
 buttons.quit.onclick=()=>{pauseMedia();action(()=>host.quit());};
 host.onState(apply);action(()=>host.getState());
 document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseMedia();});
})();
