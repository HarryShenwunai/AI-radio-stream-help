"""One-pass local driver verification. No installs, inference or external service.

The caller supplies the existing lo-only namespace launcher and licensed local
runtime. Run only in the coordinated Core window; no automatic retries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--owner-local',type=Path,required=True)
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONPATH':str(ROOT/'src')+os.pathsep+str(ROOT/'tests')}
    report={'scope':'Node plus actual local Core driver checks; not Windows or final visual acceptance','commands':[],'passed':False}
    stages=[('node',['node','--test','tests/test_live2d_motion_ownership.mjs','tests/test_live2d_adapter_ui.mjs'])]
    for name,script in [('natural','audience_motion_adapter.py'),('controlled','audience_motion_comparison.py')]:
        output=(args.out/name).resolve()
        command=[sys.executable,str(args.launcher.resolve()),'--evidence',str(output/'namespace.json'),'--',sys.executable,str(ROOT/'tests'/script),
                 '--model',str(args.model.resolve()),'--owner-local',str(args.owner_local.resolve()),'--chrome',args.chrome,'--out',str(output)]
        stages.append((name,command))
    try:
        for name,command in stages:
            with (args.out/(name+'.log')).open('w') as log:
                result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,close_fds=True)
            report['commands'].append({'stage':name,'exit_code':result.returncode,'command':command})
            if result.returncode:raise RuntimeError(name+' failed; inspect retained log/report, no retry performed')
        report['passed']=True
    except Exception as error:
        report['failure']=str(error)
    finally:
        report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'frontend/live2d-renderer.mjs',ROOT/'app/static/live2d-renderer.js',*(ROOT/'tests'/name for name in ['test_live2d_motion_ownership.mjs','test_live2d_adapter_ui.mjs','audience_motion_probe.html','audience_motion_adapter_probe.html','audience_motion_comparison.py','audience_motion_adapter.py','audience_motion_verify.py'])]}
        (args.out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':report['passed'],'failure':report.get('failure'),'output':str(args.out.resolve())},ensure_ascii=False))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
