"""Reproducible actual-Core cup shape measurement, independent of grip success.

Requires the owner's installed licensed Core. Never downloads SDKs, changes a
MOC, or infers an artistic threshold. Supply explicit limits to make a gate.
Raw texture alpha support is separated from unused/transparent vertices; clip
masks and final GPU visibility require the separate product/GL visual review.
"""
from __future__ import annotations
import argparse,base64,datetime,json,math,os,platform
from pathlib import Path
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script
from hand_cup_metamorphic_check import runtime_binding_files,runtime_files,sha,write_report
from live2d_cup_geometry import fit_transform,quantiles


def alpha_groups(data,textures,threshold):
    from PIL import Image
    index=data['texture_index']
    if not 0<=index<len(textures):raise ValueError('actual cup texture index is outside package')
    with Image.open(textures[index])as image:
        if image.width>4096 or image.height>4096 or image.width*image.height>32000000:raise ValueError('analysis texture budget exceeded')
        rgba=image.convert('RGBA');width,height=rgba.size;pixels=rgba.load();supported=[];alphas=[]
        for u,v in zip(data['uvs'][::2],data['uvs'][1::2]):
            if not math.isfinite(u)or not math.isfinite(v):raise ValueError('nonfinite actual UV')
            # Same pinned shader convention as hand_cup_browser.mjs. Any of
            # four bilinear texels may contribute; this is conservative support.
            px=u*width-.5;py=(1-v)*height-.5;alpha=max(pixels[min(width-1,max(0,math.floor(px)+dx)),min(height-1,max(0,math.floor(py)+dy))][3]for dx in(0,1)for dy in(0,1));alphas.append(alpha)
    used=sorted(set(data['triangle_indices']));count=len(data['baseline'])
    if any(not isinstance(i,int)or not 0<=i<count for i in used):raise ValueError('invalid actual triangle index')
    supported=[i for i in used if alphas[i]>=threshold]
    return {'all':list(range(count)),'triangle_used':used,'triangle_used_texture_alpha_supported':supported,'triangle_used_texture_alpha_below_threshold':[i for i in used if i not in supported],'unused':[i for i in range(count)if i not in used]},alphas


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in('model','poses','runtime-dir','cup-id','output'):p.add_argument('--'+key,required=True)
    p.add_argument('--hold-parameter');p.add_argument('--held-value',type=float,default=1);p.add_argument('--alpha-threshold',type=int,default=32)
    p.add_argument('--max-affine-residual-px',type=float);p.add_argument('--max-similarity-residual-px',type=float);p.add_argument('--min-similarity-scale',type=float)
    p.add_argument('--timing-warmup',type=int,default=32)
    p.add_argument('--gate-vertices',choices=('triangle_used','all','triangle_used_texture_alpha_supported'),default='triangle_used')
    args=p.parse_args();model=Path(args.model).resolve();posefile=Path(args.poses).resolve();runtime=Path(args.runtime_dir).resolve();setting=json.loads(model.read_text());files=runtime_files(model);moc=model.parent/setting['FileReferences']['Moc'];textures=[model.parent/name for name in setting['FileReferences']['Textures']]
    dataset=json.loads(posefile.read_text());poses=dataset['held_sweep']['off_key_parameters']
    if not isinstance(poses,list)or not 1<=len(poses)<=10000 or not all(isinstance(row,dict)and len(row)<=32 for row in poses):raise ValueError('requires 1..10000 bounded actual parameter poses')
    if not 1<=args.alpha_threshold<=255:raise ValueError('alpha threshold must be1..255')
    for v in(args.max_affine_residual_px,args.max_similarity_residual_px,args.min_similarity_scale):
        if v is not None and(not math.isfinite(v)or v<0):raise ValueError('declared limit must be finite nonnegative')
    if not 16<=args.timing_warmup<=256:raise ValueError('timing warmup must be16..256 actual updates')
    core=installed_script(runtime,'core');paths=files+[posefile,Path(__file__).resolve(),Path(__file__).with_name('live2d_cup_geometry.py'),*runtime_binding_files(runtime)];sources={str(path):sha(path)for path in paths}
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running','sources':sources,'scope':'Actual raw owner Core cup vertices; affine/similarity geometry, not grip/GL/Windows/art acceptance','declared_limits':{'affine_px':args.max_affine_residual_px,'similarity_px':args.max_similarity_residual_px,'min_similarity_scale':args.min_similarity_scale},'not_proven':['GPU/clipping visibility','continuous-domain upper bound','hand grip contact or finger roots','Windows or real-time performance']}
    try:
        with sync_playwright()as pw:
            b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=b.new_page();page.add_script_tag(content='(function(){var WebAssembly={};\n'+core.read_text()+'\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
            browser_version=b.version
            data=page.evaluate(r'''input=>{const C=Live2DCubismCore,a=Uint8Array.from(atob(input.moc),x=>x.charCodeAt(0));if(C.Moc.prototype.hasMocConsistency(a.buffer)!==1)throw Error('Actual Core rejects MOC');const moc=C.Moc.fromArrayBuffer(a.buffer),m=C.Model.fromMoc(moc),p=m.parameters,d=m.drawables,c=m.canvasinfo,i=d.ids.indexOf(input.id);if(i<0)throw Error('Actual cup ID missing');if(d.vertexCounts[i]>16384)throw Error('Analysis vertex budget exceeded');const times=[];function pose(values,timed=true){p.values.set(p.defaultValues);const requested={...values};if(input.hold)requested[input.hold]=input.held;for(const[id,v]of Object.entries(requested)){const j=p.ids.indexOf(id);if(j<0||!Number.isFinite(v)||v<p.minimumValues[j]||v>p.maximumValues[j])throw Error('Invalid actual parameter '+id);p.values[j]=v;}const t0=timed?performance.now():0;m.update();if(timed)times.push(performance.now()-t0);const v=d.vertexPositions[i];return{parameters:requested,opacity:d.opacities[i],points:Array.from({length:v.length/2},(_,j)=>[c.CanvasOriginX+v[2*j]*c.PixelsPerUnit,c.CanvasOriginY-v[2*j+1]*c.PixelsPerUnit])};}for(let w=0;w<input.warmup;w++)pose(input.poses[w%input.poses.length],false);const baseline=pose({},false),repeat=pose({},false);if(JSON.stringify(baseline)!==JSON.stringify(repeat))throw Error('Same actual default pose is not exact');const rows=input.poses.map(values=>pose(values,true));let timerStep=Infinity,prior=performance.now();for(let k=0;k<4096;k++){const now=performance.now();if(now>prior)timerStep=Math.min(timerStep,now-prior);prior=now;}const r={core_version:C.Version.csmGetVersion(),core_update_times_ms:times,timer_step_estimate_ms:Number.isFinite(timerStep)?timerStep:null,reported_browser_hardware_threads:navigator.hardwareConcurrency,user_agent:navigator.userAgent,baseline:baseline.points,rows,repeat_exact:true,uvs:Array.from(d.vertexUvs[i]),triangle_indices:Array.from(d.indices[i]),texture_index:d.textureIndices[i],mask_count:d.maskCounts[i],canvasInfo:{width:c.CanvasWidth,height:c.CanvasHeight,ppu:c.PixelsPerUnit,originX:c.CanvasOriginX,originY:c.CanvasOriginY}};m.release();moc._release();return r;}''',{'moc':base64.b64encode(moc.read_bytes()).decode(),'poses':poses,'id':args.cup_id,'hold':args.hold_parameter,'held':args.held_value,'warmup':args.timing_warmup});b.close()
        timing=data['core_update_times_ms'];assert len(timing)==len(poses);timing_q=quantiles(timing,(50,95,99,100));cpu_model=None
        if Path('/proc/cpuinfo').is_file():cpu_model=next((line.partition(':')[2].strip()for line in Path('/proc/cpuinfo').read_text().splitlines()if line.startswith('model name')),None)
        report['core_update_timing']={'sample_count':len(timing),'warmup_updates':args.timing_warmup,'p50_ms':timing_q['50'],'p95_ms':timing_q['95'],'p99_ms':timing_q['99'],'max_ms':max(timing),'timer_step_estimate_ms':data['timer_step_estimate_ms'],'engine':'owner-installed official Core asm.js fallback in Chromium (WebAssembly locally disabled as in application loader)','browser_version':browser_version,'platform':platform.platform(),'machine':platform.machine(),'reported_cpu_model':cpu_model,'reported_logical_cpu_count':os.cpu_count(),'process_cpu_affinity_count':len(os.sched_getaffinity(0))if hasattr(os,'sched_getaffinity')else None,'browser_reported_hardware_threads':data['reported_browser_hardware_threads'],'user_agent':data['user_agent'],'windows_executed':False,'render_or_fps_measurement':False,'timed_region':'model.update only; excludes parameter writes, vertex extraction, JS/Python transport and GPU rendering','reference_30fps_frame_budget_ms':1000/30,'p95_fraction_of_30fps_entire_frame_budget':timing_q['95']/(1000/30),'p95_exceeds_entire_30fps_frame_budget':timing_q['95']>=1000/30,'caveat':'Shared executor and timer quantization; zero-ms samples mean below timer resolution, not free computation.'}
        groups,alphas=alpha_groups(data,textures,args.alpha_threshold);rows=[];worst={};all_metrics={'affine':[],'similarity':[]};all_vertex_metrics={'affine':[],'similarity':[]};min_scale=math.inf;failures=[]
        if len(groups[args.gate_vertices])<3:raise ValueError('selected gate lacks three actual vertices')
        for row in data['rows']:
            result={'parameters':row['parameters'],'opacity':row['opacity']}
            for kind in('affine','similarity'):
                fit=fit_transform(data['baseline'],row['points'],kind,fit_indices=groups[args.gate_vertices]);metrics={name:{'count':len(ids),'max_source_px':max((fit['residual_source_px'][i]for i in ids),default=None)}for name,ids in groups.items()};gate_max=metrics[args.gate_vertices]['max_source_px'];result[kind]={'max_source_px':fit['max_source_px'],'gate_max_source_px':gate_max,'rms_source_px':fit['rms_source_px'],'matrix_3x2':fit['matrix_3x2'],'singular_values':fit['singular_values'],'similarity_scale':fit['similarity_scale'],'groups':metrics};all_metrics[kind].append(gate_max);all_vertex_metrics[kind].append(fit['max_source_px'])
                if kind not in worst or gate_max>worst[kind]['gate_max_source_px']:worst[kind]={'parameters':row['parameters'],'gate_max_source_px':gate_max,**fit}
                if kind=='similarity':min_scale=min(min_scale,fit['similarity_scale'])
            supported=groups['triangle_used_texture_alpha_supported']
            if len(supported)>=3:
                try:
                    fit=fit_transform(data['baseline'],row['points'],fit_indices=supported);result['supported_only_affine_fit']={'fit_count':len(supported),'max_on_supported_source_px':max(fit['residual_source_px'][i]for i in supported),'max_all_source_px':fit['max_source_px']}
                except ValueError:result['supported_only_affine_fit']={'unresolved':'supported reference points degenerate'}
            for kind,limit in(('affine',args.max_affine_residual_px),('similarity',args.max_similarity_residual_px)):
                if limit is not None and result[kind]['gate_max_source_px']>limit:failures.append({'parameters':row['parameters'],'gate':kind,'actual':result[kind]['gate_max_source_px'],'declared_limit':limit})
            if (args.max_affine_residual_px is not None or args.max_similarity_residual_px is not None)and result['similarity']['similarity_scale']<=0:failures.append({'parameters':row['parameters'],'gate':'strictly_positive_similarity_scale','actual':result['similarity']['similarity_scale']})
            if args.min_similarity_scale is not None and result['similarity']['similarity_scale']<args.min_similarity_scale:failures.append({'parameters':row['parameters'],'gate':'min_similarity_scale','actual':result['similarity']['similarity_scale'],'declared_limit':args.min_similarity_scale})
            rows.append(result)
        report.update(status='failed_declared_geometry_limit'if failures else'measured_geometry_without_declared_limits'if all(v is None for v in report['declared_limits'].values())else'passed_declared_geometry_limits',core_version=data['core_version'],canvasInfo=data['canvasInfo'],case_count=len(rows),vertex_count=len(data['baseline']),same_default_pose_exact=data['repeat_exact'],alpha_threshold=args.alpha_threshold,mask_count=data['mask_count'],gate_vertex_group=args.gate_vertices,vertex_groups={k:len(v)for k,v in groups.items()},vertex_alpha=alphas,per_pose_max_percentiles_source_px={kind:quantiles(values)for kind,values in all_metrics.items()},all_vertex_max_percentiles_source_px={kind:quantiles(values)for kind,values in all_vertex_metrics.items()},min_similarity_scale=min_scale,worst=worst,failures=failures,samples=rows)
    except Exception as error:report.update(status='failed_instrument_or_model',error=str(error))
    report['sources_unchanged']=all(Path(path).is_file()and sha(Path(path))==v for path,v in sources.items())
    if not report['sources_unchanged']:report.update(status='failed_source_changed')
    write_report(args.output,report);print(json.dumps({k:report.get(k)for k in('status','case_count','vertex_count','vertex_groups','per_pose_max_percentiles_source_px','min_similarity_scale','sources_unchanged','error')}))
    raise SystemExit(2 if report['status'].startswith('failed')else 0)
if __name__=='__main__':main()
