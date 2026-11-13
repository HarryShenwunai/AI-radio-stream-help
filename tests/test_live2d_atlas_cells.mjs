import test from 'node:test';
import assert from 'node:assert/strict';
import {atlasCell,assertTransparentCellEdges} from '../scripts/live2d_atlas_cells.mjs';

test('explicit gutters isolate unevenly spaced eye sprites',()=>{
 assert.deepEqual(atlasCell({width:1024,height:1536,col:0,row:2,cols:2,rows:5,yBounds:[0,350,685,960,1230,1536]}),{left:0,top:685,width:512,height:275});
 assert.equal(atlasCell({width:1024,height:1536,col:0,row:2,cols:2,rows:5}).top,614);
});
test('an old grid cut through an iris is rejected before layer resizing',()=>{
 const data=Buffer.alloc(8*6*4);for(let x=2;x<6;x++)data[x*4+3]=252;
 assert.throws(()=>assertTransparentCellEdges(data,{width:8,height:6,channels:4},'upper eyelash'),/cuts visible artwork.*top/);
});
test('a complete sprite with transparent gutters and low alpha noise is retained',()=>{
 const data=Buffer.alloc(8*6*4);for(let i=3;i<data.length;i+=4)data[i]=2;
 for(let y=1;y<5;y++)for(let x=1;x<7;x++)data[(y*8+x)*4+3]=253;
 assert.deepEqual(assertTransparentCellEdges(data,{width:8,height:6,channels:4},'iris').visible_boundary_pixels,{top:0,bottom:0,left:0,right:0});
});
for(const [edge,x,y]of [['top',2,0],['bottom',2,5],['left',0,2],['right',7,2]])test('visible '+edge+' crop is refused at the exact alpha threshold',()=>{
 const data=Buffer.alloc(8*6*4);data[(y*8+x)*4+3]=8;
 assert.throws(()=>assertTransparentCellEdges(data,{width:8,height:6,channels:4},edge),/cuts visible artwork/);
});
test('invalid or incomplete atlas partitions fail',()=>{
 const base={width:1024,height:1536,col:0,row:2,cols:2,rows:5};
 for(const yBounds of [[0,350,685,960,1230],[1,350,685,960,1230,1536],[0,350,350,960,1230,1536],[0,350,685.5,960,1230,1536]])assert.throws(()=>atlasCell({...base,yBounds}),/boundaries/);
 assert.throws(()=>atlasCell({...base,col:2}),/outside/);
});
test('non-RGBA, truncated buffers and invalid threshold fail',()=>{
 for(const [data,info,options]of [[Buffer.alloc(4),{width:8,height:6,channels:4},{}],[Buffer.alloc(144),{width:8,height:6,channels:3},{}],[Buffer.alloc(192),{width:8,height:6,channels:4},{threshold:0}]])assert.throws(()=>assertTransparentCellEdges(data,info,'invalid',options),/RGBA/);
});
