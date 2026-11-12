'use strict';
const fs=require('node:fs');const path=require('node:path');
function readJSON(file){if(!fs.existsSync(file))return null;if(fs.statSync(file).size>64*1024)throw new Error('Runtime profile metadata exceeds limit');return JSON.parse(fs.readFileSync(file,'utf8'));}
function backendDirectory(resources,profile){if(!['cpu','cuda'].includes(profile))throw new Error('Unsupported runtime profile');return profile==='cpu'?path.join(resources,'backend'):path.join(resources,'backend-profiles','cuda');}
function selectRuntimeProfile(resources){
 let selection;
 try{selection=readJSON(path.join(resources,'active-runtime-profile.json'))||{profile:'cpu'};}
 catch{return {profile:'cpu',fallback:'运行时配置损坏，已使用CPU。'};}
 if(selection.profile!=='cuda')return {profile:'cpu',fallback:typeof selection.fallback==='string'?selection.fallback.slice(0,256):null};
 let cpu,cuda;
 try{cpu=readJSON(path.join(backendDirectory(resources,'cpu'),'runtime-profile-manifest.json'));cuda=readJSON(path.join(backendDirectory(resources,'cuda'),'runtime-profile-manifest.json'));}
 catch{return {profile:'cpu',fallback:'CUDA配置元数据损坏，已使用CPU。'};}
 if(!cpu||!cuda||cpu.source_id!==cuda.source_id||cpu.python_version!==cuda.python_version||!/^[a-f0-9]{64}$/.test(cpu.source_id))return {profile:'cpu',fallback:'CUDA配置缺失或与当前程序版本不同，已使用CPU。'};
 return {profile:'cuda',fallback:null};
}
function saveRuntimeProfile(resources,profile,fallback=null){
 backendDirectory(resources,profile);
 const file=path.join(resources,'active-runtime-profile.json'),temporary=file+'.'+process.pid+'.tmp';
 fs.writeFileSync(temporary,JSON.stringify({profile,fallback})+'\n',{mode:0o600});fs.renameSync(temporary,file);
}
module.exports={backendDirectory,selectRuntimeProfile,saveRuntimeProfile};
