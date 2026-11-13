// Coordinate-preserving layout only. All source artwork is supplied by imagegen.
// No painting, inpainting, hue correction, rotation, or per-part fitting.
// Polygon extraction only selects existing source pixels for separate rig pieces.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const sharp = createRequire(import.meta.url)('sharp');
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const sourceDefinitions = [
  {source:'torso', name:'topwear', id:'aa173158-7296-41ff-ab74-e57bd3bb604b', parts:[{name:'topwear',top:0,bottom:1470}]},
  // Cubism anatomical R/L: the viewer-left sleeve belongs to the right arm.
  {source:'viewerLeftSleeve', name:'arm-r', id:'064baaa6-6c40-4faf-b6bd-2d2a0269da6d', parts:[{name:'upperarm-r',top:0,bottom:1470,polygon:[[0,0],[1070,0],[1070,928.3],[400,928.3],[350,978.3],[0,1168.3]]},{name:'forearm-r',top:0,bottom:1470,polygon:[[0,1140],[350,950],[400,900],[1070,900],[1070,1470],[0,1470]]}]},
  {source:'viewerRightSleeve', name:'arm-l', id:'2ee57343-61a2-40c2-b8fa-e7ef254b7ab2', parts:[{name:'upperarm-l',top:0,bottom:1470,polygon:[[0,0],[1070,0],[1070,1208.3],[790,928.3],[0,928.3]]},{name:'forearm-l',top:0,bottom:1470,polygon:[[0,900],[790,900],[1070,1180],[1070,1470],[0,1470]]}]},
];
const referenceId = 'f2e6bcf0-997b-4742-a582-b61503265ca6';

function alphaBounds(data, width, height, threshold = 8, padding = 3) {
  let left = width, top = height, right = -1, bottom = -1;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (data[(y * width + x) * 4 + 3] >= threshold) {
      left = Math.min(left, x); top = Math.min(top, y);
      right = Math.max(right, x); bottom = Math.max(bottom, y);
    }
  }
  if (right < left) throw new Error('Source artwork has no visible pixels.');
  left = Math.max(0, left - padding); top = Math.max(0, top - padding);
  right = Math.min(width - 1, right + padding); bottom = Math.min(height - 1, bottom + padding);
  return {left, top, width:right - left + 1, height:bottom - top + 1};
}

function containsPolygon(x, y, polygon) {
  let inside = false;
  for (let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const [xi,yi]=polygon[i],[xj,yj]=polygon[j];
    if (((yi>y)!==(yj>y)) && x<(xj-xi)*(y-yi)/(yj-yi)+xi) inside=!inside;
  }
  return inside;
}

export async function assembleLive2DBody({
  outDir = path.join(projectRoot, '.build/original-character-art-r4-body'),
  sourceDirectory = '/workspace/generated_images',
  canvas = {width:1536, height:2048}, scale = 1.4, offsetX = 0, offsetY = -50, torsoSourceId = undefined,
} = {}) {
  if (!Number.isFinite(scale) || scale <= 0 || !Number.isInteger(offsetX) || !Number.isInteger(offsetY)) throw new Error('Invalid shared coordinate transform.');
  const scaledWidth = 1070 * scale, scaledHeight = 1470 * scale;
  if (!Number.isInteger(scaledWidth) || !Number.isInteger(scaledHeight)) throw new Error('Use an exact scale whose full source canvas has integer pixel dimensions.');
  outDir = path.resolve(outDir);
  await fs.mkdir(path.join(outDir, 'layers'), {recursive:true});
  await fs.mkdir(path.join(outDir, 'sources'), {recursive:true});
  const sources = {}, layers = [];
  if (torsoSourceId !== undefined && !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(torsoSourceId)) throw new Error('Invalid explicit torso source image ID.');
  const selectedDefinitions = sourceDefinitions.map(definition=>({...definition,id:definition.source==='torso' && torsoSourceId ? torsoSourceId : definition.id}));
  for (const definition of selectedDefinitions) {
    const filename = 'exec-' + definition.id + '.png';
    const bytes = await fs.readFile(path.join(sourceDirectory, filename));
    const image = sharp(bytes), metadata = await image.metadata();
    if (metadata.width !== 1070 || metadata.height !== 1470) throw new Error('Source canvas changed: ' + filename);
    const sourceFile = 'sources/' + definition.source + '.png';
    await fs.writeFile(path.join(outDir, sourceFile), bytes);
    const original = await sharp(bytes).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const originalBounds = alphaBounds(original.data, original.info.width, original.info.height);
    // Resize the ENTIRE source canvas first. A trimmed part is never fit to an
    // independently chosen rectangle; all three layers share one exact matrix.
    const scaled = await sharp(bytes).resize(scaledWidth, scaledHeight, {fit:'fill', kernel:'lanczos3'}).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    sources[definition.source] = {file:sourceFile, generated_image:filename, sha256:sha(bytes), width:1070, height:1470};
    for (const part of definition.parts) {
      const region = {left:0,top:Math.round(part.top*scale),width:scaledWidth,height:Math.round((part.bottom-part.top)*scale)};
      const pixels = await sharp(scaled.data,{raw:scaled.info}).extract(region).raw().toBuffer({resolveWithObject:true});
      if (part.polygon) for (let py=0;py<pixels.info.height;py++) for(let px=0;px<pixels.info.width;px++) {
        if (!containsPolygon((px+region.left+.5)/scale,(py+region.top+.5)/scale,part.polygon)) pixels.data[(py*pixels.info.width+px)*4+3]=0;
      }
      const localCrop = alphaBounds(pixels.data,pixels.info.width,pixels.info.height);
      const crop = {...localCrop,left:localCrop.left+region.left,top:localCrop.top+region.top};
      const x = crop.left + offsetX, y = crop.top + offsetY;
      if (x < 0 || y < 0 || x + crop.width > canvas.width || y + crop.height > canvas.height) throw new Error('Visible source artwork does not fit target canvas: ' + definition.source);
      const file = 'layers/' + part.name + '.png';
      await sharp(pixels.data, {raw:pixels.info}).extract(localCrop).png().toFile(path.join(outDir, file));
      const output = await fs.readFile(path.join(outDir, file));
      layers.push({name:part.name, file, x, y, width:crop.width, height:crop.height, visible:true,
        source:definition.source, source_cell:{left:0,top:part.top,width:1070,height:part.bottom-part.top},
        source_alpha_bounds:originalBounds, source_polygon:part.polygon||null, shared_scaled_canvas_crop:crop, sha256:sha(output)});
    }
  }
  const order = ['upperarm-r','upperarm-l','topwear','forearm-r','forearm-l'];
  layers.sort((a,b)=>order.indexOf(a.name)-order.indexOf(b.name));
  const composite = await sharp({create:{...canvas, channels:4, background:'#00000000'}})
    .composite(layers.map(layer => ({input:path.join(outDir, layer.file),left:layer.x,top:layer.y})))
    .png().toBuffer();
  await fs.writeFile(path.join(outDir, 'neutral-body-assembly.png'), composite);
  const reference = await fs.readFile(path.join(sourceDirectory, 'exec-' + referenceId + '.png'));
  await fs.writeFile(path.join(outDir, 'sources/coherent-reference.png'), reference);
  sources.coherentReference = {file:'sources/coherent-reference.png',generated_image:'exec-' + referenceId + '.png',sha256:sha(reference),width:1070,height:1470,not_a_rig_layer:true};
  const alignedReference = await sharp(reference).resize(scaledWidth,scaledHeight,{fit:'fill',kernel:'lanczos3'})
    .extract({left:Math.max(0,-offsetX),top:Math.max(0,-offsetY),
      width:Math.min(scaledWidth-Math.max(0,-offsetX),canvas.width-Math.max(0,offsetX)),
      height:Math.min(scaledHeight-Math.max(0,-offsetY),canvas.height-Math.max(0,offsetY))}).png().toBuffer();
  await sharp({create:{...canvas,channels:4,background:'#00000000'}})
    .composite([{input:alignedReference,left:Math.max(0,offsetX),top:Math.max(0,offsetY)}])
    .png().toFile(path.join(outDir,'coherent-reference-aligned.png'));

  const point = (x, y) => ({source:{x,y},target:{x:Number((x*scale+offsetX).toFixed(3)),y:Number((y*scale+offsetY).toFixed(3))}});
  const anchors = {
    neck_top_center:point(535,525), collar_center:point(550,665),
    viewer_left_shoulder:point(280,590), viewer_right_shoulder:point(790,700),
    viewer_left_cuff_center:point(500,974), viewer_right_cuff_center:point(720,940),
    viewer_left_cuff_rim_start:point(456,935), viewer_left_cuff_rim_end:point(555,1000),
    viewer_right_cuff_rim_start:point(650,964), viewer_right_cuff_rim_end:point(790,917),
  };
  // A geometric shoulder-gap diagnostic, not color/material/art acceptance.
  // Evaluate aligned source coordinates to avoid comparing differently fit crops.
  const finalRaw = await sharp(composite).ensureAlpha().raw().toBuffer();
  const referenceRaw = await sharp(reference).ensureAlpha().raw().toBuffer();
  const shoulderCoverage = {};
  for (const [name, box] of Object.entries({viewer_left:{left:205,top:590,width:170,height:210},viewer_right:{left:710,top:690,width:140,height:200}})) {
    let referenceOpaque = 0, uncovered = 0;
    for (let y=box.top;y<box.top+box.height;y++) for(let x=box.left;x<box.left+box.width;x++) {
      const index=(y*1070+x)*4+3;
      if(referenceRaw[index]>=220){
        referenceOpaque++;const tx=Math.floor(x*scale+offsetX),ty=Math.floor(y*scale+offsetY);
        if(tx<0||ty<0||tx>=canvas.width||ty>=canvas.height||finalRaw[(ty*canvas.width+tx)*4+3]<8)uncovered++;
      }
    }
    shoulderCoverage[name]={measured_on_final_target_composite:true,source_roi:box,reference_opaque_pixels:referenceOpaque,uncovered_pixels:uncovered,
      uncovered_ratio:referenceOpaque ? uncovered/referenceOpaque : null};
  }
  const manifest = {format:'original-live2d-layers-v1',revision:4,canvas,
    comparison_reference_file:'coherent-reference-aligned.png',
    purpose:'Coordinate-preserving torso and independent sleeves fragment; head/hands/fingers/cup are assembled separately.',
    art_method:'Existing imagegen artwork; extraction and one shared full-source coordinate transform only.',
    body_scope:'Independent torso and each anatomical sleeve split into back upperarm/front forearm; no hands, fingers or cup baked into these layers.',
    layer_order_back_to_front:order,
    sleeve_split:{method:'Hand-authored polygon extraction along elbow folds; source RGBA unchanged inside each selected region, alpha outside is absent.',overlap_source_y_pixels:28.3,overlap_target_y_pixels:28.3*scale,minimum_diagonal_overlap_target_pixels:28.3*scale/Math.sqrt(2)},
    quality_accepted:false, sources, layers,
    shared_source_mapping:{source_canvas:{width:1070,height:1470},scaled_canvas:{width:scaledWidth,height:scaledHeight},
      matrix:[scale,0,0,scale,offsetX,offsetY],equation:'targetX=sourceX*scale+offsetX; targetY=sourceY*scale+offsetY',
      rotation_degrees:0,per_layer_fit:false},
    anchors,anchor_precision:'Approximate manually observed anatomical guides in full source coordinates; source canvas transform is exact.',
    shoulder_coverage:shoulderCoverage,notes:['Shoulder geometry diagnostic is not a seamless-material or final art acceptance test.','Any artwork changes require imagegen or an artist; this module never paints patches.']};
  await fs.writeFile(path.join(outDir,'layers.json'),JSON.stringify(manifest,null,2)+'\n');
  return manifest;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const manifest = await assembleLive2DBody({outDir:process.argv[2] || undefined,torsoSourceId:process.argv[3] || undefined});
  console.log(JSON.stringify({layers:manifest.layers.length,transform:manifest.shared_source_mapping,
    shoulders:manifest.shoulder_coverage,quality_accepted:false}));
}
