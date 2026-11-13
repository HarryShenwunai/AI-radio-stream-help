"""Run the separate real-Python schedule and bounded action-word checks."""
from pathlib import Path
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source=ROOT/'tests/test_formal_boundaries.py'
    spec=importlib.util.spec_from_file_location('formal_boundary_checks',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    files=['app/server.py','src/companion_runtime/playback.py','tests/test_formal_boundaries.py']
    before={name:sha(ROOT/name) for name in files}
    log=ROOT/'review/formal-models/logs/implementation.txt';log.parent.mkdir(exist_ok=True)
    started=time.monotonic()
    with log.open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    after={name:sha(ROOT/name) for name in files}
    report={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'kind':'actual Python implementation, controlled thread schedules and exhaustive bounded action words',
        'tests_run':result.testsRun,'passed':result.wasSuccessful() and before==after,'source_changed_during_check':before!=after,
        'elapsed_seconds':round(time.monotonic()-started,3),
        'playback':{'alphabet':list(module.ACTION_ALPHABET),**module.PROPERTY_RESULT,
                    'all_shorter_words_checked_as_prefixes':True,'nonce_values_are_random_but_action_words_are_deterministic':True,
                    'merge_persistence_permutations_checked':6,
                    'real_sqlite_persistence_permutations_checked':6},
        'actual_scheduler_cases':module.SCHEDULER_RESULT,
        'source_sha256_before':before,'source_sha256_after':after,
        'log':str(log.relative_to(ROOT)),
        'scope_limits':['Bounded 11-action alphabet to depth five, not all Python executions.',
            'The two legacy negative controls transform only an in-memory AST copy of one mutex boundary; production source is unchanged.',
            'No real LLM, sound hardware, WebGL, account, external message, Windows or CUDA tested.',
            'This is not proof that a human heard or understood playback.'],
        'reproduce':'python review/formal-models/run_implementation.py'}
    (ROOT/'review/formal-implementation-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('tests_run','passed','source_changed_during_check','elapsed_seconds','playback')}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
