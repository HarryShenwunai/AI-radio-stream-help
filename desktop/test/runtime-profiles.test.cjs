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

test('owned backend receives early telemetry opt-out without changing parent environment',()=>{
 const vm=require('node:vm');
 const source=fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8');
 const body=source.slice(source.indexOf('function backendEnvironment() {'),source.indexOf('async function startBackend() {'));
 assert.ok(body.startsWith('function backendEnvironment() {'));
 for(const profile of ['cpu','cuda'])for(const packaged of [false,true])for(const inherited of ['0',undefined]){
  const environment={KEEP:'preserved',CUDA_PATH:'user-cuda',COMPANION_VOICES:'/configured/voices'};
  if(inherited!==undefined)environment.ORT_DISABLE_TELEMETRY=inherited;
  const context={process:{env:environment,execPath:'/app/companion',resourcesPath:'/resources'},
   runtimeSelection:{profile,fallback:null},app:{isPackaged:packaged,getPath:()=>'/user-data'},
   fs:{existsSync:()=>false},path};
  const result=vm.runInNewContext(body+';backendEnvironment()',context);
  assert.equal(result.ORT_DISABLE_TELEMETRY,'1');assert.equal(result.KEEP,'preserved');
  assert.equal(result.COMPANION_VOICES,'/configured/voices');assert.equal(result.COMPANION_RUNTIME_PROFILE,profile);
  assert.equal(environment.ORT_DISABLE_TELEMETRY,inherited);assert.equal(environment.CUDA_PATH,'user-cuda');
  assert.equal(result.CUDA_PATH,packaged?undefined:'user-cuda');
 }
});
