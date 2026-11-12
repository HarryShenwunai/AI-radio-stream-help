// E1 controlled DOM fixtures: no platform login, network, or real sending.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const createUI = require('../app/static/connectors-ui.js');
const pending = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; };
const tick = () => new Promise(r => setImmediate(r));
function harness(route = async () => ({wechat:{configured:false},bili:{state:'not_connected'}})) {
  const walk = n => [n, ...n.children.flatMap(walk)];
  function node(tag) { return {tagName:tag, children:[], textContent:'', hidden:false, value:'', checked:false, type:'', disabled:false, dataset:{},
    append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; },
    setAttribute(name,value) { this[name] = value; }, remove() {},
    querySelectorAll(selector) { return walk(this).filter(n => n.tagName === selector); },
  }; }
  const nav=node('nav'), workspace=node('main'), calls=[], confirms=[], toasts=[], listeners={}, copies=[];
  let id='role-a', decision=true, interval;
  const doc={hidden:false,createElement:node,querySelector:s=>s==='.rail nav'?nav:workspace,addEventListener:(name,fn)=>listeners[name]=fn,removeEventListener:name=>delete listeners[name]};
  const ui=createUI({document:doc,eventTarget:{addEventListener:(name,fn)=>listeners[name]=fn,removeEventListener:name=>delete listeners[name]},api:async(path,data)=>{calls.push({path,data});return route(path,data);},characterId:()=>id,
    showView:()=>ui.section.hidden=false,confirm:text=>{confirms.push(text);return decision;},toast:text=>toasts.push(text),
    clipboard:{writeText:async text=>copies.push(text)},setInterval:fn=>{interval=fn;return 1;},clearInterval(){}});
  const button = text => walk(ui.section).find(n=>n.tagName==='button'&&n.textContent===text);
  return {ui,doc,calls,confirms,toasts,copies,button,walk,nav,setId:value=>id=value,setDecision:value=>decision=value,poll:()=>interval(),listeners};
}
test('mount never connects, authenticates, or reads storage; explicit navigation reads status',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.ui.nav.onclick();await tick();
  assert.equal(h.calls[0].path,'connectors/status');assert.equal(h.ui.fields.voice.checked,true);assert.equal(h.ui.fields.auto_approve.checked,false);
});
test('one-time pairing token is shown only after configure and cleared on character reset',async()=>{
  const h=harness(async path=>path.endsWith('/configure')?{pairing_token:'secret-once'}:{wechat:{configured:false}});
  h.ui.fields.owner_origin.value='weixin_oc:FriendMessage:owner';
  await h.button('绑定当前角色').onclick();assert.equal(h.ui.fields.pairing_token.value,'secret-once');
  assert.equal(h.ui.fields.pairing_token.type,'password');await h.button('复制').onclick();assert.deepEqual(h.copies,['secret-once']);
  h.setId('role-b');h.ui.resetCharacter();assert.equal(h.ui.fields.pairing_token.value,'');
  await h.ui.refresh();assert.equal(h.ui.fields.pairing_token.value,'');
});
test('automatic replies require explicit confirmation and cancelled approval makes no POST',async()=>{
  const h=harness();h.ui.fields.auto_approve.checked=true;h.setDecision(false);
  await h.button('绑定当前角色').onclick();assert.equal(h.confirms.length,1);assert.equal(h.calls.length,0);
  h.setDecision(true);await h.button('绑定当前角色').onclick();
  const req=h.calls.find(x=>x.path.endsWith('/configure'));assert.equal(req.data.confirm_owner_auto_reply,true);assert.equal(req.data.expected_character_id,'role-a');
});
test('only current character private previews appear and real send approval requires confirmation',async()=>{
  const h=harness();h.ui.renderStatus({wechat:{configured:true,character_id:'role-a',previews:[
    {id:'a',character_id:'role-a',text:'current',state:'preview'}, {id:'b',character_id:'role-b',text:'private-other',state:'preview'}]}});
  const texts=h.walk(h.ui.section).map(n=>n.textContent);assert.ok(texts.includes('current'));assert.ok(!texts.includes('private-other'));
  h.setDecision(false);await h.button('批准发送').onclick();assert.equal(h.calls.length,0);
  h.setDecision(true);await h.button('批准发送').onclick();assert.deepEqual(h.calls[0],{path:'connectors/wechat/approve',data:{id:'a',expected_character_id:'role-a'}});
});
test('a stale configure cannot reveal its token after switching characters',async()=>{
  const wait=pending(),h=harness(()=>wait.promise);const configure=h.button('绑定当前角色').onclick();
  h.setId('role-b');h.ui.resetCharacter();wait.resolve({pairing_token:'old-secret'});await configure;
  assert.equal(h.ui.fields.pairing_token.value,'');assert.deepEqual(h.toasts,[]);
});
test('stale status never paints private preview after reset',async()=>{
  const wait=pending(),h=harness(()=>wait.promise);const read=h.ui.refresh();h.setId('role-b');h.ui.resetCharacter();
  wait.resolve({wechat:{configured:true,character_id:'role-a',previews:[{character_id:'role-a',text:'old-private'}]}});await read;
  assert.ok(!h.walk(h.ui.section).some(n=>n.textContent==='old-private'));
});
test('Bili connection is explicit, secret fields clear, output UI only generates local preview',async()=>{
  const h=harness();for(const n of ['access_key_id','access_key_secret','app_id','room_id','anchor_code'])h.ui.fields[n].value=n+'-fixture';
  h.setDecision(false);await h.button('连接直播间').onclick();assert.equal(h.calls.length,0);
  h.setDecision(true);await h.button('连接直播间').onclick();const req=h.calls[0];assert.equal(req.path,'connectors/bili/configure');assert.equal(req.data.connect,true);
  assert.equal(h.ui.fields.access_key_secret.value,'');assert.equal(h.ui.fields.anchor_code.value,'');
  h.ui.renderStatus({public_events:[{event_id:'fixture-event',room_id:'123',text:'<script>untrusted</script>'}]});
  assert.ok(h.walk(h.ui.section).some(n=>n.textContent==='<script>untrusted</script>'));
  await h.button('生成预览').onclick();assert.equal(h.calls.find(x=>x.path==='connectors/bili/reply').data.event_id,'fixture-event');
});
test('hidden view does not poll and clears one-time secrets; role-change event clears previews',async()=>{
  const h=harness();h.ui.fields.pairing_token.value='secret';h.poll();assert.equal(h.calls.length,0);assert.equal(h.ui.fields.pairing_token.value,'');
  h.ui.section.hidden=false;h.poll();await tick();assert.equal(h.calls.length,1);
  h.ui.fields.pairing_token.value='again';h.listeners['companion:character-change']();assert.equal(h.ui.fields.pairing_token.value,'');
});
test('pause endpoint explicitly promises suspension and cancellation, no delivery success claim',async()=>{
  const h=harness();await h.button('暂停自动发送并取消待发').onclick();
  assert.equal(h.calls[0].path,'connectors/wechat/stop');assert.equal(h.ui.fields.auto_approve.checked,false);
  assert.ok(h.toasts[0].includes('已暂停自动发送'));
});

test('native host pause immediately clears credentials while document remains visible; status codes stay internal',()=>{
  const h=harness();h.ui.fields.pairing_token.value='secret';h.ui.fields.access_key_secret.value='key';
  h.listeners['companion:desktop-pause']();assert.equal(h.doc.hidden,false);assert.equal(h.ui.fields.pairing_token.value,'');assert.equal(h.ui.fields.access_key_secret.value,'');
  h.ui.renderStatus({bili:{state:'internal_unknown',last_error:'open_live_internal_error'}});
  const text=h.walk(h.ui.section).map(n=>n.textContent).join(' ');assert.ok(text.includes('连接异常'));assert.ok(!text.includes('open_live_internal_error'));assert.ok(!text.includes('internal_unknown'));
});
