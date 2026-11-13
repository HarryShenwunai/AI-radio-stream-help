'use strict';
const { test }=require('node:test'); const assert=require('node:assert/strict');
const {normalizeBackendURL,trustedNavigation,validateCommand,compactBounds,expandedBounds,restoreOutputBounds}=require('../window-policy.cjs');
test('only explicit local backend origins are accepted',()=>{
 assert.equal(normalizeBackendURL('http://127.0.0.1:8765'),'http://127.0.0.1:8765/');
 for(const value of ['https://127.0.0.1:8765','http://example.com:8765','file:///etc/passwd','http://u:p@localhost:8765','http://localhost','http://localhost:8765/other','http://localhost:8765/?key=x'])assert.throws(()=>normalizeBackendURL(value));
});
test('returning from display output preserves visible bounds after monitor removal or resolution changes',()=>{
 for(const area of [{x:0,y:0,width:1920,height:1080},{x:-900,y:30,width:240,height:300}]){
  const saved={x:2100,y:-800,width:1120,height:850};const restored=restoreOutputBounds(saved,area);
  assert.ok(restored.x>=area.x&&restored.y>=area.y);assert.ok(restored.x+restored.width<=area.x+area.width);
  assert.ok(restored.y+restored.height<=area.y+area.height);
 }
 assert.deepEqual(restoreOutputBounds({x:20,y:30,width:330,height:470},{x:0,y:0,width:1920,height:1080}),{x:20,y:30,width:330,height:470});
});
test('navigation never leaves the paired page',()=>{
 const base='http://127.0.0.1:8765/';assert.equal(trustedNavigation(base,base),true);assert.equal(trustedNavigation(base+'index.html#chat',base),true);
 for(const value of ['http://127.0.0.1:8766/','http://localhost:8765/','https://evil.invalid/','file:///etc/passwd',base+'api/export'])assert.equal(trustedNavigation(value,base),false);
});
test('bridge payload is typed and cannot invoke arbitrary host methods',()=>{
 assert.equal(validateCommand('set-expanded',true),true);assert.equal(validateCommand('quit'),undefined);
 for(const [key,value]of [['set-expanded','true'],['set-click-through',1],['quit','payload'],['shell','rm']])assert.throws(()=>validateCommand(key,value));
});
test('compact and expanded bounds stay inside normal and small monitors',()=>{
 for(const area of [{x:0,y:0,width:1920,height:1080},{x:-900,y:30,width:240,height:300}])for(const bound of [compactBounds(area),expandedBounds(area)]){
  assert.ok(bound.x>=area.x);assert.ok(bound.y>=area.y);assert.ok(bound.x+bound.width<=area.x+area.width);assert.ok(bound.y+bound.height<=area.y+area.height);
 }
});
