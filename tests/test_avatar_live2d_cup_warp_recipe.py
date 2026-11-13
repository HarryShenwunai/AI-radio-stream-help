"""Reject false completeness and unstable source evidence before authoring."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('cupwarp', SCRIPTS / 'avatar_live2d_cup_warp_recipe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CupWarpEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.grid = {'axes': [{'id': 'A', 'keys': [-1, 0, 1]}, {'id': 'B', 'keys': [0, 1]}],
                     'samples': [{'pose': {'A': a, 'B': b}} for a in (-1, 0, 1) for b in (0, 1)]}

    def test_complete_grid_accepts_actual_cartesian_members(self):
        module.validate_observed_grid(self.grid)

    def test_equal_count_illegal_key_cannot_replace_missing_corner(self):
        bad = copy.deepcopy(self.grid)
        bad['samples'][0]['pose']['A'] = -.5
        with self.assertRaisesRegex(ValueError, 'outside'):
            module.validate_observed_grid(bad)

    def test_duplicate_missing_and_unexpected_axis_rejected(self):
        for mode in ('duplicate', 'missing', 'extra'):
            bad = copy.deepcopy(self.grid)
            if mode == 'duplicate':
                bad['samples'][0] = bad['samples'][1]
            elif mode == 'missing':
                bad['samples'].pop()
            else:
                bad['samples'][0]['pose']['C'] = 0
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.validate_observed_grid(bad)

    def test_source_drift_cannot_be_relabelled_stable_after_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.moc3'
            source.write_bytes(b'original source')
            before = module.source_fingerprints([source])
            module.assert_sources_unchanged(before)
            source.write_bytes(b'changed during evaluation')
            with self.assertRaisesRegex(ValueError, 'changed'):
                module.assert_sources_unchanged(before)
