'use strict';
// Private credentials stay in the caller's closure. Every resource is read by
// POST against the frozen scene allowlist; none is granted by a URL or cookie.
window.ProgramScene=(()=>{
 function create({call,container,image,onState}){
  let current=null,serial=0,disposed=false,resources=new Map(),urls=new Map(),loading=null;
  const nonce=document.querySelector('script[data-program-loader]').nonce;
  const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  async function checked(action,name,descriptor,own){
   const blob=await call(action,{revision:current.sha256,name},true),bytes=await blob.arrayBuffer();
   if(disposed||own!==serial)throw Error('节目人物已失效。');
   if(await digest(bytes)!==descriptor.sha256)throw Error('节目资源校验失败。');
   return new Blob([bytes],{type:descriptor.mime||blob.type});
  }
  function key(url){const parsed=new URL(url,location.href);if(!current||parsed.origin!==location.origin||parsed.pathname!==('/api/assets/'+encodeURIComponent(current.appearance_id)+'/'+parsed.pathname.split('/').at(-1))||parsed.searchParams.get('character_id')!==current.character_id||parsed.searchParams.size!==1)throw Error('未批准的节目资源。');const value=resources.get(parsed.href);if(!value)throw Error('未批准的节目资源。');return parsed.href;}
  const transport={
   async fetch(url){const name=key(url),item=resources.get(name),own=serial;const blob=await checked('resource',item.resource,item,own);return new Response(blob,{headers:{'Content-Type':item.mime}});},
   resolve(url){const name=key(url);if(!urls.has(name))throw Error('节目资源尚未校验。');return urls.get(name);},
   async script(path){if(!['/live2d-core.js','/live2d-runtime.js'].includes(path))throw Error('未批准的节目运行时。');const kind=path==='/live2d-core.js'?'core':'bundle',own=serial,sha=current?.runtime_sha256?.[kind];if(!sha)throw Error('需要先安装已获授权的 Live2D 运行时。');const blob=await checked('runtime',kind,{sha256:sha,mime:'application/javascript'},own);if(own!==serial||disposed)throw Error('节目人物已失效。');const tag=document.createElement('script');tag.nonce=nonce;tag.textContent=await blob.text();document.head.append(tag);tag.remove();}
  };
  const api=async path=>{if(path!=='live2d/runtime')throw Error('未允许的节目接口。');return {available:current?.runtime_available===true,core_url:'/live2d-core.js',runtime_url:'/live2d-runtime.js'};};
  const scene=CompanionScene.create({container,image,api,transport,onState});scene.setExpanded(false);
  function clear(){serial++;loading=null;scene.clear();for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();resources.clear();current=null;}
  async function sync(snapshot){
   if(disposed)return false;if(current?.sha256===snapshot?.sha256)return loading||scene.ready;
   clear();if(!snapshot)return false;current=structuredClone(snapshot);const own=serial,asset=current.asset;
   if(asset&&!['live2d','png','png-states'].includes(asset.format||'png'))throw Error('此节目暂不支持该形象格式。');
   for(const item of [...Object.values(asset?.states||{}),...Object.values(asset?.resources||{}),asset?.model].filter(Boolean))resources.set(new URL(item.url,location.href).href,item);
   loading=(async()=>{
    if(asset?.format==='live2d'){
     // The SDK may load motions later. Resolve only blobs already read and
     // checked from this same frozen manifest, never arbitrary model paths.
     for(const [url,item]of resources){const blob=await checked('resource',item.resource,item,own);if(own!==serial||disposed)return false;urls.set(url,URL.createObjectURL(blob));}
    }
    if(own!==serial||disposed)return false;
    return scene.sync({character_id:current.character_id,epoch:current.sha256,asset:asset||null,scale:100});
   })();try{return await loading;}finally{if(own===serial)loading=null;}
  }
  return {sync,clear,setSpeaking:v=>scene.setSpeaking(v),setAudio:v=>scene.setAudio(v),get ready(){return scene.ready;},getStats:()=>scene.getStats(),getDiagnostics:options=>scene.getDiagnostics(options),get snapshot(){return current;},dispose(){disposed=true;clear();scene.dispose();}};
 }
 return Object.freeze({create});
})();
