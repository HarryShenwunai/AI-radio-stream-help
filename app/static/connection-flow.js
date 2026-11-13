'use strict';
window.CompanionConnection=(()=>{
 function create({core,ui}){
  const {el,button,field,row,hint,error,formAction}=CompanionUI;
  function open(initial){
   const stamp=core.scope(),state=core.get().state,settings=state?.settings||{},frame=ui.panel('让对话开始',{id:'connection',subtitle:'连接供你的角色共同使用'});let page=initial||'choose';
   const alive=()=>core.current(stamp)&&ui.active==='connection';
   function render(){
    frame.body.replaceChildren();
    if(page==='choose'){
     const intro=el('p','flow-lead','选择她从哪里获得对话能力。');frame.body.append(intro);
     const choices=el('div','choice-grid');
     choices.append(button('使用本机模型',{icon:'spark',variant:'choice-card',action:()=>{page='local';render();}}),button('连接模型服务',{icon:'platform',variant:'choice-card',action:()=>{page='api';render();}}));
     frame.body.append(choices,hint('本机运行与外部服务的费用、速度和数据范围不同。连接后仍由你决定发送什么。'));return;
    }
    frame.body.append(button('返回选择',{icon:'chevron',variant:'back-button',action:()=>{page='choose';render();}}));
    const form=el('form','purpose-form'),issue=el('p','inline-error');issue.hidden=true;issue.setAttribute('role','alert');
    if(page==='local'){
     const readiness=el('div','readiness-card');readiness.append(el('h3','',state?.runtime_installed&&state?.model_installed?'本机模型已安装':'本机模型还未准备好'),hint(state?.runtime_installed&&state?.model_installed?state.model_label||'将在首次对话时加载。':'你可以保留本机方式，完成运行组件与模型准备后再对话。'));
     const device=field('运行方式',{id:'connection-device',value:settings.local_compute||'cpu',options:[{value:'cpu',label:'CPU'},{value:'auto',label:'自动选择可用设备'},{value:'cuda',label:'NVIDIA CUDA'}]});
     const advanced=el('details','flow-disclosure'),summary=el('summary','','调整本机推理');advanced.append(summary);
     const layers=field('显卡卸载层数',{type:'number',value:settings.local_gpu_layers??20}),context=field('上下文长度',{value:String(settings.local_context||4096),options:[{value:'2048',label:'2048'},{value:'4096',label:'4096'}]});layers.input.min='0';layers.input.max='64';layers.input.step='1';advanced.append(row(layers.label,context.label));
     form.append(readiness,device.label,advanced,issue);formAction(form,'使用本机方式',async()=>{try{await core.api('settings',{engine:'local',local_compute:device.input.value,local_gpu_layers:Number(layers.input.value),local_context:Number(context.input.value)});if(!alive())return;await core.refresh(true);ui.close();ui.notify('已选择本机对话方式。');}catch(cause){if(alive())error(issue,cause.message);}});
    }else{
     const address=field('服务地址',{id:'connection-address',type:'url',value:settings.api_base||'',placeholder:'https://服务地址/v1',required:true}),model=field('模型',{id:'connection-model',value:settings.api_model||'',required:true}),key=field('密钥',{id:'connection-key',type:'password',placeholder:state?.has_api_key?'已保存，留空保留':'服务提供方的密钥'});key.input.autocomplete='new-password';
     const clear=field('清除已保存密钥',{type:'checkbox'});clear.input.checked=false;
     form.append(el('p','flow-lead','后续对话与必要上下文将发送到你选择的服务。'),address.label,model.label,key.label,clear.label,issue);
     formAction(form,'保存并用于后续对话',async()=>{try{await core.api('settings',{engine:'api',api_base:address.input.value.trim(),api_model:model.input.value.trim(),api_key:key.input.value,clear_api_key:clear.input.checked});if(!alive())return;key.input.value='';await core.refresh(true);ui.close();ui.notify('对话连接已保存。');}catch(cause){if(alive())error(issue,cause.message);}});
    }
    frame.body.append(form);
   }
   render();ui.open(frame.node,{id:'connection',onClose:()=>{for(const input of frame.node.querySelectorAll('input[type=password]'))input.value='';}});
  }
  return {open};
 }
 return Object.freeze({create});
})();
