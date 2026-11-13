// E1 controlled-DOM transport/lifecycle tests; real Core/UI checked separately.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Node {
 constructor(tag,text=''){this.tagName=tag;this.textContent=text;this.children=[];this.dataset={};this.attrs={};this.hidden=false;this.disabled=false;}
 append(...items){this.children.push(...items);}
 setAttribute(k,v){this.attrs[k]=String(v);}
 getAttribute(k){return this.attrs[k];}
 click(){if(!this.disabled)return this.onclick?.();}
}
function setup(){
 let stamp={character_id:'role-a',appearance_id:'asset-a',epoch:1},hidden=false,handlers=new Map(),calls=[],run=async()=>true,reloads=0;
 const state={state:{active_character:{appearance:{id:'asset-a',format:'live2d'}}},transitioning:false,mutating:false};
 const core={scope:()=>({...stamp}),current:s=>s.character_id===stamp.character_id&&s.epoch===stamp.epoch,get:()=>state,on(k,f){if(!handlers.has(k))handlers.set(k,[]);handlers.get(k).push(f);return()=>{};}};
 const scene={ready:true,retry:async()=>{reloads++;return true;},getDiagnostics:()=>({available:true,motions:{接杯:1,移开杯子:1,招手:1,空手:1,'同组动作':2}}),applyControls:value=>{calls.push(value);return run(value);}};
 const el=(tag,cls,text)=>new Node(tag,text),button=(label,{action}={})=>{const node=new Node('button',label);node.onclick=action;return node;};let frame=null,cleanup=null;
 const ui={active:null,panel(title){frame={node:el('section'),body:el('div')};return frame;},open(node,options){this.active=options.id;cleanup=options.onClose;},close(){this.active=null;const old=cleanup;cleanup=null;old?.();}};
 const window={};const context={window,CompanionUI:{el,button},document:{hidden:false},console};vm.runInNewContext(fs.readFileSync(new URL('../app/static/stage-actions.js',import.meta.url),'utf8'),context);
 const trigger=new Node('button');const actions=window.CompanionStageActions.create({core,scene,ui,trigger,isHidden:()=>hidden});
 return {actions,trigger,core,scene,ui,state,calls,reloads:()=>reloads,frame:()=>frame,buttons:()=>frame.body.children[0].children,error:()=>frame.body.children[1],setRun:fn=>run=fn,setScope:next=>{stamp={...stamp,...next};},setHidden:value=>hidden=value,emit:(name,arg)=>handlers.get(name)?.forEach(fn=>fn(arg)),flush:async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();}};
}
test('only an actual ready Live2D motion list exposes main-stage controls',()=>{
 const s=setup();assert.equal(s.trigger.hidden,false);for(const format of ['vrm','png-states','layered-2d']){s.state.state.active_character.appearance.format=format;s.actions.refresh();assert.equal(s.trigger.hidden,true);}s.state.state.active_character.appearance.format='live2d';s.scene.ready=false;s.actions.refresh();assert.equal(s.trigger.hidden,true);s.scene.ready=true;s.scene.getDiagnostics=()=>({available:true,motions:{}});s.actions.refresh();assert.equal(s.trigger.hidden,true);
});
test('actual package names and indices drive active-scene requests without external operations',async()=>{
 const s=setup();s.trigger.click();assert.deepEqual(s.buttons().map(x=>x.textContent),['接杯','移开杯子','招手','空手','同组动作 1','同组动作 2']);assert.equal(s.trigger.getAttribute('aria-expanded'),'true');await s.buttons()[5].click();assert.equal(JSON.stringify(s.calls),JSON.stringify([{motion:{group:'同组动作',index:1}}]));assert.equal(s.trigger.getAttribute('aria-expanded'),'false');assert.equal(s.ui.active,null);assert.equal(s.frame().node.getAttribute('role'),'dialog');
});
test('double activation is suppressed during actual asynchronous preparation',async()=>{
 const s=setup();let release;s.setRun(()=>new Promise(r=>release=r));s.actions.open();s.buttons()[0].click();s.buttons()[1].click();assert.equal(s.calls.length,1);assert.ok(s.buttons().every(b=>b.disabled));release(true);await s.flush();assert.equal(s.ui.active,null);
});
test('failure stays recoverable in place and a second request can succeed',async()=>{
 const s=setup();s.setRun(async()=>{throw Error('资源读取失败');});s.actions.open();await s.buttons()[0].click();assert.equal(s.error().hidden,false);assert.match(s.error().textContent,/读取失败/);assert.ok(s.buttons().every(b=>!b.disabled));s.setRun(async()=>true);await s.buttons()[0].click();assert.equal(s.error().hidden,true);assert.equal(s.calls.length,2);
});
test('false start is an error, never a success notification',async()=>{
 const s=setup();s.setRun(async()=>false);s.actions.open();await s.buttons()[0].click();assert.equal(s.error().hidden,false);assert.match(s.error().textContent,/没有开始/);
});
test('late result after identity switch cannot mutate the new role layer',async()=>{
 const s=setup();let reject;s.setRun(()=>new Promise((_,r)=>reject=r));s.actions.open();s.buttons()[0].click();const error=s.error();s.setScope({character_id:'role-b',epoch:2,appearance_id:'asset-b'});s.emit('invalidate');reject(Error('旧角色失败'));await s.flush();assert.equal(error.hidden,true);assert.equal(s.ui.active,null);assert.equal(s.calls.length,1);
});
test('appearance-only switch is guarded even when the core epoch is unchanged',async()=>{
 const s=setup();let reject;s.setRun(()=>new Promise((_,r)=>reject=r));s.actions.open();s.buttons()[0].click();const error=s.error();s.setScope({appearance_id:'asset-new'});reject(Error('旧形象失败'));await s.flush();assert.equal(error.hidden,true);s.emit('media-stop',{reason:'appearance-change'});assert.equal(s.ui.active,null);assert.equal(s.trigger.hidden,true);
});
test('package readiness loss closes actions instead of offering stale motion IDs',()=>{
 const s=setup();s.actions.open();s.scene.getDiagnostics=()=>({available:false});s.actions.refresh();assert.equal(s.ui.active,null);assert.equal(s.trigger.hidden,true);
});
test('close and hidden invalidate pending UI side effects, and reopening permits retry',async()=>{
 const s=setup();let reject;s.setRun(()=>new Promise((_,r)=>reject=r));s.actions.open();s.buttons()[0].click();const error=s.error();s.ui.close();reject(Error('旧请求'));await s.flush();assert.equal(error.hidden,true);assert.equal(s.trigger.getAttribute('aria-expanded'),'false');s.setRun(async()=>true);s.actions.open();await s.buttons()[1].click();assert.equal(s.calls.length,2);s.setHidden(true);s.actions.refresh();assert.equal(s.trigger.hidden,true);assert.equal(s.ui.active,null);
});
test('restore uses supported reset without inventing parameter IDs',async()=>{
 const s=setup();s.actions.open();const reset=s.frame().body.children[3];assert.equal(reset.id,'stage-reset-pose');await reset.click();assert.equal(s.calls[0].reset,true);assert.equal('parameters'in s.calls[0],false);assert.equal(s.calls[0].idleMotion,true);
});
test('real scene reload is offered only after failure and is scoped before execution',async()=>{
 const s=setup();s.setRun(async()=>false);s.actions.open();const reload=s.frame().body.children[2];assert.equal(reload.hidden,true);await s.buttons()[0].click();assert.equal(reload.hidden,false);reload.click();await s.flush();assert.equal(s.reloads(),1);assert.equal(s.ui.active,null);
 const stale=setup();stale.setRun(async()=>false);stale.actions.open();await stale.buttons()[0].click();stale.setScope({appearance_id:'asset-new'});stale.frame().body.children[2].click();await stale.flush();assert.equal(stale.reloads(),0);
});
test('expression-only models expose actual expression names without inventing motions',async()=>{
 const s=setup();s.scene.getDiagnostics=()=>({available:true,motions:{},expressions:['Smile','Sad','Smile']});s.actions.refresh();assert.equal(s.trigger.hidden,false);s.actions.open();assert.deepEqual(s.buttons().map(n=>n.textContent),['Smile','Sad']);await s.buttons()[0].click();assert.equal(JSON.stringify(s.calls),JSON.stringify([{expression:'Smile'}]));assert.equal(s.ui.active,null);
});
test('reset clears expression and the same actual expression remains selectable',async()=>{
 const s=setup();s.scene.getDiagnostics=()=>({available:true,motions:{},expressions:['Smile']});s.actions.open();await s.buttons()[0].click();s.actions.open();await s.frame().body.children[3].click();s.actions.open();await s.buttons()[0].click();assert.equal(s.calls[0].expression,'Smile');assert.equal(s.calls[1].reset,true);assert.equal(s.calls[1].expression,null);assert.equal(s.calls[2].expression,'Smile');
});
test('late expression selection cannot close or report into a newer selection',async()=>{
 const s=setup();s.scene.getDiagnostics=()=>({available:true,motions:{},expressions:['Smile','Sad']});let late;s.setRun(value=>value.expression==='Smile'?new Promise(r=>late=r):Promise.resolve(true));s.actions.open();s.buttons()[0].click();s.ui.close();s.actions.open();const latestError=s.error();await s.buttons()[1].click();late(false);await s.flush();assert.equal(s.calls.length,2);assert.equal(latestError.hidden,true);assert.equal(s.ui.active,null);
});
