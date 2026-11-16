// Read-only actual Cubism Core geometry/Part probe; no renderer, inference or SDK install.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
const [corePath, baselinePath, candidatePath, badPath, outputPath] = process.argv.slice(2);
if (!outputPath) throw Error('Usage: node probe core.js baseline.moc3 candidate.moc3 known-bad.moc3 report.json');
const module = {exports:{}};
const sandbox = {console, process, require:createRequire(import.meta.url), module, exports:module.exports,
  __dirname:path.dirname(corePath), setTimeout, clearTimeout, TextDecoder, TextEncoder, atob, Buffer};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(corePath,'utf8'),sandbox,{filename:corePath});
const Core=sandbox.Live2DCubismCore;
for(let n=0;n<100;n++){try{Core.Version.csmGetVersion();break;}catch{await new Promise(r=>setTimeout(r,10));}}
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
function open(file){const data=fs.readFileSync(file),moc=Core.Moc.fromArrayBuffer(data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength));if(!moc)throw Error('MOC rejected');const model=Core.Model.fromMoc(moc);if(!model)throw Error('Model rejected');return {model,moc,sha256:sha(data)};}
function partTree(model){return Array.from(model.parts.ids,(id,i)=>({id,parentIndex:model.parts.parentIndices[i],parent:model.parts.ids[model.parts.parentIndices[i]]??null,members:Array.from(model.drawables.ids).filter((_,j)=>model.drawables.parentPartIndices[j]===i)}));}
function snapshot(model,values={}){for(let i=0;i<model.parameters.count;i++)model.parameters.values[i]=model.parameters.defaultValues[i];for(const[k,v]of Object.entries(values)){const i=model.parameters.ids.indexOf(k);if(i<0)throw Error('Missing '+k);model.parameters.values[i]=v;}model.update();return {parameters:Object.fromEntries(Array.from(model.parameters.ids,(id,i)=>[id,model.parameters.values[i]])),parts:Array.from(model.parts.ids,(id,i)=>({id,opacity:model.parts.opacities[i]})),drawables:Array.from(model.drawables.ids,(id,i)=>({id,opacity:model.drawables.opacities[i],vertices:Array.from(model.drawables.vertexPositions[i])}))};}
function compare(a,b){const changes=[];for(let i=0;i<a.drawables.length;i++){const x=a.drawables[i],y=b.drawables[i];if(x.id!==y.id||x.vertices.length!==y.vertices.length)throw Error('Drawable structure changed');const max=Math.max(...x.vertices.map((v,j)=>Math.abs(v-y.vertices[j])));if(max||x.opacity!==y.opacity)changes.push({id:x.id,maxVertexDelta:max,opacityDelta:Math.abs(x.opacity-y.opacity)});}return changes;}
const baseline=open(baselinePath),candidate=open(candidatePath),bad=open(badPath);
try{
 const baseTree=partTree(baseline.model),newTree=partTree(candidate.model);
 function descendants(tree,id){const children=tree.filter(p=>p.parent===id);return children.flatMap(p=>[p.id,...descendants(tree,p.id)]);}
 const empty=baseTree.find(p=>p.id==='PartFace'),desc=descendants(baseTree,'PartFace');
 const baselineNeutral=snapshot(baseline.model),neutral=snapshot(candidate.model),badNeutral=snapshot(bad.model);
 const cases=[{}, {ParamEyeLOpen:0,ParamEyeROpen:0}, ...[['ParamAngleX',[-15,15]],['ParamAngleY',[-10,10]],['ParamAngleZ',[-2,2]],['ParamEyeBallX',[-1,1]],['ParamEyeBallY',[-1,1]]].flatMap(([id,vs])=>vs.map(v=>({[id]:v})))];
 const nonmouth=cases.map(values=>({values,changes:compare(snapshot(baseline.model,values),snapshot(candidate.model,values))}));
 const cycle=[...Array.from({length:21},(_,i)=>i/20),...Array.from({length:20},(_,i)=>(19-i)/20)].map(value=>{
  const pose=snapshot(candidate.model,{ParamMouthOpenY:value}),badPose=snapshot(bad.model,{ParamMouthOpenY:value});return {value,changes:compare(neutral,pose),mouthOpacity:pose.drawables.find(x=>x.id==='ArtMeshLayer2').opacity,partOpacity:pose.parts.find(x=>x.id==='PartFace').opacity,badChanges:compare(badNeutral,badPose)};
 });
 const checks={originalPartFaceHasNoDirectMembers:!!empty&&empty.members.length===0,originalPartFaceHasNoChildParts:desc.length===0,candidatePartFaceOwnsOnlyMouth:JSON.stringify(newTree.find(p=>p.id==='PartFace').members)===JSON.stringify(['ArtMeshLayer2']),partTreeUnchanged:baseTree.every((p,i)=>p.id===newTree[i].id&&p.parent===newTree[i].parent),candidateNeutralExactlyMatchesBaseline:compare(baselineNeutral,neutral).length===0,nonmouthPosesExactlyMatchBaseline:nonmouth.every(p=>p.changes.length===0),cycleAllGeometryExactlyUnchanged:cycle.every(p=>p.changes.every(c=>c.maxVertexDelta===0)),cycleOnlyMouthOpacityMayChange:cycle.every(p=>p.changes.every(c=>c.id==='ArtMeshLayer2')),mouthOpacityTracksInputFloat32:cycle.every(p=>Math.abs(p.mouthOpacity-p.value)<=2**-22),knownBadMeshKeyformsRejected:cycle.some(p=>p.badChanges.some(c=>c.maxVertexDelta!==0)),cycleClosedReturnsExactly:cycle.at(-1).changes.length===0};
 const report={scope:'Actual Core Node structure/finite geometry checks only; no rendered pixels or independent naturalness',coreSha256:sha(fs.readFileSync(corePath)),baselineSha256:baseline.sha256,candidateSha256:candidate.sha256,knownBadSha256:bad.sha256,originalPartTree:baseTree,candidatePartTree:newTree,originalPartFaceDescendants:desc,nonmouth,cycle,checks,passed:Object.values(checks).every(Boolean)};
 fs.mkdirSync(path.dirname(outputPath),{recursive:true});fs.writeFileSync(outputPath,JSON.stringify(report,null,2));console.log(JSON.stringify({checks,passed:report.passed}));if(!report.passed)process.exitCode=1;
}finally{for(const x of [baseline,candidate,bad]){x.model.release();x.moc._release();}}
