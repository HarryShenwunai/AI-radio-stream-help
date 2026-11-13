'use strict';
window.CompanionStageActions=(()=>{
 function create({core,scene,ui,trigger,isHidden=()=>document.hidden||window.companionDesktopHidden===true}){
  let revision=0,opened=null;
  function scope(){return core.scope();}
  function same(stamp){const now=scope();return core.current(stamp)&&now.appearance_id===stamp.appearance_id&&!isHidden();}
  function catalog(){const snapshot=core.get(),asset=snapshot.state?.active_character?.appearance;if(snapshot.transitioning||snapshot.mutating||asset?.format!=='live2d'||!scene.ready)return {motions:[],expressions:[]};
   const diagnostics=scene.getDiagnostics();if(!diagnostics.available)return {motions:[],expressions:[]};const motions=[];
   for(const[group,count]of Object.entries(diagnostics.motions||{}))if(typeof group==='string'&&group&&Number.isInteger(count)&&count>0&&count<=64){for(let index=0;index<count&&motions.length<64;index++)motions.push({group,index,label:count===1?group:group+' '+(index+1)});}const expressions=Array.isArray(diagnostics.expressions)?[...new Set(diagnostics.expressions.filter(name=>typeof name==='string'&&name))].slice(0,64):[];return {motions,expressions};
  }
  function invalidate(){revision++;if(ui.active==='stage-actions')ui.close('role-change');opened=null;trigger.hidden=true;trigger.setAttribute('aria-expanded','false');}
  function refresh(){const items=catalog(),available=(items.motions.length>0||items.expressions.length>0)&&!isHidden();trigger.hidden=!available;trigger.setAttribute('aria-expanded',String(ui.active==='stage-actions'));if(!available&&ui.active==='stage-actions')ui.close('role-change');}
  function open(){if(ui.active==='stage-actions'){ui.close();refresh();return;}const items=catalog();if((!items.motions.length&&!items.expressions.length)||isHidden())return;const stamp=scope(),own=++revision,{el,button}=CompanionUI,frame=ui.panel('角色互动',{id:'stage-actions',className:'stage-actions-panel',modal:false}),list=el('div','stage-action-list'),error=el('p','inline-error'),buttons=[];error.hidden=true;error.setAttribute('role','alert');let busy=false;
   frame.node.id='stage-actions-panel';frame.node.setAttribute('role','dialog');
   const alive=()=>own===revision&&same(stamp)&&ui.active==='stage-actions'&&opened===frame;
   async function run(value){if(busy||!alive())return;const current=catalog();if((value.motion&&!current.motions.some(item=>item.group===value.motion.group&&item.index===value.motion.index))||(typeof value.expression==='string'&&!current.expressions.includes(value.expression))){invalidate();return;}busy=true;error.hidden=true;reload.hidden=true;list.setAttribute('aria-busy','true');for(const node of buttons)node.disabled=true;
    try{const result=await scene.applyControls(value);if(!alive())return;if(result===false)throw new Error('动作没有开始，可以重试。');ui.close();}
    catch(cause){if(alive()){error.textContent=cause?.message||'动作未能播放，请重试。';error.hidden=false;reload.hidden=false;}}
    finally{if(alive()){busy=false;list.setAttribute('aria-busy','false');for(const node of buttons)node.disabled=false;}}
   }
   for(const item of items.motions){const node=button(item.label,{action:()=>run({motion:{group:item.group,index:item.index}})});node.dataset.motionGroup=item.group;node.dataset.motionIndex=String(item.index);buttons.push(node);list.append(node);}
   for(const name of items.expressions){const node=button(name,{action:()=>run({expression:name})});node.dataset.expressionName=name;buttons.push(node);list.append(node);}
   const reload=button('重新载入形象',{icon:'reset',action:()=>{if(busy||!alive())return;busy=true;ui.close();Promise.resolve().then(()=>{if(same(stamp))return scene.retry();}).catch(()=>{if(same(stamp))ui.notify('形象未能重新载入，可以再次重试。');});}});reload.id='stage-reload-model';reload.hidden=true;
   const reset=button('恢复姿态',{icon:'reset',action:()=>run({reset:true,idleMotion:true,breath:true,autoBlink:true,physics:true,expression:null})});reset.id='stage-reset-pose';buttons.push(reset);frame.body.append(list,error,reload,reset);opened=frame;ui.open(frame.node,{id:'stage-actions',modal:false,onClose:()=>{revision++;opened=null;trigger.setAttribute('aria-expanded','false');}});trigger.setAttribute('aria-expanded','true');
  }
  trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls','stage-actions-panel');trigger.setAttribute('aria-expanded','false');trigger.onclick=open;
  const unbind=[core.on('invalidate',invalidate),core.on('media-stop',event=>{if(event.reason==='appearance-change')invalidate();})];
  refresh();return {open,refresh,invalidate,dispose(){invalidate();for(const stop of unbind)stop?.();trigger.onclick=null;}};
 }
 return Object.freeze({create});
})();
