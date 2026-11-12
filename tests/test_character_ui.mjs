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
  window:{addEventListener(){}},localStorage:{getItem:()=> '__local__',setItem(){}},
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

test('a response finishing during native hide never creates a new Audio object',async()=>{
 const body=deferred(),h=harness(async()=>({ok:true,blob:()=>body.promise}));
 const spoken=h.context.speak('尚在下载',{message_id:1});await tick();h.context.document.hidden=true;
 body.resolve({audio:true});await spoken;assert.equal(h.audios.length,0);
});
