import test from 'node:test';
import assert from 'node:assert/strict';
import { bindCurrentWorldTransform } from '../frontend/live2d-renderer.mjs';
function fixture(parent=null){
 const cached={a:1,b:0,c:0,d:1,tx:0,ty:0};let allocations=0,calls=0;
 const prototype={get worldTransform(){return cached;}};
 const model=Object.assign(Object.create(prototype),{parent,x:360,y:438,sx:.633245382585752,sy:.633245382585752,px:568.5,py:691.5,
  getGlobalTransform(out,skip){assert.equal(this,model);assert.equal(skip,false);calls++;if(!out){out={};allocations++;}let a=this.sx,d=this.sy,tx=this.x-this.px*a,ty=this.y-this.py*d;
   for(let p=this.parent;p;p=p.parent){tx=p.x+p.sx*tx;ty=p.y+p.sy*ty;a*=p.sx;d*=p.sy;}
   Object.assign(out,{a,b:0,c:0,d,tx,ty});return out;}});
 return {model,cached,get allocations(){return allocations;},get calls(){return calls;}};
}
test('cached first frame is a counterexample; public current transform fixes it without a render warmup',()=>{
 const f=fixture();assert.notEqual(f.model.worldTransform.a,f.model.sx);
 const restore=bindCurrentWorldTransform(f.model),first=f.model.worldTransform,second=f.model.worldTransform;
 assert.equal(first,second);assert.equal(first.a,f.model.sx);assert.equal(first.tx,f.model.x-f.model.px*f.model.sx);assert.equal(f.allocations,1);
 restore();assert.equal(Object.hasOwn(f.model,'worldTransform'),false);assert.equal(f.model.worldTransform,f.cached);
});
test('nested parents, resize/scale and parent motion are current before the next render',()=>{
 const parent={x:11,y:7,sx:2,sy:3,parent:{x:5,y:9,sx:.5,sy:2}},f=fixture(parent);const restore=bindCurrentWorldTransform(f.model);
 assert.equal(f.model.worldTransform.a,f.model.sx);assert.equal(f.model.worldTransform.d,f.model.sy*6);
 f.model.sx=.8;f.model.x=200;parent.x=35;const m=f.model.worldTransform;
 assert.equal(m.tx,5+.5*(35+2*(200-568.5*.8)));assert.equal(m.a,.8);assert.equal(f.allocations,1);restore();
});
test('restores an existing configurable own descriptor; incompatible and recursive APIs fail explicitly',()=>{
 const f=fixture(),old={value:f.cached,writable:true,enumerable:true,configurable:true};Object.defineProperty(f.model,'worldTransform',old);const restore=bindCurrentWorldTransform(f.model);restore();assert.deepEqual(Object.getOwnPropertyDescriptor(f.model,'worldTransform'),old);
 assert.throws(()=>bindCurrentWorldTransform({}),/不兼容/);
 const bad=fixture();bad.model.getGlobalTransform=()=>({});assert.throws(()=>bindCurrentWorldTransform(bad.model),/不兼容/);
 const recursive=fixture();recursive.model.getGlobalTransform=function(out){return out?this.worldTransform:this.worldTransform;};const undo=bindCurrentWorldTransform(recursive.model);assert.throws(()=>recursive.model.worldTransform,/递归/);undo();
});
