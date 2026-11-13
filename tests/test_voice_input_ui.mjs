import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../app/static/voice-input.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness({ready=true,permission,transcription}={}){
 const calls=[],errors=[],drafts=[],phases=[],timers=[],recorders=[],track={stopped:0,stop(){this.stopped++;}},stream={getTracks:()=>[track]};let id='role-A',hidden=false,mediaCalls=0;
 class Recorder{static isTypeSupported(){return true;}constructor(){this.state='inactive';recorders.push(this);}start(){this.state='recording';}stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['fixture-webm'],{type:'audio/webm'})});const callback=this.onstop;queueMicrotask(()=>callback?.());}}
 class Decoder{async decodeAudioData(){return {duration:1,length:48000};}async close(){}}
 class Offline{constructor(channels,length,rate){assert.equal(channels,1);assert.equal(rate,16000);this.length=length;this.destination={};}createBufferSource(){return {connect(){},start(){}};}async startRendering(){return {getChannelData:()=>Float32Array.from({length:this.length},(_,i)=>Math.sin(i*.2)*.2)};}}
 const context={window:{MediaRecorder:Recorder,AudioContext:Decoder,OfflineAudioContext:Offline},navigator:{mediaDevices:{getUserMedia:async()=>{mediaCalls++;return permission?await permission.promise:stream;}}},AbortController,Blob,DataView,ArrayBuffer,Uint8Array,Float32Array,btoa,crypto:{randomUUID:()=>`operation-${recorders.length}`},setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},fetch:async(url,options={})=>{calls.push({url,...options});if(url==='/api/voice/status')return {ok:true,json:async()=>({asr:{ready,reason:'尚未安装本机识别模型'}})};if(url==='/api/transcribe/stop')return {ok:true,json:async()=>({ok:true})};const payload=JSON.parse(options.body);return transcription?await transcription.promise:{ok:true,json:async()=>({text:'本机识别的文字',character_id:payload.expected_character_id,operation_id:payload.operation_id})};}};
 vm.createContext(context);vm.runInContext(source,context);const input=context.window.CompanionVoiceInput.create({getCharacterId:()=>id,isHidden:()=>hidden,onDraft:x=>drafts.push(x),onStatus:x=>phases.push(x),onError:x=>errors.push(x)});
 return {context,input,calls,errors,drafts,phases,timers,track,stream,recorders,get mediaCalls(){return mediaCalls;},setRole:x=>id=x,setHidden:x=>hidden=x};
}

test('PCM WAV encoding produces mono 16k PCM16 and clamps samples',()=>{
 const h=harness(),bytes=h.context.window.CompanionVoiceInput.pcm16Wav(new Float32Array([-2,-1,0,1,2])),view=new DataView(bytes);
 assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint16(22,true),1);assert.equal(view.getUint16(34,true),16);assert.equal(view.getUint32(40,true),10);
 assert.deepEqual(Array.from({length:5},(_,i)=>view.getInt16(44+i*2,true)),[-32768,-32768,0,32767,32767]);
});
test('unready local ASR does not request a microphone or fallback online',async()=>{
 const h=harness({ready:false});await h.input.start();assert.equal(h.mediaCalls,0);assert.equal(h.input.phase,'idle');assert.match(h.errors[0],/本机/);assert.deepEqual(h.calls.map(x=>x.url),['/api/voice/status']);
});
test('explicit recording stop sends only scoped PCM and fills draft without chat',async()=>{
 const h=harness();await h.input.start();assert.equal(h.input.phase,'recording');h.input.stop();await tick();await tick();
 assert.equal(h.track.stopped,1);assert.deepEqual(h.drafts,['本机识别的文字']);assert.equal(h.input.phase,'idle');
 const request=h.calls.find(x=>x.url==='/api/transcribe'),payload=JSON.parse(request.body),bytes=Buffer.from(payload.audio_base64,'base64');
 assert.equal(payload.expected_character_id,'role-A');assert.equal(bytes.toString('ascii',0,4),'RIFF');assert.equal(bytes.readUInt32LE(24),16000);assert.equal(bytes.readUInt16LE(22),1);assert.equal(bytes.readUInt32LE(40),32000);assert.equal(h.calls.some(x=>x.url.includes('/chat')),false);
});
test('the 60 second timer stops recording and uploads only once',async()=>{
 const h=harness();await h.input.start();h.timers[0]();await tick();await tick();assert.equal(h.recorders[0].state,'inactive');assert.equal(h.calls.filter(x=>x.url==='/api/transcribe').length,1);
});
test('cancel while microphone permission is pending stops every late track',async()=>{
 const permission=deferred(),h=harness({permission});const starting=h.input.start();await tick();h.input.cancel();permission.resolve(h.stream);await starting;
 assert.equal(h.track.stopped,1);assert.equal(h.recorders.length,0);assert.equal(h.input.phase,'idle');assert.equal(h.calls.some(x=>x.url==='/api/transcribe'),false);
});
test('cancelled local transcription cannot inject a late result after role switch',async()=>{
 const transcription=deferred(),h=harness({transcription});await h.input.start();h.input.stop();await tick();const upload=h.calls.find(x=>x.url==='/api/transcribe');assert.ok(upload);h.input.cancel();h.setRole('role-B');transcription.resolve({ok:true,json:async()=>({text:'迟到的旧结果',character_id:'role-A',operation_id:'operation-0'})});await tick();await tick();
 assert.equal(upload.signal.aborted,true);assert.deepEqual(h.drafts,[]);const cancelled=JSON.parse(h.calls.find(x=>x.url==='/api/transcribe/stop').body);assert.equal(cancelled.expected_character_id,'role-A');assert.equal(h.input.phase,'idle');
});
test('hidden input cannot acquire a microphone and late hidden output is discarded',async()=>{
 const h=harness();h.setHidden(true);await h.input.start();assert.equal(h.mediaCalls,0);assert.equal(h.calls.length,0);
 const transcription=deferred(),late=harness({transcription});await late.input.start();late.input.stop();await tick();late.setHidden(true);transcription.resolve({ok:true,json:async()=>({text:'隐藏时的结果',character_id:'role-A',operation_id:'operation-0'})});await tick();assert.deepEqual(late.drafts,[]);
});
test('repeated starts do not open more than one microphone',async()=>{
 const permission=deferred(),h=harness({permission});const first=h.input.start();await tick();await h.input.start();permission.resolve(h.stream);await first;assert.equal(h.mediaCalls,1);assert.equal(h.recorders.length,1);h.input.cancel();
});

test('audit01 stale recorder stop preserves the new recording',async()=>{const h=harness();await h.input.start();const old=h.recorders[0].onstop;h.input.cancel();await h.input.start();const count=h.track.stopped;old();await tick();assert.equal(h.track.stopped,count);assert.equal(h.input.phase,'recording');h.input.stop();await tick();assert.equal(h.recorders[1].state,'inactive');});

test('audit02 changed role during permission returns to idle',async()=>{const permission=deferred(),h=harness({permission});const start=h.input.start();await tick();h.setRole('role-B');permission.resolve(h.stream);await start;assert.equal(h.input.phase,'idle');assert.equal(h.track.stopped,1);assert.equal(h.recorders.length,0);});
