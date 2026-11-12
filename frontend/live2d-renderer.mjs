// Original adapter only. Vendor Core/framework are separately owner-installed and hash-checked.
export const version='0.1.0';
export function checkMocVersion(asset,core){const modelVersion=asset?.moc3_version?.code,latest=core?.Version?.csmGetLatestMocVersion?.();if(Number.isInteger(modelVersion)&&Number.isInteger(latest)&&modelVersion>latest)throw new Error('此模型需要更新的 Live2D Core。当前最高支持 MOC '+latest+'，模型为 MOC '+modelVersion+'。请使用兼容运行时或重新导出。');}
function localResource(value){const parsed=new URL(value,window.location.href);if(parsed.origin!==window.location.origin||!parsed.pathname.startsWith('/api/assets/'))throw new Error('Live2D 只允许本机已检查的角色资源。');return parsed.href;}
export function rewriteModel(json,asset){
 if(!json||json.Version!==3||!json.FileReferences)throw new Error('不是受支持的 Cubism 模型包。');
 const copy=JSON.parse(JSON.stringify(json)),references=copy.FileReferences;
 const scope=new URL(asset.model.url,window.location.href).searchParams.get('character_id');if(!scope)throw new Error('角色资源缺少身份作用域。');
 const checked=(value,name)=>{const result=localResource(value),parsed=new URL(result);if(parsed.pathname!=='/api/assets/'+encodeURIComponent(asset.id)+'/'+name||parsed.searchParams.get('character_id')!==scope)throw new Error('角色资源不属于当前运行包。');return result;};
 const map=name=>{if(typeof name!=='string'||!/^r[0-9]{4}\.(moc3|png|motion3\.json|exp3\.json|physics3\.json|cdi3\.json|pose3\.json)$/.test(name))throw new Error('模型引用未经过安全检查。');const item=asset.resources?.[name];if(!item?.url)throw new Error('角色包缺少已检查的资源。');return checked(item.url,name);};
 references.Moc=map(references.Moc);references.Textures=references.Textures.map(map);
 for(const key of ['Physics','DisplayInfo','Pose'])if(references[key])references[key]=map(references[key]);
 for(const expression of references.Expressions||[])expression.File=map(expression.File);
 for(const rows of Object.values(references.Motions||{}))for(const motion of rows){if(motion.Sound)throw new Error('不播放角色包自带音频。');motion.File=map(motion.File);}
 copy.url=checked(asset.model.url,asset.model.resource||'model.model3.json');return copy;
}
export function create({container,onError=()=>{},onStats=()=>{},collapsedFps=30,expandedFps=60}={}){
 const runtime=window.CompanionLive2DRuntime;if(!runtime?.PIXI||!runtime.Live2DModel||!window.Live2DCubismCore)throw new Error('尚未安装并验证 Live2D 运行时。');
 const {PIXI,Live2DModel}=runtime;
 let app=null,model=null,disposed=false,serial=0,request=null,raf=0,hidden=false,expanded=true,speaking=false,size=1,state='empty',frames=0,mouth=0,last=0,statsAt=0,lost=false;
 let audioContext=null,source=null,analyser=null,samples=null,audioElement=null;
 const report=()=>onStats({state,frames,hidden,lost,mouth:Number(mouth.toFixed(4)),blinkCount:null});
 function cancelFrame(){if(raf)cancelAnimationFrame(raf);raf=0;}
 function clearModel(){if(model){app?.stage.removeChild(model);model.destroy({children:true,texture:true,textureSource:true});model=null;}}
 function fail(error){cancelFrame();state='error';onError(error?.message||String(error));report();}
 function draw(){
  // Cubism clears its clipping targets with white. Its direct GL writes bypass
  // Pixi's clear-color cache; alpha=0/RGB=white makes the browser composite white
  // on a premultiplied canvas. Restore transparent black before Pixi's clear.
  app.renderer.gl.clearColor(0,0,0,0);app.renderer.render(app.stage);
 }
 function resize(){if(!app||disposed)return;const box=container.getBoundingClientRect(),width=Math.max(1,Math.round(box.width)),height=Math.max(1,Math.round(box.height));app.renderer.resize(width,height,Math.min(window.devicePixelRatio||1,2,2048/Math.max(width,height)));if(model){const fit=Math.min(width/Math.max(1,model.internalModel.width),height/Math.max(1,model.internalModel.height));model.scale.set(fit*size);model.position.set(width*.5,height*.51);}}
 function render(now){raf=0;if(disposed||hidden||lost||state!=='ready')return;const fps=Math.max(10,Math.min(60,expanded?expandedFps:collapsedFps));if(now-last>=1000/fps-1){const delta=Math.min(80,now-last||1000/fps);last=now;
  let desired=0;if(speaking){if(analyser&&samples){analyser.getByteTimeDomainData(samples);let sum=0;for(const x of samples)sum+=((x-128)/128)**2;desired=Math.min(.9,Math.sqrt(sum/samples.length)*4);}else desired=.2+.12*Math.sin(now*.013);}
  try{mouth+=(desired-mouth)*Math.min(1,delta*.018);model.setLipSyncValue?.(mouth);model.update(delta);draw();frames++;if(now-statsAt>1000){statsAt=now;report();}}catch(error){fail(error);return;}}
  raf=requestAnimationFrame(render);
 }
 function resume(){if(state==='ready'&&!raf&&!hidden&&!lost&&!disposed){last=performance.now();raf=requestAnimationFrame(render);}}
 const contextLost=event=>{event.preventDefault();lost=true;fail(new Error('Live2D 显示已中断，请重新加载。'));};
 async function init(){if(app)return;const candidate=new PIXI.Application();await candidate.init({width:Math.max(1,container.clientWidth),height:Math.max(1,container.clientHeight),backgroundAlpha:0,antialias:true,preference:'webgl',autoStart:false,sharedTicker:false,resolution:Math.min(window.devicePixelRatio||1,2),autoDensity:true,powerPreference:'low-power'});if(disposed){candidate.destroy(true,{children:true});return;}app=candidate;app.ticker.stop();app.canvas.className='vrm-canvas live2d-canvas';app.canvas.setAttribute('aria-label','Live2D 角色');app.canvas.addEventListener('webglcontextlost',contextLost);container.append(app.canvas);resize();}
 async function load(asset){const ticket=++serial;request?.abort();request=new AbortController();state='loading';report();try{
  checkMocVersion(asset,window.Live2DCubismCore);await init();if(disposed||ticket!==serial)return false;
  const response=await fetch(localResource(asset.model.url),{credentials:'same-origin',signal:request.signal});if(!response.ok)throw new Error('模型读取失败，请重新预览。');
  const json=rewriteModel(await response.json(),asset);if(disposed||ticket!==serial)return false;
  // Pixi defaults to a blob worker for image decode; keep the existing self-only worker policy.
  PIXI.Assets.setPreferences({preferWorkers:false,preferCreateImageBitmap:false});
  const candidate=await Live2DModel.from(json,{autoUpdate:false,autoFocus:false,autoHitTest:false,motionPreload:'NONE'});
  if(disposed||ticket!==serial){candidate.destroy({children:true,texture:true,textureSource:true});return false;}
  clearModel();model=candidate;model.anchor.set(.5,.5);model.setEyeBlinkEnabled?.(true);model.setBreathEnabled?.(true);model.setLipSyncEnabled?.(true);app.stage.addChild(model);resize();model.update(0);draw();frames++;state='ready';resume();report();return true;
 }catch(error){if(disposed||ticket!==serial||error.name==='AbortError')return false;fail(error);return false;}}
 const pointer=event=>{if(!model)return;const box=container.getBoundingClientRect();model.focus?.((event.clientX-box.left-box.width*.5)*.35+box.width*.5,(event.clientY-box.top-box.height*.5)*.35+box.height*.5);};container.addEventListener('pointermove',pointer);
 const observer=new ResizeObserver(resize);observer.observe(container);
 function detachAudio(){try{source?.disconnect();analyser?.disconnect();}catch{}source=null;analyser=null;samples=null;audioElement=null;}
 return {load,setSpeaking(value){speaking=Boolean(value);if(!speaking){mouth=0;model?.setLipSyncValue?.(0);detachAudio();}},setAudio(audio){if(!audio||audio===audioElement)return;detachAudio();try{audioContext??=new(window.AudioContext||window.webkitAudioContext)();source=audioContext.createMediaElementSource(audio);analyser=audioContext.createAnalyser();analyser.fftSize=512;samples=new Uint8Array(512);source.connect(analyser);analyser.connect(audioContext.destination);audioElement=audio;audioContext.resume().catch(()=>{});}catch{detachAudio();}},setExpanded(value){expanded=Boolean(value);},setScale(value){size=Math.max(.6,Math.min(1.3,Number(value)||1));resize();},setHidden(value){hidden=Boolean(value);if(hidden){speaking=false;mouth=0;model?.setLipSyncValue?.(0);cancelFrame();report();}else resume();},getStats(){return {state,frames,mouth,hidden,lost};},dispose(){if(disposed)return;disposed=true;serial++;request?.abort();cancelFrame();observer.disconnect();container.removeEventListener('pointermove',pointer);detachAudio();audioContext?.close().catch(()=>{});clearModel();if(app){app.canvas.removeEventListener('webglcontextlost',contextLost);app.destroy(true,{children:true,texture:true,textureSource:true});app=null;}state='disposed';}};
}
