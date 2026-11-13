import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('quality_contract',Path(__file__).resolve().parents[1]/'scripts/quality_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
def invoke(root,full=False,timeout=False):
 report=root/'result.json';count=0
 def run(command,**kwargs):
  nonlocal count
  count+=1
  if timeout and count==1:raise subprocess.TimeoutExpired(command,600,output=b'partial-stdout-marker',stderr=b'partial-stderr-marker')
  return subprocess.CompletedProcess(command,0,stdout='fixture',stderr='')
 with patch.object(sys,'argv',['quality_gate','--report',str(report)]+(['--full'] if full else [])),patch.object(gate,'source_hashes',return_value={}),patch.object(gate.subprocess,'run',side_effect=run),patch.object(gate.importlib.metadata,'version',return_value='fixture'):
  result=gate.main()
 return result,json.loads(report.read_text())

class RegressionEvidenceTests(unittest.TestCase):
 def test_audit24_missing_regression_report_fails_full_gate(self):
  with tempfile.TemporaryDirectory() as d:
   code,report=invoke(Path(d),full=True)
   self.assertEqual(code,1);self.assertFalse(report['passed'])

