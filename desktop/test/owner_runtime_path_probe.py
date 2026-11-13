"""Actual Linux Electron readonly owner-path CLI; no window/backend startup."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]

def main():
    files=[ROOT/'desktop/main.cjs',ROOT/'desktop/owner-runtime-path.cjs']
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    report={'passed':False,'scope':'Real Linux Electron readonly CLI; no Windows execution','checks':[]}
    with tempfile.TemporaryDirectory(prefix='owner-runtime-path-') as directory:
        directory=Path(directory);display=':196';auth=directory/'Xauthority'
        subprocess.run(['xauth','-f',str(auth),'add',display,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],capture_output=True,check=True);auth.chmod(0o600)
        env={**os.environ,'DISPLAY':display,'XAUTHORITY':str(auth)}
        xvfb=subprocess.Popen(['/workspace/.desktop-tools/xvfb/usr/bin/Xvfb',display,'-screen','0','800x600x24','-nolisten','tcp','-auth',str(auth)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            time.sleep(.3);marker=directory/'backend-must-not-start';stub=directory/'backend-sentinel'
            stub.write_text('#!/bin/sh\nprintf invoked > "'+str(marker)+'"\nexit 7\n');stub.chmod(0o700)
            for key in ['COMPANION_DATA','COMPANION_LIVE2D_RUNTIME']:env.pop(key,None)
            env['COMPANION_PYTHON']=str(stub)
            cases=[({},directory/'用户 profile'/'profile-data',directory/'用户 profile'/'profile-data/live2d-runtime'),
                   ({'COMPANION_DATA':'relative profile','COMPANION_LIVE2D_RUNTIME':'relative runtime'},ROOT/'relative profile',ROOT/'relative runtime')]
            for overrides,data,runtime in cases:
                command=[str(ROOT/'desktop/node_modules/electron/dist/electron'),str(ROOT/'desktop'),'--owner-runtime-path','--user-data-dir='+str(directory/'用户 profile'),'--disable-gpu']
                result=subprocess.run(command,env={**env,**overrides},capture_output=True,text=True,encoding='utf-8',timeout=12)
                values=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
                assert result.returncode==0,(result.returncode,result.stderr[-1000:]);assert len(values)==1,values
                value=values[0];assert value['data_root']==str(data) and value['live2d_runtime_root']==str(runtime),value
                assert value['backend_started'] is False and value['window_count']==0 and not marker.exists(),value
                report['checks'].append({'overrides':overrides,'passed':True,'output':value})
            report['passed']=True
        except Exception as error:report['error']=str(error)
        finally:
            xvfb.terminate();xvfb.wait(timeout=5)
    after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    report['source_sha256']=after;report['sources_unchanged_during_checks']=before==after
    report['passed']=report['passed'] and before==after
    (ROOT/'review/owner-runtime-path-native-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
