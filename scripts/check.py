"""Run local regression and protocol tests; never connects platform accounts."""
from pathlib import Path
import datetime as dt
import json
import os
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'app')]
loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.discover(str(ROOT / 'app'), pattern='test_*.py'))
suite.addTests(unittest.TestLoader().discover(str(ROOT / 'tests'), pattern='test_*.py'))
started = time.monotonic()
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = {
    'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
    'scope': 'local regression, character catalog/assets, isolated HTTP and protocol checks',
    'tests_run': result.testsRun,
    'failures': [{'test': str(t), 'traceback': tb} for t, tb in result.failures],
    'errors': [{'test': str(t), 'traceback': tb} for t, tb in result.errors],
    'skipped': [{'test': str(t), 'reason': why} for t, why in result.skipped],
    'elapsed_seconds': round(time.monotonic() - started, 3),
    'passed': result.wasSuccessful(),
    'upstream_or_platform_tests_executed': 0,
    'does_not_verify': ['Zerolan deployment', 'real live room', 'user hardware', 'AR or MC execution', 'long-term character quality'],
}
report_dir = Path(os.environ.get('COMPANION_REPORT_DIR', str(ROOT / 'review')))
report_dir.mkdir(parents=True, exist_ok=True)
(report_dir / 'character-regression.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
