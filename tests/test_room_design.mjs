import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url), D=require('../app/static/room-design.js');
test('old settings migrate to the existing picture and retain false switches',()=>{
 assert.deepEqual(D.normalize(),{layout:'right',theme:'carbon',characterId:'',showTopic:true,showQuestion:true,showCaption:true,showTimer:true});
 assert.equal(D.normalize({showTopic:false}).showTopic,false);
});
test('invalid presentation cannot inject CSS or private content into saved designs',()=>{
 const d=D.normalize({theme:'url(https://bad)',layout:'other',characterId:'../../private',caption:'PRIVATE',api_key:'PRIVATE',showTimer:'false'});
 assert.equal(d.theme,'carbon');assert.equal(d.layout,'right');assert.equal(d.characterId,'');assert.equal(d.showTimer,true);assert.ok(!JSON.stringify(d).includes('PRIVATE'));
});
test('saved designs are bounded, deduplicated and exclude dialogue and timer state',()=>{
 const inputs=Array.from({length:20},(_,i)=>({name:String(i),design:{layout:'left',theme:'slate',topic:'PRIVATE',focus:{phase:'running'}}}));
 const saved=D.presets(inputs);assert.equal(saved.length,12);assert.ok(!JSON.stringify(saved).includes('PRIVATE'));assert.ok(!JSON.stringify(saved).includes('running'));
 assert.equal(D.presets([{name:'A',design:{}},{name:'A',design:{theme:'forest'}},{name:'',design:{}}]).length,1);
 assert.deepEqual(D.presets({}),[]);assert.deepEqual(D.presets(null),[]);
});

test('legacy designs migrate without discarding settings or false visibility',()=>{
 for(const [old,current] of [['paper','carbon'],['forest','midnight'],['slate','daylight']]){
  const d=D.normalize({theme:old,layout:'left',showCaption:false});assert.equal(d.theme,current);assert.equal(d.layout,'left');assert.equal(d.showCaption,false);
 }
});
function luminance(hex){const channels=hex.slice(1).match(/../g).map(c=>parseInt(c,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
test('all text tokens meet 4.5 against both gradient endpoints; bad muted text fails',()=>{
 for(const p of Object.values(D.palettes))for(const fg of ['foreground','muted'])for(const bg of ['background','ambient'])assert.ok(contrast(p[fg],p[bg])>=4.5,`${p.name} ${fg}/${bg}`);
 assert.ok(contrast('#64735f','#dedbd1')<4.5);
});
