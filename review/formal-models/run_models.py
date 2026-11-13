"""Run real TLC on the finite models, preserving expected counterexamples."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MODELS = Path(__file__).resolve().parent
JAR_SHA256 = '936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88'
CASES = [
    ('Dispatch-fixed', True, 'current atomically registered and cleared public model slot'),
    ('Dispatch-legacy-startup', False, 'regression: public lock acquired before handle becomes visible'),
    ('Dispatch-legacy-cleanup', False, 'regression: handle cleared before public lock release'),
    ('Dispatch-mutant-commit', False, 'sensitivity control: cancel may interleave between approval and append'),
    ('Dispatch-mutant-no-priority', False, 'sensitivity control: new public work may overtake a private waiter'),
    ('Playback-fixed', True, 'full initial completion plus replay/scope switch and arbitrary persistence order'),
    ('Playback-short-prefix', True, 'first synthesis covers a strict prefix, second may cover full message'),
    ('Playback-mutant-last-write', False, 'sensitivity control: naive last-write loses earlier confirmed prefix'),
    ('Playback-mutant-stale', False, 'sensitivity control: stale scope/nonce receipt may be accepted'),
    ('Playback-mutant-terminal', False, 'sensitivity control: stopped attempt may be revived'),
    ('Perception-fixed', True, 'bounded owner consent, two sessions, role/appearance epoch and late provider result'),
    ('Perception-mutant-late', False, 'sensitivity control: accept a frame after stop/scope/device invalidation'),
    ('Perception-mutant-owner', False, 'sensitivity control: plugin ingress may start a private capture'),
    ('Perception-mutant-consent', False, 'sensitivity control: a declared device is treated as capture consent'),
]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar',type=Path,default=Path(os.environ.get('TLA2TOOLS_JAR','/workspace/.formal-tools/tla2tools-1.7.4.jar')))
    parser.add_argument('--output',type=Path,default=ROOT/'review/formal-model-check.json')
    args=parser.parse_args()
    preflight = None
    if not args.jar.is_file():
        preflight = 'Missing official tla2tools.jar. Provide --jar or TLA2TOOLS_JAR; no automatic download is performed. See review/formal-models/README.md.'
    elif sha(args.jar) != JAR_SHA256:
        preflight = 'Tool SHA256 differs from the pinned observed official v1.7.4 asset; refusing to execute it.'
    elif shutil.which('java') is None:
        preflight = 'Java is missing. Install a supported Java runtime explicitly; no automatic installation is performed.'
    if preflight:
        report = {'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'passed':False,
                  'status':'preflight_failed', 'error':preflight, 'cases':[],
                  'jar_path':str(args.jar), 'pinned_sha256':JAR_SHA256,
                  'jar_sha256_observed':sha(args.jar) if args.jar.is_file() else None}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        raise SystemExit(2)
    logs=MODELS/'logs';logs.mkdir(exist_ok=True)
    checks=[]
    source_files = [ROOT/name for name in ('app/server.py','src/companion_runtime/playback.py',
        'src/companion_runtime/perception.py','src/companion_runtime/perception_tracking.py','src/companion_runtime/devices.py')]
    source_files += [Path(__file__).resolve(), *MODELS.glob('*.tla'), *MODELS.glob('*.cfg')]
    before = {str(path.relative_to(ROOT)):sha(path) for path in source_files}
    with tempfile.TemporaryDirectory(prefix='companion-tlc-') as temp:
        for name,expected_safe,description in CASES:
            spec=name.split('-',1)[0]
            command=['java','-Xmx512m','-XX:+UseParallelGC','-cp',str(args.jar.resolve()),'tlc2.TLC',
                     '-workers','1','-seed','20261112','-fp','0','-config',str(MODELS/(name+'.cfg')),
                     '-metadir',str(Path(temp)/name),str(MODELS/(spec+'.tla'))]
            try:
                result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=45)
                return_code, text = result.returncode, result.stdout+result.stderr
            except (OSError,subprocess.TimeoutExpired) as error:
                return_code, text = 124, str(error)
            log=logs/(name+'.txt');log.write_text(text,encoding='utf-8')
            safe=return_code==0 and 'Model checking completed. No error has been found.' in text
            counterexample='Invariant Safety is violated' in text and 'The behavior up to this point is:' in text
            match=re.search(r'([\d,]+) states generated, ([\d,]+) distinct states found, ([\d,]+) states left on queue',text)
            counts=dict(zip(('generated','distinct','queue_left'),[int(n.replace(',','')) for n in match.groups()])) if match else None
            depth=re.search(r'depth of the complete state graph search is (\d+)',text)
            checks.append({'case':name,'description':description,'expected_safe':expected_safe,'safe':safe,
                'counterexample_found':counterexample,'passed':safe if expected_safe else counterexample,
                'return_code':return_code,'states':counts,'reported_search_depth':int(depth.group(1)) if depth else None,
                'command':command,'log':str(log.relative_to(ROOT)), 'config_sha256':sha(MODELS/(name+'.cfg'))})
    after = {str(path.relative_to(ROOT)):sha(path) for path in source_files}
    report={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'kind':'real TLA+/TLC finite-state model checking; not a full-program proof',
            'tool':{'name':'TLC','release':'tlaplus/tlaplus v1.7.4','reported_engine':'2.19 (2024-08-08)',
                    'source':'https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar',
                    'sha256_observed':sha(args.jar),'pinned_sha256':JAR_SHA256,
                    'official_published_digest':False,'java_version':subprocess.run(['java','-version'],capture_output=True,text=True).stderr.splitlines()[0]},
            'scope':{'perception':'two session starts, two scope epoch changes, one in-flight frame, owner/plugin callers, consent and camera availability; uncooperative provider may return late',
                     'dispatch':'one public attempt, one private attempt, one optional stop, primitive model mutex assumed correct',
                     'playback':'one owner, two attempts of same full text, one role/appearance switch, arbitrary finite receipt-persistence order',
                     'safety_only':True,'deadlock_check':False,'liveness_proved':False,'hash_unforgeability_proved':False,
                     'implementation_refinement_proved':False},
            'cases':checks,'passed':before == after and all(case['passed'] for case in checks),
            'source_changed_during_check':before != after,
            'source_sha256_before':before,'source_sha256_after':after,
            'spec_sha256':{p.name:sha(p) for p in MODELS.glob('*.tla')},
            'implementation_review_snapshot':{name:sha(ROOT/name) for name in ('app/server.py','src/companion_runtime/playback.py',
                'src/companion_runtime/perception.py','src/companion_runtime/perception_tracking.py','src/companion_runtime/devices.py')},
            'remaining_limits':['No equivalence proof from Python to TLA+; source mapping and separate real-code tests are required.',
                'No unbounded multi-owner/multi-provider progress, C/CUDA behavior, sockets, UI, Windows hardware or platform/account verification.',
                'TLC uses 64-bit state fingerprints; consult raw logs for calculated collision estimates.',
                'Counterexamples for legacy/mutant specifications are deliberate negative controls, not current production failures.'],
            'reproduce':'python review/formal-models/run_models.py --jar /path/to/official/tla2tools.jar'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(checks),'output':str(args.output),
                      'safe_cases':[x['case'] for x in checks if x['safe']],
                      'counterexamples':[x['case'] for x in checks if x['counterexample_found']]}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
