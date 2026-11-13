import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../app/static/playback-receipts.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const meta=()=>({playback_id:'playback-1',nonce:'n'.repeat(32),character_id:'role-A',appearance_id:null,message_id:17,duration_seconds:4,text_length:100});
function harness(options={}){
 const calls=[],states=[],timers=[];let now=0;const context={window:{},atob,performance:{now:()=>now},setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},fetch:async(url,request)=>{const body=JSON.parse(request.body);calls.push({url,...request,body});if(options.fetch)return options.fetch(body);return {ok:true,json:async()=>({accepted:true,stale:false,status:body.status,confirmed_characters:body.status==='completed'?100:0})};}};
 vm.createContext(context);vm.runInContext(source,context);const create=value=>context.window.CompanionPlayback.create(value||meta(),{onState:(status,result)=>states.push({status,result}),onLimit:()=>states.push({status:'limit'})});
 return {context,calls,states,timers,create,advance:value=>now=value};
}

test('a complete Audio receipt requires observed end position and retains the bound duration',async()=>{
 const h=harness(),audio={currentTime:0,duration:4,ended:false},p=h.create();p.attachAudio(audio);await p.progress(true);audio.currentTime=4;audio.ended=true;await p.complete();
 assert.deepEqual(h.calls.map(x=>x.body.status),['playing','completed']);assert.equal(h.calls[1].body.position_seconds,4);assert.equal(h.calls[1].body.duration_seconds,4);assert.equal(h.calls[1].keepalive,true);
});
test('stopping captures the current position before cleanup and seals late ended callbacks',async()=>{
 const h=harness(),audio={currentTime:1.25,duration:4,ended:false},p=h.create();p.attachAudio(audio);await p.stop();audio.currentTime=0;audio.ended=true;await p.complete();
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].body.status,'stopped');assert.equal(h.calls[0].body.position_seconds,1.25);assert.equal(h.calls[0].body.expected_character_id,'role-A');
});
test('progress uploads are throttled to about one second',async()=>{
 const h=harness(),audio={currentTime:0,duration:4,ended:false},p=h.create();p.attachAudio(audio);await p.progress(true);h.advance(200);audio.currentTime=.2;await p.progress();h.advance(1100);audio.currentTime=1.1;await p.progress();assert.equal(h.calls.length,2);await p.stop();
});
test('early ended cannot confirm an unplayed tail',async()=>{
 const h=harness(),p=h.create();p.attachAudio({currentTime:.5,duration:4,ended:true});await p.complete();assert.equal(h.calls[0].body.status,'stopped');assert.equal(h.calls[0].body.position_seconds,.5);
});
test('terminal keepalive is immediate and older queued progress cannot revive playback',async()=>{
 let finish;const first=new Promise(resolve=>finish=resolve),h=harness({fetch:body=>body.status==='playing'?first:Promise.resolve({ok:true,json:async()=>({accepted:true,status:body.status})})}),p=h.create(),audio={currentTime:0,duration:4,ended:false};p.attachAudio(audio);p.progress(true);await tick();h.advance(1100);audio.currentTime=1.1;p.progress();await p.stop();finish({ok:true,json:async()=>({accepted:true,status:'playing'})});await tick();
 assert.deepEqual(h.calls.map(x=>x.body.status),['playing','stopped']);assert.equal(h.states.at(-1).status,'stopped');
});
test('unknown system duration is only confirmed by real completion elapsed time',async()=>{
 const h=harness(),m={...meta(),duration_seconds:null},p=h.create(m);p.startSystem();h.advance(6000);await p.progress();assert.equal(h.calls.length,0);await p.complete();assert.equal(h.calls[0].body.duration_seconds,6);assert.equal(h.calls[0].body.position_seconds,6);assert.equal(h.calls[0].body.status,'completed');
});
test('cancel before system start reports stopped zero and late completion cannot confirm',async()=>{
 const h=harness(),p=h.create({...meta(),duration_seconds:null});await p.stop();p.startSystem();h.advance(4000);await p.complete();assert.equal(h.calls.length,1);assert.equal(h.calls[0].body.status,'stopped');assert.equal(h.calls[0].body.position_seconds,0);assert.equal(h.calls[0].body.duration_seconds,null);
});
test('system playback over the 180 second bound remains conservatively unconfirmed',async()=>{
 const h=harness(),p=h.create({...meta(),duration_seconds:null});p.startSystem();h.advance(181000);await p.complete();assert.equal(h.calls[0].body.status,'stopped');assert.equal(h.calls[0].body.position_seconds,180);
});
test('a failed terminal request is not described as confirmed playback',async()=>{
 const h=harness({fetch:async()=>{throw new Error('offline');}}),p=h.create();p.attachAudio({currentTime:4,duration:4,ended:true});await p.complete();assert.equal(h.states.at(-1).status,'unconfirmed');assert.equal(p.terminal,true);
});
test('malformed header metadata is rejected before any receipt request',()=>{
 const h=harness();assert.throws(()=>h.context.window.CompanionPlayback.fromHeader(btoa(JSON.stringify({...meta(),nonce:''}))),/无效/);assert.equal(h.calls.length,0);
});
test('bounded exhaustive Audio event sequences never emit two terminal states or confirm an early end',async()=>{
 // 5^4 paths through actual shipped controller; a bounded state exploration,
 // not a proof over arbitrary JavaScript, browser timing or human hearing.
 const actions=['advance','progress','stop','complete','reachEnd'];let paths=0;
 for(let code=0;code<625;code++){
  const h=harness(),p=h.create(),audio={currentTime:0,duration:4,ended:false};p.attachAudio(audio);let value=code;
  for(let step=0;step<4;step++){const action=actions[value%5];value=Math.floor(value/5);if(action==='advance'){h.advance((step+1)*1100);audio.currentTime=Math.min(3,audio.currentTime+.5);}else if(action==='reachEnd'){audio.currentTime=4;audio.ended=true;}else if(action==='progress')await p.progress();else if(action==='stop')await p.stop();else await p.complete();}
  await p.stop();const terminal=h.calls.filter(x=>x.body.status!=='playing');assert.equal(terminal.length,1);for(const call of h.calls){assert.ok(call.body.position_seconds>=0&&call.body.position_seconds<=4);if(call.body.status==='completed')assert.equal(call.body.position_seconds,4);}paths++;
 }
 assert.equal(paths,625);
});

test('audit04 duplicate system start cannot reset elapsed time',async()=>{const h=harness(),p=h.create({...meta(),duration_seconds:null});p.startSystem();h.advance(2000);p.startSystem();h.advance(4000);await p.complete();assert.equal(h.calls[0].body.position_seconds,4);assert.equal(h.timers.length,1);});

test('audit05 caller mutation cannot change receipt owner or nonce',async()=>{const h=harness(),m=meta(),p=h.create(m);m.character_id='role-B';m.nonce='changed';await p.stop();assert.equal(h.calls[0].body.character_id,'role-A');assert.equal(h.calls[0].body.nonce,'n'.repeat(32));});
