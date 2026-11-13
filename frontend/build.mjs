import {build} from 'esbuild';
await build({entryPoints:[new URL('./renderer.mjs',import.meta.url).pathname],bundle:true,format:'iife',globalName:'CompanionVrm',target:['chrome120'],minify:true,legalComments:'eof',outfile:new URL('../app/static/vrm-renderer.js',import.meta.url).pathname});

await build({entryPoints:[new URL('./live2d-renderer.mjs',import.meta.url).pathname],bundle:true,format:'iife',globalName:'CompanionLive2D',target:['chrome120'],minify:true,legalComments:'eof',outfile:new URL('../app/static/live2d-renderer.js',import.meta.url).pathname});
