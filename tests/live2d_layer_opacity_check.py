"""Actual Core opacity gate: author visibility/export settings are not evidence."""
import argparse
import base64
import hashlib
import json
import shlex
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from live2d_original_core_check import installed_script

parser = argparse.ArgumentParser(description=__doc__)
for name in ['model', 'runtime-dir', 'hidden-id', 'shown-id', 'sweep-param', 'output']:
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
model = Path(args.model).resolve()
moc = model.parent / json.loads(model.read_text())['FileReferences']['Moc']
core = installed_script(Path(args.runtime_dir), 'core')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
paths = [model, moc, core, Path(__file__).resolve()]
sources = {str(p): sha(p) for p in paths}
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
    page = browser.new_page()
    page.add_script_tag(content='(function(){var WebAssembly={};\n' + core.read_text() + '\nwindow.Live2DCubismCore=Live2DCubismCore;})();')
    measurement = page.evaluate(r'''args=>{
      const C=Live2DCubismCore,bytes=Uint8Array.from(atob(args.bytes),v=>v.charCodeAt(0));
      if(C.Moc.prototype.hasMocConsistency(bytes.buffer)!==1)throw Error('Actual Core consistency rejected');
      const moc=C.Moc.fromArrayBuffer(bytes.buffer),raw=C.Model.fromMoc(moc),p=raw.parameters,d=raw.drawables;
      const parameter=p.ids.indexOf(args.parameter),hidden=d.ids.indexOf(args.hidden),shown=d.ids.indexOf(args.shown);
      if(parameter<0||hidden<0||shown<0||hidden===shown)throw Error('Declared actual IDs missing/aliased');
      const low=p.minimumValues[parameter],high=p.maximumValues[parameter],rows=[];
      for(const value of new Set([low,p.defaultValues[parameter],low+.37*(high-low),high])){p.values.set(p.defaultValues);p.values[parameter]=value;raw.update();rows.push({parameter:args.parameter,requested:value,actual:p.values[parameter],hiddenId:args.hidden,hiddenOpacity:d.opacities[hidden],shownId:args.shown,shownOpacity:d.opacities[shown]});}
      const result={coreVersion:C.Version.csmGetVersion(),rows};raw.release();moc._release();return result;
    }''', {'bytes': base64.b64encode(moc.read_bytes()).decode(), 'parameter': args.sweep_param, 'hidden': args.hidden_id, 'shown': args.shown_id})
    browser.close()
passed = all(v['hiddenOpacity'] == 0 and v['shownOpacity'] == 1 for v in measurement['rows'])
report = {'status': 'passed' if passed else 'failed', 'sources': sources,
          'sources_unchanged': all(sha(Path(p)) == value for p, value in sources.items()),
          'measurement': measurement, 'not_proven': ['Actual material look/coverage', 'All continuous parameter states'],
          'reproduce_command': 'PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright ' + shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])}
Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'sources_unchanged': report['sources_unchanged'], 'measurement': measurement}))
raise SystemExit(0 if passed else 2)
