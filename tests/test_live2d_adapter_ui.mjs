// Original adapter mapping tests only. No proprietary Core/framework is loaded.
import assert from 'node:assert/strict';
import test from 'node:test';
import {rewriteModel,create,checkMocVersion,requireModelAPI,validateControls,refreshActiveTextures,clearSelectedExpression,restoreDefaultPose} from '../frontend/live2d-renderer.mjs';
globalThis.window={location:{href:'http://127.0.0.1:4444/',origin:'http://127.0.0.1:4444'}};
const id='asset-fixture',url=name=>`/api/assets/${id}/${name}?character_id=role-A`;
function asset(){return {id,model:{url:url('model.model3.json')},resources:Object.fromEntries(['r0001.moc3','r0002.png','r0003.motion3.json','r0004.exp3.json','r0005.physics3.json'].map(name=>[name,{url:url(name)}]))};}
function model(){return {Version:3,FileReferences:{Moc:'r0001.moc3',Textures:['r0002.png'],Physics:'r0005.physics3.json',Expressions:[{Name:'gentle',File:'r0004.exp3.json'}],Motions:{Idle:[{File:'r0003.motion3.json'}]}}};}
test('every model3 resource retains its authenticated character scope',()=>{
 const original=model(),rewritten=rewriteModel(original,asset());for(const item of [rewritten.FileReferences.Moc,...rewritten.FileReferences.Textures,rewritten.FileReferences.Physics,rewritten.FileReferences.Expressions[0].File,rewritten.FileReferences.Motions.Idle[0].File])assert.match(item,/^http:\/\/127\.0\.0\.1:4444\/api\/assets\/asset-fixture\/.*\?character_id=role-A$/);
 assert.equal(original.FileReferences.Moc,'r0001.moc3');assert.match(rewritten.url,/character_id=role-A$/);
});
test('unmapped paths and external resources are rejected before invoking any runtime',()=>{
 for(const path of ['../other.moc3','https://example.com/a.moc3','data:application/octet-stream,AA','evil.js']){const value=model();value.FileReferences.Moc=path;assert.throws(()=>rewriteModel(value,asset()),/安全检查/);}
 const item=asset();item.resources['r0001.moc3'].url='https://example.com/model.moc3';assert.throws(()=>rewriteModel(model(),item),/本机/);
});
test('model-authored audio never acquires another playback owner',()=>{
 const value=model();value.FileReferences.Motions.Idle[0].Sound='r0006.wav';assert.throws(()=>rewriteModel(value,asset()),/自带音频/);
});
test('an absent owner-installed Core/framework fails closed before WebGL creation',()=>{
 assert.throws(()=>create({container:{}}),/尚未安装/);
});
test('same-origin resources cannot cross asset or role boundaries',()=>{
 for(const replacement of ['/api/assets/other/r0001.moc3?character_id=role-A','/api/assets/asset-fixture/r0001.moc3?character_id=role-B']){const item=asset();item.resources['r0001.moc3'].url=replacement;assert.throws(()=>rewriteModel(model(),item),/当前运行包/);}
});

test('observed Core maximum rejects newer MOC before GPU allocation',()=>{
 const core={Version:{csmGetLatestMocVersion:()=>5}};assert.throws(()=>checkMocVersion({moc3_version:{code:6}},core),/当前最高支持 MOC 5/);for(const code of [1,2,3,4,5])assert.doesNotThrow(()=>checkMocVersion({moc3_version:{code}},core));
});

// A legacy setter-only surface silently accepted the absent enable method.
// The current contract must reject that shape before activating any model.
test('a setter without actual start/stop lipsync APIs is incompatible',()=>{
 const model={setLipSyncValue(){},setEyeBlinkEnabled(){},setBreathEnabled(){},update(){}};
 assert.throws(()=>requireModelAPI(model),/startLipSync/);
});
test('bounded controls reject NaN, infinity, unknown authority and invalid motion indexes',()=>{
 for(const value of [{headX:NaN},{gazeY:Infinity},{bodyZ:1.1},{owner:'system'},{motion:{group:'Idle',index:-1}},{physics:1}])assert.throws(()=>validateControls(value));
 assert.doesNotThrow(()=>validateControls({headX:.5,gazeY:-1,mouthForm:0,physics:false,autoBlink:true,motion:{group:'Idle',index:0},expression:null}));
});

test('custom controls accept only bounded data entries without authority or duplicate IDs',()=>{
 assert.doesNotThrow(()=>validateControls({parameters:[{id:'CupVisible',value:0},{id:'CupX',value:12}]}));
 for(const parameters of [[{id:'CupX',value:NaN}],[{id:'CupX',value:0,owner:'system'}],[{id:'CupX',value:0},{id:'CupX',value:1}],Array.from({length:33},(_,i)=>({id:'p'+i,value:0}))])assert.throws(()=>validateControls({parameters}));
});

test('active textures use current Pixi getGlSource rather than the obsolete touched flag',()=>{
 const active={uid:'active'},unused={uid:'unused'},seen=[],handle={};const renderer={texture:{getGlSource(source){seen.push(source);source._gcLastUsed=123;return {texture:handle};}}},model={textures:[{source:active}],cachedGlTextures:[handle]};refreshActiveTextures(renderer,model);assert.deepEqual(seen,[active]);assert.equal(active._gcLastUsed,123);assert.equal(unused._gcLastUsed,undefined);assert.equal(active.touched,undefined);
});
test('a recreated managed texture invalidates stale wrapper handles without disabling GC',()=>{
 const fresh={},old={},model={textures:[{source:{}}],cachedGlTextures:[old]},renderer={gc:{enabled:true},texture:{getGlSource:()=>({texture:fresh})}};refreshActiveTextures(renderer,model);assert.equal(model.forceTextureUpdate,true);assert.equal(renderer.gc.enabled,true);assert.throws(()=>refreshActiveTextures({texture:{}},model),/生命周期/);
});

test('reset restores SDK-motion-saved values that never entered any manual control map',()=>{
 const values=[0,0,240,-8],defaults=[1,1,0,0],saved=[],calls=[],defaultExpression={id:'default'},oldExpression={id:'sad'};
 const manager={defaultExpression,currentExpression:oldExpression,reserveExpressionIndex:2,stopAllExpressions(){calls.push('stop-expression');},resetExpression(){calls.push('default-expression');}};
 const model={internalModel:{motionManager:{expressionManager:manager,stopAllMotions(){calls.push('stop-motion');}},coreModel:{setParameterValueByIndex(i,value){assert.ok(i>=0&&i<values.length);values[i]=value;},saveParameters(){saved.splice(0,saved.length,...values);}},focusController:{focus(...args){calls.push(args);}}}};
 restoreDefaultPose(model,defaults.map((value,index)=>({id:['CupHold','CupVisible','CupX','Finger'][index],index,default:value})));
 assert.deepEqual(values,defaults);assert.deepEqual(saved,defaults);assert.equal(manager.currentExpression,defaultExpression);assert.equal(manager.reserveExpressionIndex,-1);assert.deepEqual(calls,['stop-motion','stop-expression','default-expression',[0,0,true]]);
});
test('clearing selected expression invalidates a reserved load and allows the same expression again',()=>{
 const initial={},selected={};let stopped=0,resets=0;
 const manager={defaultExpression:initial,currentExpression:selected,reserveExpressionIndex:1,stopAllExpressions(){stopped++;},resetExpression(){resets++;}};
 clearSelectedExpression({internalModel:{motionManager:{expressionManager:manager}}});
 assert.equal(manager.currentExpression,initial);assert.equal(manager.reserveExpressionIndex,-1);assert.notEqual(manager.currentExpression,selected);assert.equal(stopped,1);assert.equal(resets,1);
 assert.throws(()=>clearSelectedExpression({internalModel:{motionManager:{expressionManager:{resetExpression(){}}}}}),/不兼容/);
});

// E1 scheduling probes: controlled SDK promises, no Core/GL claims. The actual
// resource-delay Chromium cases independently exercise the pinned real SDK.
function controlledAdapter(){
 const saved={fetch:globalThis.fetch,raf:globalThis.requestAnimationFrame,caf:globalThis.cancelAnimationFrame,observer:globalThis.ResizeObserver,runtime:window.CompanionLive2DRuntime,core:window.Live2DCubismCore};
 let resolveExpression;const expression=new Promise(resolve=>resolveExpression=resolve);
 const makeModel=()=>{
  const values=new Float32Array([0]),raw={parameters:{ids:['ParamMouthOpenY'],minimumValues:new Float32Array([0]),maximumValues:new Float32Array([1]),defaultValues:new Float32Array([0])},drawables:{count:0}};
  const expressionManager={reserveExpressionIndex:-1,defaultExpression:{},currentExpression:{},stopAllExpressions(){},resetExpression(){}};
  const item={stops:0,motions:0,textures:[{source:{}}],cachedGlTextures:[],anchor:{set(){}},scale:{set(){}},position:{set(){}},destroy(){this.destroyed=true;},update(){},startLipSync(){},stopLipSync(){},setLipSyncValue(){},isLipSyncEnabled(){return false;},getLipSyncValue(){return 0;},setEyeBlinkEnabled(){},setBreathEnabled(){},setBreathIntensity(){},async expression(){return expression;},async motion(){item.motions++;return true;}};
  item.internalModel={width:100,height:100,physics:{},on(){},off(){},focusController:{focus(){}},coreModel:{getModel:()=>raw,setParameterValueByIndex(i,value){values[i]=value;},getParameterValueByIndex:i=>values[i],saveParameters(){}},motionManager:{expressionManager,state:{shouldRequestIdleMotion:()=>true},stopAllMotions(){item.stops++;}}};
  return item;
 };
 const a=makeModel(),b=makeModel(),queue=[a,b];
 const runner={add(){},remove(){}};
 class Application{async init(){this.canvas={setAttribute(){},addEventListener(){},removeEventListener(){}};this.stage={children:[],addChild(value){this.children.push(value);},removeChild(value){this.children=this.children.filter(v=>v!==value);}};this.renderer={resize(){},gl:{clearColor(){}},runners:{prerender:runner},texture:{getGlSource:()=>({texture:{}})},render(){}};this.ticker={stop(){}};}destroy(){}}
 window.CompanionLive2DRuntime={PIXI:{Application,Assets:{setPreferences(){}}},Live2DModel:{from:async()=>queue.shift()}};window.Live2DCubismCore={Version:{csmGetLatestMocVersion:()=>5,csmGetVersion:()=>83951616}};
 globalThis.fetch=async()=>({ok:true,json:async()=>model()});globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};globalThis.ResizeObserver=class{observe(){}disconnect(){}};
 const container={clientWidth:100,clientHeight:100,getBoundingClientRect:()=>({width:100,height:100}),append(){},addEventListener(){},removeEventListener(){}};
 const adapter=create({container}),makeAsset=value=>{const data=asset();data.id=value;data.model.url=`/api/assets/${value}/model.model3.json?character_id=role-A`;for(const[name,item]of Object.entries(data.resources))item.url=`/api/assets/${value}/${name}?character_id=role-A`;return data;};
 return{adapter,a,b,makeAsset,resolveExpression,cleanup(){adapter.dispose();Object.assign(globalThis,{fetch:saved.fetch,requestAnimationFrame:saved.raf,cancelAnimationFrame:saved.caf,ResizeObserver:saved.observer});window.CompanionLive2DRuntime=saved.runtime;window.Live2DCubismCore=saved.core;}};
}
test('an old expression result cannot overwrite or stop a newly loaded model',async t=>{
 const h=controlledAdapter();t.after(h.cleanup);assert.equal(await h.adapter.load(h.makeAsset('A')),true);
 const pending=h.adapter.applyControls({expression:'gentle',motion:{group:'Idle',index:0}});
 assert.equal(await h.adapter.load(h.makeAsset('B')),true);h.resolveExpression(true);
 assert.equal(await pending,false);assert.equal(h.b.stops,0);assert.equal(h.a.motions,0);assert.equal(h.adapter.getDiagnostics().currentExpression,null);
});
test('reset supersedes an in-flight expression even if its SDK promise later succeeds',async t=>{
 const h=controlledAdapter();t.after(h.cleanup);await h.adapter.load(h.makeAsset('A'));
 const pending=h.adapter.applyControls({expression:'gentle',motion:{group:'Idle',index:0}});
 assert.equal(await h.adapter.applyControls({reset:true}),true);const stops=h.a.stops;h.resolveExpression(true);
 assert.equal(await pending,false);assert.equal(h.a.stops,stops);assert.equal(h.a.motions,0);assert.equal(h.adapter.getDiagnostics().currentExpression,null);
});
