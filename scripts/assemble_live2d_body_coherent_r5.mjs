// Same-source Live2D texture partition. No generated paint, blur, color change,
// per-piece fit, or inferred pixels. Hidden underpainting is separately supplied
// by imagegen and remains disabled until actual rig/glue validation.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const sharp=createRequire(import.meta.url)('sharp');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const W=1536,H=2048,SCALE=1.4,OX=0,OY=-50;
const SOURCE='122aa5bb-f263-4f79-9bca-844eaf3c3d37';
const BACKFILL='ade190fa-7107-46be-87dd-7d55c4c11ae4';
// Viewer-left is anatomical right. Forearm regions take priority over upperarm
// regions. Torso is the exact complement, so each neutral pixel has one owner.
const regions=[
 {name:'cuff-front-r',polygon:[[462,945],[470,946],[480,960],[490,969],[500,977],[510,983],[520,988],[530,992],[540,995],[550,997],[560,1000],[574,1005],[570,1030],[550,1060],[510,1060],[465,1035],[438,1000],[445,960]]},
 {name:'cuff-front-l',polygon:[[690,978],[722,968],[751,953],[777,936],[787,955],[795,1000],[785,1038],[760,1054],[716,1053],[681,1032],[665,1000]]},
 {name:'forearm-r',polygon:[[0,1140],[330,955],[382,956],[419,982],[439,960],[456,916],[500,911],[552,944],[583,982],[569,1049],[540,1100],[494,1155],[408,1228],[320,1282],[200,1335],[110,1345],[0,1290]]},
 {name:'forearm-l',polygon:[[638,963],[660,944],[703,927],[747,915],[775,918],[785,932],[791,967],[798,1010],[830,1005],[855,1020],[900,1025],[960,1080],[1044,1160],[1025,1265],[965,1335],[900,1360],[825,1330],[760,1250],[710,1180],[674,1110],[641,1070]]},
 {name:'upperarm-r',polygon:[[0,0],[340,0],[365,850],[350,965],[170,1175],[0,1180]]},
 {name:'upperarm-l',polygon:[[790,0],[1070,0],[1070,1195],[900,1170],[790,960],[740,760]]},
];
const order=['upperarm-r','upperarm-l','topwear','forearm-r','forearm-l','cuff-front-r','cuff-front-l'];
const PAD=4; // Each side expands 4 target px; combined shared band ~5.714 source px.
const ownerAt=(x,y)=>regions.find(item=>inside(x,y,item.polygon))?.name||'topwear';
function inside(x,y,polygon){let yes=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){const [xi,yi]=polygon[i],[xj,yj]=polygon[j];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)yes=!yes;}return yes;}
async function alignedSource(file){
 const original=await fs.readFile(file),meta=await sharp(original).metadata();
 if(meta.width!==1070||meta.height!==1470)throw new Error('Expected unchanged 1070x1470 source canvas.');
 const scaled=await sharp(original).resize(1498,2058,{fit:'fill',kernel:'lanczos3'}).ensureAlpha().raw().toBuffer();
 const aligned=Buffer.alloc(W*H*4);
 // One common canvas mapping. The first 50 scaled rows are outside the target.
 for(let y=0;y<2008;y++)scaled.copy(aligned,(y*W)*4,((y+50)*1498)*4,((y+50)*1498+1498)*4);
 return {original,aligned};
}
function sharedBoundaryAnchor(original,from,to,names){
 const dx=to[0]-from[0],dy=to[1]-from[1],length=Math.hypot(dx,dy),nx=-dy/length,ny=dx/length;
 const steps=Math.ceil(Math.max(Math.abs(dx),Math.abs(dy))*4),runs=[];let start=null;
 const opaque=(x,y)=>x>=0&&y>=0&&x<1070&&y<1470&&original[(Math.floor(y)*1070+Math.floor(x))*4+3]>=8;
 for(let step=0;step<=steps;step++){
  const t=step/steps,x=from[0]+dx*t,y=from[1]+dy*t;
  const a=ownerAt(x+nx*.6,y+ny*.6),b=ownerAt(x-nx*.6,y-ny*.6);
  const supported=opaque(x+nx*.6,y+ny*.6)&&opaque(x-nx*.6,y-ny*.6)&&a!==b&&names.includes(a)&&names.includes(b);
  if(supported&&start===null)start=step;
  if((!supported||step===steps)&&start!==null){runs.push([start,supported?step:step-1]);start=null;}
 }
 if(!runs.length)throw new Error('No actual opaque shared boundary: '+names.join('/'));
 runs.sort((a,b)=>(b[1]-b[0])-(a[1]-a[0]));const run=runs[0],t=(run[0]+run[1])/2/steps;
 const rounded=n=>Number(n.toFixed(4));const x=from[0]+dx*t,y=from[1]+dy*t;
 return {source:{x:rounded(x),y:rounded(y)},target:{x:rounded(x*SCALE+OX),y:rounded(y*SCALE+OY)},
  defined_from:'Midpoint of longest alpha>=8 actually shared ownership-boundary run; source-pixel support sampled every <=0.25px, both sides checked.',
  source_segment:[from,to],supported_t:[run[0]/steps,run[1]/steps],owners:names,
  meaning:'Deterministic authored partition/glue pivot, not an automatically measured human bone joint.'};
}

function bounds(raw,threshold=1){let x0=W,y0=H,x1=-1,y1=-1;for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(raw[(y*W+x)*4+3]>=threshold){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);}if(x1<x0)throw new Error('Empty extraction.');return {left:x0,top:y0,width:x1-x0+1,height:y1-y0+1};}
export async function assembleCoherentBodyR5({outDir=path.join(root,'.build/original-character-art-r4-body-r5'),sourceDirectory='/workspace/generated_images'}={}){
 outDir=path.resolve(outDir);await fs.mkdir(path.join(outDir,'layers'),{recursive:true});await fs.mkdir(path.join(outDir,'sources'),{recursive:true});
 const source=await alignedSource(path.join(sourceDirectory,'exec-'+SOURCE+'.png'));
 const fill=await alignedSource(path.join(sourceDirectory,'exec-'+BACKFILL+'.png'));
 await fs.writeFile(path.join(outDir,'sources/coherent-empty-body.png'),source.original);
 await fs.writeFile(path.join(outDir,'sources/hidden-torso-source.png'),fill.original);
 await sharp(source.aligned,{raw:{width:W,height:H,channels:4}}).png().toFile(path.join(outDir,'coherent-reference-aligned.png'));
 const pixels=Object.fromEntries(order.map(name=>[name,Buffer.alloc(W*H*4)]));
 const hidden=Buffer.alloc(W*H*4),counts=Object.fromEntries(order.map(name=>[name,0]));
 let covered=0;const primaryOwner=new Uint8Array(W*H),drawCounts=new Uint8Array(W*H);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){
  const index=(y*W+x)*4;if(!source.aligned[index+3])continue;
  const sx=(x-OX+.5)/SCALE,sy=(y-OY+.5)/SCALE;
  const name=ownerAt(sx,sy);
  source.aligned.copy(pixels[name],index,index,index+4);counts[name]++;covered++;primaryOwner[y*W+x]=order.indexOf(name)+1;
  // Actual source paint, only beneath regions assigned to sleeves. No exposed
  // torso pixels are replaced. This is an optional, initially hidden rig piece.
  if(name!=='topwear'&&fill.aligned[index+3])fill.aligned.copy(hidden,index,index,index+4);
 }
 // Standard same-source texture overlap for actual GPU bilinear sampling.
 // Euclidean-radius extraction copies ORIGINAL aligned RGBA at neighboring
 // source positions; no color extrapolation, alpha blur, or inpainting.
 for(const [id,name]of order.entries()){
  const expanded=new Uint8Array(W*H);
  for(let y=0;y<H;y++){
   let x=0;
   while(x<W){
    if(primaryOwner[y*W+x]!==id+1){x++;continue;}
    const begin=x;while(x<W&&primaryOwner[y*W+x]===id+1)x++;const end=x-1;
    for(let dy=-PAD;dy<=PAD;dy++){
     const ty=y+dy;if(ty<0||ty>=H)continue;
     const rx=Math.floor(Math.sqrt(PAD*PAD-dy*dy));
     expanded.fill(1,ty*W+Math.max(0,begin-rx),ty*W+Math.min(W,end+rx+1));
    }
   }
  }
  for(let pixel=0;pixel<W*H;pixel++)if(expanded[pixel]&&source.aligned[pixel*4+3]&&(primaryOwner[pixel]===id+1||source.aligned[pixel*4+3]>=250)){
   const i=pixel*4;source.aligned.copy(pixels[name],i,i,i+4);drawCounts[pixel]++;
  }
 }
 const layers=[];
 async function emit(name,raw,visible,sourceKey){
  const crop=bounds(raw),file='layers/'+name+'.png';
  await sharp(raw,{raw:{width:W,height:H,channels:4}}).extract(crop).png().toFile(path.join(outDir,file));
  const bytes=await fs.readFile(path.join(outDir,file));
  layers.push({name,file,x:crop.left,y:crop.top,width:crop.width,height:crop.height,visible,
   source:sourceKey,parent_part:name==='cuff-front-r'?'forearm-r':name==='cuff-front-l'?'forearm-l':null,rig_bounds:bounds(raw,8),rig_bounds_alpha_threshold:8,rig_bounds_coordinate_space:'target canvas pixels; texture remains unmodified',source_polygon:regions.find(item=>item.name===name)?.polygon||null,
   extraction:name==='topwear'?'exact complement of the six ordered sleeve/cuff polygons':name==='topwear-backfill'?'imagegen source restricted to sleeve-covered coordinates':'exclusive ordered polygon region',
   sha256:hash(bytes)});
 }
 await emit('topwear-backfill',hidden,false,'hiddenTorso');
 for(const name of order)await emit(name,pixels[name],true,'coherentBody');
 const visible=layers.filter(layer=>layer.visible);
 const assembled=await sharp({create:{width:W,height:H,channels:4,background:'#00000000'}}).composite(visible.map(l=>({input:path.join(outDir,l.file),left:l.x,top:l.y}))).png().toBuffer();
 await fs.writeFile(path.join(outDir,'neutral-body-assembly.png'),assembled);
 const actual=await sharp(assembled).ensureAlpha().raw().toBuffer();
 // Independent reconstruction from the encoded crop textures, rather than
 // trusting the in-memory region buffers used to construct them.
 const reconstructed=Buffer.alloc(W*H*4);let textureVisiblePixels=0;
 for(const layer of visible){
  const raw=await sharp(path.join(outDir,layer.file)).ensureAlpha().raw().toBuffer();
  for(let y=0;y<layer.height;y++)for(let x=0;x<layer.width;x++){
   const i=(y*layer.width+x)*4;if(raw[i+3]){const target=((y+layer.y)*W+x+layer.x)*4;raw.copy(reconstructed,target,i,i+4);textureVisiblePixels++;}
  }
 }
 let exactTextureDifferences=0,displayDifferences=0,maxDisplayDelta=0,uncovered=0;
 for(let i=0;i<source.aligned.length;i+=4){
  if(!source.aligned[i+3])continue;
  if(!reconstructed[i+3])uncovered++;
  let texChanged=false,displayChanged=false;
  for(let c=0;c<4;c++){if(source.aligned[i+c]!==reconstructed[i+c])texChanged=true;const delta=Math.abs(source.aligned[i+c]-actual[i+c]);if(delta)displayChanged=true;maxDisplayDelta=Math.max(maxDisplayDelta,delta);}
  if(texChanged)exactTextureDifferences++;if(displayChanged)displayDifferences++;
 }
 const point=(x,y)=>({source:{x,y},target:{x:Number((x*SCALE+OX).toFixed(3)),y:Number((y*SCALE+OY).toFixed(3))}});
 const originalPixels=await sharp(source.original).ensureAlpha().raw().toBuffer();
 const rigAnchors={
  shoulder_r:sharedBoundaryAnchor(originalPixels,[340,0],[365,850],['upperarm-r','topwear']),
  shoulder_l:sharedBoundaryAnchor(originalPixels,[790,0],[740,760],['upperarm-l','topwear']),
  elbow_r:sharedBoundaryAnchor(originalPixels,[0,1140],[330,955],['upperarm-r','forearm-r']),
  elbow_l:sharedBoundaryAnchor(originalPixels,[900,1025],[960,1080],['upperarm-l','forearm-l']),
 };

 const validation={source_nonzero_alpha_pixels:covered,encoded_piece_visible_pixels:textureVisiblePixels,
  uncovered_pixels:uncovered,exact_encoded_texture_rgba_difference_pixels:exactTextureDifferences,
  sharp_composite_rgba_difference_pixels:displayDifferences,sharp_composite_max_channel_delta:maxDisplayDelta,
  encoded_texture_reconstruction_passed:uncovered===0&&exactTextureDifferences===0,
  all_pieces_from_one_source:true,visible_overlap_pixels:drawCounts.reduce((n,c)=>n+(c>1?1:0),0),
  texture_overlap:{method:'Euclidean-radius same-source extraction',target_radius_each_side:PAD,source_radius_each_side:PAD/SCALE,combined_source_overlap_width:2*PAD/SCALE,additional_overlap_minimum_source_alpha:250,outer_translucent_source:'Retained by original owner only; no duplicate alpha strengthening of transparent silhouette'},
  meaning:'Encoded samples copy exact common-source RGBA. Same-source overlap intentionally changes alpha-over compositing; actual difference is reported separately. Prior disjoint Core export showed sampling seams, so actual Core comparison is required and encoded equality is not acceptance.'};
 const manifest={format:'original-live2d-layers-v1',revision:5,body_snapshot:'r4-body-r5',geometry_parent_snapshot:'.build/original-character-art-r4-body-r4/layers.json',canvas:{width:W,height:H},quality_accepted:false,
  purpose:'Seven actual independent same-source clothing texture regions for a Cubism rig, plus disabled imagegen underpaint; not animation frames.',
  art_method:'One imagegen complete empty sweater; complementary standard polygon texture extraction with no new painted pixels.',
  sources:{coherentBody:{file:'sources/coherent-empty-body.png',generated_image:'exec-'+SOURCE+'.png',sha256:hash(source.original),width:1070,height:1470},hiddenTorso:{file:'sources/hidden-torso-source.png',generated_image:'exec-'+BACKFILL+'.png',sha256:hash(fill.original),width:1070,height:1470}},
  shared_source_mapping:{source_canvas:{width:1070,height:1470},matrix:[SCALE,0,0,SCALE,OX,OY],rotation_degrees:0,per_layer_fit:false},
  layers,layer_order_back_to_front:['topwear-backfill',...order],
  hands_insertion:{background_parts:['upperarm-r','upperarm-l','topwear','forearm-r','forearm-l'],then:'all ordered palm/finger/cup pieces',foreground_wrist_occluders:['cuff-front-r','cuff-front-l'],reason:'Only actual front cuff rim covers a wrist; forearm ownership excludes the old chest rectangles.'},
  rig_anchors:rigAnchors,
  anchors:{viewer_left_cuff_center:point(518,958),viewer_right_cuff_center:point(710,953),viewer_left_wrist_front_lip:point(518,997),viewer_right_wrist_front_lip:point(710,976),
   viewer_left_cuff_rim_start:point(458,917),viewer_left_cuff_rim_end:point(580,995),
   viewer_right_cuff_rim_start:point(638,966),viewer_right_cuff_rim_end:point(780,924),
   viewer_left_shoulder:point(280,590),viewer_right_shoulder:point(790,700),
   viewer_left_elbow_glue:point(190,1160),viewer_right_elbow_glue:point(940,1190)},
  anchor_precision:'Manually observed source guides; cuff dark-cavity ROI used as additional check, not automatic anatomical truth.',
  validation,
  rig_constraints:{neutral_texture_stage_only:true,
   enabled_before_core_validation:['Common body/parent transform applied to all seven visible clothing pieces together'],
   independent_arm_motion_default:'disabled until actual mesh glue and occlusion tests',
   needed_glue:['torso↔upperarm-r shoulder edge','torso↔upperarm-l shoulder edge','upperarm-r↔forearm-r elbow fold','upperarm-l↔forearm-l elbow fold','hand-r root↔viewer-left cuff','hand-l root↔viewer-right cuff','cuff-front-r↔forearm-r same transform','cuff-front-l↔forearm-l same transform'],
   hidden_fill:{layer:'topwear-backfill',neutral_visible:false,action:'Only enable within actual occluded arm-covered regions after Core inspection; independent source color/alpha may alter neutral appearance.'},
   exploratory_range_after_glue_only:{arm_translation_target_pixels:[-6,6],arm_rotation_degrees:[-2,2],verified:false},
   unsupported_without_new_art_and_core_proof:['large independent shoulder or elbow swing','fully lowered or raised arms','turning sleeves to reveal their backs','wide arm separation','claiming zero holes in cup release/empty-hand motion']},
  notes:['Nominal ownership is complementary, with a real same-source 4-target-px extraction pad on both sides for GPU sampling. No fabricated colors or alpha blur; final Core seam/warp validation remains required.','Insert all hands after the five base clothing pieces and before the two cuff-front pieces. Root avatar authoring must add shared deformation/glue and validate exposed coverage; source image reconstruction alone is insufficient.']};
 await fs.writeFile(path.join(outDir,'layers.json'),JSON.stringify(manifest,null,2)+'\n');
 return manifest;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const manifest=await assembleCoherentBodyR5({outDir:process.argv[2]||undefined});
 console.log(JSON.stringify({layers:manifest.layers.length,validation:manifest.validation,anchors:manifest.anchors},null,2));
}
