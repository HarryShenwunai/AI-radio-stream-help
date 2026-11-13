"""Compare two original exports through actual Core, never inferred author settings."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from live2d_joint_poses import joint_combinations, joint_interiors
from live2d_original_core_check import installed_script


parser = argparse.ArgumentParser(description=__doc__)
for name in ['before', 'after', 'runtime-dir', 'output']:
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
models = [Path(args.before).resolve(), Path(args.after).resolve()]
mocs = [p.parent / json.loads(p.read_text())['FileReferences']['Moc'] for p in models]
core = installed_script(Path(args.runtime_dir).resolve(), 'core')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
paths = [*models, *mocs, core, Path(__file__).resolve(), Path(__file__).with_name('live2d_joint_poses.py')]
sources = {str(p): sha(p) for p in paths}
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
    page = browser.new_page()
    page.add_script_tag(content='(function(){var WebAssembly={};\n' + core.read_text() + '\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
    parameters = page.evaluate(r'''encoded=>{
      const C=Live2DCubismCore,b=Uint8Array.from(atob(encoded),v=>v.charCodeAt(0));
      if(C.Moc.prototype.hasMocConsistency(b.buffer)!==1)throw Error('Actual Core consistency rejected');
      const moc=C.Moc.fromArrayBuffer(b.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters;
      const rows=Array.from(p.ids,(id,i)=>({id,min:p.minimumValues[i],default:p.defaultValues[i],max:p.maximumValues[i]}));
      raw.release();moc._release();return rows;
    }''', base64.b64encode(mocs[0].read_bytes()).decode())
    poses = [{'name': 'actual-defaults', 'parameters': {}}]
    for item in parameters:
        if item['id'] in {'ParamArmL', 'ParamArmR', 'ParamForearmL', 'ParamForearmR'}:
            poses += [{'name': item['id'] + '-' + end, 'parameters': {item['id']: item[end]}} for end in ['min', 'max']]
    poses += joint_combinations(parameters) + joint_interiors(parameters)
    measurement = page.evaluate(r'''args=>{
      const C=Live2DCubismCore,models=args.bytes.map(encoded=>{const bytes=Uint8Array.from(atob(encoded),v=>v.charCodeAt(0));if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core consistency rejected');const moc=C.Moc.fromArrayBuffer(bytes.buffer);return {moc,raw:C.Model.fromMoc(moc)};});
      const [a,b]=models.map(v=>v.raw);if(JSON.stringify(a.parameters.ids)!==JSON.stringify(b.parameters.ids)||JSON.stringify(a.drawables.ids)!==JSON.stringify(b.drawables.ids))throw Error('Parameter/drawable identity changed; cannot use exact same-topology comparator');
      const result=[];for(const pose of args.poses){for(const {raw}of models){raw.parameters.values.set(raw.parameters.defaultValues);for(const [id,value]of Object.entries(pose.parameters)){const i=raw.parameters.ids.indexOf(id);if(i<0)throw Error('Missing pose ID');raw.parameters.values[i]=value;}raw.update();}
        const changed=[];for(let i=0;i<a.drawables.count;i++){const v=a.drawables.vertexPositions[i],w=b.drawables.vertexPositions[i];if(v.length!==w.length||JSON.stringify(Array.from(a.drawables.indices[i]))!==JSON.stringify(Array.from(b.drawables.indices[i])))throw Error('Topology changed; corresponding coordinates are not comparable');let count=0,max=0;for(let j=0;j<v.length;j++){if(!Number.isFinite(v[j])||!Number.isFinite(w[j]))throw Error('Nonfinite Core vertex');if(v[j]!==w[j])count++;max=Math.max(max,Math.abs(v[j]-w[j])*a.canvasinfo.PixelsPerUnit);}const opacity=Math.abs(a.drawables.opacities[i]-b.drawables.opacities[i]);if(count||opacity)changed.push({id:a.drawables.ids[i],exactDifferentCoordinates:count,maxCoordinateDifferenceSourcePx:max,opacityDifference:opacity});}
        result.push({...pose,changedDrawables:changed});}
      for(const item of models){item.raw.release();item.moc._release();}return result;
    }''', {'bytes': [base64.b64encode(p.read_bytes()).decode() for p in mocs], 'poses': poses})
    browser.close()
report = {'status': 'actual_same_topology_core_comparison_measured', 'sources': sources,
          'sources_unchanged': all(sha(Path(p)) == digest for p, digest in sources.items()),
          'poses': measurement, 'all_exact_same': all(not p['changedDrawables'] for p in measurement),
          'not_proven': ['Continuous state space', 'Authoring glue mechanism or why exports agree', 'Pixel/texture equivalence', 'Art acceptance']}
Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'all_exact_same': report['all_exact_same'], 'poses': len(measurement), 'sources_unchanged': report['sources_unchanged']}))
