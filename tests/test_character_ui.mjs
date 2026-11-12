// Executes the shipped UI code against controlled browser primitives.
// These checks cover cross-character races and preview safety, not visual quality.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=fs.readFileSync(new URL('../app/static/app.js',import.meta.url),'utf8');
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const PACK='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=value=>({ok:true,json:async()=>value??{},blob:async()=>({wav:true})});
function pack(id=PACK){return {id,states:{idle:{resource:'idle.png',width:96,height:160,url:`/api/assets/${id}/idle.png?character_id=${A}`},talk:{resource:'talk.png',width:96,height:160,url:`/api/assets/${id}/talk.png?character_id=${A}`}},thumbnail:{resource:'thumbnail.png',url:`/api/assets/${id}/thumbnail.png?character_id=${A}`}};}
function state(id=A,appearance=null){return {active_character_id:id,active_character:{id,name:id===A?'角色甲':'角色乙',appearance_id:appearance?.id||null,appearance},characters:[{id:A,name:'角色甲',archived:false},{id:B,name:'角色乙',archived:false}],settings:{name:id===A?'角色甲':'角色乙',voice:true,engine:'api',voice_rate:1},local_voice_available:true,messages:[],memories:[],tasks:[],model_busy:false};}
function file(width=96,height=160,name='自选.PNG'){
 const bytes=new Uint8Array(40);bytes.set([137,80,78,71,13,10,26,10],0);bytes.set([73,72,68,82],12);
 const view=new DataView(bytes.buffer);view.setUint32(16,width);view.setUint32(20,height);
 return {name,size:bytes.length,arrayBuffer:async()=>bytes.buffer,slice:(start,end)=>({arrayBuffer:async()=>bytes.slice(start,end).buffer})};
}
function harness(route=async()=>response({})){ 
 const nodes=new Map(),calls=[],audios=[],urls=[],revoked=[],bodyClasses=new Set(),channels=[];
 const node=()=>({textContent:'',hidden:false,disabled:false,value:'',dataset:{},style:{},files:[],children:[],classList:{add(){},remove(){},toggle(){}},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},get firstChild(){return this.children[0];},setAttribute(){},removeAttribute(){},addEventListener(){},focus(){},querySelector(){return null;}});
 const get=s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);};
 class Audio{constructor(url){this.src=url;this.paused=true;audios.push(this);}async play(){this.paused=false;this.onplay?.();}pause(){this.paused=true;}}
 class BroadcastChannel{constructor(name){this.name=name;this.sent=[];channels.push(this);}postMessage(data){this.sent.push(data);}close(){}}
 let initial=true;
 const context={console,AbortController,TextDecoder,Uint8Array,Response,ReadableStream,Audio,BroadcastChannel,btoa,
  document:{querySelector:get,querySelectorAll:()=>[],createElement:node,hidden:false,addEventListener(){},body:{classList:{add:x=>bodyClasses.add(x),remove:x=>bodyClasses.delete(x),toggle:(x,on)=>on?bodyClasses.add(x):bodyClasses.delete(x)}}},
  window:{addEventListener(){},SpeechRecognition:class{start(){}stop(){}abort(){}}},localStorage:{getItem:()=> '__local__',setItem(){}},
  URL:{createObjectURL:()=>{const url=`blob:fixture-${urls.length}`;urls.push(url);return url;},revokeObjectURL:url=>revoked.push(url)},
  crypto:{randomUUID:()=> 'fixture-request'},setTimeout:()=>0,clearTimeout(){},setInterval(){},confirm:()=>true,
  fetch:(url,options={})=>{calls.push({url,...options});if(initial&&url==='/api/state'){initial=false;return new Promise(()=>{});}return route(url,options);},
 };
 vm.createContext(context);vm.runInContext(source,context);
 vm.runInContext(`app=${JSON.stringify(state())};render=()=>{};renderMessages=()=>{};renderCharacters=()=>{};renderCharacterPicker=()=>{};`,context);
 return {context,get,calls,audios,urls,revoked,channels,bodyClasses,read:code=>vm.runInContext(code,context),setState:value=>vm.runInContext(`app=${JSON.stringify(value)}`,context)};
}

test('ordinary writes carry expected identity; character management keeps its explicit target',async()=>{
 const h=harness();await h.context.api('memories',{text:'合成事实'});await h.context.api('characters/select',{id:B});
 const writes=h.calls.filter(call=>call.body).map(call=>JSON.parse(call.body));
 assert.deepEqual(writes,[{text:'合成事实',expected_character_id:A},{id:B}]);
});

test('real playback events select talk artwork and cancellation restores idle',async()=>{
 const h=harness();h.setState(state(A,pack()));h.context.renderCharacterImage();
 assert.ok(h.get('#portrait-avatar').src.includes('/idle.png'));
 await h.context.speak('合成回复',{message_id:7});
 assert.equal(JSON.parse(h.calls.find(call=>call.url==='/api/speech').body).expected_character_id,A);
 assert.ok(h.get('#portrait-avatar').src.includes('/talk.png'));
 h.context.stopVoice();assert.ok(h.get('#portrait-avatar').src.includes('/idle.png'));assert.equal(h.audios[0].paused,true);
});

test('switching after manual invalidation preserves drafts separately and clears old media',async()=>{
 const h=harness(async url=>url==='/api/state'?response(state(B)):response({assets:[]}));
 h.get('#message-input').value='角色甲的未发草稿';h.read(`characterDrafts.set('${B}','角色乙的草稿')`);
 await h.context.speak('旧角色声音',{message_id:1});await h.context.characterAction('select',{id:B});
 assert.equal(h.read('currentCharacterId()'),B);assert.equal(h.get('#message-input').value,'角色乙的草稿');
 assert.equal(h.read(`characterDrafts.get('${A}')`),'角色甲的未发草稿');assert.equal(h.audios[0].paused,true);
 assert.equal(h.read('activeRequest'),'');assert.equal(h.read('lastSeen'),0);
});

test('a stale state request cannot restore an identity after a switch',async()=>{
 const old=deferred(),h=harness(async url=>url==='/api/state'?old.promise:response({}));
 const request=h.context.refresh(true);h.context.invalidateCharacterContext();h.context.adoptState(state(B));
 old.resolve(response(state(A)));await request;assert.equal(h.read('currentCharacterId()'),B);
});

test('late old stream does not inject text or draft into a new character',async()=>{
 const pending=deferred(),h=harness(async url=>url==='/api/chat/stream'?pending.promise:response(state(B)));
 const chat=h.context.runChat('旧角色问题');const request=h.calls.find(call=>call.url==='/api/chat/stream');
 assert.equal(JSON.parse(request.body).expected_character_id,A);
 h.context.invalidateCharacterContext();h.context.adoptState(state(B));h.get('#message-input').value='新角色草稿';
 pending.resolve(new Response('data: '+JSON.stringify({type:'done',message:{id:1,role:'assistant',text:'迟到旧回复'}})+'\n\n'));
 await chat;
 assert.equal(request.signal.aborted,true);assert.equal(h.read('currentCharacterId()'),B);assert.equal(h.read('app.messages.length'),0);assert.equal(h.get('#message-input').value,'新角色草稿');
});

test('huge PNG dimensions are rejected before creating any local preview URL',async()=>{
 const h=harness();h.get('#asset-idle').files=[file(100000,100000)];await h.context.showLocalAppearancePreview();
 assert.equal(h.urls.length,0);assert.equal(h.get('#appearance-preview').hidden,true);assert.match(h.get('#character-error').textContent,/尺寸过大/);
});

test('local preview is immediate and inactive until server validation and explicit activation',async()=>{
 let activated=false;
 const h=harness(async(url)=>{
  if(url==='/api/characters/assets/import')return response({asset:pack()});
  if(url==='/api/characters/assets/activate'){activated=true;return response({ok:true});}
  if(url==='/api/state')return response(state(A,activated?pack():null));
  return response({assets:[pack()]});
 });
 h.get('#asset-idle').files=[file()];await h.context.showLocalAppearancePreview();assert.equal(h.urls.length,1);assert.equal(h.read('pendingAsset'),null);assert.equal(h.get('#activate-appearance').disabled,true);
 await h.context.importAppearance();assert.equal(activated,false);assert.equal(h.read('activeAppearance()'),null);assert.equal(h.read('pendingAsset.id'),PACK);assert.match(h.get('#appearance-status').textContent,/尚未启用/);
 assert.equal(h.calls.filter(call=>call.url.includes('/assets/activate')).length,0);
 await h.context.activateAppearance(PACK);assert.equal(activated,true);assert.equal(h.read('activeAppearance().id'),PACK);assert.equal(h.read('pendingAsset'),null);
});

test('inconsistent state image dimensions never create a preview',async()=>{
 const h=harness();h.get('#asset-idle').files=[file(96,160)];h.get('#asset-talk').files=[file(96,161)];
 await h.context.showLocalAppearancePreview();assert.equal(h.urls.length,0);assert.match(h.get('#character-error').textContent,/尺寸须一致/);
});

test('server rejection leaves the active appearance unchanged',async()=>{
 const h=harness(async()=>({ok:false,json:async()=>({error:'测试夹具：CRC错误'})}));h.setState(state(A,pack()));h.get('#asset-idle').files=[file()];
 await h.context.importAppearance();assert.equal(h.read('activeAppearance().id'),PACK);assert.equal(h.read('pendingAsset'),null);assert.match(h.get('#character-error').textContent,/CRC/);
 assert.equal(h.calls.some(call=>call.url.includes('/assets/activate')),false);
});

test('late validated preview is removed from its original role and never activates under another',async()=>{
 const pending=deferred(),h=harness(async url=>url==='/api/characters/assets/import'?pending.promise:response({assets:[]}));
 h.get('#asset-idle').files=[file()];const imported=h.context.importAppearance();await tick();
 h.context.invalidateCharacterContext();h.context.adoptState(state(B));pending.resolve(response({asset:pack()}));await imported;await tick();
 assert.equal(h.read('pendingAsset'),null);assert.equal(h.read('currentCharacterId()'),B);
 const cleanup=h.calls.find(call=>call.url==='/api/characters/assets/delete');assert.equal(JSON.parse(cleanup.body).character_id,A);assert.equal(h.calls.some(call=>call.url.includes('/assets/activate')),false);
});

test('an appearance revision change stops playback without discarding the identity draft',async()=>{
 const h=harness();h.setState(state(A,pack()));h.get('#message-input').value='同角色草稿';await h.context.speak('正在说话',{message_id:3});
 h.context.adoptState(state(A,null));assert.equal(h.audios[0].paused,true);assert.equal(h.get('#message-input').value,'同角色草稿');assert.equal(h.read('currentCharacterId()'),A);
});

test('another window claiming playback pauses local audio and ignores its own claim',async()=>{
 const h=harness();await h.context.speak('当前声音',{message_id:1});const channel=h.channels[0];
 channel.onmessage({data:{type:'claim',owner:h.read('mediaOwner')}});assert.equal(h.audios[0].paused,false);
 channel.onmessage({data:{type:'claim',owner:'other-window'}});assert.equal(h.audios[0].paused,true);
});

test('older media claims cannot mute a more recent local playback',async()=>{
 const h=harness();await h.context.speak('刚开始的声音',{message_id:1});const channel=h.channels[0];
 channel.onmessage({data:{type:'claim',owner:'another',clock:1,token:'00000000000000000001-another'}});
 assert.equal(h.audios[0].paused,false);
 channel.onmessage({data:{type:'claim',owner:'another',clock:999999999999999,token:'99999999999999999999-another'}});
 assert.equal(h.audios[0].paused,true);
});

test('a completed old-role mutation cannot apply success-side UI effects to a new identity',async()=>{
 const pending=deferred(),h=harness(async()=>pending.promise);
 const write=h.context.api('memories',{text:'旧角色合成记忆'});h.context.invalidateCharacterContext();h.context.adoptState(state(B));
 pending.resolve(response({ok:true}));await assert.rejects(write,/角色已切换/);
 assert.equal(JSON.parse(h.calls.find(call=>call.url==='/api/memories').body).expected_character_id,A);
});

test('appearance rollback controls unlock after an activation finishes',()=>{
 const h=harness(),old=pack(),newer=pack('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
 h.setState(state(A,old));h.read(`appearanceAssets=${JSON.stringify([old,newer])};assetLoadedFor='${A}'`);
 h.context.setCharactersBusy(true);
 assert.equal(h.get('#appearance-list').children[2].children[1].disabled,true);
 h.setState(state(A,newer));h.context.setCharactersBusy(false);
 const oldCard=h.get('#appearance-list').children[1],newCard=h.get('#appearance-list').children[2];
 assert.equal(oldCard.children[1].textContent,'使用');assert.equal(oldCard.children[1].disabled,false);
 assert.equal(newCard.children[1].textContent,'正在使用');assert.equal(newCard.children[1].disabled,true);
});

test('the saved voice preference is loaded for the initial active character',()=>{
 const h=harness();h.context.localStorage.getItem=key=>key==='character-voice:'+A?'voice-for-A':null;
 h.read("app=null;selectedVoice='legacy-voice'");h.context.adoptState(state(A));assert.equal(h.read('selectedVoice'),'voice-for-A');
});

test('hidden views cannot revive audio from late generation or reminder callbacks',async()=>{
 const h=harness();h.context.document.hidden=true;
 await h.context.speak('迟到回复',{message_id:1});
 assert.equal(h.calls.some(call=>call.url==='/api/speech'),false);assert.equal(h.audios.length,0);
});

test('native hide blocks new speech, late audio and recognition even when document stays visible',async()=>{
 const failures=[],hidden=harness();hidden.context.window.companionDesktopHidden=true;
 assert.equal(hidden.context.document.hidden,false);
 await hidden.context.speak('隐藏期间的新回复',{message_id:1});
 if(hidden.calls.some(call=>call.url==='/api/speech')||hidden.audios.length)failures.push('native-hidden entry requested speech');
 const body=deferred(),h=harness(async()=>({ok:true,blob:()=>body.promise}));
 const spoken=h.context.speak('尚在下载',{message_id:1});await tick();h.context.window.companionDesktopHidden=true;
 assert.equal(h.context.document.hidden,false);
 body.resolve({audio:true});await spoken;
 if(h.audios.length)failures.push('late speech created Audio while native-hidden');
 h.read(`recording=true;recognitionEpoch=contextEpoch;recognitionCharacter=currentCharacterId();recognition.onresult({results:[[{transcript:'隐藏后迟到的识别'}]]});`);
 if(h.get('#message-input').value)failures.push('late ASR modified hidden draft');
 assert.deepEqual(failures,[]);
});

function vrmFile(size=64){const bytes=new Uint8Array(size),view=new DataView(bytes.buffer);view.setUint32(0,0x46546c67,true);view.setUint32(4,2,true);view.setUint32(8,size,true);return {name:'自选模型.vrm',size,arrayBuffer:async()=>bytes.buffer};}
function vrmPack(){return {id:PACK,format:'vrm',model:{resource:'model.vrm',url:`/api/assets/${PACK}/model.vrm?character_id=${A}`},metadata:{name:'<自选模型>',authors:['作者']},states:{}};}
function mockVrm(h,load=async()=>true){const instances=[];h.context.window.CompanionVrm={create:options=>{const item={options,disposed:false,speaking:false,load,setSpeaking(value){this.speaking=value;},setAudio(audio){this.audio=audio;},setScale(){},setExpanded(){},setHidden(value){this.hidden=value;},dispose(){this.disposed=true;}};instances.push(item);return item;}};return instances;}

test('VRM upload rejects oversize and invalid headers before sending any model',async()=>{
 const h=harness();h.get('#asset-vrm').files=[{name:'too-large.vrm',size:64*1024*1024+1}];await h.context.importVrmAppearance();
 assert.match(h.get('#character-error').textContent,/64 MB/);assert.equal(h.calls.some(x=>x.url.includes('assets/import')),false);
 h.get('#asset-vrm').files=[{name:'wrong.vrm',size:40,arrayBuffer:async()=>new Uint8Array(40).buffer}];await h.context.importVrmAppearance();
 assert.match(h.get('#character-error').textContent,/完整的 VRM/);assert.equal(h.calls.some(x=>x.url.includes('assets/import')),false);
});

test('VRM server validation and real renderer readiness precede explicit activation',async()=>{
 const h=harness(async url=>response(url.endsWith('/import')?{asset:vrmPack()}:{assets:[vrmPack()]}));const instances=mockVrm(h);h.get('#asset-vrm').files=[vrmFile()];
 await h.context.importVrmAppearance();const write=h.calls.find(x=>x.url.endsWith('/import'));
 assert.equal(JSON.parse(write.body).format,'vrm');assert.equal(JSON.parse(write.body).character_id,A);
 assert.equal(h.read('app.active_character.appearance'),null);assert.equal(h.get('#activate-appearance').disabled,false);
 assert.equal(instances.length,1);assert.equal(h.get('#vrm-model-credit').textContent,'<自选模型> · 作者');
 assert.equal(h.calls.some(x=>x.url.endsWith('/activate')),false);
});

test('a failed VRM preview never enables activation or replaces the current character',async()=>{
 const h=harness(async url=>response(url.endsWith('/import')?{asset:vrmPack()}:{assets:[]}));mockVrm(h,async()=>false);h.get('#asset-vrm').files=[vrmFile()];await h.context.importVrmAppearance();
 assert.equal(h.get('#activate-appearance').disabled,true);assert.equal(h.read('app.active_character.appearance'),null);
});

test('VRM preview cancelled during load cannot re-enable activation after a role change',async()=>{
 const ready=deferred(),h=harness(async url=>response(url.endsWith('/import')?{asset:vrmPack()}:{assets:[]}));const instances=mockVrm(h,()=>ready.promise);h.get('#asset-vrm').files=[vrmFile()];
 const loading=h.context.importVrmAppearance();await tick();h.context.invalidateCharacterContext();h.setState(state(B));ready.resolve(true);await loading;
 assert.equal(instances[0].disposed,true);assert.equal(h.get('#activate-appearance').disabled,true);assert.equal(h.read('pendingAsset'),null);
});

test('native-hidden VRM stage disposes GPU ownership and ignores a late model load',async()=>{
 const ready=deferred(),h=harness();const instances=mockVrm(h,()=>ready.promise);h.setState(state(A,vrmPack()));
 const loading=h.context.renderVrmStage(vrmPack(),100);await tick();h.context.window.companionDesktopHidden=true;h.context.pauseVrmViews();ready.resolve(true);await loading;
 assert.equal(instances[0].disposed,true);assert.equal(h.read('stageVrm'),null);assert.equal(h.get('#vrm-stage').hidden,true);
});

test('missing Live2D runtime blocks preview activation without fetching vendor scripts',async()=>{
 const h=harness(async url=>response(url==='/api/live2d/runtime'?{available:false,core_url:null,reason:'owner_runtime_setup_required'}:{assets:[]}));
 const asset={id:PACK,format:'live2d',model:{resource:'model.model3.json',url:`/api/assets/${PACK}/model.model3.json?character_id=${A}`},resources:{}};
 await h.context.previewExistingLive2D(asset);assert.equal(h.get('#activate-appearance').disabled,true);assert.match(h.get('#appearance-status').textContent,/运行时尚未准备好/);assert.equal(h.get('#appearance-status').textContent.includes('owner_runtime_setup_required'),false);assert.equal(h.read('app.active_character.appearance'),null);
 assert.equal(h.calls.filter(x=>x.url==='/api/live2d/runtime').length,1);assert.equal(h.calls.some(x=>x.url.endsWith('/activate')),false);
});
test('Core without the separately installed display framework remains unavailable',async()=>{
 const h=harness(async()=>response({available:true,core_url:'/live2d-core.js',runtime_url:null}));
 await assert.rejects(h.context.ensureLive2DRuntime(),/显示框架尚未安装/);assert.equal(h.calls.length,2);
});
test('two requests for the same dynamic preview create only the latest renderer',async()=>{
 const engine=deferred(),h=harness(),instances=mockVrm(h);const factory=h.context.window.CompanionVrm;h.context.ensureCharacterRenderer=()=>engine.promise;
 h.read(`pendingAsset=${JSON.stringify(vrmPack())};pendingAssetCharacter='${A}'`);
 const first=h.context.renderVrmPreview(vrmPack()),second=h.context.renderVrmPreview(vrmPack());engine.resolve(factory);await first;await second;
 assert.equal(instances.length,1);assert.equal(instances[0].disposed,false);assert.equal(h.get('#activate-appearance').disabled,false);
});

test('ASR device changes select a compatible precision and preserve a valid preference',()=>{
 const h=harness(),device=h.get('#asr-device'),precision=h.get('#asr-precision');precision.options=['int8','float16','float32','int8_float16'].map(value=>({value,disabled:false}));
 device.value='cuda';precision.value='int8';h.context.syncAsrPrecision();assert.equal(precision.value,'float16');assert.equal(precision.options[0].disabled,true);assert.equal(precision.options[3].disabled,false);
 device.value='cpu';h.context.syncAsrPrecision();assert.equal(precision.value,'int8');assert.equal(precision.options[1].disabled,true);assert.equal(precision.options[3].disabled,true);
 precision.value='float32';device.value='cuda';h.context.syncAsrPrecision();assert.equal(precision.value,'float32');
});
test('optional PNG blink states follow real speaking and release timers on hide',async()=>{
 const h=harness(),timers=[],cleared=[];h.context.setTimeout=(fn,delay)=>{timers.push({fn,delay});return timers.length;};h.context.clearTimeout=id=>cleared.push(id);
 const asset=pack();for(const [key,resource]of [['blink','blink.png'],['talk_blink','talk_blink.png']])asset.states[key]={resource,url:`/api/assets/${PACK}/${resource}?character_id=${A}`};h.setState(state(A,asset));h.context.renderCharacterImage();
 assert.equal(timers.length,1);assert.ok(timers[0].delay>=1500&&timers[0].delay<=6000);await h.context.speak('实际播放',{message_id:1});
 timers[0].fn();assert.ok(h.get('#portrait-avatar').src.includes('/talk_blink.png'));assert.equal(timers[1].delay,120);timers[1].fn();assert.ok(h.get('#portrait-avatar').src.includes('/talk.png'));
 h.context.window.companionDesktopHidden=true;h.context.pauseVrmViews();assert.equal(h.read('pngBlinkActive'),false);assert.equal(h.read('pngBlinkTimer'),0);assert.ok(cleared.includes(3));
});
