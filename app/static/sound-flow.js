'use strict';
window.CompanionSound=(()=>{
 function create({core,ui,speech,getInputMode,setInputMode}){
  const {el,button,field,row,hint,error,formAction}=CompanionUI;
  async function open(){
   const stamp=core.scope(),s=core.get().state?.settings||{},frame=ui.panel('声音相处',{id:'sound'}),choices=el('div','segmented');let page='listen',status=null;
   const alive=()=>core.current(stamp)&&ui.active==='sound';
   function render(){frame.body.replaceChildren();for(const node of choices.children)node.setAttribute('aria-pressed',String(node.dataset.page===page));frame.body.append(choices);
    const form=el('form','purpose-form'),issue=el('p','inline-error');issue.hidden=true;issue.setAttribute('role','alert');
    if(page==='listen'){
     const backend=field('让她如何开口',{id:'sound-output',value:s.voice_backend||'kokoro',options:[{value:'kokoro',label:'本机语音模型'},{value:'system',label:'此设备的系统朗读'},{value:'external',label:'自选语音服务'}]}),auto=field('回复后自动朗读',{type:'checkbox'});auto.input.checked=Boolean(s.voice);
     const rate=field('语速',{type:'range',value:s.voice_rate||1});rate.input.min='.7';rate.input.max='1.4';rate.input.step='.05';
     const external=el('div','flow-group'),endpoint=field('语音服务地址',{type:'url',value:s.tts_endpoint||'',placeholder:'http://127.0.0.1:9880'}),reference=field('服务可读取的参考音频路径',{value:s.tts_reference_audio||''}),prompt=field('参考音频文字',{type:'textarea',value:s.tts_prompt_text||''}),language=field('生成语言',{value:s.tts_text_lang||'zh'}),referenceLanguage=field('参考音频语言',{value:s.tts_prompt_lang||'zh'});external.append(hint('仅向你指定的语音服务发送待朗读文字与参考信息。路径由服务读取，不会自动上传本机文件。'),endpoint.label,reference.label,prompt.label,row(language.label,referenceLanguage.label));
     const voices=field('系统音色',{options:(window.speechSynthesis?.getVoices()||[]).map(v=>({value:v.voiceURI,label:v.name+' · '+v.lang}))});try{voices.input.value=localStorage.getItem('character-voice:'+stamp.character_id)||'';}catch{}
     function update(){external.hidden=backend.input.value!=='external';voices.label.hidden=backend.input.value!=='system';endpoint.input.required=backend.input.value==='external';}backend.input.onchange=update;update();form.append(backend.label,auto.label,rate.label,voices.label,external,issue);
     formAction(form,'保存声音偏好',async()=>{try{await core.api('settings',{voice_backend:backend.input.value,voice:auto.input.checked,voice_rate:Number(rate.input.value),tts_endpoint:endpoint.input.value,tts_reference_audio:reference.input.value,tts_prompt_text:prompt.input.value,tts_text_lang:language.input.value,tts_prompt_lang:referenceLanguage.input.value});if(!alive())return;try{localStorage.setItem('character-voice:'+stamp.character_id,voices.input.value);}catch{}await core.refresh(true);ui.notify('声音偏好已保存。');}catch(cause){if(alive())error(issue,cause.message);}});
     form.append(button('试听当前已保存声音',{icon:'volume',action:()=>speech.speak('现在这样的声音，你听起来舒服吗？')}));
    }else{
     const mode=field('转写方式',{id:'sound-input',value:getInputMode(),options:[{value:'local',label:'本机识别'},{value:'browser',label:'浏览器识别（可能联网）'}]}),device=field('本机识别设备',{id:'asr-device',value:s.asr_device||'cpu',options:[{value:'cpu',label:'CPU'},{value:'cuda',label:'NVIDIA CUDA'}]}),precision=field('计算精度',{id:'asr-precision',value:s.asr_compute_type||'int8',options:['int8','float16','int8_float16','float32'].map(value=>({value,label:value}))}),local=el('div','flow-group'),readiness=el('p','readiness-note',status?.asr?.ready?'本机转写已准备好，单次最长60秒。':status?.asr?.reason||'正在读取本机识别状态…');
     const sync=()=>{const allowed=device.input.value==='cuda'?['float16','int8_float16','float32']:['int8','float32'];for(const option of precision.input.options)option.disabled=!allowed.includes(option.value);if(!allowed.includes(precision.input.value))precision.input.value=device.input.value==='cuda'?'float16':'int8';};device.input.onchange=sync;sync();local.append(readiness,row(device.label,precision.label));mode.input.onchange=()=>local.hidden=mode.input.value!=='local';mode.input.onchange();
     form.append(hint('点按录音，结束后文字留在输入框，确认后才发送。没有常开麦克风或双向通话。'),mode.label,local,hint('浏览器识别是否联网由浏览器与系统决定；选择后才会使用，不会作为本机识别失败的替代。'),issue);
     formAction(form,'使用此输入方式',async()=>{try{await core.api('settings',{asr_device:device.input.value,asr_compute_type:precision.input.value});if(!alive())return;setInputMode(mode.input.value);await core.refresh(true);ui.notify('语音输入方式已保存。');}catch(cause){if(alive())error(issue,cause.message);}});
    }frame.body.append(form);
   }
   for(const [value,title]of[['listen','听她说话'],['speak','语音输入']]){const b=button(title,{action:()=>{page=value;render();}});b.dataset.page=value;choices.append(b);}render();ui.open(frame.node,{id:'sound',onClose:()=>speech.stop()});
   try{status=await core.api('voice/status');if(alive()&&page==='speak')render();}catch{}
  }
  return {open};
 }
 return Object.freeze({create});
})();
