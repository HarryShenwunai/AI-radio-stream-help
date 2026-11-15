"""Reject known bad old interface sources as well as the current checkout."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from check_ui_copy import check

class CopyContracts(unittest.TestCase):
 def test_known_bad_copy_and_preview_controls_are_rejected(self):
  bad={'app/static/room.html':'<main id="room"><button>设置</button><p>稍后继续</p></main>', 'app/static/index.html':'<input placeholder="例如：生成的内容">'}
  self.assertEqual({x[1] for x in check(bad)},{'C01','C02','C03'})
 def test_empty_preview_and_functional_labels_are_allowed(self):
  self.assertEqual(check({'app/static/room.html':'<main id="room"><p id="topic" hidden></p></main><aside><button>应用</button></aside>'}),[])
 def test_checkout_satisfies_contract(self):
  paths=[*sorted((ROOT/'app/static').glob('*.html')),*sorted((ROOT/'app/static').glob('*.js')),ROOT/'app/server.py']
  self.assertEqual(check({str(p.relative_to(ROOT)):p.read_text() for p in paths}),[])
