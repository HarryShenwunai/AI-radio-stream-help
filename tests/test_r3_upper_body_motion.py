import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('upper_body', Path(__file__).resolve().parents[1] / 'scripts/build_r3_upper_body_motion.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UpperBodyMotionTest(unittest.TestCase):
    def test_retired_actions_removed_other_actions_and_assets_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'motions').mkdir()
            refs = {'Moc': 'model.moc3', 'Textures': ['original.png'], 'Motions': {
                'Review': [{'File': 'motions/R3_review.motion3.json'}, {'File': 'motions/other.motion3.json'}],
                'GentleLower': [{'File': 'motions/R3_lower_eased.motion3.json'}],
                'Custom': [{'File': 'motions/other.motion3.json'}],
            }}
            (root / 'model.model3.json').write_text(json.dumps({'Version': 3, 'FileReferences': refs}))
            for name in ['model.moc3', 'original.png', 'motions/other.motion3.json',
                         'motions/R3_review.motion3.json', 'motions/R3_lower_eased.motion3.json']:
                (root / name).write_bytes(b'original')
            module.build(root)
            first = (root / 'model.model3.json').read_bytes()
            module.build(root)
            self.assertEqual(first, (root / 'model.model3.json').read_bytes())
            motions = json.loads(first)['FileReferences']['Motions']
            self.assertNotIn('GentleLower', motions)
            self.assertEqual(motions['Review'], refs['Motions']['Custom'])
            for name in ['model.moc3', 'original.png', 'motions/other.motion3.json']:
                self.assertEqual((root / name).read_bytes(), b'original')
            self.assertFalse((root / 'motions/R3_review.motion3.json').exists())
            self.assertFalse((root / 'motions/R3_lower_eased.motion3.json').exists())
            clip = json.loads((root / 'motions/R3_upper_body.motion3.json').read_text())
            tracks = {c['Id']: [c['Segments'][1], *c['Segments'][4::3]] for c in clip['Curves']}
            self.assertEqual(set(tracks['ParamCupLower']), {0})
            self.assertEqual(set(tracks['ParamCupVisible']), {1})
            self.assertLessEqual(max(map(abs, tracks['ParamAngleZ'])), 2)
            self.assertEqual(min(tracks['ParamEyeROpen']), 0)
            for values in tracks.values():
                self.assertEqual(values[0], values[-1])

    def test_both_eyes_are_opt_in_and_synchronized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'model.model3.json').write_text(json.dumps({'FileReferences': {}}))
            module.build(root)
            read_tracks = lambda: {c['Id']: c['Segments'] for c in json.loads((root / 'motions/R3_upper_body.motion3.json').read_text())['Curves']}
            self.assertNotIn('ParamEyeLOpen', read_tracks())
            module.build(root, bound_both_eyes=True, bound_gaze=True, bound_breath=True)
            tracks = read_tracks()
            self.assertEqual(tracks['ParamEyeLOpen'], tracks['ParamEyeROpen'])
            self.assertIn('ParamEyeBallX', tracks)
            self.assertIn('ParamEyeBallY', tracks)
            encoded = tracks['ParamEyeROpen']
            points = [(encoded[0], encoded[1]), *[(encoded[i + 1], encoded[i + 2]) for i in range(2, len(encoded), 3)]]
            closing = [(t, v) for t, v in points if 2.1 <= t <= 2.2]
            self.assertGreater(len(closing), 3)
            self.assertTrue(all(a[1] >= b[1] for a, b in zip(closing, closing[1:])))
            rates = [abs((b[1] - a[1]) / (b[0] - a[0])) for a, b in zip(closing, closing[1:])]
            self.assertLess(rates[0], max(rates))
            self.assertLess(rates[-1], max(rates))


if __name__ == '__main__':
    unittest.main()
