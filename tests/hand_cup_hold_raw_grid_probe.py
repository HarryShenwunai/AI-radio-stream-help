"""Fast actual-Core diagnostic of all declared held poses without early abort.

Preserves genuine off-key errors to diagnose interpolation, while leaving the
production and strict acceptance checks unchanged. No GL/Windows/art pass.
"""
import argparse,base64,datetime,json
from pathlib import Path
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script
from hand_cup_metamorphic_check import sha,runtime_binding_files,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','landmarks','poses-from-report','runtime-dir','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();model=Path(args.model).resolve();landmark=Path(args.landmarks).resolve();poses=Path(args.poses_from_report).resolve();runtime=Path(args.runtime_dir).resolve()
    setting=json.loads(model.read_text());moc=model.parent/setting['FileReferences']['Moc'];mapping=json.loads(landmark.read_text())
    baseline_report=json.loads(poses.read_text());held=baseline_report['held_sweep'];levels=held['levels'];offkey=held['off_key_parameters']
    core=installed_script(runtime,'core');paths=[model,moc,landmark,poses,Path(__file__).resolve(),*runtime_binding_files(runtime)]
    sources={str(path):sha(path)for path in paths}
    with sync_playwright()as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page();page.add_script_tag(content=core.read_text())
        data=page.evaluate(r'''input=>{
          const C=Live2DCubismCore,bytes=Uint8Array.from(atob(input.moc),x=>x.charCodeAt(0));
          if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('actual Core rejects MOC');
          const moc=C.Moc.fromArrayBuffer(bytes.buffer),model=C.Model.fromMoc(moc),p=model.parameters,d=model.drawables,c=model.canvasinfo;
          const known=Object.fromEntries(Array.from(p.ids,(id,i)=>[id,i]));
          function point(name){const a=input.mapping.landmarks[name],i=d.ids.indexOf(a.drawable_id);if(i<0)throw Error('missing actual anchor mesh');let x=0,y=0;
            for(let n=0;n<3;n++){const j=a.vertex_indices[n],w=a.weights[n];if(j<0||j>=d.vertexCounts[i])throw Error('invalid actual triangle index');x+=d.vertexPositions[i][j*2]*w;y+=d.vertexPositions[i][j*2+1]*w;}
            return [c.CanvasOriginX+x*c.PixelsPerUnit,c.CanvasOriginY-y*c.PixelsPerUnit];}
          function pose(values,hold){p.values.set(p.defaultValues);for(const [id,value]of Object.entries({...values,ParamCupHold:hold})){
            if(known[id]===undefined||value<p.minimumValues[known[id]]||value>p.maximumValues[known[id]])throw Error('invalid real pose');p.values[known[id]]=value;}
            model.update();return ['r','l'].map(side=>({cup:point('grip_'+side+'_cup'),hand:point('grip_'+side+'_palm')}));}
          pose({},1);for(const [name,a]of Object.entries(input.mapping.landmarks)){const q=point(name);if(Math.hypot(q[0]-a.source_canvas[0],q[1]-a.source_canvas[1])>.01)throw Error('grip mapping not bound to this actual default MOC');}
          const corners=[],names=Object.keys(input.levels);function visit(i,state){if(i===names.length){corners.push({...state});return;}for(const value of input.levels[names[i]]){state[names[i]]=value;visit(i+1,state);}}visit(0,{});
          const samples=[];for(const [kind,states]of [['authored_key',corners],['off_key',input.offkey]])for(const values of states){
            const held=pose(values,1),detached=pose(values,0),errors=held.map(a=>Math.hypot(a.cup[0]-a.hand[0],a.cup[1]-a.hand[1]));
            samples.push({kind,parameters:values,held_errors_source_px:errors,detached_errors_source_px:detached.map(a=>Math.hypot(a.cup[0]-a.hand[0],a.cup[1]-a.hand[1])),over_one_source_pixel:Math.max(...errors)>1});}
          const result={coreVersion:C.Version.csmGetVersion(),consistency:1,parameter_count:p.count,core_evaluations:1+2*samples.length,
            authored_key_count:corners.length,off_key_count:input.offkey.length,worst_held_error_source_px:Math.max(...samples.flatMap(s=>s.held_errors_source_px)),
            failing_samples:samples.filter(s=>s.over_one_source_pixel),samples};
          model.release();moc._release();return result;
        }''',{'moc':base64.b64encode(moc.read_bytes()).decode(),'mapping':mapping,'levels':levels,'offkey':offkey})
        browser.close()
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'failed_grip_budget'if data['failing_samples']else'measured_core_grips_within_budget_not_full_acceptance',
        'scope':'actual Core only all frozen poses; retains every off-key error, no GL/performance/Windows/art completion claim',
        'sources':sources,'sources_unchanged':all(sha(Path(path))==digest for path,digest in sources.items()),'measurement':data}
    write_report(args.output,report);print(json.dumps({'status':report['status'],'authored_keys':data['authored_key_count'],'off_key':data['off_key_count'],'worst':data['worst_held_error_source_px'],'failures':len(data['failing_samples'])},ensure_ascii=False))


if __name__=='__main__':main()
