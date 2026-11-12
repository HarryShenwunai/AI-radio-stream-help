// Race tests execute the real app.js with controlled browser primitives.
// They exercise client behavior; they do not measure real audio or server latency.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=fs.readFileSync(new URL('../app/static/app.js',import.meta.url),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(blob={audio:'fixture'})=>({ok:true,blob:async()=>blob,json:async()=>({ok:true})});
function harness(route){
 const nodes=new Map(),audios=[],revoked=[],calls=[],events=[],bodyClasses=new Set(),urls=[];
 const node=()=>({textContent:'',hidden:false,disabled:false,value:'',dataset:{},style:{},children:[],classList:{add(){},remove(){},toggle(){}},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},get firstChild(){return this.children[0];},setAttribute(){},addEventListener(){},focus(){},querySelector(){return null;}});
 const get=s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);};
 class Audio {
  constructor(url){this.src=url;this.paused=true;audios.push(this);}
  async play(){this.paused=false;if(this.onplay)this.onplay();if(this.failPlay)throw this.failPlay;}
  pause(){events.push('pause');this.paused=true;}
 }
 const context={console,AbortController,TextDecoder,Uint8Array,Response,ReadableStream,Audio,
  document:{querySelector:get,querySelectorAll:()=>[],createElement:node,hidden:false,addEventListener(){},body:{classList:{add:x=>bodyClasses.add(x),remove:x=>bodyClasses.delete(x),toggle:(x,on)=>on?bodyClasses.add(x):bodyClasses.delete(x)}}},
  window:{addEventListener(){}},localStorage:{getItem:()=> '__local__',setItem(){}},
  URL:{createObjectURL:()=>{const u=`blob:test-${urls.length+1}`;urls.push(u);return u;},revokeObjectURL:u=>revoked.push(u)},
  crypto:{randomUUID:()=> 'request-new'},setTimeout:()=>0,clearTimeout(){},setInterval(){},
  fetch:(url,options={})=>{calls.push({url,...options});if(url==='/api/state')return new Promise(()=>{});events.push('fetch:'+url);return route(url,options);},
 };
 vm.createContext(context);vm.runInContext(source,context);
 vm.runInContext("app={settings:{name:'角色',voice:true,engine:'api',voice_rate:1},local_voice_available:true,messages:[],model_busy:false};renderMessages=()=>{};refresh=async()=>{};",context);
 return {context,nodes,get,audios,revoked,calls,events,bodyClasses,urls,read:code=>vm.runInContext(code,context)};
}

test('stop aborts pending TTS and suppresses a provider which ignores abort',async()=>{
 const pending=deferred(),h=harness(()=>pending.promise);
 const spoken=h.context.speak('回复',{generation_id:'gen-1',request_id:'req-1'});
 const request=h.calls.find(x=>x.url==='/api/speech');
 assert.deepEqual(JSON.parse(request.body),{text:'回复',generation_id:'gen-1',request_id:'req-1'});
 h.context.stopVoice();assert.equal(request.signal.aborted,true);
 pending.resolve(response());await spoken;assert.equal(h.audios.length,0);assert.equal(h.urls.length,0);
});

test('stop during response body download never creates or plays late audio',async()=>{
 const body=deferred(),h=harness(async()=>({ok:true,blob:()=>body.promise}));
 const spoken=h.context.speak('回复',{message_id:9});await tick();
 assert.deepEqual(JSON.parse(h.calls.find(x=>x.url==='/api/speech').body),{message_id:9});
 h.context.stopVoice();body.resolve({audio:'late'});await spoken;assert.equal(h.audios.length,0);
});

test('cached old Audio callbacks cannot clear or revoke a newer playback',async()=>{
 const h=harness(async()=>response());
 await h.context.speak('旧回复',{message_id:1});
 const old=h.audios[0],callbacks=[old.onended,old.onerror,old.onplay];
 await h.context.speak('新回复',{message_id:2});
 const fresh=h.audios[1],freshUrl=fresh.src;
 assert.equal(old.paused,true);assert.equal(old.src,'');assert.ok(h.bodyClasses.has('is-speaking'));
 for(const callback of callbacks)callback();
 assert.equal(h.read('localAudio')===fresh,true);assert.ok(h.bodyClasses.has('is-speaking'));assert.equal(h.revoked.includes(freshUrl),false);
 fresh.onended();assert.equal(h.read('localAudio'),null);assert.equal(h.bodyClasses.has('is-speaking'),false);assert.equal(h.revoked.filter(x=>x===freshUrl).length,1);
});

test('generation stop mutes before failed backend cancellation and blocks late audio',async()=>{
 const late=deferred(),h=harness((url)=>url==='/api/speech'?late.promise:Promise.reject(new Error('backend unavailable')));
 h.read("activeRequest='req-stop';activeGeneration='gen-stop'");
 const spoken=h.context.speak('回复',{generation_id:'gen-stop',request_id:'req-stop'});
 await h.get('#stop-generation').onclick();
 assert.equal(h.read('stopping'),true);assert.equal(h.calls.find(x=>x.url==='/api/speech').signal.aborted,true);
 assert.deepEqual(JSON.parse(h.calls.find(x=>x.url==='/api/chat/stop').body),{request_id:'req-stop',generation_id:'gen-stop'});
 late.resolve(response());await spoken;assert.equal(h.audios.length,0);
});

test('voice stop pauses current audio before contacting backend for completed generation',async()=>{
 const h=harness(async()=>response());await h.context.speak('回复',{generation_id:'gen-done',request_id:'req-done'});
 h.events.length=0;h.get('#stop-voice').onclick();await tick();
 assert.equal(h.audios[0].paused,true);assert.equal(h.events[0],'pause');assert.equal(h.events[1],'fetch:/api/chat/stop');
 assert.deepEqual(JSON.parse(h.calls.find(x=>x.url==='/api/chat/stop').body),{request_id:'req-done',generation_id:'gen-done'});
});

test('new chat invalidates pending old TTS and automatic response uses SSE generation',async()=>{
 const old=deferred();let speechCount=0;
 const messages=[{type:'meta',generation_id:'generation-new',user:{id:10,role:'user',text:'新话题',request_id:'request-new'}},{type:'done',generation_id:'generation-new',message:{id:11,role:'assistant',text:'新回复',kind:'chat',request_id:'request-new'}}];
 const sse=messages.map(x=>'data: '+JSON.stringify(x)+'\n\n').join('');
 const h=harness(async(url)=>{
  if(url==='/api/chat/stream')return new Response(sse);
  if(url==='/api/speech')return ++speechCount===1?old.promise:response();
  return response();
 });
 const earlier=h.context.speak('旧回复',{message_id:1});
 const chat=h.context.runChat('新话题');assert.equal(h.calls.find(x=>x.url==='/api/speech').signal.aborted,true);
 old.resolve(response());await earlier;await chat;await tick();
 const requests=h.calls.filter(x=>x.url==='/api/speech');assert.equal(requests.length,2);
 assert.deepEqual(JSON.parse(requests[1].body),{text:'新回复',generation_id:'generation-new',request_id:'request-new'});
 assert.equal(h.audios.length,1);assert.equal(h.read('voiceContext.generation_id'),'generation-new');
});

test('settings sample keeps text payload; historical reading uses only message ID',async()=>{
 const h=harness(async()=>response());
 await h.context.speak('试音');await h.context.speak('页面上的不可信文字',{message_id:51});
 const bodies=h.calls.filter(x=>x.url==='/api/speech').map(x=>JSON.parse(x.body));
 assert.deepEqual(bodies,[{text:'试音'},{message_id:51}]);
});

test('system speech callbacks from a stopped utterance cannot change fresh playback UI',async()=>{
 const h=harness(async()=>response()),utterances=[];
 h.context.window.speechSynthesis=h.context.speechSynthesis={getVoices:()=>[{lang:'zh-CN',name:'Test',voiceURI:'test'}],cancel(){},speak:u=>utterances.push(u)};
 h.context.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
 h.read("selectedVoice='test';app.local_voice_available=false");
 await h.context.speak('旧声音');const old=utterances[0];
 await h.context.speak('新声音');const fresh=utterances[1];fresh.onstart();old.onend();old.onerror({error:'synthesis-failed'});old.onstart();
 assert.ok(h.bodyClasses.has('is-speaking'));assert.equal(h.get('#toast').textContent,'');fresh.onend();assert.equal(h.bodyClasses.has('is-speaking'),false);
});
