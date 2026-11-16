// Actual program-scene module under a controlled DOM/renderer, not Core or visual acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {createHash,webcrypto} from 'node:crypto';
const source=fs.readFileSync(process.env.PROGRAM_SCENE_SOURCE||new URL('../app/static/program-scene.js',import.meta.url),'utf8');
function harness(){
 const surface={dataset:{}},engine={ready:true,sync:async()=>true,clear(){},setExpanded(){},setSpeaking(){},setAudio(){},getStats(){return{};},getDiagnostics(){return{};},dispose(){}};
 const win={},context={window:win,document:{querySelector:s=>s==='#program'?surface:{nonce:'fixture'}},CompanionScene:{create:()=>engine},crypto:webcrypto,structuredClone,URL,Blob,Response,location:{href:'http://127.0.0.1:4444/live-stage.html',origin:'http://127.0.0.1:4444'}};
 vm.createContext(context);vm.runInContext(source,context);
 return {surface,engine,program:win.ProgramScene.create({call:async()=>{throw Error('No resource belongs to this presentation fixture');},container:{},image:{}})};
}
function snapshot(layout='right',theme='carbon'){
 const value={version:1,character_id:'current',appearance_id:null,layout_revision:'program-v2',layout,theme,asset:null};
 return {...value,sha256:createHash('sha256').update(JSON.stringify(value)).digest('hex')};
}
test('approved position and palette reach the actual program surface',async()=>{
 const h=harness();
 for(const [layout,theme]of [['right','carbon'],['left','midnight'],['small','daylight']]){
  await h.program.sync(snapshot(layout,theme));assert.equal(h.surface.dataset.layout,layout);assert.equal(h.surface.dataset.theme,theme);
 }
});
test('unsupported presentation does not become arbitrary CSS or conceal the answer',async()=>{
 for(const change of [{layout:'scaleX(-1)'},{layout:false},{layout:null},{theme:'url(private)'},{theme:[]},{showCaption:false}]){
  const h=harness();await assert.rejects(h.program.sync({...snapshot(),...change}));
 }
});
test('late previous scene cannot restore its earlier presentation',async()=>{
 const h=harness();let finish;h.engine.sync=()=>new Promise(resolve=>finish=resolve);
 const old=h.program.sync(snapshot('right','carbon'));await Promise.resolve();
 h.engine.sync=async()=>true;await h.program.sync(snapshot('left','midnight'));finish(true);await old;
 assert.equal(h.surface.dataset.layout,'left');assert.equal(h.surface.dataset.theme,'midnight');
});

test('all supported program palette tokens stay aligned with the existing room palette',()=>{
 const require=createRequire(import.meta.url),{palettes}=require('../app/static/room-design.js'),css=fs.readFileSync(new URL('../app/static/live-stage.css',import.meta.url),'utf8');
 for(const [theme,palette]of Object.entries(palettes)){
  const selector=theme==='carbon'?'#program{':'#program[data-theme='+theme+']{',start=css.indexOf(selector);assert.ok(start>=0,theme);
  const declarations=css.slice(start+selector.length,css.indexOf('}',start));
  for(const [name,key]of [['surface','background'],['foreground','foreground'],['accent','accent']]){
   assert.ok(declarations.includes('--program-'+name+':'+palette[key]),theme+' '+name);
  }
 }
});

test('empty scene stays empty and legacy snapshots retain the explicit supported defaults',async()=>{
 const h=harness();h.engine.ready=false;assert.equal(await h.program.sync(null),false);assert.deepEqual(h.surface.dataset,{});
 const legacy=snapshot();delete legacy.layout;delete legacy.theme;await h.program.sync(legacy);assert.equal(h.surface.dataset.layout,'right');assert.equal(h.surface.dataset.theme,'carbon');
});
