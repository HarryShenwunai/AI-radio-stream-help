// E1 purpose-flow behavior, controlled DOM/API. No accounts are paired or sent.
import test from'node:test';import assert from'node:assert/strict';import fs from'node:fs';import vm from'node:vm';import{deferred,tick}from'./ui_rebuild_harness.mjs';
function harness(route=async()=>({wechat:{configured:false},bili:{state:'not_connected'}})){
 const walk=n=>[n,...n.children.flatMap(walk)],frames=[],calls=[],confirms=[];let role='role-a',decision=true,active=null,cleanup=null;
 function el(tag,cls='',text=''){return {tagName:tag,className:cls,textContent:text,children:[],value:'',checked:false,hidden:false,disabled:false,dataset:{},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},querySelectorAll(selector){return walk(this).filter(n=>selector==='input[type=password]'?n.tagName==='input'&&n.type==='password':n.tagName===selector);},setAttribute(){}};}
 const kit={el,hint:text=>el('p','',text),row:(...nodes)=>{const n=el('div');n.append(...nodes);return n;},button:(title,options={})=>{const n=el('button','',title);n.onclick=options.action;return n;},field:(title,options={})=>{const label=el('label','',title),input=el('input');input.type=options.type||'text';input.value=options.value||'';label.append(input);return {label,input};},error:(n,text)=>{n.textContent=text;n.hidden=!text;},formAction:(form,title,action)=>{const n=el('button','',title);n.onclick=action;form.append(n);}};
 const ui={panel(){const node=el('section'),body=el('div');node.append(body);const frame={node,body};frames.push(frame);return frame;},open(node,options){cleanup?.();active=options.id;cleanup=options.onClose;},close(){active=null;cleanup?.();cleanup=null;},notify(){},get active(){return active;}};
 const core={scope:()=>({character_id:role,epoch:0}),current:stamp=>stamp.character_id===role,api:async(path,data)=>{calls.push({path,data:data?{...data,expected_character_id:role}:undefined});return route(path,data);}};
 const context={window:{},CompanionUI:kit,confirm:text=>{confirms.push(text);return decision;}};vm.createContext(context);vm.runInContext(fs.readFileSync(process.env.CONNECTOR_UI_SOURCE||new URL('../app/static/connectors-ui.js',import.meta.url),'utf8'),context);const contacts=context.window.CompanionContacts.create({core,ui});
 const nodes=()=>frames.length?walk(frames.at(-1).node):[],button=text=>nodes().find(n=>n.tagName==='button'&&n.textContent===text),field=text=>nodes().find(n=>n.tagName==='label'&&n.textContent===text)?.children[0];
 return {contacts,ui,calls,confirms,nodes,button,field,setDecision:v=>decision=v,changeRole:v=>{role=v;ui.close();},async open(page){await contacts.open();if(page)button(page==='wechat'?'微信私聊桥接':'哔哩哔哩直播预览').onclick();}};
}
test('mount is inert; opening a purpose flow only reads status',async()=>{const h=harness();assert.equal(h.calls.length,0);await h.open();assert.deepEqual(h.calls.map(c=>c.path),['connectors/status']);});
test('one-time pairing token appears only after configure and clears on close',async()=>{const h=harness(async path=>path.endsWith('/configure')?{pairing_token:'only-once'}:{wechat:{configured:false}});await h.open('wechat');h.field('AstrBot私聊来源').value='origin';await h.button('绑定当前角色').onclick();const token=h.field('本次配对令牌');assert.equal(token.value,'only-once');assert.equal(token.type,'password');h.ui.close();assert.equal(token.value,'');});
test('automatic replies require explicit confirmation before any write',async()=>{const h=harness();await h.open('wechat');h.field('允许自动回复这个私聊').checked=true;h.setDecision(false);await h.button('绑定当前角色').onclick();assert.equal(h.calls.filter(c=>c.data).length,0);assert.equal(h.confirms.length,1);});
test('current-role private previews alone render and approval can be refused',async()=>{const h=harness(async()=>({wechat:{configured:true,character_id:'role-a',previews:[{id:'a',character_id:'role-a',state:'preview',text:'current'},{id:'b',character_id:'role-b',state:'preview',text:'foreign-private'}]}}));await h.open('wechat');assert.ok(h.nodes().some(n=>n.textContent==='current'));assert.equal(h.nodes().some(n=>n.textContent==='foreign-private'),false);h.setDecision(false);await h.button('审核并批准这条发送').onclick();assert.equal(h.calls.filter(c=>c.data).length,0);});
test('late configure cannot reveal a token after role changes',async()=>{const late=deferred(),h=harness(path=>path.endsWith('/configure')?late.promise:Promise.resolve({wechat:{}}));await h.open('wechat');const configuring=h.button('绑定当前角色').onclick();h.changeRole('role-b');late.resolve({pairing_token:'old-secret'});await configuring;assert.equal(h.nodes().some(n=>n.value==='old-secret'),false);});
test('late status cannot paint private content after role change',async()=>{const late=deferred(),h=harness(()=>late.promise);const opening=h.contacts.open();h.changeRole('role-b');late.resolve({wechat:{configured:true,character_id:'role-a',previews:[{text:'old-private'}]}});await opening;assert.equal(h.nodes().some(n=>n.textContent==='old-private'),false);});
test('Bili connection is explicit; secret fields clear after attempted connection',async()=>{const h=harness();await h.open('bili');for(const name of['Access Key ID','Access Key Secret','应用ID','直播间ID','主播身份码'])h.field(name).value='fixture';h.setDecision(false);await h.button('连接并接收弹幕').onclick();assert.equal(h.calls.filter(c=>c.data).length,0);h.setDecision(true);const secret=h.field('Access Key Secret'),anchor=h.field('主播身份码');await h.button('连接并接收弹幕').onclick();assert.equal(secret.value,'');assert.equal(anchor.value,'');assert.equal(h.calls.find(c=>c.path==='connectors/bili/configure').data.connect,true);});
test('hidden flows do not poll and clear credentials on close',async()=>{const h=harness();await h.open('bili');const secret=h.field('Access Key Secret');secret.value='private';const count=h.calls.length;h.ui.close();await tick();assert.equal(secret.value,'');assert.equal(h.calls.length,count);});
test('pause uses cancellation endpoint without a fake delivered claim',async()=>{const h=harness();await h.open('wechat');await h.button('暂停自动发送并取消待发').onclick();assert.ok(h.calls.some(c=>c.path==='connectors/wechat/stop'));assert.equal(h.nodes().some(n=>n.textContent==='发送成功'),false);});
test('native pause cleanup works while browser visibility is unchanged and unknown codes stay internal',async()=>{const h=harness(async()=>({bili:{state:'internal_auth_error'}}));await h.open('bili');const secret=h.field('Access Key Secret');secret.value='private';h.ui.close();assert.equal(secret.value,'');assert.equal(h.nodes().some(n=>n.textContent==='internal_auth_error'),false);});

test('live review pairs answer with its question and keeps playback approval explicit',async()=>{
 const h=harness(async()=>({bili:{state:'not_connected'},public_events:[{event_id:'e1',room_id:'1',text:'Unique question'}],live_output:{material:{text:'Public material'},jobs:[{id:'j1',event_id:'e1',room_id:'1',question:'Unique question',text:'Answer',state:'review'}]}}));
 await h.open('bili');assert.equal(h.nodes().filter(n=>n.textContent==='Unique question').length,1);assert.equal(h.button('准备回答'),undefined);
 h.setDecision(false);await h.button('播放这条回答').onclick();assert.equal(h.calls.filter(c=>c.data).length,0);
 h.setDecision(true);await h.button('播放这条回答').onclick();assert.equal(h.calls.find(c=>c.path==='connectors/bili/approve').data.confirm_output,true);
});

test('refresh preserves unsaved public material without approving it',async()=>{
 const h=harness(async()=>({bili:{state:'not_connected'},live_output:{material:{text:'Saved source'},jobs:[]}}));
 await h.open('bili');h.field('本场公开教材').value='Unsaved source Δx';
 await h.button('刷新').onclick();assert.equal(h.field('本场公开教材').value,'Unsaved source Δx');
 assert.equal(h.field('允许在直播中使用这份教材').checked,false);
 assert.equal(h.calls.filter(c=>c.data).length,0);
});

test('late older refresh cannot replace the newer response',async()=>{
 const old=deferred(),fresh=deferred();let count=0;
 const h=harness(async()=>{count++;return count===1?{bili:{state:'not_connected'}}:count===2?old.promise:fresh.promise;});
 await h.open('bili');const first=h.button('刷新').onclick(),second=h.button('刷新').onclick();
 fresh.resolve({live_output:{jobs:[{state:'review',id:'new',question:'new question',text:'new answer'}]}});await second;
 old.resolve({live_output:{jobs:[{state:'review',id:'old',question:'old question',text:'old answer'}]}});await first;
 assert.ok(h.nodes().some(n=>n.textContent==='new answer'));assert.ok(!h.nodes().some(n=>n.textContent==='old answer'));
});
test('repeated playback clicks produce only one approval request',async()=>{
 const pending=deferred();const snapshot={live_output:{jobs:[{id:'one',state:'review',question:'question',text:'answer'}]}};
 const h=harness((path)=>path.endsWith('/approve')?pending.promise:Promise.resolve(snapshot));await h.open('bili');
 const control=h.button('播放这条回答'),first=control.onclick(),second=control.onclick();
 const count=h.calls.filter(c=>c.path==='connectors/bili/approve').length;pending.resolve({});await Promise.all([first,second]);assert.equal(count,1);
});
