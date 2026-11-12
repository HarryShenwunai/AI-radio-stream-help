// Original adapter mapping tests only. No proprietary Core/framework is loaded.
import assert from 'node:assert/strict';
import test from 'node:test';
import {rewriteModel,create,checkMocVersion} from '../frontend/live2d-renderer.mjs';
globalThis.window={location:{href:'http://127.0.0.1:4444/',origin:'http://127.0.0.1:4444'}};
const id='asset-fixture',url=name=>`/api/assets/${id}/${name}?character_id=role-A`;
function asset(){return {id,model:{url:url('model.model3.json')},resources:Object.fromEntries(['r0001.moc3','r0002.png','r0003.motion3.json','r0004.exp3.json','r0005.physics3.json'].map(name=>[name,{url:url(name)}]))};}
function model(){return {Version:3,FileReferences:{Moc:'r0001.moc3',Textures:['r0002.png'],Physics:'r0005.physics3.json',Expressions:[{Name:'gentle',File:'r0004.exp3.json'}],Motions:{Idle:[{File:'r0003.motion3.json'}]}}};}
test('every model3 resource retains its authenticated character scope',()=>{
 const original=model(),rewritten=rewriteModel(original,asset());for(const item of [rewritten.FileReferences.Moc,...rewritten.FileReferences.Textures,rewritten.FileReferences.Physics,rewritten.FileReferences.Expressions[0].File,rewritten.FileReferences.Motions.Idle[0].File])assert.match(item,/^http:\/\/127\.0\.0\.1:4444\/api\/assets\/asset-fixture\/.*\?character_id=role-A$/);
 assert.equal(original.FileReferences.Moc,'r0001.moc3');assert.match(rewritten.url,/character_id=role-A$/);
});
test('unmapped paths and external resources are rejected before invoking any runtime',()=>{
 for(const path of ['../other.moc3','https://example.com/a.moc3','data:application/octet-stream,AA','evil.js']){const value=model();value.FileReferences.Moc=path;assert.throws(()=>rewriteModel(value,asset()),/安全检查/);}
 const item=asset();item.resources['r0001.moc3'].url='https://example.com/model.moc3';assert.throws(()=>rewriteModel(model(),item),/本机/);
});
test('model-authored audio never acquires another playback owner',()=>{
 const value=model();value.FileReferences.Motions.Idle[0].Sound='r0006.wav';assert.throws(()=>rewriteModel(value,asset()),/自带音频/);
});
test('an absent owner-installed Core/framework fails closed before WebGL creation',()=>{
 assert.throws(()=>create({container:{}}),/尚未安装/);
});
test('same-origin resources cannot cross asset or role boundaries',()=>{
 for(const replacement of ['/api/assets/other/r0001.moc3?character_id=role-A','/api/assets/asset-fixture/r0001.moc3?character_id=role-B']){const item=asset();item.resources['r0001.moc3'].url=replacement;assert.throws(()=>rewriteModel(model(),item),/当前运行包/);}
});

test('observed Core maximum rejects newer MOC before GPU allocation',()=>{
 const core={Version:{csmGetLatestMocVersion:()=>5}};assert.throws(()=>checkMocVersion({moc3_version:{code:6}},core),/当前最高支持 MOC 5/);for(const code of [1,2,3,4,5])assert.doesNotThrow(()=>checkMocVersion({moc3_version:{code}},core));
});
