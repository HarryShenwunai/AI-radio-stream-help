import fs from 'node:fs';import vm from 'node:vm';
export const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
export const tick=()=>new Promise(resolve=>setImmediate(resolve));
export const response=value=>({ok:true,json:async()=>value??{},blob:async()=>new Blob(['audio'])});
export const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
export function state(id=A,appearance=null){return {active_character_id:id,active_character:{id,appearance_id:appearance?.id||null,appearance},characters:[{id:A},{id:B}],messages:[],settings:{voice:true,voice_backend:'kokoro',voice_rate:1,name:id},local_voice_available:true,model_busy:false};}
export function harness(route=async()=>response()){
 const calls=[],audios=[],revoked=[],urls=[],channels=[],events=[],utterances=[],receipts=[],sceneEvents=[];let now=0,hidden=false,uuid=0;
 class Audio{constructor(url){this.src=url;this.currentTime=0;this.duration=4;this.ended=false;this.paused=true;audios.push(this);}async play(){this.paused=false;this.onplay?.();}pause(){events.push('pause');this.paused=true;}}
 class Channel{constructor(){this.sent=[];channels.push(this);}postMessage(value){this.sent.push(value);}close(){}}
 const context={window:{},console,AbortController,TextDecoder,Uint8Array,Response,ReadableStream,Blob,DataView,ArrayBuffer,Audio,BroadcastChannel:Channel,crypto:{randomUUID:()=>`request-${++uuid}`},URL:{createObjectURL:()=>{const url='blob:fixture-'+urls.length;urls.push(url);return url;},revokeObjectURL:url=>revoked.push(url)},localStorage:{getItem:()=>null},performance:{now:()=>now},setTimeout:()=>1,clearTimeout(){},btoa,atob,fetch:async(url,options={})=>{events.push('fetch:'+url);calls.push({url,...options});return route(url,options);}};
 context.speechSynthesis={cancel(){events.push('system-cancel');},getVoices:()=>[{voiceURI:'zh',lang:'zh-CN'}],speak(utterance){utterances.push(utterance);}};context.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};context.window.speechSynthesis=context.speechSynthesis;
 vm.createContext(context);function load(name){vm.runInContext(fs.readFileSync(new URL('../app/static/'+name,import.meta.url),'utf8'),context);}
 load('companion-core.js');const core=context.window.CompanionCore.create();core.adopt(state());
 context.window.CompanionPlayback={fromHeader:value=>JSON.parse(atob(value)),create(meta,{onState}){const proof={meta,terminal:false,position:null,attachAudio(value){this.audio=value;},startSystem(){this.started=now;},progress(){},complete(){this.terminal=true;onState('completed',{});},stop(){if(this.terminal)return;this.position=this.audio?.currentTime??(now-(this.started??now))/1000;this.terminal=true;events.push('receipt-stop');onState('stopped',{});}};receipts.push(proof);return proof;}};
 const scene={setSpeaking:value=>sceneEvents.push(['speaking',value]),setAudio:value=>sceneEvents.push(['audio',value]),systemBoundary:()=>sceneEvents.push(['boundary'])};
 load('speech-controller.js');const speech=context.window.CompanionSpeech.create({core,scene,isHidden:()=>hidden||context.window.companionDesktopHidden===true,onReceipt(){},onError:message=>events.push('error:'+message)});
 return {context,core,speech,calls,audios,revoked,urls,channels,events,utterances,receipts,sceneEvents,load,setHidden:value=>hidden=value,setNow:value=>now=value};
}
export function meta(){return {playback_id:'proof',nonce:'a'.repeat(32),character_id:A,appearance_id:null,message_id:1,duration_seconds:4};}
export function audioResponse(proof=null,body=null){return {ok:true,headers:{get:()=>proof?btoa(JSON.stringify(proof)):null},blob:async()=>body?await body.promise:new Blob(['fixture'])};}
