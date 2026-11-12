'use strict';
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const version=require('./node_modules/electron/package.json').version;
const checksums=require('./node_modules/electron/checksums.json');
const name=`electron-v${version}-win32-x64.zip`;
const output=path.resolve(process.argv.find(a=>a.startsWith('--output='))?.slice(9)||path.join(__dirname,'..','.build','windows-electron'));
(async()=>{
 if(fs.existsSync(output)&&fs.readdirSync(output).length)throw new Error('Output must be a new or empty directory');
 const {downloadArtifact}=await import('@electron/get');
 const archive=await downloadArtifact({version,platform:'win32',arch:'x64',artifactName:'electron',checksums,cacheRoot:process.env.electron_config_cache});
 const observed=crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex');
 if(observed!==checksums[name])throw new Error('Official Electron archive checksum mismatch');
 fs.mkdirSync(output,{recursive:true});
 const {extract}=require('@electron-internal/extract-zip');await extract(archive,{dir:output});
 const {assertWindowsX64PE}=require('./windows-artifact.cjs');assertWindowsX64PE(path.join(output,'electron.exe'));
 const record={source:`https://github.com/electron/electron/releases/download/v${version}/${name}`,version,platform:'win32',arch:'x64',sha256_expected:checksums[name],sha256_observed:observed,verified:true,executed:false};
 fs.writeFileSync(path.join(output,'artifact-provenance.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({output,...record}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
