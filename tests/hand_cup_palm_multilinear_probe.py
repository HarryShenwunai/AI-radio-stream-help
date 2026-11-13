"""Independent actual-Core palm q interpolation diagnostic; never writes a rig.

Compares the same frozen off-key poses against 486, 810, and 1350-point source
grids, distinguishing source-palm nonlinearity from the existing cup's actual
representation error. Prospective grid estimates are not exported MOC passes.
"""
import argparse,base64,bisect,datetime,itertools,json,math
from pathlib import Path
from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script
from hand_cup_metamorphic_check import sha,runtime_binding_files,write_report

AXES=['ParamBodyAngleX','ParamBodyAngleY','ParamBodyAngleZ','ParamBodyLean','ParamProportion','ParamBreath']


def interpolate(samples,levels,pose):
    brackets=[]
    for name,keys in levels.items():
        value=pose[name]
        if not keys or value<keys[0]or value>keys[-1]:raise ValueError('no source-pose extrapolation allowed')
        if value in keys:brackets.append([(value,1)])
        else:
            hi=bisect.bisect_left(keys,value);lo=hi-1;t=(value-keys[lo])/(keys[hi]-keys[lo])
            brackets.append([(keys[lo],1-t),(keys[hi],t)])
    result=[[0.0,0.0],[0.0,0.0]]
    for corner in itertools.product(*brackets):
        values=tuple(part[0]for part in corner);weight=math.prod(part[1]for part in corner)
        if values not in samples:raise ValueError('missing actual sampled q corner')
        for hand in range(2):
            for axis in range(2):result[hand][axis]+=samples[values][hand][axis]*weight
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-model','palm-guides','held-model','held-landmarks','poses-from-report','runtime-dir','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args();model=Path(args.source_model).resolve();heldmodel=Path(args.held_model).resolve()
    palmguide=Path(args.palm_guides).resolve();heldguide=Path(args.held_landmarks).resolve();posesfile=Path(args.poses_from_report).resolve();runtime=Path(args.runtime_dir).resolve()
    moc=model.parent/json.loads(model.read_text())['FileReferences']['Moc'];heldmoc=heldmodel.parent/json.loads(heldmodel.read_text())['FileReferences']['Moc']
    core=installed_script(runtime,'core');palm=json.loads(palmguide.read_text());mapping=json.loads(heldguide.read_text());poses=json.loads(posesfile.read_text())['held_sweep']['off_key_parameters']
    paths=[model,moc,palmguide,heldmodel,heldmoc,heldguide,posesfile,Path(__file__).resolve(),*runtime_binding_files(runtime)]
    sources={str(path):sha(path)for path in paths}
    with sync_playwright()as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=browser.new_page();page.add_script_tag(content=core.read_text())
        measured=page.evaluate(r'''input=>{
          const C=Live2DCubismCore;
          function revive(encoded){const bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0));if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core rejects MOC');const moc=C.Moc.fromArrayBuffer(bytes.buffer),model=C.Model.fromMoc(moc);return{moc,model};}
          const source=revive(input.source),held=revive(input.held),p=source.model.parameters;
          function point(m,a){const d=m.drawables,c=m.canvasinfo,i=d.ids.indexOf(a.drawable_id);if(i<0)throw Error('Missing actual anchor mesh');let x=0,y=0;
            for(let n=0;n<3;n++){const j=a.vertex_indices[n],w=a.weights[n];if(j<0||j>=d.vertexCounts[i])throw Error('Invalid actual triangle');x+=d.vertexPositions[i][j*2]*w;y+=d.vertexPositions[i][j*2+1]*w;}
            return[c.CanvasOriginX+x*c.PixelsPerUnit,c.CanvasOriginY-y*c.PixelsPerUnit];}
          function pose(m,values){const p=m.parameters;p.values.set(p.defaultValues);for(const[id,value]of Object.entries(values)){const i=p.ids.indexOf(id);if(i<0||value<p.minimumValues[i]||value>p.maximumValues[i])throw Error('No valid actual axis '+id);p.values[i]=value;}m.update();}
          pose(source.model,{});pose(held.model,{ParamCupHold:1});
          for(const [name,a]of Object.entries(input.palms.landmarks).filter(([name])=>name.endsWith('_palm'))){const q=point(source.model,a);if(Math.hypot(q[0]-a.source_canvas[0],q[1]-a.source_canvas[1])>.01)throw Error('Unbound source-palm guide '+name);}
          for(const[name,a]of Object.entries(input.mapping.landmarks)){const q=point(held.model,a);if(Math.hypot(q[0]-a.source_canvas[0],q[1]-a.source_canvas[1])>.01)throw Error('Unbound actual held guide '+name);}
          const levels={},parameters=[];
          for(const id of input.axes){const i=p.ids.indexOf(id);if(i<0)throw Error('Missing actual body parameter');const a=p.minimumValues[i],b=p.defaultValues[i],c=p.maximumValues[i];parameters.push({id,min:a,default:b,max:c});levels[id]=Array.from(new Set([a,b,c,...((id==='ParamBodyAngleX'||id==='ParamBodyLean')?[(a+b)/2,(b+c)/2]:[])])).sort((a,b)=>a-b);}
          const samples=[];function visit(index,values){if(index===input.axes.length){const state=Object.fromEntries(input.axes.map((id,i)=>[id,values[i]]));pose(source.model,state);samples.push({values:[...values],palms:['r','l'].map(side=>point(source.model,input.palms.landmarks['grip_'+side+'_palm']))});return;}
            for(const value of levels[input.axes[index]]){values[index]=value;visit(index+1,values);}}visit(0,[]);
          const cases=[];for(const state of input.poses){pose(source.model,state);const q=['r','l'].map(side=>point(source.model,input.palms.landmarks['grip_'+side+'_palm']));pose(held.model,{...state,ParamCupHold:1});
            cases.push({parameters:state,source_palms:q,held_palms:['r','l'].map(side=>point(held.model,input.mapping.landmarks['grip_'+side+'_palm'])),
              actual_held_cup:['r','l'].map(side=>point(held.model,input.mapping.landmarks['grip_'+side+'_cup']))});}
          const result={coreVersion:C.Version.csmGetVersion(),consistency:1,parameters,levels,samples,cases,actual_core_evaluations:2+samples.length+2*cases.length};
          source.model.release();source.moc._release();held.model.release();held.moc._release();return result;
        }''',{'source':base64.b64encode(moc.read_bytes()).decode(),'held':base64.b64encode(heldmoc.read_bytes()).decode(),'palms':palm,'mapping':mapping,'axes':AXES,'poses':poses})
        browser.close()
    actual={tuple(sample['values']):sample['palms']for sample in measured['samples']}
    parameters={p['id']:p for p in measured['parameters']}
    def keylevels(extra):
        return {pid:sorted(set([p['min'],p['default'],p['max']]+([(p['min']+p['default'])/2,(p['default']+p['max'])/2]if pid in extra else[])))for pid,p in parameters.items()}
    results={}
    for name,extras in [('base_486',set()),('lean5_810',{'ParamBodyLean'}),('lean5_x5_1350',{'ParamBodyLean','ParamBodyAngleX'})]:
        levels=keylevels(extras);cases=[]
        for case in measured['cases']:
            predicted=interpolate(actual,levels,case['parameters']);components=[]
            for hand in range(2):
                truth=case['source_palms'][hand];target=case['held_palms'][hand];cup=case['actual_held_cup'][hand];estimate=predicted[hand]
                nonlinear=[estimate[i]-truth[i]for i in range(2)];representation=[cup[i]-estimate[i]for i in range(2)];export=[target[i]-truth[i]for i in range(2)]
                total=[cup[i]-target[i]for i in range(2)]
                residual=[representation[i]+nonlinear[i]-export[i]-total[i]for i in range(2)]
                assert max(abs(v)for v in residual)<1e-9,'vector decomposition is inconsistent'
                components.append({'predicted_q':estimate,'actual_source_q':truth,'actual_held_cup':cup,
                    'source_q_nonlinearity_xy_px':nonlinear,'source_q_nonlinearity_px':math.hypot(*nonlinear),
                    'existing_cup_representation_xy_px':representation,'existing_cup_representation_px':math.hypot(*representation),
                    'export_palm_delta_xy_px':export,'export_palm_delta_px':math.hypot(*export),
                    'existing_total_grip_error_px':math.hypot(*total)})
            cases.append({'parameters':case['parameters'],'hands':components})
        results[name]={'prospective_grid_states':math.prod(len(v)for v in levels.values()),'levels':levels,
            'source_q_worst_prediction_error_px':max(h['source_q_nonlinearity_px']for c in cases for h in c['hands']),
            'source_q_cases_over_one_px':sum(max(h['source_q_nonlinearity_px']for h in c['hands'])>1 for c in cases),
            'existing_cup_worst_representation_difference_px':max(h['existing_cup_representation_px']for c in cases for h in c['hands']),
            'cases':cases}
    report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'measured_prospective_math_not_a_rig_acceptance',
        'scope':'independent actual Core q samples and multilinear vector decomposition; no MOC or production edits, new-grid predictions are not exported-model proof',
        'sources':sources,'sources_unchanged':all(sha(Path(path))==digest for path,digest in sources.items()),
        'actual_core_evaluations':measured['actual_core_evaluations'],'unique_actual_source_grid_samples':len(actual),
        'same_frozen_off_key_cases':len(poses),'core_version':measured['coreVersion'],'results':results}
    write_report(args.output,report);print(json.dumps({'status':report['status'],'sources_unchanged':report['sources_unchanged'],'samples':len(actual),
        'grids':{name:{key:value for key,value in data.items()if key not in('cases','levels')}for name,data in results.items()}},ensure_ascii=False))


if __name__=='__main__':main()
