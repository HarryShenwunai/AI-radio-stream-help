'use strict';
window.CompanionUI=(()=>{
 const NS='http://www.w3.org/2000/svg';
 function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
 function icon(name){const node=document.createElementNS(NS,'svg');node.setAttribute('class','icon');node.setAttribute('aria-hidden','true');const use=document.createElementNS(NS,'use');use.setAttribute('href','#i-'+name);node.append(use);return node;}
 function button(text,{icon:name,variant='',action,compact=false}={}){const node=el('button','button '+variant);node.type='button';node.setAttribute('aria-label',text);node.title=text;if(name)node.append(icon(name));node.append(el('span',compact?'sr-only':'',text));if(action)node.onclick=action;return node;}
 function field(title,{type='text',value='',placeholder='',required=false,maxLength,id,options}={}){
  const label=el('label','field'),caption=el('span','field-caption',title);let input;
  if(options){input=el('select');for(const item of options){const option=el('option','',item.label);option.value=item.value;input.append(option);}}
  else input=el(type==='textarea'?'textarea':'input');if(!options&&type!=='textarea')input.type=type;input.value=value??'';input.placeholder=placeholder;input.required=required;if(maxLength)input.maxLength=maxLength;if(id)input.id=id;label.append(caption,input);if(type==='file'){input.classList.add('sr-only');input.tabIndex=-1;const choose=button('选择文件',{icon:'upload',action:event=>{event.preventDefault();input.click();}}),filename=el('span','chosen-filename','尚未选择'),wrap=el('div','file-picker');choose.setAttribute('aria-label',title);input.addEventListener('change',()=>filename.textContent=input.files?.length?[...input.files].map(file=>file.name).join('、'):'尚未选择');wrap.append(choose,filename);label.append(wrap);}return {label,input};
 }
 function row(...nodes){const node=el('div','field-row');node.append(...nodes);return node;}
 function hint(text){return el('p','flow-hint',text);}
 function error(target,message){target.textContent=message||'';target.hidden=!message;}
 function formAction(form,text,action){const footer=el('footer','flow-footer'),submit=button(text,{variant:'primary'});submit.type='submit';footer.append(submit);form.append(footer);form.onsubmit=async event=>{event.preventDefault();if(submit.disabled)return;submit.disabled=true;try{await action(submit);}finally{if(submit.isConnected)submit.disabled=false;}};return {footer,submit};}
 function create({root,toast,beforeOpen=()=>{},onChange=()=>{}}){
  let active=null,theme='day',toastTimer=0;const changed=()=>onChange(active?.id||null);
  function notify(message){toast.textContent=message;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.hidden=true,4200);}
  function close(reason='close'){
   if(!active)return;const previous=active;active=null;try{previous.cleanup?.(reason);}finally{root.replaceChildren();root.hidden=true;document.body.dataset.layer='';document.querySelector('#scene-screen').inert=false;changed();if(reason!=='switch'&&reason!=='role-change'&&reason!=='hidden'){const target=previous.origin?.isConnected?previous.origin:document.querySelector('#compose-text');target?.focus?.();}}
  }
  function open(node,{id='flow',modal=true,onClose,focus}={}){
   const origin=document.activeElement;close('switch');beforeOpen(id);active={id,node,modal,origin,cleanup:onClose};root.replaceChildren(node);root.hidden=false;root.dataset.modal=String(modal);document.body.dataset.layer=id;document.querySelector('#scene-screen').inert=modal;changed();
   const target=focus||node.querySelector('input,textarea,select,button');queueMicrotask(()=>target?.focus?.());
  }
  function panel(title,{id='flow',className='',subtitle='',modal=true}={}){
   const node=el('section','experience-panel '+className);node.dataset.flow=id;node.setAttribute('role',modal?'dialog':'region');if(modal)node.setAttribute('aria-modal','true');
   const heading=el('header','experience-header'),titles=el('div'),h=el('h2','',title);h.id='heading-'+id;node.setAttribute('aria-labelledby',h.id);titles.append(h);if(subtitle)titles.append(el('p','eyebrow',subtitle));const quit=button('返回陪伴',{icon:'close',compact:true,action:()=>close()});quit.classList.add('close-layer');heading.append(titles,quit);const body=el('div','experience-body');node.append(heading,body);return {node,body,heading};
  }
  function setTheme(value,persist=true){theme=value==='night'?'night':'day';document.documentElement.dataset.theme=theme;if(persist)try{localStorage.setItem('companion-theme',theme);}catch{};onChange(active?.id||null);}
  document.addEventListener('keydown',event=>{if(!active||event.defaultPrevented)return;if(event.key==='Escape'){event.preventDefault();close();return;}if(event.key!=='Tab'||!active.modal)return;const items=[...active.node.querySelectorAll('button,input,textarea,select,a[href],[tabindex="0"]')].filter(node=>!node.disabled&&node.getClientRects().length);if(!items.length)return;const first=items[0],last=items.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}});
  root.addEventListener('click',event=>{if(event.target===root)close();});
  document.addEventListener('invalid',event=>{if(!active?.node.contains(event.target))return;for(let parent=event.target.parentElement;parent&&parent!==active.node;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;queueMicrotask(()=>{event.target.focus();event.target.scrollIntoView({block:'nearest'});});},true);
  try{setTheme(localStorage.getItem('companion-theme'),false);}catch{setTheme('day',false);}
  return {open,close,panel,notify,setTheme,get theme(){return theme;},get active(){return active?.id||null;},get activeModal(){return Boolean(active?.modal);}};
 }
 window.CompanionIcons={make:icon,button(node,name,label,compact=false){node.replaceChildren(icon(name),el('span',compact?'sr-only':'',label));node.setAttribute('aria-label',label);node.title=label;}};
 return Object.freeze({create,el,icon,button,field,row,hint,error,formAction});
})();
