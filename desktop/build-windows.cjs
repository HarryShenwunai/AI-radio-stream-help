'use strict';
const fs=require('node:fs');const path=require('node:path');
const {assertWindowsX64PE}=require('./windows-artifact.cjs');
const arg=name=>process.argv.find(value=>value.startsWith(name+'='))?.slice(name.length+1);
const linkImmutable=process.argv.includes('--link-immutable');
function copyTree(source,target){
 const info=fs.lstatSync(source);if(info.isSymbolicLink())throw new Error('Do not package external symbolic links');
 if(info.isDirectory()){fs.mkdirSync(target,{recursive:true});for(const name of fs.readdirSync(source))copyTree(path.join(source,name),path.join(target,name));return;}
 fs.mkdirSync(path.dirname(target),{recursive:true});
 if(linkImmutable&&/\.(dll|pyd|exe|lib|gguf|onnx|bin)$/i.test(source)){try{fs.linkSync(source,target);return;}catch(error){if(!['EXDEV','EPERM','EACCES','ENOTSUP'].includes(error.code))throw error;}}
 fs.copyFileSync(source,target);
}
const native=arg('--backend'),embedded=arg('--embedded-backend');
if(Boolean(native)===Boolean(embedded))throw new Error('Choose exactly one --backend=Windows-PyInstaller-dir or --embedded-backend=Windows-embedded-dir');
const backend=path.resolve(native||embedded);
if(native)assertWindowsX64PE(path.join(backend,'companion-backend.exe'));
else {
 assertWindowsX64PE(path.join(backend,'python','python.exe'));
 for(const required of ['app/server.py','src/companion_runtime'])if(!fs.existsSync(path.join(backend,required)))throw new Error('Embedded backend missing '+required);
 if(!fs.readdirSync(path.join(backend,'python')).some(file=>/^python3\d+\._pth$/.test(file)))throw new Error('Embedded Python requires an isolated python3xx._pth');
}
const output=path.resolve(arg('--output')||path.join(__dirname,'..','.build','desktop','character-windows-x64'));
if(fs.existsSync(output)&&fs.readdirSync(output).length)throw new Error('Output must be a new or empty directory');
const electron=path.resolve(arg('--electron-dist')||path.join(__dirname,'node_modules','electron','dist'));
assertWindowsX64PE(path.join(electron,'electron.exe'));
const version=require('./package.json').devDependencies.electron;
if(!/^\d+\.\d+\.\d+$/.test(version))throw new Error('Electron must be pinned to an exact release in desktop/package.json');
if(fs.readFileSync(path.join(electron,'version'),'utf8').trim().replace(/^v/,'')!==version)throw new Error('Electron dist version does not match pinned dependency');
for(const file of ['LICENSE','LICENSES.chromium.html','resources/default_app.asar'])if(!fs.existsSync(path.join(electron,file)))throw new Error('Incomplete Electron dist: '+file);
fs.mkdirSync(output,{recursive:true});copyTree(electron,output);fs.renameSync(path.join(output,'electron.exe'),path.join(output,'companion-desktop.exe'));
const appDir=path.join(output,'resources','app');fs.mkdirSync(appDir,{recursive:true});
for(const file of ['main.cjs','preload.cjs','window-policy.cjs','runtime-profiles.cjs','media-policy.cjs','screen-capture.cjs','screen-capture.html','screen-capture-view.js','screen-capture.css','owner-runtime-path.cjs','switch_runtime_profile.py','icon.png'])fs.copyFileSync(path.join(__dirname,file),path.join(appDir,file));
fs.writeFileSync(path.join(appDir,'package.json'),JSON.stringify({name:'companion-desktop-runtime',version:require('./package.json').version,main:'main.cjs',license:'GPL-3.0'},null,2)+'\n');
copyTree(backend,path.join(output,'resources','backend'));
const cudaSource=arg('--cuda-backend');
if(cudaSource){
 const cuda=path.resolve(cudaSource);assertWindowsX64PE(path.join(cuda,'python','python.exe'));
 const cpuManifest=JSON.parse(fs.readFileSync(path.join(backend,'runtime-profile-manifest.json'),'utf8'));
 const cudaManifest=JSON.parse(fs.readFileSync(path.join(cuda,'runtime-profile-manifest.json'),'utf8'));
 if(cpuManifest.source_id!==cudaManifest.source_id||cpuManifest.python_version!==cudaManifest.python_version)throw new Error('CPU and CUDA profiles must use the same source snapshot and Python runtime');
 copyTree(cuda,path.join(output,'resources','backend-profiles','cuda'));
 fs.writeFileSync(path.join(output,'使用CUDA.cmd'),'@echo off\r\ncd /d "%~dp0"\r\n"%~dp0resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0resources\\app\\switch_runtime_profile.py" --profile cuda --launch\r\nif errorlevel 1 pause\r\n');
 fs.writeFileSync(path.join(output,'使用CPU.cmd'),'@echo off\r\ncd /d "%~dp0"\r\n"%~dp0resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0resources\\app\\switch_runtime_profile.py" --profile cpu --launch\r\nif errorlevel 1 pause\r\n');
}
fs.copyFileSync(path.join(__dirname,'..','app','LICENSE'),path.join(output,'COMPANION-LICENSE'));
fs.cpSync(path.join(__dirname,'..','app','licenses'),path.join(output,'licenses'),{recursive:true});
const distributionLicenses=path.join(backend,'licenses','distributions');
if(fs.existsSync(distributionLicenses))fs.cpSync(distributionLicenses,path.join(output,'licenses','distributions'),{recursive:true});
if(cudaSource){const cudaNotices=path.join(path.resolve(cudaSource),'licenses','distributions');if(fs.existsSync(cudaNotices))fs.cpSync(cudaNotices,path.join(output,'licenses','distributions'),{recursive:true});}
fs.copyFileSync(path.join(__dirname,'..','NOTICE.md'),path.join(output,'NOTICE.md'));
fs.copyFileSync(path.join(__dirname,'..','app','ATTRIBUTIONS.md'),path.join(output,'ATTRIBUTIONS.md'));
fs.writeFileSync(path.join(output,'start.cmd'),'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0companion-desktop.exe" %*\r\n');
fs.writeFileSync(path.join(output,'README.txt'),'\uFEFF二次元桌面陪伴 · Windows 10 / 11 x64\r\n\r\n1. 完整解压文件夹，双击 companion-desktop.exe 或 start.cmd。\r\n2. 点击“聊天”展开；打开“角色”创建自己的角色，上传有权使用的 PNG，预览后启用。默认头像只是占位。\r\n3. “收起”回到桌面一角；拖动顶部图标移动。“停声”停止声音与当前回复。\r\n4. Ctrl+Shift+Space 恢复角色和鼠标；“穿透”最长60秒自动恢复。\r\n5. 点击“退出”，或在托盘图标右键菜单选择“退出”，关闭应用与本机后端。\r\n\r\n完整包附带 models 与 voices 文件夹，可使用本地模型；精简包不含这些大文件，需要另行放入或在设置连接自己的模型 API。以压缩包清单为准。\r\n高级用户可用 COMPANION_MODELS / COMPANION_VOICES 指定已有资产，COMPANION_DATA 指定独立数据目录。\r\n此脚本只打包程序与后端，完整包的模型和声音由构建流水线另行加入。\r\nWindows 10/11 真机、多屏DPI、独占全屏与实际人声体验仍需验收。\r\n');
if(embedded){
 fs.appendFileSync(path.join(output,'README.txt'),'\r\n此嵌入运行时版本在Linux上组装，尚未完成真实Windows运行验收。依赖兼容限制见 resources/backend/BUILD-STATUS.txt 与 embedded-runtime-manifest.json。\r\n');
 const status=path.join(backend,'BUILD-STATUS.txt');if(fs.existsSync(status))fs.copyFileSync(status,path.join(output,'BUILD-STATUS.txt'));
}
console.log(JSON.stringify({output,backend_included:true,backend_kind:embedded?'embedded-python':'pyinstaller',electron:version,models_included:false,target_platform:'win32',target_arch:'x64',assembly_host:process.platform,windows_execution_verified:false}));
