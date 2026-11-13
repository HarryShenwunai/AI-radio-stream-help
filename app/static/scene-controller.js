'use strict';
window.CompanionScene=(()=>{
 const bundles=new Map();
 function script(path){return new Promise((resolve,reject)=>{const tag=document.createElement('script');tag.src=path;tag.onload=resolve;tag.onerror=()=>{tag.remove();reject(new Error('角色显示组件读取失败。'));};document.head.append(tag);});}
 async function engine(format,api){
  if(format==='vrm'){
   if(!bundles.has('vrm'))bundles.set('vrm',script('/vrm-renderer.js').then(()=>{if(typeof window.CompanionVrm?.create!=='function')throw new Error('角色显示组件未正确初始化。');return window.CompanionVrm;}).catch(error=>{bundles.delete('vrm');throw error;}));return bundles.get('vrm');
  }
  const status=await api('live2d/runtime');
  if(!status.available||status.core_url!=='/live2d-core.js'||status.runtime_url!=='/live2d-runtime.js')throw new Error('需要先安装已获授权的 Live2D 运行时。');
  if(!bundles.has('live2d'))bundles.set('live2d',(async()=>{if(!window.Live2DCubismCore)await script('/live2d-core.js');if(!window.CompanionLive2DRuntime)await script('/live2d-runtime.js');await script('/live2d-renderer.js');if(typeof window.CompanionLive2D?.create!=='function')throw new Error('角色显示组件未正确初始化。');return window.CompanionLive2D;})().catch(error=>{bundles.delete('live2d');throw error;}));return bundles.get('live2d');
 }
 function resource(asset,state='idle'){
  const item=state==='model'?asset?.model:state==='thumbnail'?asset?.thumbnail:asset?.states?.[state];if(!item?.url)return '';
  const parsed=new URL(item.url,location.href);if(parsed.origin!==location.origin||!parsed.pathname.startsWith('/api/assets/'))throw new Error('角色引用了未允许的资源。');return item.url;
 }
 function create({container,image,api,onState=()=>{},preview=false}){
  let model=null,spec=null,key='',ticket=0,disposed=false,visible=true,speaking=false,audio=null,blink=false,blinkTimer=0,blinkEnd=0,expanded=true,ready=false,assetRequest=null;
  let pngCanvas=null,pngContext=null,drawKey='',patches=new Map();let cache=new Map(),audioContext=null,source=null,analyser=null,samples=null,analysisRaf=0,analysisTime=0,smoothed=0,mouthOpen=false,systemTimer=0,requestCount=0;
  function stopBlink(){clearTimeout(blinkTimer);clearTimeout(blinkEnd);blinkTimer=blinkEnd=0;blink=false;}
  function stopAnalysis(){if(analysisRaf)cancelAnimationFrame(analysisRaf);analysisRaf=0;clearTimeout(systemTimer);systemTimer=0;smoothed=0;mouthOpen=false;}
  function detachAudio(close=false){stopAnalysis();try{source?.disconnect();analyser?.disconnect();}catch{}source=analyser=samples=null;audio=null;if(close){audioContext?.close().catch(()=>{});audioContext=null;}}
  function release(){ticket++;ready=false;stopBlink();detachAudio(true);assetRequest?.abort();assetRequest=null;model?.dispose();model=null;for(const entry of cache.values())URL.revokeObjectURL(entry.url);cache.clear();for(const patch of patches.values())patch.width=patch.height=0;patches.clear();pngCanvas=null;pngContext=null;drawKey='';key='';container.replaceChildren();if(image){image.hidden=true;image.removeAttribute('src');delete image.dataset.source;}}
  function publish(state,error=''){onState({state,error,ready,placeholder:!spec?.asset||state==='error'||state==='empty',format:spec?.asset?.format||'png'});}
  function patch(state,name,region){const key=state+':'+name;if(patches.has(key))return patches.get(key);const result=document.createElement('canvas');result.width=region.width;result.height=region.height;const ctx=result.getContext('2d');ctx.drawImage(cache.get(state).image,region.x,region.y,region.width,region.height,0,0,region.width,region.height);const feather=region.feather||0;if(feather){ctx.globalCompositeOperation='destination-in';for(const vertical of [false,true]){const limit=vertical?region.height:region.width,gradient=ctx.createLinearGradient(0,0,vertical?0:limit,vertical?limit:0);gradient.addColorStop(0,'transparent');gradient.addColorStop(feather/limit,'#000');gradient.addColorStop(1-feather/limit,'#000');gradient.addColorStop(1,'transparent');ctx.fillStyle=gradient;ctx.fillRect(0,0,region.width,region.height);}}patches.set(key,result);return result;}
  function regionalPng(){const regions=spec.asset.animation_regions;if(!regions||!Object.keys(regions).length)return false;const idle=cache.get('idle');if(!pngCanvas){pngCanvas=document.createElement('canvas');pngCanvas.className='regional-png-canvas';pngCanvas.setAttribute('role','img');pngCanvas.setAttribute('aria-label','当前角色形象');pngCanvas.width=idle.width;pngCanvas.height=idle.height;pngContext=pngCanvas.getContext('2d',{alpha:true});container.replaceChildren(pngCanvas);}container.hidden=false;image.hidden=true;pngCanvas.style.transform='scale('+((spec.scale||100)/100)+')';const opening=speaking&&mouthOpen,eyes=blink?(opening&&cache.has('talk_blink')?'talk_blink':cache.has('blink')?'blink':'idle'):'idle',mouth=opening?(blink&&cache.has('talk_blink')?'talk_blink':cache.has('talk')?'talk':'idle'):'idle',next=eyes+':'+mouth;if(next!==drawKey){drawKey=next;pngContext.clearRect(0,0,idle.width,idle.height);pngContext.drawImage(idle.image,0,0);for(const [name,state]of [['eyes',eyes],['mouth',mouth]])if(regions[name]&&state!=='idle'){const region=regions[name];pngContext.drawImage(patch(state,name,region),region.x,region.y);}}return true;}
  function png(){
   if(!image||!spec?.asset||!ready){if(image)image.hidden=true;return;}
   const asset=spec.asset,opening=speaking&&mouthOpen;
   const state=blink&&opening&&cache.has('talk_blink')?'talk_blink':blink&&cache.has('blink')?'blink':opening&&cache.has('talk')?'talk':'idle';
   const src=cache.get(state)?.url||cache.get('idle')?.url;if(!src){image.hidden=true;return;}if(image.dataset.source!==src){image.dataset.source=src;image.src=src;}image.hidden=false;image.style.transform='scale('+((spec.scale||100)/100)+')';regionalPng();
   const canBlink=!preview&&(cache.has('blink')||opening&&cache.has('talk_blink'));if(!canBlink||!visible){stopBlink();return;}
   if(!blinkTimer&&!blinkEnd&&!blink){const own=ticket;blinkTimer=setTimeout(()=>{blinkTimer=0;if(own!==ticket||!visible)return;blink=true;png();blinkEnd=setTimeout(()=>{blinkEnd=0;if(own!==ticket)return;blink=false;png();},120);},1500+Math.random()*4500);}
  }
  async function preload(asset,own){const controller=new AbortController();assetRequest=controller;const entries=Object.entries(asset.states||{});let failed=false;try{await Promise.all(entries.map(async([state,item])=>{const url=resource(asset,state);requestCount++;const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw new Error('角色状态图读取失败。');const blob=await response.blob();if(blob.size>4*1024*1024)throw new Error('角色状态图过大。');if(ticket!==own||disposed)return;const local=URL.createObjectURL(blob),decoded=new Image();try{decoded.src=local;await decoded.decode();if(failed||ticket!==own||disposed){URL.revokeObjectURL(local);return;}cache.set(state,{url:local,image:decoded,width:decoded.naturalWidth,height:decoded.naturalHeight});}catch(error){URL.revokeObjectURL(local);throw error;}}));if(ticket!==own||disposed)return false;if(!cache.has('idle'))throw new Error('形象没有可显示的常态图片。');return true;}catch(error){failed=true;controller.abort();throw error;}finally{if(assetRequest===controller)assetRequest=null;}}
  function analyse(now){analysisRaf=0;if(disposed||!visible||preview||!speaking||!analyser)return;if(now-analysisTime>=32){analysisTime=now;analyser.getByteTimeDomainData(samples);let sum=0;for(const value of samples)sum+=((value-128)/128)**2;const rms=Math.sqrt(sum/samples.length);smoothed=rms>smoothed?smoothed*.4+rms*.6:smoothed*.2+rms*.8;const next=mouthOpen?smoothed>.006:smoothed>.012;if(next!==mouthOpen){mouthOpen=next;png();}}analysisRaf=requestAnimationFrame(analyse);}
  async function sync(value){
   if(disposed)return;spec=value;if(!visible)return;
   const nextKey=[value.character_id,value.epoch,value.asset?.id||'placeholder'].join(':');
   if(nextKey===key){model?.setScale((value.scale||100)/100);if(!model)png();return ready;}
   release();key=nextKey;const own=ticket,asset=value.asset;
   if(!asset){container.hidden=true;ready=true;publish('ready');return true;}
   if(!['vrm','live2d','layered-2d'].includes(asset.format)){container.hidden=true;publish('loading');try{if(!await preload(asset,own))return false;ready=true;png();publish('ready');return true;}catch(error){if(ticket===own){ready=false;for(const entry of cache.values())URL.revokeObjectURL(entry.url);cache.clear();publish('error',error.message);}return false;}}
   container.hidden=false;publish('loading');if(image)image.hidden=true;
   try{
    const library=asset.format==='layered-2d'?await layered():await engine(asset.format,api);if(disposed||ticket!==own||!visible)return false;
    let paintedResolve;const painted=new Promise(resolve=>paintedResolve=resolve);
    model=library.create({container,collapsedFps:preview?20:30,expandedFps:preview?30:60,onError:error=>{if(ticket===own){ready=false;container.hidden=true;publish('error',error);paintedResolve(false);}},onStats:stats=>{if(ticket!==own)return;container.dataset.state=stats.state;container.dataset.frames=String(stats.frames);container.dataset.mouth=String(stats.mouth);if(stats.frames>0&&stats.state==='ready')paintedResolve(true);}});
    const instance=model,result=await instance.load(['live2d','layered-2d'].includes(asset.format)?asset:resource(asset,'model'));
    if(ticket!==own||disposed){instance.dispose();return false;}if(!result){instance.dispose();if(model===instance)model=null;ready=false;container.hidden=true;publish('error','角色加载失败，可以重试。');return false;}
    const timer=setTimeout(()=>paintedResolve(false),15000);const rendered=instance.getStats?.().frames>0||await painted;clearTimeout(timer);
    if(ticket!==own||disposed||!visible)return false;if(!rendered){instance.dispose();model=null;publish('error','角色尚未成功绘制，可以重试。');return false;}
    ready=true;instance.setScale((spec.scale||100)/100);instance.setExpanded(expanded);instance.setSpeaking(speaking);if(speaking&&audio)instance.setAudio(audio);publish('ready');return true;
   }catch(error){if(ticket===own){ready=false;model?.dispose();model=null;container.hidden=true;publish('error',error.message);if(image)image.hidden=true;}return false;}
  }
  async function layered(){if(!bundles.has('layered'))bundles.set('layered',script('/layered-2d-renderer.js').then(()=>{if(typeof window.CompanionLayered2D?.create!=='function')throw new Error('角色显示组件未正确初始化。');return window.CompanionLayered2D;}).catch(error=>{bundles.delete('layered');throw error;}));return bundles.get('layered');}
  return {sync,retry(){if(spec){const value=spec;release();return sync(value);}},setSpeaking(value){speaking=Boolean(value);if(model){model.setSpeaking(speaking);if(!speaking)audio=null;}else{if(!speaking)detachAudio();png();}},
   systemBoundary(){if(model){model.systemBoundary?.();return;}if(!speaking||audio||!visible||preview)return;mouthOpen=true;png();clearTimeout(systemTimer);systemTimer=setTimeout(()=>{mouthOpen=false;png();},125);},
   setAudio(value){if(disposed||!value||!visible||preview)return;if(model){audio=value;model.setAudio(value);return;}if(audio===value)return;detachAudio();audio=value;try{audioContext??=new(window.AudioContext||window.webkitAudioContext)();source=audioContext.createMediaElementSource(value);analyser=audioContext.createAnalyser();analyser.fftSize=512;samples=new Uint8Array(analyser.fftSize);source.connect(analyser);analyser.connect(audioContext.destination);audioContext.resume().catch(()=>{});if(speaking&&!analysisRaf)analysisRaf=requestAnimationFrame(analyse);}catch{detachAudio();}},
   setExpanded(value){expanded=Boolean(value);model?.setExpanded(expanded);},setTracking(value){model?.setTracking?.(value);},applyControls(value){if(!model?.applyControls)throw new Error('此形象没有这些模型控制。');return model.applyControls(value);},getDiagnostics(options){return model?.getDiagnostics?.(options)||{available:false,state:ready?'ready':'empty'};},
   setVisible(value,{free=false}={}){visible=Boolean(value);if(!visible){stopBlink();stopAnalysis();if(free)release();else model?.setHidden(true);}else if(spec){if(model){model.setScale((spec.scale||100)/100);model.setHidden(false);model.setSpeaking(speaking);if(speaking&&audio)model.setAudio(audio);}else{sync(spec);if(speaking&&analyser&&!analysisRaf)analysisRaf=requestAnimationFrame(analyse);}}},
   clear(){release();spec=null;speaking=false;audio=null;publish('empty');},get ready(){return ready;},getStats(){return model?.getStats?.()||{state:ready?'ready':'empty',cacheSize:cache.size,requestCount,mouth:mouthOpen?1:0,audioAnalysis:Boolean(analysisRaf),format:spec?.asset?.format};},dispose(){disposed=true;release();spec=null;}};
 }
 return Object.freeze({create,resource});
})();
