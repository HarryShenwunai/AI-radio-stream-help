"""Actual Core-only calibration for one authored parameter and one target drawable.

The explicit target/provenance are supplied by the authoring operation; this does not
infer artistic correctness. It checks symmetry and all other geometry as a negative.
"""
from pathlib import Path
import hashlib
import json
import shlex
import sys

import live2d_original_core_check as harness

original_arguments = list(sys.argv[1:])

def take(flag, default):
    if flag not in sys.argv:
        return default
    index = sys.argv.index(flag)
    value = sys.argv[index + 1]
    del sys.argv[index:index + 2]
    return value

parameter_id = take('--calibration-parameter', 'ParamLipCalibration')
target_id = take('--target-drawable', 'ArtMeshLayer3')
original_check = harness.RAW_CHECK
harness.RAW_CHECK = r'''async args=>{
 const result=await (''' + original_check + r''')(args);
 const setting=await(await fetch(args.modelURL)).json(),buffer=await(await fetch(new URL(setting.FileReferences.Moc,args.modelURL))).arrayBuffer();
 const C=Live2DCubismCore,moc=C.Moc.fromArrayBuffer(buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables;
 const id=PARAM_LITERAL,target=TARGET_LITERAL,index=p.ids.indexOf(id);if(index<0)throw Error('Calibration parameter missing');
 const targetIndex=d.ids.indexOf(target);if(targetIndex<0)throw Error('Calibration target missing');
 function snapshot(value){p.values.set(p.defaultValues);p.values[index]=value;raw.update();return Array.from(d.vertexPositions,v=>Array.from(v));}
 const low=snapshot(p.minimumValues[index]),neutral=snapshot(p.defaultValues[index]),high=snapshot(p.maximumValues[index]);
 function centroid(vertices){let x=0,y=0;for(let i=0;i<vertices.length;i+=2){x+=vertices[i];y+=vertices[i+1];}return [x/(vertices.length/2),y/(vertices.length/2)];}
 const changed=[],asymmetry=[];for(let j=0;j<d.count;j++){const altered=neutral[j].some((x,i)=>Math.abs(low[j][i]-x)>1e-7||Math.abs(high[j][i]-x)>1e-7);if(altered)changed.push(d.ids[j]);for(let k=0;k<neutral[j].length;k++)asymmetry.push(Math.abs((low[j][k]+high[j][k])/2-neutral[j][k]));}
 const coordinates={min:low[targetIndex],default:neutral[targetIndex],max:high[targetIndex]},centroids=Object.fromEntries(Object.entries(coordinates).map(([key,value])=>[key,centroid(value)]));
 const info={parameter:id,target,values:{min:p.minimumValues[index],default:p.defaultValues[index],max:p.maximumValues[index]},canvasInfo:Object.fromEntries(Object.entries(raw.canvasinfo).filter(([,v])=>typeof v==='number')),changedDrawables:changed,otherDrawablesChanged:changed.filter(x=>x!==target),maxSymmetryError:Math.max(...asymmetry),centroids,coordinates};
 if(changed.length!==1||changed[0]!==target)throw Error('Calibration touched unexpected Core geometry: '+JSON.stringify(info));
 if(info.maxSymmetryError>1e-6)throw Error('Calibration is not symmetric around default: '+JSON.stringify(info));
 raw.release();moc._release();return {...result,coordinateCalibration:info};
}'''
harness.RAW_CHECK = harness.RAW_CHECK.replace('PARAM_LITERAL', json.dumps(parameter_id)).replace('TARGET_LITERAL', json.dumps(target_id))
if '--probe-pixels' not in sys.argv:
    sys.argv.append('--probe-pixels')
if '--require-parameter' not in sys.argv:
    sys.argv.extend(['--require-parameter', parameter_id])
output = Path(sys.argv[sys.argv.index('--output') + 1])
harness.main()
report = json.loads(output.read_text())
report['status'] = 'coordinate_calibration_passed'
report['acceptance_complete'] = False
report['scope'] = 'Actual official Core calibration of one ORIGINAL authored parameter/drawable; all other drawable coordinates unchanged; not character art acceptance'
report['checks']['actual_core_coordinate_symmetry_and_other_mesh_negative'] = 'passed'
report['harness_variant'] = {'file': str(Path(__file__).resolve()), 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'raw_javascript_sha256': hashlib.sha256(harness.RAW_CHECK.encode()).hexdigest()}
report['reproduce_command'] = 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *original_arguments])
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'calibration': report['raw_core']['coordinateCalibration']}, ensure_ascii=False))
