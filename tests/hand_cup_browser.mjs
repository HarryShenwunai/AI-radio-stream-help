/* Test-only: real owner-installed Core + the actual product adapter.
 * No invented parameter IDs, fake GL, stats-only mouth, SDK redistribution,
 * or changes to production canvas policy. Loaded by Playwright evaluation.
 */
window.__handCup = (() => {
  let raw = null, moc = null, asset = null, setting = null;
  let parameters = [], topology = {}, textures = [];
  let hiddenHelpers = [];
  const pixelFrames = new Map();
  const scene = () => window.CompanionApp.scene;
  function checkHelpers(drawables) {
    for (const id of hiddenHelpers) {
      const item=drawables.find(item=>item.id===id);
      if(!item || item.opacity!==0)throw Error('Technical cup helper became visible or is missing: '+id);
    }
    return drawables;
  }
  function setHiddenHelpers(ids) {
    if(!Array.isArray(ids)||!([0,2].includes(ids.length))||new Set(ids).size!==ids.length)throw Error('Exactly two declared helper IDs required');
    hiddenHelpers=[...ids];snapshot(raw);productSnapshot();
  }
  function actual() {
    const app = window.__actualPixiApps.find(app => app.stage?.children?.some(c => c.internalModel));
    if (!app) throw Error('No real product Pixi model');
    return {app, model: app.stage.children.find(c => c.internalModel)};
  }
  function snapshot(model) {
    const p = model.parameters, d = model.drawables;
    return {parameters: Array.from(p.ids, (id, i) => ({id, min:p.minimumValues[i], default:p.defaultValues[i], max:p.maximumValues[i], value:p.values[i]})),
      drawables: checkHelpers(Array.from(d.ids, (id, i) => ({id, vertices:Array.from(d.vertexPositions[i]), opacity:Number(d.opacities[i])})))};
  }
  function canvasInfo(model) {
    const c = model.canvasinfo;
    return {width:c.CanvasWidth,height:c.CanvasHeight,originX:c.CanvasOriginX,originY:c.CanvasOriginY,ppu:c.PixelsPerUnit};
  }
  async function fetchOK(url) {
    const response = await fetch(url, {credentials:'same-origin'});
    if (!response.ok) throw Error('Actual authenticated resource failed: ' + response.status);
    return response;
  }
  async function init(manifest) {
    asset = manifest;
    setting = await (await fetchOK(asset.model.url)).json();
    const descriptor = name => {
      const resource = asset.resources[name];
      if (!resource?.url) throw Error('Missing canonical authenticated resource: ' + name);
      return resource.url;
    };
    const buffer = await (await fetchOK(descriptor(setting.FileReferences.Moc))).arrayBuffer();
    const C = window.Live2DCubismCore;
    if (C.Moc.prototype.hasMocConsistency(buffer) !== 1) throw Error('Actual Core rejects MOC consistency');
    moc = C.Moc.fromArrayBuffer(buffer);
    raw = C.Model.fromMoc(moc);
    raw.parameters.values.set(raw.parameters.defaultValues);
    raw.update();
    parameters = snapshot(raw).parameters;
    topology = Object.fromEntries(Array.from(raw.drawables.ids, (id, i) => [id, {
      indices:Array.from(raw.drawables.indices[i]), uvs:Array.from(raw.drawables.vertexUvs[i]),
      textureIndex:raw.drawables.textureIndices[i], mask_count:raw.drawables.maskCounts[i],
      masks:Array.from(raw.drawables.masks[i]), render_order:raw.drawables.renderOrders[i]
    }]));
    for (const reference of setting.FileReferences.Textures) {
      const image = new Image();
      image.src = descriptor(reference);
      await image.decode();
      // Analysis canvas only: does not alter production contexts or rendering.
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      const ctx = canvas.getContext('2d', {willReadFrequently:true});
      ctx.drawImage(image,0,0);
      textures.push({width:canvas.width,height:canvas.height,data:ctx.getImageData(0,0,canvas.width,canvas.height).data});
      canvas.width = canvas.height = 0;
    }
    if (textures.reduce((sum,item)=>sum+item.width*item.height,0)>32000000) throw Error('Test texture readback budget exceeded');
    return {rest:snapshot(raw),topology,canvasInfo:canvasInfo(raw),coreVersion:C.Version.csmGetVersion(),mocVersion:C.Version.csmGetMocVersion(moc,buffer),mocConsistency:1};
  }
  function rawPose(values) {
    raw.parameters.values.set(raw.parameters.defaultValues);
    for (const [id,value] of Object.entries(values)) {
      const index = raw.parameters.ids.indexOf(id);
      if (index < 0) throw Error('Unknown actual raw Core parameter: ' + id);
      const p = parameters[index];
      if (!Number.isFinite(value) || value < p.min || value > p.max) throw Error('Out of actual range: ' + id);
      raw.parameters.values[index] = value;
    }
    raw.update();
    return snapshot(raw);
  }
  function controllerSnapshot(controller) {
    const d = controller.getDiagnostics({drawables:true,includeVertices:true});
    if (!d.available || d.verticesTruncated || d.drawablesTruncated) throw Error('Missing bounded real product vertices');
    return {parameters:d.parameters,drawables:checkHelpers(d.drawables.map(({id,vertices,opacity})=>({id,vertices,opacity}))),evaluations:d.coreEvaluations};
  }
  function productSnapshot(){return controllerSnapshot(scene());}
  async function stable(controller=scene()) {
    const deadline = performance.now()+10000;
    let previous = '', same = 0, last = -1, result;
    while (performance.now()<deadline) {
      await new Promise(requestAnimationFrame);
      const d = controllerSnapshot(controller);
      if (d.evaluations===last) continue;
      last = d.evaluations;
      const key = JSON.stringify({parameters:d.parameters.map(p=>[p.id,p.value]),drawables:d.drawables});
      same = key===previous ? same+1 : 0;
      previous=key; result=d;
      if (same>=4) return result;
    }
    throw Error('Actual product Core parameters/vertices/opacity did not settle');
  }
  async function productPose(values, releasePins=false) {
    await scene().applyControls({reset:true,idleMotion:false,breath:false,autoBlink:false,physics:false,expression:null});
    const entries = parameters.map(p=>({id:p.id,value:values[p.id]??p.default}));
    for (let offset=0;offset<entries.length;offset+=32) await scene().applyControls({parameters:entries.slice(offset,offset+32)});
    const result = await stable();
    if (releasePins) {
      await scene().applyControls({reset:true});
      // Test-only initial condition for an authored action. Clear the product's
      // persistent manual pins first, then save actual Core state so the motion
      // remains free to change it. Never leave pins masking an authored motion.
      const core=actual().model.internalModel.coreModel;
      for(const [id,value]of Object.entries(values)){
        const index=parameters.findIndex(p=>p.id===id);
        if(index<0)throw Error('Unknown initial actual Core parameter');
        core.setParameterValueByIndex(index,value);
      }
      core.saveParameters();
      return await stable();
    }
    return result;
  }
  function pixels(key, compare) {
    const {app} = actual(), gl=app.renderer.gl;
    // This performs the same real render lifecycle as production, including GC.
    app.renderer.render(app.stage);
    const data = new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);
    gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,data);
    const error=gl.getError();
    let opaque=0,colored=0,changed=0;
    const previous=compare?pixelFrames.get(compare):null;
    if (compare && (!previous || previous.length!==data.length)) throw Error('Missing same-size actual render baseline');
    for(let i=0;i<data.length;i+=4) {
      if(data[i+3]>8){opaque++;if(data[i]+data[i+1]+data[i+2]<740)colored++;}
      if(previous && (data[i]!==previous[i]||data[i+1]!==previous[i+1]||data[i+2]!==previous[i+2]||data[i+3]!==previous[i+3]))changed++;
    }
    if(key)pixelFrames.set(key,data);
    if(pixelFrames.size>4)pixelFrames.delete(pixelFrames.keys().next().value);
    return {error,opaque,colored,changed,width:gl.drawingBufferWidth,height:gl.drawingBufferHeight};
  }
  function barycentric(a,b,c,x,y) {
    const denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
    if(Math.abs(denominator)<1e-12)return null;
    const wa=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator;
    const wb=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator;
    const w=[wa,wb,1-wa-wb];
    return Math.min(...w)>=-1e-8?w:null;
  }
  function alphaSupport(points) {
    rawPose({});
    const c=canvasInfo(raw),d=raw.drawables,result=[];
    for(const point of points){
      const x=(point[0]-c.originX)/c.ppu,y=(c.originY-point[1])/c.ppu,supports=[];
      for(let mesh=0;mesh<d.count;mesh++){
        const t=topology[d.ids[mesh]],v=d.vertexPositions[mesh],texture=textures[t.textureIndex];
        if(!texture)throw Error('Invalid actual texture index');
        for(let i=0;i<t.indices.length;i+=3){
          const ids=t.indices.slice(i,i+3),p=ids.map(index=>[v[index*2],v[index*2+1]]),w=barycentric(...p,x,y);
          if(!w)continue;
          const u=ids.reduce((sum,index,n)=>sum+t.uvs[index*2]*w[n],0);
          const uv=ids.reduce((sum,index,n)=>sum+t.uvs[index*2+1]*w[n],0);
          // Pinned wrapper shader flips the UV y; textureFlipY is false.
          // Conservative bilinear support: any of the four texels may contribute.
          const px=u*texture.width-.5,py=(1-uv)*texture.height-.5;
          let alpha=0;
          for(const tx of [Math.floor(px),Math.ceil(px)])for(const ty of [Math.floor(py),Math.ceil(py)]){
            const cx=Math.max(0,Math.min(texture.width-1,tx)),cy=Math.max(0,Math.min(texture.height-1,ty));
            alpha=Math.max(alpha,texture.data[(cy*texture.width+cx)*4+3]);
          }
          supports.push({id:d.ids[mesh],triangle:ids,weights:w,uv:[u,uv],alpha,opacity:Number(d.opacities[mesh]),mask_count:t.mask_count,render_order:t.render_order});
          break;
        }
      }
      result.push({source_point:point,supports});
    }
    return result;
  }
  async function action(item) {
    await productPose(item.start_pose,true);
    const {model}=actual(),start=model.elapsedTime;
    if(item.kind==='motion')await scene().applyControls({motion:{group:item.group,index:item.index}});
    else await scene().applyControls({expression:item.name});
    const deadline=performance.now()+item.sample_seconds*5000+10000,trajectory=[];
    let evaluation=-1;
    while(model.elapsedTime-start<item.sample_seconds*1000){
      if(performance.now()>deadline)throw Error('Authored motion did not advance enough actual model time');
      await new Promise(requestAnimationFrame);
      const sample=productSnapshot();
      if(sample.evaluations!==evaluation){
        evaluation=sample.evaluations;
        trajectory.push({time:(model.elapsedTime-start)/1000,evaluation,
          parameters:Object.fromEntries(sample.parameters.map(p=>[p.id,p.value])),
          target_geometry:sample.drawables.filter(d=>item.target_meshes.includes(d.id)).map(d=>({id:d.id,opacity:d.opacity,
            centroid:[d.vertices.filter((_,i)=>i%2===0).reduce((a,b)=>a+b,0)/(d.vertices.length/2),
                      d.vertices.filter((_,i)=>i%2===1).reduce((a,b)=>a+b,0)/(d.vertices.length/2)]}))});
      }
    }
    return {...productSnapshot(),elapsed_model_seconds:(model.elapsedTime-start)/1000,trajectory};
  }
  function dispose(){pixelFrames.clear();textures=[];raw?.release();moc?._release();raw=moc=null;}
  return {init,setHiddenHelpers,rawPose,productPose,productSnapshot,stable,pixels,alphaSupport,action,dispose};
})();
