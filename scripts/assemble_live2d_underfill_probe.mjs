// Isolated hidden-underpaint probe. Only selects existing imagegen RGBA samples
// in the established canvas; no painting, fill color, blur, or rig mutation.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const sharp=createRequire(import.meta.url)('sharp');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const W=1536,H=2048,hash=b=>crypto.createHash('sha256').update(b).digest('hex');
export async function assembleUnderfillProbe({outDir=path.join(root,'.build/original-character-art-r4-underfill-aa-probe-r1')}={}){
 const tracked={};
 async function read(file){file=path.resolve(file);const bytes=await fs.readFile(file);tracked[file]=hash(bytes);return bytes;}
 const bodyDir=path.join(root,'.build/original-character-art-r4-body-r5');
 const previousDir=path.join(root,'.build/original-character-art-r4-body');
 const body=JSON.parse(await read(path.join(bodyDir,'layers.json')));
 const previous=JSON.parse(await read(path.join(previousDir,'layers.json')));
 const sourceLayer=previous.layers.find(l=>l.name==='topwear');
 if(!sourceLayer||sourceLayer.x!==154||sourceLayer.y!==659)throw new Error('Original AA source placement changed.');
 const original=await read('/workspace/generated_images/exec-aa173158-7296-41ff-ab74-e57bd3bb604b.png');
 const layoutBytes=await read(path.join(previousDir,sourceLayer.file));
 if(hash(layoutBytes)!==sourceLayer.sha256)throw new Error('AA layout source hash mismatch.');
 if(hash(original)!==previous.sources.torso.sha256)throw new Error('Original imagegen AA hash mismatch.');
 const coherent=await sharp(await read(path.join(bodyDir,'coherent-reference-aligned.png'))).ensureAlpha().raw().toBuffer();
 const source=await sharp(layoutBytes).ensureAlpha().raw().toBuffer();
 const sleeveUnion=new Uint8Array(W*H),candidate=Buffer.alloc(W*H*4);
 for(const l of body.layers.filter(l=>l.visible&&l.name!=='topwear')){
  const pixels=await sharp(await read(path.join(bodyDir,l.file))).ensureAlpha().raw().toBuffer();
  for(let y=0;y<l.height;y++)for(let x=0;x<l.width;x++)if(pixels[(y*l.width+x)*4+3]>=8)sleeveUnion[(y+l.y)*W+x+l.x]=1;
 }
 let count=0,left=W,top=H,right=-1,bottom=-1;
 for(let y=0;y<sourceLayer.height;y++)for(let x=0;x<sourceLayer.width;x++){
  const gx=x+sourceLayer.x,gy=y+sourceLayer.y,i=(gy*W+gx)*4,j=(y*sourceLayer.width+x)*4;
  if(source[j+3]&&coherent[i+3]>=250&&sleeveUnion[gy*W+gx]){
   source.copy(candidate,i,j,j+4);count++;left=Math.min(left,gx);top=Math.min(top,gy);right=Math.max(right,gx);bottom=Math.max(bottom,gy);
  }
 }
 if(!count)throw new Error('No existing underpaint samples selected.');
 const crop={left,top,width:right-left+1,height:bottom-top+1};
 outDir=path.resolve(outDir);await fs.mkdir(outDir);await fs.mkdir(path.join(outDir,'layers'));await fs.mkdir(path.join(outDir,'sources'));
 await fs.writeFile(path.join(outDir,'sources/aa-torso-original.png'),original);
 await fs.writeFile(path.join(outDir,'sources/aa-torso-existing-layout.png'),layoutBytes);
 const file='layers/topwear-backfill.png';
 await sharp(candidate,{raw:{width:W,height:H,channels:4}}).extract(crop).png().toFile(path.join(outDir,file));
 const encoded=await fs.readFile(path.join(outDir,file)),decoded=await sharp(encoded).ensureAlpha().raw().toBuffer();
 let changedSamples=0;
 for(let y=0;y<crop.height;y++)for(let x=0;x<crop.width;x++){
  const i=(y*crop.width+x)*4,j=((y+top)*W+x+left)*4;
  if(decoded[i+3]&&[0,1,2,3].some(c=>decoded[i+c]!==candidate[j+c]))changedSamples++;
 }
 const foreground=await read(path.join(bodyDir,'neutral-body-assembly.png'));
 const baseline=await sharp(foreground).ensureAlpha().raw().toBuffer();
 const combined=await sharp(candidate,{raw:{width:W,height:H,channels:4}}).composite([{input:foreground,left:0,top:0}]).ensureAlpha().raw().toBuffer();
 let newSilhouette=0,maxRGB=0,maxAlpha=0;
 for(let i=0;i<baseline.length;i+=4){if(baseline[i+3]<8&&combined[i+3]>=8)newSilhouette++;for(let c=0;c<3;c++)maxRGB=Math.max(maxRGB,Math.abs(combined[i+c]-baseline[i+c]));maxAlpha=Math.max(maxAlpha,Math.abs(combined[i+3]-baseline[i+3]));}
 function sample(x,y){const x0=Math.floor(x),y0=Math.floor(y);let result=[0,0,0,0];for(let dx=0;dx<=1;dx++)for(let dy=0;dy<=1;dy++){const weight=(1-Math.abs(x-x0-dx))*(1-Math.abs(y-y0-dy));const i=((y0+dy)*W+x0+dx)*4;for(let c=0;c<4;c++)result[c]+=candidate[i+c]*weight;}return result.map(n=>Number(n.toFixed(4)));}
 const points=[{screen:[210,776],canvas:[190.94588235294123,1810.6729411764704]},{screen:[610,586],canvas:[1154.7105882352942,1352.884705882353]},{screen:[616,588],canvas:[1169.1670588235295,1357.7035294117647]}];
 const probes=points.map(point=>({...point,candidate_bitmap_rgba:sample(...point.canvas),current_live_core_triangle_hits:0,
  meaning:'Current continuous-cloth actual Core has no geometry at this point; candidate bitmap coverage is not proof of a new export.'}));
 if(changedSamples||newSilhouette||probes.some(p=>p.candidate_bitmap_rgba[3]<220))throw new Error('Source-preservation, neutral-silhouette or bitmap coverage constraint failed.');
 const stable=(await Promise.all(Object.entries(tracked).map(async([p,sha])=>hash(await fs.readFile(p))===sha))).every(Boolean);
 if(!stable)throw new Error('An input source changed during extraction.');
 const manifest={format:'original-live2d-layers-v1',revision:1,fragment:'hidden-underfill-aa-probe-r1',canvas:{width:W,height:H},quality_accepted:false,
  purpose:'Replace only the existing hidden Topwear2 underpaint bitmap and its isolated mesh footprint in a new authoring revision. Not a full character or a rig acceptance result.',
  art_method:'Exact existing imagegen AA pixels copied from the frozen common-scale layout, selected by explicit neutral silhouette and real sleeve coverage masks.',
  sources:{aaOriginal:{file:'sources/aa-torso-original.png',generated_image:'exec-aa173158-7296-41ff-ab74-e57bd3bb604b.png',sha256:hash(original),width:1070,height:1470},aaExistingLayout:{file:'sources/aa-torso-existing-layout.png',sha256:hash(layoutBytes),x:154,y:659,width:1075,height:1349}},
  shared_source_mapping:{matrix:[1.4,0,0,1.4,0,-50],rotation_degrees:0,per_piece_fit:false},
  selection:'coherent neutral alpha>=250 AND existing six sleeve/cuff union alpha>=8 AND AA source alpha>0',
  layers:[{name:'topwear-backfill',file,x:left,y:top,width:crop.width,height:crop.height,visible:true,source:'aaExistingLayout',sha256:hash(encoded),role:'hidden underpaint, behind all foreground body/arms/hands'}],
  authoring_probe:{replace_only:'ArtMeshTopwear2 hidden underpaint and isolated footprint',preserve:['34 measured cloth poses and their current geometry','current common-body parent/deformers','arm fields','all glue configuration','all hands/cup/head art and UVs'],
   required:'Old Topwear2 mesh does not contain the three white-hole points. Refresh mesh and UV footprint to match this bitmap, then inspect actual Core at the same full-range combined poses.',
   forbidden_claims:['bitmap coverage proves new actual Core coverage','neutral source test proves dynamic no-hole behavior','full artistic acceptance','large arm movement is now universally safe']},
  validation:{source_pixels_selected:count,encoded_rgba_changes:changedSamples,neutral_static_new_alpha_ge8_silhouette_pixels:newSilhouette,neutral_static_max_rgb_delta:maxRGB,neutral_static_max_alpha_delta:maxAlpha,bitmap_gap_probes:probes,source_hashes_unchanged:stable},
  remaining_goals:['Final controlled-default face eye and closed-mouth ROI review remains open.','Whole-range actual Core coverage, neutral edge exposure, material continuity and topology must be checked after this isolated underpaint probe.']};
 await fs.writeFile(path.join(outDir,'layers.json'),JSON.stringify(manifest,null,2)+'\n');
 await fs.writeFile(path.join(outDir,'source-binding.json'),JSON.stringify({sources:tracked,sources_unchanged:stable},null,2)+'\n');
 return {outDir,manifest};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const {outDir,manifest}=await assembleUnderfillProbe({outDir:process.argv[2]||undefined});
 console.log(JSON.stringify({outDir,layer:manifest.layers[0],validation:manifest.validation},null,2));
}
