import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url), D=require('../app/static/room-design.js');
test('old settings migrate to the existing picture and retain false switches',()=>{
 assert.deepEqual(D.normalize(),{layout:'right',theme:'paper',characterId:'',showTopic:true,showQuestion:true,showCaption:true,showTimer:true});
 assert.equal(D.normalize({showTopic:false}).showTopic,false);
});
test('invalid presentation cannot inject CSS or private content into saved designs',()=>{
 const d=D.normalize({theme:'url(https://bad)',layout:'other',characterId:'../../private',caption:'PRIVATE',api_key:'PRIVATE',showTimer:'false'});
 assert.equal(d.theme,'paper');assert.equal(d.layout,'right');assert.equal(d.characterId,'');assert.equal(d.showTimer,true);assert.ok(!JSON.stringify(d).includes('PRIVATE'));
});
test('saved designs are bounded, deduplicated and exclude dialogue and timer state',()=>{
 const inputs=Array.from({length:20},(_,i)=>({name:String(i),design:{layout:'left',theme:'slate',topic:'PRIVATE',focus:{phase:'running'}}}));
 const saved=D.presets(inputs);assert.equal(saved.length,12);assert.ok(!JSON.stringify(saved).includes('PRIVATE'));assert.ok(!JSON.stringify(saved).includes('running'));
 assert.equal(D.presets([{name:'A',design:{}},{name:'A',design:{theme:'forest'}},{name:'',design:{}}]).length,1);
 assert.deepEqual(D.presets({}),[]);assert.deepEqual(D.presets(null),[]);
});
