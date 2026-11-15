/* Presentation settings contain no dialogue, credentials or timer state. */
'use strict';
(function(root){
 const fields=['showTopic','showQuestion','showCaption','showTimer'];
 function normalize(value={}){value=value&&typeof value==='object'?value:{};const out={layout:'right',theme:'paper',characterId:'',showTopic:true,showQuestion:true,showCaption:true,showTimer:true};
  if(['right','left','small'].includes(value.layout))out.layout=value.layout;
  if(['paper','forest','slate'].includes(value.theme))out.theme=value.theme;
  if(typeof value.characterId==='string'&&/^[a-f0-9-]{36}$/.test(value.characterId))out.characterId=value.characterId;
  for(const field of fields)if(typeof value[field]==='boolean')out[field]=value[field];return out;
 }
 function presets(value){if(!Array.isArray(value))return [];const result=[],seen=new Set();for(const item of value){if(!item||typeof item.name!=='string')continue;const name=item.name.trim();if(!name||name.length>40||/[\x00-\x1f\x7f]/.test(name)||seen.has(name))continue;seen.add(name);result.push({name,design:normalize(item.design)});if(result.length===12)break;}return result;}
 const api=Object.freeze({normalize,presets,fields});if(typeof module==='object'&&module.exports)module.exports=api;else root.RoomDesign=api;
})(globalThis);
