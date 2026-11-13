// Imagegen-authored independent artwork -> bounded, aligned PSD layer inputs.
// This is texture extraction/layout; no invented pixels, painting or inpainting.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {atlasCell,assertTransparentCellEdges} from './live2d_atlas_cells.mjs';
const sharp=createRequire(import.meta.url)('sharp');
const root=path.resolve(import.meta.dirname,'..');
const out=path.resolve(process.argv[2]||path.join(root,'.build/original-character-art-r4-head'));
await fs.mkdir(path.dirname(out),{recursive:true});
await fs.mkdir(out); // A frozen source revision must never be silently replaced.
await fs.mkdir(path.join(out,'sources'));
await fs.mkdir(path.join(out,'layers'),{recursive:true});
const ids={face:'583b92a4-b4e7-4a2d-919b-8c2cafb50251',back:'71361f4b-1aaa-4d53-add3-fb86392b27b1',
  frontLeft:'778fad51-261b-4232-94b6-3687891f64f3',frontCenter:'65852dac-c0bc-45b4-9b48-e603f33a6002',
  frontRight:'b76cec1a-3394-481f-a0d9-abb7719cbe33',eyes:'4592f4be-d9f0-4255-aac0-6a3544a96fd2',
  mouth:'ea88a197-e86e-492c-8a93-db1b41273d32'};
const sources={};
for(const [name,id]of Object.entries(ids)){
  const file='sources/'+name+'.png';await fs.copyFile('/workspace/generated_images/exec-'+id+'.png',path.join(out,file));
  const raw=await fs.readFile(path.join(out,file)),m=await sharp(raw).metadata();
  sources[name]={file,width:m.width,height:m.height,generated_image:'exec-'+id+'.png',sha256:crypto.createHash('sha256').update(raw).digest('hex')};
}
const definitions=[
  {name:'back hair',source:'back',box:[315,0,900,860]},
  {name:'face',source:'face',box:[525,100,600,670]},
  {name:'eyewhite-r',source:'eyes',cell:[0,0,2,5],box:[717,460,128,53]},
  {name:'eyewhite-l',source:'eyes',cell:[1,0,2,5],box:[881,458,126,52]},
  {name:'iris-r',source:'eyes',cell:[0,1,2,5],box:[765,458,58,58]},
  {name:'iris-l',source:'eyes',cell:[1,1,2,5],box:[914,455,58,58]},
  {name:'eyelash-r',source:'eyes',cell:[0,2,2,5],box:[713,453,137,42]},
  {name:'eyelash-l',source:'eyes',cell:[1,2,2,5],box:[877,451,137,42]},
  {name:'lower eyelash-r',source:'eyes',cell:[0,3,2,5],box:[718,496,128,22]},
  {name:'lower eyelash-l',source:'eyes',cell:[1,3,2,5],box:[882,494,126,22]},
  {name:'eyebrow-r',source:'eyes',cell:[0,4,2,5],box:[714,409,132,28]},
  {name:'eyebrow-l',source:'eyes',cell:[1,4,2,5],box:[885,405,129,28]},
  {name:'mouth',source:'mouth',cell:[0,0,2,3],box:[815,662,126,43]},
  {name:'upper teeth',source:'mouth',cell:[1,0,2,3],box:[827,663,105,20]},
  {name:'tongue',source:'mouth',cell:[0,2,2,3],box:[841,688,79,21]},
  {name:'upper lip',source:'mouth',cell:[0,1,2,3],box:[806,649,145,23]},
  {name:'lower lip',source:'mouth',cell:[1,1,2,3],box:[806,694,145,25]},
  // Keep this real source drawable in the authoring project. The rig owns its
  // complementary MouthOpen opacity; invisible PSD layers may be omitted on export.
  {name:'mouth close',source:'mouth',cell:[1,2,2,3],box:[806,651,145,42],visible:true},
  {name:'front hair 1',source:'frontLeft',aligned:true},
  {name:'front hair 3',source:'frontRight',aligned:true},
  {name:'front hair 2',source:'frontCenter',aligned:true},
];
// The real iris crosses y=614, the old uniform five-row boundary. That cut
// mixed iris fragments into the upper lash and compressed its actual stroke.
const atlasRows={eyes:[0,350,685,960,1230,1536]};
const layers=[];
for(const [i,d] of definitions.entries()){
  const s=sources[d.source],[col,row,cols,rows]=d.cell||[0,0,1,1];
  const cell=atlasCell({width:s.width,height:s.height,col,row,cols,rows,yBounds:d.cell?atlasRows[d.source]:undefined});
  const {left,top}=cell;
  const {data,info}=await sharp(path.join(out,s.file)).extract(cell).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const gutter=d.cell?assertTransparentCellEdges(data,info,d.name):null;
  let x0=info.width,y0=info.height,x1=-1,y1=-1;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++)if(data[(y*info.width+x)*4+3]>=8){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);}
  if(x1<0)throw new Error('Empty independent source part '+d.name);
  x0=Math.max(0,x0-3);y0=Math.max(0,y0-3);x1=Math.min(info.width-1,x1+3);y1=Math.min(info.height-1,y1+3);
  const crop={left:x0,top:y0,width:x1-x0+1,height:y1-y0+1};
  const [x,y,width,height]=d.aligned?[Math.round((left+x0)*1.4),Math.round((top+y0)*1.4),Math.round(crop.width*1.4),Math.round(crop.height*1.4)]:d.box;
  if(x<0||y<0||x+width>1536||y+height>2048)throw new Error('Out of source canvas '+d.name);
  const file='layers/'+String(i).padStart(2,'0')+'-'+d.name.replaceAll(' ','-')+'.png';
  await sharp(data,{raw:info}).extract(crop).resize(width,height,{fit:'fill',kernel:'lanczos3'}).png().toFile(path.join(out,file));
  const bytes=await fs.readFile(path.join(out,file));
  layers.push({name:d.name,file,x,y,width,height,visible:d.visible!==false,source:d.source,source_cell:cell,source_alpha_bounds:crop,...(gutter?{atlas_gutter_check:gutter}:{}),
    sha256:crypto.createHash('sha256').update(bytes).digest('hex')});
}
const manifest={format:'original-live2d-layers-v1',revision:5,canvas:{width:1536,height:2048},atlas_rows:atlasRows,sources,layers,
  purpose:'Independently generated, repainted head source parts; requires real mesh, mask, keyform and art verification',
  quality_accepted:false};
await fs.writeFile(path.join(out,'layers.json'),JSON.stringify(manifest,null,2)+'\n');
await sharp({create:{width:1536,height:2048,channels:4,background:'#00000000'}})
  .composite(layers.filter(l=>l.visible).map(l=>({input:path.join(out,l.file),left:l.x,top:l.y}))).png().toFile(path.join(out,'head-assembly.png'));
console.log(JSON.stringify({output:out,layers:layers.length,quality_accepted:false}));
