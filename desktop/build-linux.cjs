'use strict';
const fs=require('node:fs');const path=require('node:path');const os=require('node:os');
if(process.platform!=='linux'||process.arch!=='x64')throw new Error('This builder is verified only on Linux x64');
const outputArg=process.argv.find(a=>a.startsWith('--output='));
const output=path.resolve(outputArg?outputArg.slice(9):path.join(__dirname,'..','..','dist','companion-desktop-linux-x64'));
const backendArg=process.argv.find(a=>a.startsWith('--backend='));
if(!backendArg&&!process.argv.includes('--host-only'))throw new Error('Provide --backend=/path/to/compiled/backend, or explicitly choose --host-only');
if(fs.existsSync(output)&&fs.readdirSync(output).length)throw new Error('Output must be a new or empty directory');
const electronDist=path.join(__dirname,'node_modules','electron','dist');
if(!fs.existsSync(path.join(electronDist,'electron')))throw new Error('Install the pinned Electron runtime first');
require('./build-focus.cjs');
fs.mkdirSync(output,{recursive:true});fs.cpSync(electronDist,output,{recursive:true});
fs.renameSync(path.join(output,'electron'),path.join(output,'companion-desktop'));
const appDir=path.join(output,'resources','app');fs.mkdirSync(appDir,{recursive:true});
for(const file of ['main.cjs','preload.cjs','window-policy.cjs','runtime-profiles.cjs','media-policy.cjs','screen-capture.cjs','screen-capture.html','screen-capture-view.js','screen-capture.css','icon.png','focus-x11'])fs.copyFileSync(path.join(__dirname,file),path.join(appDir,file));
fs.writeFileSync(path.join(appDir,'package.json'),JSON.stringify({name:'companion-desktop-runtime',version:require('./package.json').version,main:'main.cjs',license:'GPL-3.0'},null,2)+'\n');
if(backendArg){
 const source=path.resolve(backendArg.slice(10));
 if(!fs.existsSync(source))throw new Error('Compiled backend does not exist');
 const target=path.join(output,'resources','backend');fs.mkdirSync(target,{recursive:true});
 if(fs.statSync(source).isDirectory())fs.cpSync(source,target,{recursive:true});
 else{fs.copyFileSync(source,path.join(target,'companion-backend'));fs.chmodSync(path.join(target,'companion-backend'),0o755);}
}
fs.copyFileSync(path.join(__dirname,'..','app','LICENSE'),path.join(output,'COMPANION-LICENSE'));
fs.cpSync(path.join(__dirname,'..','app','licenses'),path.join(output,'licenses'),{recursive:true});
fs.copyFileSync(path.join(__dirname,'..','NOTICE.md'),path.join(output,'NOTICE.md'));
fs.copyFileSync(path.join(__dirname,'..','app','ATTRIBUTIONS.md'),path.join(output,'ATTRIBUTIONS.md'));
fs.writeFileSync(path.join(output,'start.sh'),'#!/bin/sh\nTASK_DESKTOP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$TASK_DESKTOP_DIR/companion-desktop" "$@"\n',{mode:0o755});
fs.writeFileSync(path.join(output,'README.txt'),'本机二次元陪伴桌面壳\n\n运行 ./start.sh。需要Linux图形桌面。\nCtrl+Shift+Space恢复角色/鼠标；穿透最长60秒会自动恢复。\n默认一个角色小窗，展开继续同一页面与会话。\n聊天模型与声音资产不随壳重复下载；可继承COMPANION_MODELS/COMPANION_VOICES。\n用户数据位于系统用户数据目录，可用COMPANION_DATA指定独立目录。\nWindows/macOS、独占全屏游戏、真实目标机功耗未验证。\n'+(backendArg?'已附本地后端。\n':'此包只含桌面壳，启动时需 --backend-url=http://127.0.0.1:端口 指向你自己的本机后端。\n'));
console.log(JSON.stringify({output,backend_included:Boolean(backendArg),electron:require('./node_modules/electron/package.json').version,models_included:false,platform:os.platform()}));
