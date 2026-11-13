// Local-only VRM 0/1 renderer. No downloaded character code or external resources.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {VRMLoaderPlugin,VRMUtils} from '@pixiv/three-vrm';

export const versions=Object.freeze({three:'0.180.0',threeVrm:'3.5.5'});
export function create({container,onError=()=>{},onStats=()=>{},collapsedFps=30,expandedFps=60}={}){
 if(!container)throw new Error('缺少三维舞台。');
 let disposed=false,vrm=null,serial=0,controller=null,raf=0,hidden=false,expanded=true,speaking=false,scale=1;
 let last=0,elapsed=0,nextBlink=2.8,blinkAt=-1,mouth=0,baseDistance=2.5,statsAt=0,frames=0,blinkCount=0,loadState='empty',lost=false;
 let audioContext=null,audioSource=null,analyser=null,audioElement=null,samples=null;
 const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(32,1,.05,100),clock=new THREE.Clock();
 const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power',premultipliedAlpha:true});
 renderer.setClearColor(0x000000,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
 renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.12;
 const canvas=renderer.domElement;canvas.className='vrm-canvas';canvas.setAttribute('aria-label','三维角色');canvas.setAttribute('role','img');container.append(canvas);
 scene.add(new THREE.HemisphereLight(0xfff5ed,0xb8bed2,2));
 const key=new THREE.DirectionalLight(0xffefdf,2.8);key.position.set(-2,3,3);scene.add(key);
 const fill=new THREE.DirectionalLight(0xddeaff,1.3);fill.position.set(2,1.5,2);scene.add(fill);
 const rim=new THREE.DirectionalLight(0xffe7e7,1.5);rim.position.set(0,2,-2);scene.add(rim);
 const target=new THREE.Vector3(),lookTarget=new THREE.Object3D();lookTarget.position.set(0,1.4,3);scene.add(lookTarget);
 const resting=new Map(),pointer=new THREE.Vector2();
 const report=()=>onStats({state:loadState,frames,blinkCount,mouth:Number(mouth.toFixed(4)),hidden,lost,geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,fpsLimit:expanded?expandedFps:collapsedFps});
 function fail(message){pause();loadState='error';onError(message);report();}
 function size(){
  if(disposed)return;const box=container.getBoundingClientRect(),width=Math.max(1,Math.round(box.width)),height=Math.max(1,Math.round(box.height));
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2,2048/Math.max(width,height)));renderer.setSize(width,height,false);camera.aspect=width/height;
  frameCamera();camera.updateProjectionMatrix();
 }
 function frameCamera(){camera.position.set(target.x,target.y+.025,target.z+baseDistance/scale);camera.lookAt(target);}
 function neutralize(){if(vrm?.expressionManager){vrm.expressionManager.setValue('aa',0);vrm.expressionManager.setValue('blink',0);}mouth=0;}
 function disposeModel(model){if(model){scene.remove(model.scene);VRMUtils.deepDispose(model.scene);}}
 function clear(){neutralize();const old=vrm;vrm=null;resting.clear();disposeModel(old);}
 function place(model){
  VRMUtils.rotateVRM0(model);model.scene.updateMatrixWorld(true);
  for(const [name,z]of [['leftUpperArm',-1.12],['rightUpperArm',1.12]]){const bone=model.humanoid?.getNormalizedBoneNode(name);if(bone)bone.rotation.z=z;}
  for(const name of ['head','neck','upperChest','chest']){const bone=model.humanoid?.getNormalizedBoneNode(name);if(bone)resting.set(name,{bone,rotation:bone.rotation.clone(),position:bone.position.clone()});}
  model.update(0);model.scene.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(model.scene),dimensions=bounds.getSize(new THREE.Vector3());
  const head=model.humanoid?.getNormalizedBoneNode('head'),headPosition=head?head.getWorldPosition(new THREE.Vector3()):bounds.getCenter(new THREE.Vector3());
  const height=Math.max(.5,dimensions.y),visibleHeight=height*.68;
  target.set(headPosition.x,headPosition.y-height*.18,headPosition.z);
  baseDistance=visibleHeight/(2*Math.tan(THREE.MathUtils.degToRad(camera.fov*.5)));
  if(model.lookAt){model.lookAt.target=lookTarget;model.lookAt.autoUpdate=true;}
  scene.add(model.scene);size();
 }
 function manager(){
  const m=new THREE.LoadingManager();m.setURLModifier(url=>{if(url.startsWith('blob:'))return url;throw new Error('模型包含未允许的外部资源。');});return m;
 }
 async function load(url){
  if(disposed)return false;
  const parsed=new URL(url,window.location.href);
  if(parsed.origin!==window.location.origin||!parsed.pathname.startsWith('/api/assets/'))throw new Error('只允许本机角色资源。');
  const ticket=++serial;controller?.abort();controller=new AbortController();loadState='loading';report();
  try{
   const response=await fetch(parsed.href,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw new Error('模型读取失败，请重新预览。');
   const buffer=await response.arrayBuffer();if(disposed||ticket!==serial)return false;
   if(buffer.byteLength>64*1024*1024)throw new Error('模型超过 64 MB。');
   const m=manager(),loader=new GLTFLoader(m);
   // BufferView images use HTMLImageElement under img-src blob:, never fetch(blob:) or a remote decoder.
   loader.register(parser=>{parser.textureLoader=new THREE.TextureLoader(m);return {name:'COMPANION_LOCAL_TEXTURES'};});
   loader.register(parser=>new VRMLoaderPlugin(parser,{autoUpdateHumanBones:true}));
   const gltf=await loader.parseAsync(buffer,'');const candidate=gltf.userData.vrm;
   if(!candidate){VRMUtils.deepDispose(gltf.scene);throw new Error('文件没有有效 VRM 人形。');}
   if(disposed||ticket!==serial){VRMUtils.deepDispose(candidate.scene);return false;}
   clear();vrm=candidate;place(vrm);loadState='ready';elapsed=0;clock.start();resume();report();return true;
  }catch(error){if(disposed||ticket!==serial||error.name==='AbortError')return false;fail(error.message||'模型无法显示。');return false;}
 }
 function animate(now){
  raf=0;if(disposed||hidden||lost)return;
  const fps=expanded?expandedFps:collapsedFps,interval=1000/Math.min(60,Math.max(10,fps));
  if(now-last>=interval-1){const delta=Math.min(.08,(now-last)/1000||1/fps);last=now;elapsed+=delta;
   if(vrm){
    if(elapsed>=nextBlink&&blinkAt<0){blinkAt=elapsed;nextBlink=elapsed+3+Math.random()*3;blinkCount++;}
    let blink=0;if(blinkAt>=0){const progress=(elapsed-blinkAt)/.16;if(progress>=1)blinkAt=-1;else blink=Math.sin(progress*Math.PI);}
    let desired=0;if(speaking){if(analyser&&samples){analyser.getByteTimeDomainData(samples);let sum=0;for(const value of samples)sum+=((value-128)/128)**2;desired=Math.min(.9,Math.sqrt(sum/samples.length)*4);}else desired=.2+.14*Math.sin(elapsed*13);}
    mouth=THREE.MathUtils.lerp(mouth,desired,Math.min(1,delta*18));
    vrm.expressionManager?.setValue('blink',blink);vrm.expressionManager?.setValue('aa',mouth);
    for(const [name,rest]of resting){rest.bone.rotation.copy(rest.rotation);rest.bone.position.copy(rest.position);if(name==='upperChest'||name==='chest')rest.bone.rotation.x+=Math.sin(elapsed*1.6)*.007;if(name==='head'){rest.bone.rotation.z+=Math.sin(elapsed*.65)*.009;rest.bone.rotation.y+=Math.sin(elapsed*.4)*.012;}}
    lookTarget.position.set(target.x+pointer.x*.22,target.y+.15+pointer.y*.12,target.z+3);vrm.update(delta);
   }
   renderer.render(scene,camera);frames++;
   if(now-statsAt>1000){statsAt=now;report();}
  }
  raf=requestAnimationFrame(animate);
 }
 function resume(){if(loadState==='ready'&&!raf&&!hidden&&!disposed&&!lost){last=performance.now();raf=requestAnimationFrame(animate);}}
 function pause(){if(raf)cancelAnimationFrame(raf);raf=0;neutralize();report();}
 const onLost=event=>{event.preventDefault();lost=true;pause();fail('三维显示已中断。可点击重新加载恢复。');};
 const onRestore=()=>{lost=false;loadState=vrm?'ready':'empty';size();resume();report();};
 canvas.addEventListener('webglcontextlost',onLost);canvas.addEventListener('webglcontextrestored',onRestore);
 const onPointer=event=>{const b=container.getBoundingClientRect();pointer.set(THREE.MathUtils.clamp((event.clientX-b.left)/b.width*2-1,-1,1),THREE.MathUtils.clamp(1-(event.clientY-b.top)/b.height*2,-1,1));};
 container.addEventListener('pointermove',onPointer);
 const observer=new ResizeObserver(size);observer.observe(container);size();
 function releaseAudio(){try{audioSource?.disconnect();analyser?.disconnect();}catch{}audioSource=null;analyser=null;samples=null;audioElement=null;}
 return {
  load,
  setSpeaking(value){speaking=Boolean(value);if(!speaking){mouth=0;vrm?.expressionManager?.setValue('aa',0);releaseAudio();}},
  setAudio(audio){
   if(!audio||audio===audioElement)return;releaseAudio();
   try{audioContext??=new (window.AudioContext||window.webkitAudioContext)();audioSource=audioContext.createMediaElementSource(audio);analyser=audioContext.createAnalyser();analyser.fftSize=512;samples=new Uint8Array(analyser.fftSize);audioSource.connect(analyser);analyser.connect(audioContext.destination);audioElement=audio;audioContext.resume().catch(()=>{});}catch{releaseAudio();}
  },
  setHidden(value){hidden=Boolean(value);if(hidden){speaking=false;pause();}else resume();},
  setExpanded(value){expanded=Boolean(value);},
  setScale(value){scale=THREE.MathUtils.clamp(Number(value)||1,.6,1.3);frameCamera();},
  getStats(){report();return {frames,blinkCount,mouth,hidden,lost,state:loadState,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles};},
  dispose(){if(disposed)return;disposed=true;serial++;controller?.abort();pause();observer.disconnect();container.removeEventListener('pointermove',onPointer);canvas.removeEventListener('webglcontextlost',onLost);canvas.removeEventListener('webglcontextrestored',onRestore);releaseAudio();audioContext?.close().catch(()=>{});clear();renderer.dispose();renderer.forceContextLoss();canvas.remove();loadState='disposed';}
 };
}
