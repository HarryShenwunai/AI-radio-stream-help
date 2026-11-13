// Texture-atlas authoring pipeline. Artwork is generated separately by imagegen;
// this file only extracts declared atlas cells and places/scales source layers.
// It does not paint, infer hidden pixels, flatten frames into a fake rig, or
// modify the original generation files. The editable PSD is a separate step.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
const sharp=createRequire(import.meta.url)('sharp');

const root=path.resolve(import.meta.dirname,'..');
const out=path.resolve(process.argv[2]||path.join(root,'.build/original-character-art-r3'));
await fs.mkdir(path.join(out,'layers'),{recursive:true});
await fs.mkdir(path.join(out,'sources'),{recursive:true});
const sources={
  face:'583b92a4-b4e7-4a2d-919b-8c2cafb50251',
  body:'f2e6bcf0-997b-4742-a582-b61503265ca6',
  back:'71361f4b-1aaa-4d53-add3-fb86392b27b1',
  front:'e65bd132-7066-4b7c-8421-43b09c497768',
  eyes:'4592f4be-d9f0-4255-aac0-6a3544a96fd2',
  mouth:'ea88a197-e86e-492c-8a93-db1b41273d32',
  sleeves:'f0254475-1298-4f43-8ac1-4bb2580ae6f1',
  hands:'1ac20332-a976-466b-9194-7360d9b9735a',
};
const sourceInfo={};
for(const [key,id] of Object.entries(sources)){
  const file=path.join(out,'sources',key+'.png');
  await fs.copyFile('/workspace/generated_images/exec-'+id+'.png',file);
  const raw=await fs.readFile(file),meta=await sharp(raw).metadata();
  sourceInfo[key]={file:'sources/'+key+'.png',generated_image:'exec-'+id+'.png',
    sha256:crypto.createHash('sha256').update(raw).digest('hex'),width:meta.width,height:meta.height};
}
// Canvas placement is the authored neutral pose. L/R names are anatomical,
// matching Cubism convention; atlas columns are viewer-left then viewer-right.
// source, column, row, columns, rows, width, height, x, y, neutral visibility
const definitions=[
  ['back hair','back',0,0,1,1,940,920,360,25],
  ['topwear','body',0,0,1,1,1450,1360,40,650],
  ['face','face',0,0,1,1,600,670,540,145],
  ['eyewhite-r','eyes',0,0,2,5,128,53,741,505],
  ['eyewhite-l','eyes',1,0,2,5,126,52,939,503],
  ['iris-r','eyes',0,1,2,5,58,58,789,501],
  ['iris-l','eyes',1,1,2,5,58,58,972,498],
  ['eyelash-r','eyes',0,2,2,5,137,42,737,492],
  ['eyelash-l','eyes',1,2,2,5,137,42,935,490],
  ['lower eyelash-r','eyes',0,3,2,5,128,22,742,541],
  ['lower eyelash-l','eyes',1,3,2,5,126,22,940,539],
  ['eyebrow-r','eyes',0,4,2,5,132,28,738,454],
  ['eyebrow-l','eyes',1,4,2,5,129,28,943,450],
  ['mouth','mouth',0,0,2,3,126,43,843,707],
  ['upper teeth','mouth',1,0,2,3,105,20,855,708],
  ['tongue','mouth',0,2,2,3,79,21,869,733],
  ['upper lip','mouth',0,1,2,3,145,23,834,694],
  ['lower lip','mouth',1,1,2,3,145,25,834,739],
  ['closed mouth','mouth',1,2,2,3,145,42,834,696,false],
  ['front hair 1','front',0,0,3,1,570,790,350,25],
  ['front hair 2','front',1,0,3,1,650,610,560,20],
  ['front hair 3','front',2,0,3,1,300,730,1040,80],
];
const layers=[];
for(const [index,d] of definitions.entries()){
  const [name,source,col,row,cols,rows,width,height,x,y,visible=true]=d;
  const info=sourceInfo[source],left=Math.floor(col*info.width/cols),top=Math.floor(row*info.height/rows);
  const cell={left,top,width:Math.floor((col+1)*info.width/cols)-left,height:Math.floor((row+1)*info.height/rows)-top};
  const extracted=await sharp(path.join(out,info.file)).extract(cell).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const {data,info:pixelInfo}=extracted;
  let x0=pixelInfo.width,y0=pixelInfo.height,x1=-1,y1=-1;
  for(let yy=0;yy<pixelInfo.height;yy++)for(let xx=0;xx<pixelInfo.width;xx++){
    if(data[(yy*pixelInfo.width+xx)*4+3]>=8){x0=Math.min(x0,xx);y0=Math.min(y0,yy);x1=Math.max(x1,xx);y1=Math.max(y1,yy);}
  }
  if(x1<x0)throw new Error('Empty art cell: '+name);
  const padding=3;x0=Math.max(0,x0-padding);y0=Math.max(0,y0-padding);
  x1=Math.min(pixelInfo.width-1,x1+padding);y1=Math.min(pixelInfo.height-1,y1+padding);
  const crop={left:x0,top:y0,width:x1-x0+1,height:y1-y0+1};
  const filename='layers/'+String(index).padStart(2,'0')+'-'+name.replaceAll(' ','-')+'.png';
  await sharp(data,{raw:pixelInfo}).extract(crop).resize(width,height,{fit:'fill',kernel:'lanczos3'}).png().toFile(path.join(out,filename));
  const bytes=await fs.readFile(path.join(out,filename));
  layers.push({name,file:filename,x,y,visible,source,source_cell:cell,source_alpha_bounds:crop,
    width,height,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});
}
const document={format:'original-live2d-layers-v1',revision:3,canvas:{width:1536,height:2048},
  purpose:'Independent generated artwork assembled for an original Cubism rig; art and rig acceptance pending',
  art_method:'imagegen creates and repaints independent parts; this script extracts atlas cells and authors neutral placement',
  body_scope:'Coherent bust holding a mug. Body mesh supports authored breathing and body motion. No independent finger/arm/sipping gestures claimed.',
  quality_accepted:false,sources:sourceInfo,layers};
await fs.writeFile(path.join(out,'layers.json'),JSON.stringify(document,null,2)+'\n');
await sharp({create:{width:1536,height:2048,channels:4,background:'#00000000'}})
  .composite(layers.filter(l=>l.visible).map(l=>({input:path.join(out,l.file),left:l.x,top:l.y})))
  .png().toFile(path.join(out,'neutral-assembly.png'));
console.log(JSON.stringify({output:out,layers:layers.length,preview:path.join(out,'neutral-assembly.png'),quality_accepted:false}));
