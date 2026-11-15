// Runs the actual controller with a deferred renderer. No model/Core/browser is run.
import test,{after} from'node:test';
import assert from'node:assert/strict';
import fs from'node:fs';
import path from'node:path';
import vm from'node:vm';
import crypto from'node:crypto';

const sourcePath=process.env.SCENE_CONTROLLER_SOURCE||new URL('../app/static/scene-controller.js',import.meta.url);
const source=fs.readFileSync(sourcePath,'utf8'),observations=[];
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const settle=async()=>{await new Promise(setImmediate);await new Promise(setImmediate);};
const runtime={available:true,core_url:'/live2d-core.js',runtime_url:'/live2d-runtime.js'};
const fixedSpec={character_id:'role-visibility',epoch:0,scale:100,asset:{id:'asset-visibility',format:'live2d',model:{url:'/api/assets/asset-visibility/model.model3.json?character_id=role-visibility'},resources:{}}};

function harness(){
 const engine=deferred(),load=deferred(),states=[],models=[],timers=new Map(),frames=new Map();let serial=0;
 const container={hidden:false,dataset:{},children:[],replaceChildren(...children){this.children=children;},getBoundingClientRect:()=>({width:1000,height:665})};
 const image={hidden:true,dataset:{},style:{},removeAttribute(){}};
 const library={create(options){
  const model={state:'empty',frames:0,hidden:false,disposed:false,scale:null,hiddenCalls:[],loadCalls:0,
   report(){options.onStats({state:this.state,frames:this.frames,hidden:this.hidden,mouth:0});},
   async load(){this.loadCalls++;this.state='loading';this.report();await load.promise;if(this.disposed)return false;this.state='ready';this.frames++;this.report();return true;},
   setHidden(value){this.hidden=Boolean(value);this.hiddenCalls.push(this.hidden);this.report();},
   setScale(value){this.scale=value;},setExpanded(){},setSpeaking(){},setAudio(){},
   getStats(){return {state:this.state,frames:this.frames,hidden:this.hidden};},
   step(){if(!this.disposed&&!this.hidden&&this.state==='ready'){this.frames++;this.report();}},
   dispose(){this.disposed=true;}
  };models.push(model);return model;
 }};
 const context={window:{Live2DCubismCore:{},CompanionLive2DRuntime:{},CompanionLive2D:library},
  location:{href:'http://127.0.0.1:4444/',origin:'http://127.0.0.1:4444'},URL,AbortController,
  performance:{now:()=>0},setTimeout:fn=>{const id=++serial;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
  requestAnimationFrame:fn=>{const id=++serial;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),
  document:{createElement:()=>({remove(){}}),head:{append:script=>queueMicrotask(()=>script.onload())}}
 };
 vm.createContext(context);vm.runInContext(source,context,{filename:String(sourcePath)});
 const scene=context.window.CompanionScene.create({container,image,api:()=>engine.promise,onState:value=>states.push({...value})});
 return {scene,engine,load,models,states,container,snapshot:()=>({ready:scene.ready,lastState:states.at(-1)?.state||null,
  models:models.length,loadCalls:models.reduce((sum,model)=>sum+model.loadCalls,0),renderer:models.at(-1)?.getStats()||null,
  scale:models.at(-1)?.scale??null,hiddenCalls:[...(models.at(-1)?.hiddenCalls||[])],controllerRaf:frames.size})};
}

for(const phase of ['before-model','during-load','after-ready']){
 test('same-key scene resumes after visibility change: '+phase,async t=>{
  const h=harness(),sync=h.scene.sync(fixedSpec),record={phase,fixed:{character:fixedSpec.character_id,asset:fixedSpec.asset.id,epoch:fixedSpec.epoch,scale:fixedSpec.scale,size:h.container.getBoundingClientRect()}};
  try{
   if(phase==='before-model'){
    assert.equal(h.models.length,0);h.scene.setVisible(false);h.engine.resolve(runtime);h.load.resolve(true);await sync;
   }else{
    h.engine.resolve(runtime);await settle();assert.equal(h.models.length,1,'controlled engine must create the renderer');
    if(phase==='during-load'){
     assert.equal(h.models[0].state,'loading');h.scene.setVisible(false);h.load.resolve(true);await sync;
    }else{
     h.load.resolve(true);assert.equal(await sync,true);assert.equal(h.scene.ready,true);h.scene.setVisible(false);
    }
   }
   record.hidden=h.snapshot();const before=h.models.at(-1)?.frames||0;
   for(let step=0;step<3;step++)h.models.at(-1)?.step();
   record.simulatedHiddenFrameDelta=(h.models.at(-1)?.frames||0)-before;
   h.scene.setVisible(true);await settle();record.sameKeySyncResult=await h.scene.sync(fixedSpec);await settle();record.restored=h.snapshot();
   // Capture observations before asserting so a rejected version still leaves evidence.
   observations.push(record);t.diagnostic(JSON.stringify(record));
   assert.equal(record.simulatedHiddenFrameDelta,0,'controller must forward hiding to an existing renderer');
   assert.equal(record.restored.ready,true,'same-key show/sync must recover controller readiness');
   assert.equal(record.restored.lastState,'ready','visible scene must not remain publicly loading');
   assert.equal(record.restored.renderer?.hidden,false,'restored renderer must be unhidden');
   assert.equal(record.restored.scale,1,'restored scene keeps the same requested scale');
   assert.equal(record.restored.models,1,'resume must not leave duplicate renderer instances');
  }finally{h.scene.dispose();}
 });
}

after(()=>{
 if(!process.env.SCENE_VISIBILITY_REPORT)return;
 const destination=process.env.SCENE_VISIBILITY_REPORT;fs.mkdirSync(path.dirname(destination),{recursive:true});
 fs.writeFileSync(destination,JSON.stringify({scope:'Actual scene-controller with deferred engine and renderer; simulated frame forwarding only',
  real_browser:false,real_core:false,model_inference:false,geometry_or_crop_verified:false,
  source_sha256:crypto.createHash('sha256').update(source).digest('hex'),observations},null,2)+'\n');
});
