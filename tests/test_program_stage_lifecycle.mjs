// Actual stage source under controlled DOM/media. No Core, audible or visual claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto,createHash} from 'node:crypto';
const source=fs.readFileSync(process.env.PROGRAM_STAGE_SOURCE||new URL('../app/static/live-stage.js',import.meta.url),'utf8');
const tick=async()=>{for(let i=0;i<15;i++)await new Promise(resolve=>setImmediate(resolve));};
const until=async predicate=>{const deadline=Date.now()+2000;while(!predicate()){if(Date.now()>deadline)throw Error('Observable media state did not settle');await new Promise(resolve=>setTimeout(resolve,5));}};
function harness(){
 let fit=true,sceneState,audioResolve,holdAudio=false,ready=true,speaking=false,job=null;
 const requests=[],audios=[],intervals=[],events={},bytes=new Uint8Array([1,2,3]);
 const nodes=new Map();
 for(const id of ['caption','status','enable','character-status','character-canvas','character-image','character-space'])nodes.set('#'+id,{textContent:'',style:{},hidden:false,clientWidth:400,clientHeight:100,get scrollWidth(){return fit?400:401;},scrollHeight:100,getBoundingClientRect:()=>id==='character-space'?{left:700,right:1200,top:20,bottom:700}:{left:30,right:430,top:500,bottom:600},addEventListener(type,fn){this[type]=fn;}});
 const scene={get ready(){return ready;},snapshot:null,async sync(value){this.snapshot=value;return true;},clear(){this.snapshot=null;},setSpeaking:v=>{speaking=v;},setAudio:async()=>true,dispose(){},getStats(){return{};}};
 class Media{constructor(){this.paused=true;this.ended=false;this.events={};audios.push(this);}addEventListener(name,fn){this.events[name]=fn;}async play(){this.plays=(this.plays||0)+1;this.paused=false;}pause(){this.paused=true;this.events.pause?.();}removeAttribute(){}}
 const snapshot={sha256:'scene'},item={id:'job',state:'claimed',text:'approved',scene_snapshot:snapshot,audio_sha256:createHash('sha256').update(bytes).digest('hex')};
 const c={console,document:{querySelector:s=>nodes.get(s)},location:{hash:'#fixture',pathname:'/live-stage.html'},history:{replaceState(){}},crypto:webcrypto,performance,innerHeight:720,innerWidth:1280,Audio:Media,URL:{createObjectURL:()=> 'blob:fixture',revokeObjectURL(){}},AbortSignal,ProgramScene:{create(options){sceneState=options.onState;return scene;}},setInterval:fn=>intervals.push(fn),requestAnimationFrame:fn=>{fn();return 0;},BroadcastChannel:undefined,window:null,fetch:async(path,options)=>{const data=JSON.parse(options.body);requests.push(data);if(data.action==='audio'){if(holdAudio)await new Promise(resolve=>audioResolve=resolve);return {ok:true,blob:async()=>new Blob([bytes])};}return {ok:true,json:async()=>data.action==='poll'?{item:job,scene_snapshot:snapshot}:data.action==='scene'?{scene_snapshot:snapshot}:{}};}};
 c.window={addEventListener:(name,fn)=>events[name]=fn};vm.createContext(c);vm.runInContext(source,c);
 return {nodes,requests,audios,scene,async start(hold=false){holdAudio=hold;await tick();job=item;nodes.get('#enable').click();await until(()=>requests.some(v=>v.action==='audio'||v.state==='failed'));if(!hold)await until(()=>requests.some(v=>v.state==='playing'||v.state==='failed'));},resize(){fit=false;events.resize();},release(){audioResolve?.();},async error(){ready=false;sceneState({ready:false,error:'ownership'});await tick();},get speaking(){return speaking;},get context(){return c;}};
}
test('resize while audio is preparing never starts or acknowledges playback',async()=>{
 const h=harness();await h.start(true);h.resize();h.release();await tick();
 assert.equal(h.audios.reduce((n,a)=>n+(a.plays||0),0),0);assert.equal(h.requests.filter(v=>v.state==='playing').length,0);assert.equal(h.nodes.get('#caption').textContent,'');assert.equal(h.speaking,false);assert.match(h.nodes.get('#status').textContent,/无法完整显示/);assert.ok(h.requests.some(v=>v.state==='failed'));
});
test('actual scene error stops active media and cannot leave a speaking caption',async()=>{
 const h=harness();await h.start();assert.equal(h.audios[0].paused,false);assert.equal(h.speaking,true);await h.error();
 assert.equal(h.audios[0].paused,true);assert.equal(h.speaking,false);assert.equal(h.nodes.get('#caption').textContent,'');assert.ok(h.requests.some(v=>v.state==='failed'));assert.match(h.nodes.get('#status').textContent,/人物已失效/);
});

test('scene error while approved audio is preparing invalidates its late response',async()=>{
 const h=harness();await h.start(true);await h.error();h.release();await tick();
 assert.equal(h.audios.reduce((n,a)=>n+(a.plays||0),0),0);assert.equal(h.requests.filter(v=>v.state==='playing').length,0);assert.equal(h.nodes.get('#caption').textContent,'');assert.equal(h.speaking,false);assert.match(h.nodes.get('#status').textContent,/人物已失效/);assert.ok(h.requests.some(v=>v.state==='failed'));
});
