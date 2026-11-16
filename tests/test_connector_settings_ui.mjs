// E1 purpose-flow behavior, controlled DOM/API. No accounts are paired or sent.
import test from'node:test';import assert from'node:assert/strict';import fs from'node:fs';import vm from'node:vm';import{deferred,tick}from'./ui_rebuild_harness.mjs';
function harness(route=async()=>({wechat:{configured:false},bili:{state:'not_connected'}})){
 const walk=n=>[n,...n.children.flatMap(walk)],frames=[],calls=[],confirms=[];let role='role-a',decision=true,active=null,cleanup=null;const listeners=new Map(),channels=[];
 function el(tag,cls='',text=''){return {tagName:tag,className:cls,textContent:text,children:[],value:'',checked:false,hidden:false,disabled:false,dataset:{},append(...nodes){for(const n of nodes)n.parentNode=this;this.children.push(...nodes);},replaceChildren(...nodes){this.children=[];this.append(...nodes);},contains(node){return walk(this).includes(node);},focus(){context.document.activeElement=this;},querySelector(selector){return walk(this).find(n=>n.tagName===selector)||null;},querySelectorAll(selector){return walk(this).filter(n=>selector==='input[type=password]'?n.tagName==='input'&&n.type==='password':n.tagName===selector);},closest(selector){let n=this;while(n){if(selector==='details'?n.tagName==='details':selector.startsWith('.')&&n.className.split(' ').includes(selector.slice(1)))return n;n=n.parentNode;}return null;},setAttribute(){}};}
 const kit={el,hint:text=>el('p','',text),row:(...nodes)=>{const n=el('div');n.append(...nodes);return n;},button:(title,options={})=>{const n=el('button','',title);n.onclick=options.action;return n;},field:(title,options={})=>{const label=el('label','',title),input=el('input');input.type=options.type||'text';input.value=options.value||'';label.append(input);return {label,input};},error:(n,text)=>{n.textContent=text;n.hidden=!text;},formAction:(form,title,action)=>{const n=el('button','',title);n.onclick=action;form.append(n);}};
 const ui={panel(){const node=el('section'),body=el('div');node.append(body);const frame={node,body};frames.push(frame);return frame;},open(node,options){cleanup?.();active=options.id;cleanup=options.onClose;},close(){active=null;cleanup?.();cleanup=null;},notify(){},get active(){return active;}};
 const core={on(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);return()=>listeners.get(type).delete(fn);},refresh:async()=>{calls.push({path:'state'});},scope:()=>({character_id:role,epoch:0}),current:stamp=>stamp.character_id===role,api:async(path,data)=>{calls.push({path,data:data?{...data,expected_character_id:role}:undefined});return route(path,data);}};
 class Channel{constructor(name){this.name=name;this.closed=false;channels.push(this);}close(){this.closed=true;this.onmessage=null;}}
 const storage=new Map();const context={window:{},localStorage:{getItem:key=>storage.get(key)||null},BroadcastChannel:Channel,document:{activeElement:null},CompanionUI:kit,confirm:text=>{confirms.push(text);return decision;}};vm.createContext(context);vm.runInContext(fs.readFileSync(process.env.CONNECTOR_UI_SOURCE||new URL('../app/static/connectors-ui.js',import.meta.url),'utf8'),context);const contacts=context.window.CompanionContacts.create({core,ui});
 const nodes=()=>frames.length?walk(frames.at(-1).node):[],button=text=>nodes().find(n=>n.tagName==='button'&&n.textContent===text),field=text=>nodes().find(n=>n.tagName==='label'&&n.textContent===text)?.children[0];
 return {contacts,ui,calls,confirms,storage,nodes,button,field,channels,get focused(){return context.document.activeElement;},emit:(type,value)=>{for(const fn of [...(listeners.get(type)||[])])fn(value);},listenerCount:type=>listeners.get(type)?.size||0,setDecision:v=>decision=v,changeRole:v=>{role=v;ui.close();},async open(page){await contacts.open();if(page)button(page==='wechat'?'微信私聊桥接':'哔哩哔哩直播预览').onclick();}};
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

test('host speaking hides preparation and playback while keeping incoming questions visible',async()=>{
 const h=harness(async()=>({public_events:[{event_id:'e',text:'new question'}],live_output:{host_talking:true,jobs:[{id:'j',state:'review',text:'held answer'}]}}));
 await h.open('bili');assert.equal(h.button('准备回答'),undefined);assert.equal(h.button('播放这条回答'),undefined);assert.ok(h.nodes().some(n=>n.textContent==='new question'));assert.ok(h.button('结束讲解'));
});


test('existing core refresh updates terminal output without rebuilding unsent fields',async()=>{
 const base={session:'s1',revision:1,output_open:true,host_talking:false,jobs:[{id:'j1',state:'playing',question:'question',text:'answer'}]};
 const h=harness(async()=>({bili:{state:'local_rehearsal'},live_output:base}));await h.open('bili');
 const message=h.field('模拟观众消息'),topic=h.field('本场公开背景'),material=h.field('本场公开教材');
 message.value='unsent';topic.value='unsent context';material.value='unsent material';
 h.emit('change',{state:{live_output:{...base,revision:2,jobs:[{...base.jobs[0],state:'completed'}]}}});
 assert.ok(h.nodes().some(n=>n.textContent==='已播完'));
 assert.equal(h.field('模拟观众消息'),message);assert.equal(message.value,'unsent');assert.equal(h.field('本场公开背景'),topic);assert.equal(h.field('本场公开教材'),material);
 assert.equal(h.calls.filter(c=>c.data).length,0);assert.equal(h.calls.length,1);
 h.emit('change',{state:{live_output:base}});assert.ok(h.nodes().some(n=>n.textContent==='已播完'));assert.ok(!h.nodes().some(n=>n.textContent==='本机播放中'));
});
test('output status preserves unsubmitted credentials and changing session clears stale output link',async()=>{
 const base={session:'old',revision:8,output_open:true,host_talking:false,jobs:[{id:'a',state:'review',text:'answer'}]};
 const h=harness(async path=>path.endsWith('/open')?{path:'/live-stage.html#fixture'}:{bili:{state:'not_connected'},live_output:base});await h.open('bili');
 const secret=h.field('Access Key Secret');secret.value='unsent secret';await h.button('输出窗口').onclick();
 h.emit('change',{state:{live_output:{session:'new',revision:1,output_open:false,host_talking:true,jobs:[]}}});
 assert.equal(h.field('Access Key Secret'),secret);assert.equal(secret.value,'unsent secret');assert.ok(h.button('结束讲解'));assert.equal(h.nodes().some(n=>n.tagName==='a'&&n.href==='/live-stage.html#fixture'),false);
 h.emit('change',{state:{live_output:base}});assert.equal(h.button('播放这条回答'),undefined);
});
test('broadcast carries no authority and subscriptions close with panel or identity',async()=>{
 const h=harness();await h.open('bili');const channel=h.channels[0];assert.equal(channel.name,'companion-live-output');
 channel.onmessage({data:{type:'untrusted',state:'completed'}});assert.equal(h.calls.length,1);
 await channel.onmessage({data:{type:'changed',state:'completed'}});assert.equal(h.calls.at(-1).path,'state');assert.ok(!h.nodes().some(n=>n.textContent==='已播完'));
 h.ui.close();assert.equal(channel.closed,true);assert.equal(h.listenerCount('change'),0);assert.equal(h.listenerCount('invalidate'),0);
 const count=h.calls.length;h.emit('change',{state:{live_output:{jobs:[{state:'completed'}]}}});assert.equal(h.calls.length,count);
 const other=harness();await other.open('bili');other.emit('invalidate',{});assert.equal(other.channels[0].closed,true);assert.equal(other.listenerCount('change'),0);
});

test('unchanged core snapshot does not remove keyboard focus; changed action uses safe stop',async()=>{
 const base={session:'focus',revision:1,output_open:true,jobs:[{id:'j1',event_id:'e',state:'review',text:'answer'}]};
 const h=harness(async()=>({live_output:base}));await h.open('bili');const approve=h.button('播放这条回答');approve.focus();
 h.emit('change',{state:{live_output:base}});assert.equal(h.button('播放这条回答'),approve);assert.equal(h.focused,approve);
 h.emit('change',{state:{live_output:{...base,revision:2,jobs:base.jobs}}});assert.notEqual(h.button('播放这条回答'),approve);
 const replacement=h.button('播放这条回答');assert.ok(replacement);assert.equal(h.focused,replacement);
 h.emit('change',{state:{live_output:{...base,revision:3,jobs:[{...base.jobs[0],state:'playing'}]}}});assert.equal(h.button('播放这条回答'),undefined);assert.ok(h.button('停止播放'));assert.equal(h.focused,h.button('停止播放'));
});


test('pre-playback failures use only approved reason labels without exposing internal codes',async()=>{
 for(const [state,reason,label] of [
  ['failed','insufficient_playback_budget','剩余时限不足，未播放'],
  ['failed','invalid_audio','音频无效，未播放'],
  ['failed','private-provider-error','播放失败'],
  ['failed','__proto__','播放失败'],
  ['failed','constructor','播放失败'],
  ['playing','insufficient_playback_budget','本机播放中']
 ]){
  const h=harness(async()=>({live_output:{jobs:[{id:'reason',state,failure_reason:reason,question:'question'}]}}));await h.open('bili');
  const rendered=h.nodes().filter(n=>n.className==='live-state');assert.equal(rendered.length,1);assert.equal(rendered[0].textContent,label);assert.equal(h.nodes().some(n=>n.textContent===reason),false);
 }
});

test('output uses only explicitly applied same-identity room layout and theme',async()=>{
 const h=harness(async path=>path.endsWith('/open')?{path:'/live-stage.html#fixture'}:{});
 h.storage.set('room-settings:role-a',JSON.stringify({config:{version:1,applied:true,characterId:'role-a',layout:'left',theme:'midnight',topic:'PRIVATE_CONFIG_CANARY'},draft:{applied:true,layout:'small',theme:'daylight',caption:'PRIVATE_DRAFT_CANARY'}}));
 await h.open('bili');await h.button('输出窗口').onclick();
 const call=h.calls.find(c=>c.path.endsWith('/output/open'));assert.equal(JSON.stringify(call.data),JSON.stringify({presentation:{layout:'left',theme:'midnight'},expected_character_id:'role-a'}));
 assert.ok(!JSON.stringify(call).includes('CANARY'));
});
test('unapplied drafts do not affect an explicitly opened output',async()=>{
 const h=harness(async path=>path.endsWith('/open')?{path:'/live-stage.html#fixture'}:{});
 h.storage.set('room-settings:role-a',JSON.stringify({config:{version:1,applied:false,characterId:'role-a',layout:'left',theme:'midnight'},draft:{applied:true,layout:'small',theme:'daylight'}}));
 await h.open('bili');await h.button('输出窗口').onclick();
 assert.equal(JSON.stringify(h.calls.find(c=>c.path.endsWith('/output/open')).data),JSON.stringify({expected_character_id:'role-a'}));
});
test('another preview identity is never silently published as the current output',async()=>{
 const h=harness();h.storage.set('room-settings:role-a',JSON.stringify({config:{version:1,applied:true,characterId:'role-b',layout:'left',theme:'midnight'}}));
 await h.open('bili');await h.button('输出窗口').onclick();assert.equal(h.calls.filter(c=>c.path.endsWith('/output/open')).length,0);
});

test('an applied hidden-caption design is rejected instead of silently hiding output',async()=>{
 const h=harness();h.storage.set('room-settings:role-a',JSON.stringify({config:{version:1,applied:true,characterId:'role-a',layout:'left',theme:'midnight',showCaption:false}}));
 await h.open('bili');await h.button('输出窗口').onclick();assert.equal(h.calls.filter(c=>c.path.endsWith('/output/open')).length,0);
});

test('preparation opens the existing rehearsal page immediately and stop remains usable before ready',async()=>{
 const waiting=deferred();let snapshot={bili:{state:'not_connected'},preparation:{state:'not_ready',revision:0}};
 const h=harness(async(path,data)=>{if(path.endsWith('/rehearsal')){snapshot={bili:{state:'local_preparing'},preparation:{state:'preparing',revision:1}};return waiting.promise;}if(path.endsWith('/stop')){snapshot={bili:{state:'not_connected'},preparation:{state:'cancelled',revision:2}};return {};}return snapshot;});
 await h.open();const starting=h.button('本地互动演练').onclick();assert.ok(h.button('结束演练'));assert.equal(h.field('模拟观众消息').disabled,true);
 await h.button('加入演练').onclick();assert.equal(h.calls.filter(c=>c.data?.action==='message').length,0);
 await h.button('结束演练').onclick();assert.ok(h.calls.some(c=>c.path==='connectors/bili/stop'));
 const reads=h.calls.filter(c=>c.path==='connectors/status').length;waiting.resolve({started:true});await starting;
 assert.equal(h.calls.filter(c=>c.path==='connectors/status').length,reads);assert.ok(h.button('本地演练'));assert.equal(h.field('模拟观众消息'),undefined);
});
test('old start result and finally cannot enable or replace a newer attempt after stop',async()=>{
 const old=deferred(),fresh=deferred();let starts=0,snapshot={bili:{state:'not_connected'},preparation:{state:'not_ready',revision:0}};
 const h=harness(async(path,data)=>{if(path.endsWith('/rehearsal')){starts++;snapshot={bili:{state:'local_preparing'},preparation:{state:'preparing',revision:starts*3}};return starts===1?old.promise:fresh.promise;}if(path.endsWith('/stop')){snapshot={bili:{state:'not_connected'},preparation:{state:'cancelled',revision:2}};return {};}return snapshot;});
 await h.open();const first=h.button('本地互动演练').onclick();await h.button('结束演练').onclick();const second=h.button('本地演练').onclick();
 old.resolve({started:true});await first;assert.equal(h.field('模拟观众消息').disabled,true);assert.equal(h.button('重新准备').disabled,true);assert.ok(h.nodes().some(n=>n.textContent==='正在准备演练'));
 snapshot={bili:{state:'local_rehearsal'},preparation:{state:'ready',revision:7,capabilities:{kind:'local_default',prefix_qualification:'prepared'}}};fresh.resolve({started:true});await second;
 assert.equal(h.field('模拟观众消息').disabled,false);assert.equal(h.button('加入演练').disabled,false);assert.equal(starts,2);
});
test('existing owner refresh updates readiness in place, preserving unsent message and ignoring old revision',async()=>{
 const base={bili:{state:'local_preparing'},preparation:{state:'preparing',revision:1},live_output:{session:'preparing',revision:1,jobs:[]}};
 const h=harness(async()=>base);await h.open('bili');const input=h.field('模拟观众消息');input.value='UNSENT_MUST_REMAIN';assert.equal(input.disabled,true);
 h.emit('change',{state:{public_preparation:{state:'ready',revision:2,capabilities:{kind:'configured_api',prefix_qualification:'not_applicable'}}}});
 assert.equal(h.field('模拟观众消息'),input);assert.equal(input.value,'UNSENT_MUST_REMAIN');assert.equal(input.disabled,false);assert.ok(h.nodes().some(n=>n.textContent==='本地演练 · API 服务未验证'));
 h.emit('change',{state:{public_preparation:base.preparation}});assert.equal(input.disabled,false);
 h.emit('change',{state:{public_preparation:{state:'cancelled',revision:3,reason:'configuration_changed'}}});assert.equal(input.disabled,true);assert.equal(input.value,'UNSENT_MUST_REMAIN');assert.equal(h.button('重新准备').hidden,false);
 assert.equal(h.calls.filter(c=>c.data).length,0);assert.equal(h.calls.length,1);
});
test('context retry preserves unsent message and uses prepare without resetting public material',async()=>{
 let snapshot={bili:{state:'local_rehearsal'},preparation:{state:'ready',revision:1},live_output:{session:'s',revision:1,jobs:[],material:{text:'APPROVED_MATERIAL'}}};
 const h=harness(async(path,data)=>{if(path.endsWith('/context')){snapshot={...snapshot,preparation:{state:'cancelled',revision:2}};return {};}if(path.endsWith('/rehearsal')){assert.equal(data.action,'prepare');snapshot={...snapshot,preparation:{state:'ready',revision:4}};return {};}return snapshot;});
 await h.open('bili');h.field('模拟观众消息').value='UNSENT_DRAFT';h.field('本场公开背景').value='Applied context';h.field('允许将背景用于公开回复').checked=true;
 await h.button('应用现场设置').onclick();assert.equal(h.field('模拟观众消息').value,'UNSENT_DRAFT');assert.equal(h.field('模拟观众消息').disabled,true);
 await h.button('重新准备').onclick();assert.equal(h.field('模拟观众消息').value,'UNSENT_DRAFT');assert.equal(h.field('本场公开教材').value,'APPROVED_MATERIAL');assert.equal(h.field('模拟观众消息').disabled,false);
});

test('restart cannot overtake an in-flight stop and no late stop response refreshes another attempt',async()=>{
 const stop=deferred();let snapshot={bili:{state:'local_rehearsal'},preparation:{state:'ready',revision:1}};
 const h=harness(async(path,data)=>{if(path.endsWith('/stop'))return stop.promise;if(path.endsWith('/rehearsal'))throw Error('must not restart before stop settles');return snapshot;});
 await h.open('bili');const stopping=h.button('结束演练').onclick();assert.equal(h.button('重新准备').disabled,true);
 await h.button('重新准备').onclick();assert.equal(h.calls.filter(c=>c.path.endsWith('/rehearsal')).length,0);
 snapshot={bili:{state:'not_connected'},preparation:{state:'cancelled',revision:2}};stop.resolve({});await stopping;assert.equal(h.button('本地演练').disabled,false);
});
