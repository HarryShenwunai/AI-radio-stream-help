// Assemble actual independent head/body/hand artwork, preserving pixels and
// lineage. This produces editable source inputs, NOT an exported Cubism model.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const sharp=createRequire(import.meta.url)('sharp');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const canvas={width:1536,height:2048};

async function readPart(file,part){
  const absolute=path.resolve(file),bytes=await fs.readFile(absolute),doc=JSON.parse(bytes);
  if(doc.format!=='original-live2d-layers-v1'||doc.canvas.width!==canvas.width||doc.canvas.height!==canvas.height||!Array.isArray(doc.layers))throw new Error('Unexpected source-part manifest: '+part);
  const layers=[];
  for(const layer of doc.layers){
    if(typeof layer.name!=='string'||!layer.name||typeof layer.file!=='string'||path.isAbsolute(layer.file)||layer.file.split(/[\\/]/).includes('..'))throw new Error('Invalid source layer');
    const source=path.resolve(path.dirname(absolute),layer.file),stat=await fs.lstat(source);
    if(stat.isSymbolicLink()||!stat.isFile()||stat.size>16*1024*1024)throw new Error('Invalid source image');
    const pixels=await fs.readFile(source),m=await sharp(pixels).metadata();
    if(m.format!=='png'||m.channels!==4||hash(pixels)!==layer.sha256)throw new Error('Source texture/hash mismatch: '+layer.name);
    if(!Number.isInteger(layer.x)||!Number.isInteger(layer.y)||layer.x<0||layer.y<0||layer.x+m.width>canvas.width||layer.y+m.height>canvas.height)throw new Error('Source placement outside authoring canvas');
    layers.push({...layer,part,absolute_file:source,width:m.width,height:m.height});
  }
  return {name:part,path:absolute,sha256:hash(bytes),manifest:doc,layers};
}

export async function assembleLive2DCharacter({head,body,hands,output,revision='r4'}){
  const parts=await Promise.all([readPart(head,'head'),readPart(body,'body'),readPart(hands,'hands')]);
  const [headPart,bodyPart,handPart]=parts;
  const all=parts.flatMap(p=>p.layers),byName=new Map(all.map(l=>[l.name,l]));
  if(byName.size!==all.length)throw new Error('Duplicate layer names across authoring parts');
  for(const name of ['face','topwear','upperarm-r','upperarm-l','forearm-r','forearm-l','hand-r','hand-l','cup'])if(!byName.has(name))throw new Error('Independent authoring component missing: '+name);
  for(const side of ['r','l'])for(const finger of ['thumb','index','middle','ring','little'])if(!byName.has('finger-'+finger+'-'+side))throw new Error('An independent finger is missing');
  if(byName.get('cup').semantic_parent!=='ROOT')throw new Error('Cup must be independently authored');
  const backHair=headPart.layers.filter(l=>l.name==='back hair');
  // True forearm regions are behind palms. Only the actual, separately painted
  // front cuff rims can cover wrist roots; a whole forearm must not cover the cup.
  const rearBody=bodyPart.layers.filter(l=>!l.name.startsWith('cuff-front-'));
  const face=headPart.layers.filter(l=>l.name!=='back hair');
  const cuffs=bodyPart.layers.filter(l=>l.name.startsWith('cuff-front-'));
  const ordered=[...backHair,...rearBody,...face,...handPart.layers,...cuffs];
  if(ordered.length!==all.length||new Set(ordered.map(l=>l.name)).size!==all.length)throw new Error('Layer partition lost or duplicated source data');
  const destination=path.resolve(output);
  if(await fs.stat(destination).then(()=>true,()=>false))throw new Error('Choose a fresh source revision directory');
  await fs.mkdir(path.join(destination,'layers'),{recursive:true});
  await fs.mkdir(path.join(destination,'sources'),{recursive:true});
  const layers=[];
  for(const [i,layer]of ordered.entries()){
    const file='layers/'+String(i).padStart(2,'0')+'-'+layer.name.replaceAll(' ','-')+'.png';
    await fs.copyFile(layer.absolute_file,path.join(destination,file));
    const {absolute_file,...rest}=layer;
    layers.push({...rest,file});
  }
  const provenance=[];
  for(const part of parts){
    const folder=path.join(destination,'sources',part.name);await fs.mkdir(folder,{recursive:true});
    await fs.copyFile(part.path,path.join(folder,'part-manifest.json'));
    for(const [key,source]of Object.entries(part.manifest.sources||{})){
      if(typeof source.file!=='string'||path.isAbsolute(source.file)||source.file.split(/[\\/]/).includes('..'))throw new Error('Unsafe original art reference');
      const original=path.resolve(path.dirname(part.path),source.file),bytes=await fs.readFile(original);
      if(hash(bytes)!==source.sha256)throw new Error('Original artwork changed since authoring');
      await fs.copyFile(original,path.join(folder,key+'.png'));
    }
    provenance.push({part:part.name,manifest_sha256:part.sha256,layers:part.layers.length,original_sources:part.manifest.sources});
  }
  const semanticProbes=[{name:'central_abdomen',x:840,y:1570},{name:'lower_torso',x:800,y:1700},{name:'lower_chest',x:860,y:1500}].map(p=>({...p,
    expected_layer:'topwear',forbidden_layers:bodyPart.layers.filter(l=>/^(upperarm|forearm|cuff-front)-/.test(l.name)).map(l=>l.name),
    review_basis:'Root inspected the unified empty-body source and its anatomical region. Independent actual-alpha sampling found topwear alpha=253 and all visible arm/cuff layers alpha=0 at these exact source-canvas points. This is a source ownership constraint; actual Core proof is still required.',
    reviewed_body_manifest_sha256:bodyPart.sha256,core_verified:false}));
  const doc={format:'original-live2d-layers-v1',revision,canvas,provenance,layers,
    rig_anchors:bodyPart.manifest.rig_anchors,body_anchors:bodyPart.manifest.anchors,semantic_probes:semanticProbes,
    purpose:'Original editable character source with independently painted head, arms, palms, ten fingers and detachable cup',
    source_only:true,is_exported_live2d:false,quality_accepted:false,
    required_runtime_checks:['Official Core consistency and actual deforming meshes','Head XYZ and eyes/blinks/gaze','Audio mouth open/form and expressions','Breath/body and hair physics','Arm/hand and each finger deformation','Independent cup visibility/XY/rotation, unchanged palms when detached','Held cup and complete empty-hand poses','Actual rendered screenshots/video and long texture lifecycle'],
    not_claimed:['This texture assembly is not a MOC3, a Cubism project or runtime evidence','Independent source files do not prove natural motion or production art quality']};
  await fs.writeFile(path.join(destination,'layers.json'),JSON.stringify(doc,null,2)+'\n');
  for(const [name,filter]of [['source-assembly-open-mouth.png',()=>true],['source-assembly-cup-removed.png',l=>l.name!=='cup']]){
    await sharp({create:{...canvas,channels:4,background:'#00000000'}}).composite(layers.filter(l=>l.visible!==false&&filter(l)).map(l=>({input:path.join(destination,l.file),left:l.x,top:l.y}))).png().toFile(path.join(destination,name));
  }
  return {output:destination,layers:layers.length,independent_fingers:10,cup_meshes:1,source_only:true,quality_accepted:false};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2),get=key=>{const i=args.indexOf('--'+key);if(i<0||!args[i+1]||args[i+1].startsWith('--'))throw new Error('Provide --'+key);return args[i+1];};
  console.log(JSON.stringify(await assembleLive2DCharacter({head:get('head'),body:get('body'),hands:get('hands'),output:get('output'),revision:'r4'})));
}
