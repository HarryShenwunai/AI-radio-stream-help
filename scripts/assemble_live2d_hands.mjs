// Existing imagegen artwork only: declared atlas extraction and neutral placement.
// No brush, silhouette synthesis, inpainting, recolor, or repeated whole-hand copies.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const sharp = createRequire(import.meta.url)('sharp');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const defaults = {
  extendedPalms: 'd3bb9484-bb50-46cb-a6b3-0aa71acf5179',
  viewerLeft: '08efe181-8354-4426-9a17-7042d9890f67',
  viewerRight: 'e6b49824-1d7f-4595-9db6-9d33d581303f',
  cup: '1ac20332-a976-466b-9194-7360d9b9735a',
  coherentReference: 'f2e6bcf0-997b-4742-a582-b61503265ca6',
};

function alphaBounds(data, width, height, threshold = 8, padding = 3) {
  let left=width, top=height, right=-1, bottom=-1;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    if(data[(y*width+x)*4+3]>=threshold){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
  }
  if(right<left)throw new Error('Empty atlas part');
  return {left:Math.max(0,left-padding),top:Math.max(0,top-padding),
    width:Math.min(width-1,right+padding)-Math.max(0,left-padding)+1,
    height:Math.min(height-1,bottom+padding)-Math.max(0,top-padding)+1};
}

// Each finger uses its own painted atlas cell. Sizes and positions author the
// neutral held-cup pose; these are not a rig evaluation or artistic acceptance.
// name, source, col,row, cols,rows, resizeW,resizeH, x,y, rotation, draw-order.
const fingerRefit = {
  'finger-index-r': {width:123,height:60,source_anchor:{x:1120,y:335}},
  'finger-middle-r': {width:128,height:55,source_anchor:{x:66,y:824}},
  'finger-ring-r': {width:122,height:54,source_anchor:{x:621,y:838}},
  'finger-little-r': {width:103,height:47,source_anchor:{x:1166,y:837}},
};
function rotatedAnchor(width,height,outWidth,outHeight,angle,point){
  const radians=angle*Math.PI/180,cos=Math.cos(radians),sin=Math.sin(radians);
  const dx=point.x*width-width/2,dy=point.y*height-height/2;
  return {x:dx*cos-dy*sin+outWidth/2,y:dx*sin+dy*cos+outHeight/2};
}
const placements = [
  ['hand-r','extendedPalms',0,0,2,1,145,233,684,1135,0,80],
  ['hand-l','extendedPalms',1,0,2,1,131,183,918,1157,0,81],
  ['finger-thumb-r','viewerLeft',1,0,3,2,45,99,762,1120,0,24],
  ['finger-little-l','viewerRight',2,1,3,2,69,55,987,1247,-8,25],
  ['cup','cup',1,0,3,1,293,295,745,1038,0,40],
  ['finger-thumb-l','viewerRight',1,0,3,2,68,123,956,1104,0,45],
  ['finger-index-l','viewerRight',2,0,3,2,95,77,956,1144,-7,46],
  ['finger-middle-l','viewerRight',0,1,3,2,97,78,967,1189,-7,47],
  ['finger-ring-l','viewerRight',1,1,3,2,86,68,973,1220,-8,48],
  ['finger-little-r','viewerLeft',2,1,3,2,120,42,693,1240,10,60],
  ['finger-ring-r','viewerLeft',1,1,3,2,141,49,704,1207,14,61],
  ['finger-middle-r','viewerLeft',0,1,3,2,150,50,715,1173,15,62],
  ['finger-index-r','viewerLeft',2,0,3,2,145,55,719,1135,15,63],
];

export async function assembleLive2DHands({
  outDir=path.join(root,'.build/original-character-art-r4-hands-r4'),
  sourceDirectory='/workspace/generated_images', sourceIds=defaults,
  canvas={width:1536,height:2048},
  bodyManifestFile=path.join(root,'.build/original-character-art-r4-body-r4/layers.json'),
  handPoseDeltas={viewerLeft:{x:25.2,y:-22.4},viewerRight:{x:-14,y:18.2}},
}={}) {
  outDir=path.resolve(outDir);
  if(canvas.width!==1536||canvas.height!==2048)throw new Error('This authored pose requires the declared 1536x2048 canvas.');
  await fs.mkdir(path.join(outDir,'layers'),{recursive:true});
  await fs.mkdir(path.join(outDir,'sources'),{recursive:true});
  const sources={};
  for(const key of Object.keys(defaults)){
    const id=sourceIds[key]||defaults[key], filename=`exec-${id}.png`;
    const bytes=await fs.readFile(path.join(sourceDirectory,filename));
    const meta=await sharp(bytes).metadata();
    if(meta.channels!==4)throw new Error(`RGBA source required: ${key}`);
    const file=`sources/${key}.png`;await fs.writeFile(path.join(outDir,file),bytes);
    const raw=await sharp(bytes).ensureAlpha().raw().toBuffer();
    let transparent=0, visible=0;for(let i=3;i<raw.length;i+=4){transparent+=raw[i]===0;visible+=raw[i]>=8;}
    sources[key]={file,generated_image:filename,sha256:digest(bytes),width:meta.width,height:meta.height,
      alpha0_pixels:transparent,alpha_ge8_pixels:visible,not_a_rig_layer:key==='coherentReference'};
    if((key==='viewerLeft'||key==='viewerRight')&&(meta.width!==1536||meta.height!==1024))throw new Error('3x2 hand atlas dimensions changed.');
  }
  const layers=[];
  for(const [index,definition]of placements.entries()){
    const [name,source,col,row,cols,rows,baseW,baseH,baseX,baseY,angle,order]=definition;
    let w=baseW,h=baseH,x=baseX,y=baseY,anchorPlacement=null;
    const entry=sources[source];
    const left=Math.floor(col*entry.width/cols);
    // The painted palm wrist reaches beyond y=512. A real transparent gutter
    // separates the two artwork rows at y=560; equal-height cells would cut
    // that wrist and leak its final pixels into the middle-finger cell below.
    const top=rows===2?(row===0?0:560):0;
    const bottom=rows===2?(row===0?560:entry.height):entry.height;
    const cell={left,top,width:Math.floor((col+1)*entry.width/cols)-left,height:bottom-top};
    const raw=await sharp(path.join(outDir,entry.file)).extract(cell).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const bounds=alphaBounds(raw.data,raw.info.width,raw.info.height);
    const refit=fingerRefit[name];
    if(refit){
      const point={x:(refit.source_anchor.x-cell.left-bounds.left)/bounds.width,y:(refit.source_anchor.y-cell.top-bounds.top)/bounds.height};
      let oldImage=sharp(raw.data,{raw:raw.info}).extract(bounds).resize(baseW,baseH,{fit:'fill',kernel:'lanczos3'});
      if(angle)oldImage=oldImage.rotate(angle,{background:'#00000000'});
      const oldMeta=await sharp(await oldImage.png().toBuffer()).metadata();
      const oldAnchor=rotatedAnchor(baseW,baseH,oldMeta.width,oldMeta.height,angle,point);
      w=refit.width;h=refit.height;
      anchorPlacement={source_anchor:refit.source_anchor,normalized_cropped_anchor:point,
        previous_resize:{width:baseW,height:baseH},previous_position:{x:baseX,y:baseY},
        preserved_target_anchor:{x:baseX+oldAnchor.x,y:baseY+oldAnchor.y},anchor_is_approximate_anatomical_guide:true};
    }
    let pipeline=sharp(raw.data,{raw:raw.info}).extract(bounds).resize(w,h,{fit:'fill',kernel:'lanczos3'});
    if(angle)pipeline=pipeline.rotate(angle,{background:'#00000000'});
    const bytes=await pipeline.png().toBuffer();const meta=await sharp(bytes).metadata();
    if(anchorPlacement){
      const next=rotatedAnchor(w,h,meta.width,meta.height,angle,anchorPlacement.normalized_cropped_anchor);
      x=Math.round(anchorPlacement.preserved_target_anchor.x-next.x);y=Math.round(anchorPlacement.preserved_target_anchor.y-next.y);
      anchorPlacement.actual_target_anchor={x:x+next.x,y:y+next.y};
      anchorPlacement.rounding_error_pixels={x:anchorPlacement.actual_target_anchor.x-anchorPlacement.preserved_target_anchor.x,y:anchorPlacement.actual_target_anchor.y-anchorPlacement.preserved_target_anchor.y};
    }
    const delta=handPoseDeltas[source]||{x:0,y:0};
    if(!Number.isFinite(delta.x)||!Number.isFinite(delta.y))throw new Error('Nonfinite pose offset');
    const previousPosition={x,y},actualDelta={x:Math.round(delta.x),y:Math.round(delta.y)};
    x+=actualDelta.x;y+=actualDelta.y;
    const handPose={previous_position:previousPosition,requested_delta:delta,actual_integer_delta:actualDelta,
      integer_quantization_error:{x:actualDelta.x-delta.x,y:actualDelta.y-delta.y}};
    if(anchorPlacement){
      anchorPlacement.previous_target_anchor=anchorPlacement.preserved_target_anchor;
      anchorPlacement.requested_new_target_anchor={x:anchorPlacement.preserved_target_anchor.x+delta.x,y:anchorPlacement.preserved_target_anchor.y+delta.y};
      anchorPlacement.actual_target_anchor={x:anchorPlacement.actual_target_anchor.x+actualDelta.x,y:anchorPlacement.actual_target_anchor.y+actualDelta.y};
    }
    if(x<0||y<0||x+meta.width>canvas.width||y+meta.height>canvas.height)throw new Error('Part outside canvas: '+name);
    const file=`layers/${String(index).padStart(2,'0')}-${name}.png`;await fs.writeFile(path.join(outDir,file),bytes);
    layers.push({name,file,x,y,width:meta.width,height:meta.height,visible:true,source,source_cell:cell,
      source_alpha_bounds:bounds,resize_before_rotation:{width:w,height:h},rotation_degrees:angle,
      draw_order:order,sha256:digest(bytes),finger_root_refit:anchorPlacement,hand_pose_adjustment:handPose,
      anatomical_side:name.endsWith('-r')?'right':name.endsWith('-l')?'left':null,
      semantic_parent:name==='cup'?'ROOT':name.startsWith('finger-')?`hand-${name.at(-1)}`:'corresponding-forearm',
      note:name==='cup'?'Independent movable cup mesh, never baked into torso or a hand.':'Independently painted palm/finger texture, not a duplicated whole hand.'});
  }
  layers.sort((a,b)=>a.draw_order-b.draw_order);
  const composite=async(items,name,background='#00000000')=>{
    await sharp({create:{...canvas,channels:4,background}})
      .composite(items.map(l=>({input:l.absolute_file||path.join(outDir,l.file),left:l.x,top:l.y})))
      .png().toFile(path.join(outDir,name));
  };
  await composite(layers,'neutral-hands-and-cup.png');
  await composite(layers.filter(l=>l.name!=='cup'),'neutral-complete-hands-without-cup.png');
  let body=null,bodySHA=null;
  try{const bytes=await fs.readFile(bodyManifestFile);body=JSON.parse(bytes);bodySHA=digest(bytes);}catch(error){if(error.code!=='ENOENT')throw error;}
  const bodyLayers=body?body.layers.filter(l=>l.visible!==false).map(l=>({...l,absolute_file:path.join(path.dirname(bodyManifestFile),l.file)})):[];
  if(body){
    if(JSON.stringify(body.canvas)!==JSON.stringify(canvas))throw new Error('Body/hands canvas mismatch.');
    const back=bodyLayers.filter(l=>!l.name.startsWith('cuff-front-'));
    const front=bodyLayers.filter(l=>l.name.startsWith('cuff-front-'));
    const ordered=[...back,...layers,...front];
    await composite(ordered,'neutral-body-hands-cup-draft.png');
    await composite(ordered.filter(l=>l.name!=='cup'),'neutral-body-with-cup-removed-draft.png');
    await composite(ordered.map(l=>l.name==='cup'?{...l,x:1190,y:1038}:l),'neutral-body-cup-displaced-draft.png');
    await composite(ordered,'neutral-body-hands-cup-on-dark.png','#202428');
  }
  const metadata={format:'original-live2d-layers-v1',revision:4,canvas,
    hand_placement_revision:4,
    previous_snapshot:'original-character-art-r4-hands-r3',
    pose_adjustment_note:'New imagegen 2x1 extended-palm source replaces only the two palm textures. Ten individual finger texture bytes/positions and cup bytes/position remain exact r3. Knuckle tops align to r3; new painted wrists extend beneath front cuff lips. Original fractional finger-group offsets are retained with declared integer PSD placement.',
    purpose:'Independent palms, five individual fingers per hand and independently movable cup; authored held-cup pose.',
    art_method:'Imagegen painted each part; this module only extracts declared cells, trims transparent margins, resizes, rotates and composites.',
    original_sources_unchanged:true,quality_accepted:false,sources,layers,
    atlas_row_boundary_y:560,
    source_layout:{extendedPalms:'2 columns x 1 row: viewer-left/anatomical-right extended palm; viewer-right/anatomical-left extended palm',viewerLeft:'3 columns x 2 rows: palm/thumb/index; middle/ring/little',viewerRight:'3 columns x 2 rows: palm/thumb/index; middle/ring/little',cup:'middle column of 3x1 original hand/cup source'},
    body_coordinate_mapping:{source_canvas:{width:1070,height:1470},matrix:[1.4,0,0,1.4,0,-50],
      note:'Hand placements are independently authored to the exact shared body coordinate system; they are not independent body fits.'},
    previous_cuff_targets:{viewerLeft:{x:700,y:1313.6},viewerRight:{x:1008,y:1266}},
    cuff_targets:{viewerLeft:{x:725.2,y:1291.2},viewerRight:{x:994,y:1284.2}},
    requested_hand_pose_deltas:handPoseDeltas,
    intended_wrist_overlap_target_pixels:[15,25],
    layer_order_notes:['All five body base ownership regions, including forearms, remain behind hands.','Only the two declared real cuff-front texture regions are drawn after hands; do not place entire forearms over hands because their polygons include torso pixels.','Cup is a separate root mesh; left thumb stays behind cup. Finger roots are underneath the complete palm textures so the palm covers their cut ends; finger bellies remain in front of cup.'],
    body_preview_manifest:body?bodyManifestFile:null,body_preview_manifest_sha256:bodySHA,
    blockers:['New painted wrist extension and original finger-base/knuckle registration require real visual acceptance; not a successful anatomical rig claim.','Original palm cells include rounded knuckle contour; final fingers must be visually checked for duplicate silhouettes.'],
    rejected_source:{generated_image:'exec-5a9425d8-b0e1-42d5-b7a5-b4686e212688.png',reason:'Large semitransparent gray background; root regenerated alpha-clean source. Original file retained, never used.'},
  };
  await fs.writeFile(path.join(outDir,'layers.json'),JSON.stringify(metadata,null,2)+'\n');
  return metadata;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const result=await assembleLive2DHands({outDir:process.argv[2]||undefined});
  console.log(JSON.stringify({output:path.resolve(process.argv[2]||path.join(root,'.build/original-character-art-r4-hands-r4')),
    layers:result.layers.length,independent_palms:2,independent_fingers:10,cup_meshes:1,quality_accepted:false}));
}
