"""Opt-in actual local-model preference/advice acceptance, no model replacement.

Synthetic user data only. Does not prove Windows, a visual model, human advice
quality, hardware capability or live account delivery. Run with existing model
paths; this script never downloads weights or calls a remote service.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_files = ['app/server.py', 'src/companion_runtime/preference_learning.py',
                    'src/companion_runtime/assistance.py']
    hashes = lambda: {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files}
    report = {'observed_at':datetime.now(timezone.utc).isoformat(), 'models_mocked':False,
              'scope':'actual local Qwen via real host preference/advice adapters; synthetic inputs',
              'windows_or_rtx4060_verified':False, 'human_advice_quality_accepted':False,
              'visual_inference_tested':False, 'source_sha256_before':hashes(), 'checks':{}}
    started = time.monotonic()
    try:
        spec = importlib.util.spec_from_file_location('real_product_app', ROOT/'app/server.py')
        app = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = app
        spec.loader.exec_module(app)
        with tempfile.TemporaryDirectory(prefix='real-product-services-') as folder:
            app.DATA = Path(folder)
            app.init()
            app.set_settings({'engine':'local', 'memory_mode':'relevant', 'local_compute':'cpu'})
            assert app.MODEL.is_file(), 'Existing weights required; no automatic download'
            report['model_filename'] = app.MODEL.name
            report['model_bytes'] = app.MODEL.stat().st_size
            with app.db() as connection:
                cursor = connection.execute("INSERT INTO messages(role,text,created,kind) VALUES('user',?,?,'chat')",
                    ('我喜欢清淡的晚餐。\n我希望你不要连续追问。', app.now()))
                source_id = cursor.lastrowid
            request_started = time.monotonic()
            preferences = app.preference_request('collect', {'request_id':'real-preferences-1',
                'source_message_ids':[source_id], 'expected_character_id':app.profile_id()})
            report['preferences_seconds'] = round(time.monotonic()-request_started, 3)
            report['preference_result'] = preferences
            assert preferences['status'] == 'proposed', preferences
            assert preferences['candidates'], 'Actual model selected no explicit source'
            for candidate in preferences['candidates']:
                assert candidate['text'] in {'我喜欢清淡的晚餐。', '我希望你不要连续追问。'}
            report['checks']['real_model_selects_exact_explicit_user_sources'] = True
            assert not app.state()['memories'], 'Candidate unexpectedly persisted before approval'
            candidate = preferences['candidates'][0]
            app.preference_request('decision', {'candidate_id':candidate['candidate_id'], 'decision':'confirm'})
            memories = app.state()['memories']
            assert len(memories) == 1 and memories[0]['text'] == candidate['text']
            report['checks']['explicit_confirmation_persists_only_exact_source'] = True
            app.set_settings({'memory_mode':'off'})
            try:
                app.preference_request('collect', {'request_id':'must-not-infer','source_message_ids':[source_id]})
                raise AssertionError('Disabled memory still collected preferences')
            except app.PreferenceLearningError as error:
                assert error.code == 'memory_disabled'
            report['checks']['memory_off_blocks_learning'] = True
            request_started = time.monotonic()
            advice = app.assistance_request('proposals', {'request_id':'real-dinner-1', 'kind':'dinner',
                'inputs':{'query':'我有豆腐、西兰花和米饭，请用两句话建议一顿清淡晚餐，不要提问。'}})['proposal']
            report['advice_seconds'] = round(time.monotonic()-request_started, 3)
            report['advice_result'] = advice
            assert advice['status'] == 'proposed' and advice['summary'].strip(), advice
            assert advice['permission_scope'] == 'read_only' and not advice['result']['external_actions']
            assert not app.state()['tasks']
            report['checks']['real_local_advice_without_tools_or_memory_requirement'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    report['source_sha256_after'] = hashes()
    report['sources_unchanged'] = report['source_sha256_before'] == report['source_sha256_after']
    report['elapsed_seconds'] = round(time.monotonic()-started, 3)
    report['passed'] = not report.get('error') and report['sources_unchanged']
    path = Path(os.environ.get('COMPANION_SERVICE_REPORT', str(ROOT/'review/real-product-services-check.json')))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'passed':report['passed'], 'checks':report['checks'], 'error':report.get('error'),
                      'elapsed_seconds':report['elapsed_seconds'], 'report':str(path)}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
