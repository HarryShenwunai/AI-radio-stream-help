"""Predicate/CLI counterexamples only; no browser, Core or model inference claim."""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
from types import SimpleNamespace
import unittest
import zipfile

from program_output_browser import mouth_drawable_from_package, mouth_drawable_observation, validate_mouth_gate_options


class ProgramMouthAcceptanceTests(unittest.TestCase):
    def options(self, **changes):
        return SimpleNamespace(**({'require_visible_mouth': True, 'completion': True, 'expect_expiry': False,
                                  'expect_budget_rejection': False, 'offline_preflight': False} | changes))

    def diagnostics(self, opacity, *, lip=.6, available=True):
        return {'available': available, 'lipSyncValue': lip, 'drawables': [{'id': 'mesh-from-package', 'opacity': opacity}]}

    def test_parameter_motion_with_invisible_drawable_is_rejected(self):
        self.assertFalse(mouth_drawable_observation(self.diagnostics(0), 'mesh-from-package', speaking=True)['passed'])
        self.assertTrue(mouth_drawable_observation(self.diagnostics(.3), 'mesh-from-package', speaking=True)['passed'])
        self.assertFalse(mouth_drawable_observation(self.diagnostics(.3, lip=0), 'mesh-from-package', speaking=True)['passed'])

    def test_terminal_requires_real_available_drawable_at_exact_zero(self):
        self.assertTrue(mouth_drawable_observation(self.diagnostics(0, lip=0), 'mesh-from-package', speaking=False)['passed'])
        for diagnostics in [self.diagnostics(.001, lip=0), self.diagnostics(0, lip=0, available=False),
                            {'available': True, 'lipSyncValue': 0}, {'available': True, 'lipSyncValue': 0, 'drawables': None}]:
            with self.subTest(diagnostics=diagnostics):
                self.assertFalse(mouth_drawable_observation(diagnostics, 'mesh-from-package', speaking=False)['passed'])

    def test_missing_ambiguous_and_nonfinite_observations_are_rejected(self):
        cases = [self.diagnostics(float('nan')), self.diagnostics(float('inf')), self.diagnostics(True),
                 self.diagnostics(.5, lip=float('nan')), self.diagnostics(.5, available=False),
                 {'available': True, 'lipSyncValue': .5, 'drawables': []},
                 {'available': True, 'lipSyncValue': .5, 'drawables': [{'id': 'mesh-from-package', 'opacity': .5}]*2}]
        for diagnostics in cases:
            with self.subTest(diagnostics=diagnostics):
                self.assertFalse(mouth_drawable_observation(diagnostics, 'mesh-from-package', speaking=True)['passed'])

    def test_visible_gate_requires_completion_and_a_positive_run(self):
        validate_mouth_gate_options(self.options())
        validate_mouth_gate_options(self.options(require_visible_mouth=False, completion=False))
        with self.assertRaisesRegex(ValueError, 'requires --completion'):
            validate_mouth_gate_options(self.options(completion=False))
        for flag in ['expect_expiry', 'expect_budget_rejection', 'offline_preflight']:
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'positive-program'):
                validate_mouth_gate_options(self.options(**{flag: True}))

    def test_cli_rejects_stop_mode_before_loading_missing_model(self):
        with tempfile.TemporaryDirectory() as root:
            command = [sys.executable, str(Path(__file__).with_name('program_output_browser.py')), '--chrome', 'not-used',
                       '--model', str(Path(root)/'missing.zip'), '--runtime-dir', str(Path(root)/'missing-runtime'),
                       '--out', str(Path(root)/'out'), '--require-visible-mouth']
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires --completion', result.stderr)
            self.assertNotIn('FileNotFoundError', result.stderr)

    def package(self, root, rows, *, display=True):
        package = Path(root)/'model.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('rig/model.model3.json', json.dumps({'FileReferences': {'DisplayInfo': 'info.cdi3.json'} if display else {}}))
            archive.writestr('rig/info.cdi3.json', json.dumps({'Drawables': rows}))
        return package

    def test_package_mapping_uses_actual_cdi_id_not_a_hardcoded_r3_id(self):
        with tempfile.TemporaryDirectory() as root:
            package = self.package(root, [{'Id': 'DifferentActualId', 'Name': 'Mouth_open'}])
            mapping = mouth_drawable_from_package(package)
            self.assertEqual(mapping['id'], 'DifferentActualId')
            self.assertEqual(mapping['display_info'], 'rig/info.cdi3.json')
            self.assertEqual(len(mapping['display_info_sha256']), 64)

    def test_missing_or_ambiguous_package_mapping_never_gets_a_default(self):
        rows = [[], [{'Id': 'A', 'Name': 'Mouth_open'}, {'Id': 'B', 'Name': 'Mouth_open'}],
                [{'Id': 'A', 'Name': 'Mouth_open'}, {'Id': 'A', 'Name': 'Hair'}]]
        for values in rows:
            with self.subTest(rows=values), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):mouth_drawable_from_package(self.package(root, values))
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'DisplayInfo'):
            mouth_drawable_from_package(self.package(root, [], display=False))


if __name__ == '__main__':
    unittest.main()
