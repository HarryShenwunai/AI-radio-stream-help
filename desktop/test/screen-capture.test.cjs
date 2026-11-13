'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { createScreenCaptureManager } = require('../screen-capture.cjs');
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture() {
  const owner = new EventEmitter(); owner.isDestroyed = () => false; owner.isVisible = () => true;
  const menus = [], children = [], calls = []; let time = 1000;
  let sources = [{ id: 'screen:0:0', name: 'Display 1' }, { id: 'window:12:0', name: 'Notes' }];
  class Child extends EventEmitter {
    constructor(options) {
      super();this.options=options;this.destroyed=false;children.push(this);
      const contents=this.webContents=new EventEmitter();contents.mainFrame={url:''};contents.isDestroyed=()=>this.destroyed;
      contents.setWindowOpenHandler=handler=>{contents.open=handler;};
      contents.executeJavaScript=async code=>{calls.push(code);return this.frameValue || {state:'awaiting_user'};};
      contents.session={
        webRequest:{onBeforeRequest(handler){this.before=handler;}},
        setPermissionCheckHandler(handler){this.check=handler;},setPermissionRequestHandler(handler){this.permission=handler;},
        setDisplayMediaRequestHandler(handler){this.display=handler;},
      };
    }
    isDestroyed(){return this.destroyed;}
    async loadFile(file){this.webContents.mainFrame.url=require('node:url').pathToFileURL(file).href;}
    show(){this.shown=true;}
    destroy(){this.destroyed=true;this.emit('closed');}
  }
  const Menu={buildFromTemplate(template){const menu={template,popup(value){this.popupOptions=value;},closePopup(){},
    select(group=2,index=0){template[group].submenu[index].click();this.popupOptions.callback();},cancel(){this.popupOptions.callback();}};menus.push(menu);return menu;}};
  const desktopCapturer={async getSources(options){calls.push(options);return typeof sources==='function'?sources():sources;}};
  const manager=createScreenCaptureManager({getOwner:()=>owner,BrowserWindow:Child,desktopCapturer,Menu,now:()=>time,lifetimeMs:10000});
  return {owner,menus,children,calls,manager,advance(ms){time+=ms;},sources(value){sources=value;},
    async start(){const job=manager.start();await flush();menus.at(-1).select();return job;},
  };
}
test('native source selection creates a separate sandboxed local window without starting capture',async()=>{
  const f=fixture(), result=await f.start(), child=f.children[0];
  assert.equal(result.state,'awaiting_user');assert.equal(child.shown,true);assert.equal(f.calls.some(value=>typeof value==='string'),false);
  assert.equal(child.options.webPreferences.nodeIntegration,false);assert.equal(child.options.webPreferences.sandbox,true);
  assert.equal(child.options.webPreferences.devTools,false);assert.equal(child.options.webPreferences.partition,'capture-'+result.capture_id);
  assert.deepEqual(await f.manager.frame(result.capture_id),{capture_id:result.capture_id,state:'awaiting_user'});
  f.manager.stopAll();
});
test('isolated capture grants only its exact packaged main frame, video-only and actual chosen source',async()=>{
  const f=fixture();const result=await f.start(), child=f.children[0], contents=child.webContents, session=contents.session;
  const details={isMainFrame:true,requestingUrl:contents.mainFrame.url,mediaTypes:['video']};
  const permission=(sender,key,value)=>new Promise(resolve=>session.permission(sender,key,resolve,value));
  assert.equal(await permission(contents,'display-capture',details),true);
  for(const [sender,key,value]of [[{},'display-capture',details],[contents,'media',details],[contents,'display-capture',{...details,isMainFrame:false}],
    [contents,'display-capture',{...details,requestingUrl:'http://127.0.0.1:8765/'}],[contents,'display-capture',{...details,mediaTypes:['video','audio']}]] ) assert.equal(await permission(sender,key,value),false);
  const request={frame:contents.mainFrame,userGesture:true,videoRequested:true,audioRequested:false};
  const display=value=>new Promise(resolve=>session.display(value,resolve));
  assert.equal(await display({...request,userGesture:false}),null);
  assert.equal(await display({...request,audioRequested:true}),null);
  const granted=await display(request);assert.equal(granted.video.id,'screen:0:0');assert.equal(granted.audio,undefined);
  assert.equal(await display(request),null);f.manager.stop(result.capture_id);
});
test('dedicated window blocks network, arbitrary local files, popups and subframe navigation',async()=>{
  const f=fixture(), result=await f.start(), child=f.children[0], contents=child.webContents;
  const allowed=url=>new Promise(resolve=>contents.session.webRequest.before({url},value=>resolve(!value.cancel)));
  assert.equal(await allowed(contents.mainFrame.url),true);
  for(const url of ['https://evil.invalid/a.js','file:///etc/passwd','file:///tmp/screen-capture.html','data:text/html,evil'])assert.equal(await allowed(url),false);
  assert.deepEqual(contents.open(),{action:'deny'});let prevented=false;
  contents.emit('will-navigate',{preventDefault(){prevented=true;}},'https://evil.invalid');assert.equal(prevented,true);f.manager.stop(result.capture_id);
});
test('returned frames are bounded, single-inflight and never issued to a stale capture id',async()=>{
  const f=fixture(), result=await f.start(), child=f.children[0];
  child.frameValue={state:'active',image_base64:'QUJD',width:1280,height:720};
  const frame=await f.manager.frame(result.capture_id);assert.equal(frame.processing,'local');assert.equal(frame.retained,false);
  await assert.rejects(f.manager.frame(result.capture_id),/过快/);f.advance(600);
  child.frameValue={state:'active',image_base64:'QUJD',width:4000,height:720};await assert.rejects(f.manager.frame(result.capture_id),/无效/);
  assert.deepEqual(await f.manager.frame('stale'),{capture_id:'stale',state:'stopped'});f.manager.stop(result.capture_id);
});
test('hiding the main owner destroys its capture owner and invalidates frames',async()=>{
  const f=fixture(), result=await f.start(), child=f.children[0];f.owner.emit('hide');
  assert.equal(child.isDestroyed(),true);assert.equal((await f.manager.frame(result.capture_id)).state,'stopped');
});
test('minimizing either owner or hiding the local capture preview stops capture',async()=>{
  for(const [target,event]of [['owner','minimize'],['child','hide'],['child','minimize']]){
    const f=fixture(),result=await f.start(),child=f.children[0];(target==='owner'?f.owner:child).emit(event);
    assert.equal(child.isDestroyed(),true);assert.equal((await f.manager.frame(result.capture_id)).state,'stopped');
  }
});
test('late stop from an older capture cannot stop the new owner',async()=>{
  const f=fixture(), first=await f.start();f.manager.stop(first.capture_id);
  const second=await f.start();assert.equal(f.manager.stop(first.capture_id).stopped,true);
  assert.equal(f.children[1].isDestroyed(),false);assert.equal((await f.manager.frame(second.capture_id)).state,'awaiting_user');
  f.manager.stop(second.capture_id);
});
test('cancel and disappearing source cannot fall back to the first display',async()=>{
  const f=fixture();const pending=f.manager.start();await flush();f.menus[0].cancel();await assert.rejects(pending,/取消/);assert.equal(f.children.length,0);
  const gone=f.manager.start();await flush();f.sources([{id:'screen:99:0',name:'Other display'}]);f.menus[1].select();await assert.rejects(gone,/取消/);assert.equal(f.children.length,0);
});
test('single active capture prevents duplicate render owners',async()=>{
  const f=fixture(), result=await f.start();await assert.rejects(f.manager.start(),/先关闭/);assert.equal(f.children.length,1);f.manager.stop(result.capture_id);
});
