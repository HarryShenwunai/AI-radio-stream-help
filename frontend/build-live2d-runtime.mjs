// Optional OWNER action after explicit license acceptance. Never invoked by the default build.
// This script neither downloads packages nor accepts Live2D terms.
import {build} from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
const args=process.argv.slice(2),get=key=>args[args.indexOf(key)+1];
if(!args.includes('--licensed-node-modules')||!args.includes('--outfile'))throw new Error('Provide --licensed-node-modules PATH and --outfile PATH after separately accepting applicable official terms.');
const modules=path.resolve(get('--licensed-node-modules')),outfile=path.resolve(get('--outfile'));
for(const [name,version]of [['pixi.js','8.23.0'],['@jannchie/pixi-live2d-display','1.4.0']]){
 const file=path.join(modules,...name.split('/'),'package.json'),actual=JSON.parse(fs.readFileSync(file,'utf8')).version;
 if(actual!==version)throw new Error(`Expected ${name}@${version}, received ${actual}`);
}
const notices=['Owner-installed Live2D evaluation runtime. Not part of the default distribution.','Live2D Cubism Framework: Copyright(c) Live2D Inc. All rights reserved.','Framework governed by https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.','Core is separately installed and is not contained in this bundle.'];
for(const name of ['pixi.js','@jannchie/pixi-live2d-display']){const license=path.join(modules,...name.split('/'),'LICENSE');if(!fs.existsSync(license))throw new Error('Required upstream license is missing: '+name);notices.push(name+'\n'+fs.readFileSync(license,'utf8'));}
const notice=notices.join('\n\n');
await build({banner:{js:'/*!\n'+notice.replaceAll('*/','* /')+'\n*/'},stdin:{contents:"import*as PIXI from'pixi.js';import'pixi.js/unsafe-eval';import{Live2DModel}from'@jannchie/pixi-live2d-display/cubism4';window.CompanionLive2DRuntime={PIXI,Live2DModel,versions:{pixi:'8.23.0',wrapper:'1.4.0'}};",resolveDir:path.dirname(modules),sourcefile:'owner-installed-live2d-runtime.mjs'},nodePaths:[modules],bundle:true,format:'iife',target:['chrome120'],minify:true,legalComments:'eof',outfile});

fs.writeFileSync(outfile+'.NOTICE.txt',notice+'\n');
