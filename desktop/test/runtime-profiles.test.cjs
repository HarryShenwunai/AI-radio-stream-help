'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {backendDirectory,selectRuntimeProfile,saveRuntimeProfile}=require('../runtime-profiles.cjs');
test('runtime selection is CPU by default and never accepts arbitrary paths',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'companion-profiles-'));
 try{assert.equal(selectRuntimeProfile(dir).profile,'cpu');assert.throws(()=>backendDirectory(dir,'../../outside'));saveRuntimeProfile(dir,'cpu');assert.equal(selectRuntimeProfile(dir).profile,'cpu');}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('CUDA profiles must match the CPU application source and interpreter',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'companion-profiles-'));
 try{
  for(const profile of ['cpu','cuda']){const root=backendDirectory(dir,profile);fs.mkdirSync(root,{recursive:true});fs.writeFileSync(path.join(root,'runtime-profile-manifest.json'),JSON.stringify({source_id:'a'.repeat(64),python_version:'3.12.16'}));}
  saveRuntimeProfile(dir,'cuda');assert.equal(selectRuntimeProfile(dir).profile,'cuda');
  fs.writeFileSync(path.join(backendDirectory(dir,'cuda'),'runtime-profile-manifest.json'),JSON.stringify({source_id:'b'.repeat(64),python_version:'3.12.16'}));
  const state=selectRuntimeProfile(dir);assert.equal(state.profile,'cpu');assert.ok(state.fallback);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
