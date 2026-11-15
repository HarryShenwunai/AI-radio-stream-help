/* Presentation settings contain no dialogue, credentials or timer state. */
'use strict';
(function(root){
 const palettes=Object.freeze({
  carbon:Object.freeze({name:'炭黑 · 杏橙',background:'#17191f',ambient:'#2b2b30',foreground:'#f6f4f1',muted:'#c1c3cc',accent:'#ffaf7e',line:'#6b707c'}),
  midnight:Object.freeze({name:'午夜蓝 · 冰蓝',background:'#101e30',ambient:'#253b51',foreground:'#f4f8fc',muted:'#bdcedf',accent:'#89ccf4',line:'#6d829a'}),
  daylight:Object.freeze({name:'冷白 · 墨蓝',background:'#f2f4f7',ambient:'#e7ecf3',foreground:'#202936',muted:'#505d6f',accent:'#274e9c',line:'#7e8b9e'})
 });
 const legacy=Object.freeze({paper:'carbon',forest:'midnight',slate:'daylight'});
 const theme=value=>Object.hasOwn(palettes,value)?value:Object.hasOwn(legacy,value)?legacy[value]:'carbon';
 const palette=value=>palettes[theme(value)];
 const fields=['showTopic','showQuestion','showCaption','showTimer'];
 function normalize(value={}){value=value&&typeof value==='object'?value:{};const out={layout:'right',theme:'carbon',characterId:'',showTopic:true,showQuestion:true,showCaption:true,showTimer:true};
  if(['right','left','small'].includes(value.layout))out.layout=value.layout;
  out.theme=theme(value.theme);
  if(typeof value.characterId==='string'&&/^[a-f0-9-]{36}$/.test(value.characterId))out.characterId=value.characterId;
  for(const field of fields)if(typeof value[field]==='boolean')out[field]=value[field];return out;
 }
 function presets(value){if(!Array.isArray(value))return [];const result=[],seen=new Set();for(const item of value){if(!item||typeof item.name!=='string')continue;const name=item.name.trim();if(!name||name.length>40||/[\x00-\x1f\x7f]/.test(name)||seen.has(name))continue;seen.add(name);result.push({name,design:normalize(item.design)});if(result.length===12)break;}return result;}
 const api=Object.freeze({normalize,presets,fields,palettes,palette});if(typeof module==='object'&&module.exports)module.exports=api;else root.RoomDesign=api;
})(globalThis);
