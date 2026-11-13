import ast
from pathlib import Path
import tempfile
import unittest

class EyeSourceIntegrityTests(unittest.TestCase):
 def test_audit23_existing_paintings_survive_without_download_chunks(self):
  tree=ast.parse((Path(__file__).resolve().parents[1]/'scripts/r3_both_eyes/prepare_layers.py').read_text())
  loop=next(n for n in tree.body if isinstance(n,ast.For))
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name in ['both_closed_clean','both_white_clean']:(root/(name+'.png')).write_bytes(b'original-painting')
   exec(compile(ast.Module(body=[loop],type_ignores=[]),'<chunk-restore>','exec'),{'P':root})
   for name in ['both_closed_clean','both_white_clean']:self.assertEqual((root/(name+'.png')).read_bytes(),b'original-painting')

