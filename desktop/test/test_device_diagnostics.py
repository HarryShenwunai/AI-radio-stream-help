"""Diagnostic boundaries using synthetic data, never target GPU measurements."""
from pathlib import Path
import subprocess,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from companion_runtime.device_diagnostics import parse_nvidia_csv,_nvidia_snapshot

class HardwareBoundaries(unittest.TestCase):
    def test_gpu_snapshot_policy_and_budget_are_explicit(self):
        value=parse_nvidia_csv('NVIDIA GeForce RTX 4060,8188,7000,560.94')[0]
        self.assertTrue(value['cuda124_conservative_driver_policy_met']);self.assertEqual(value['model_budget_after_renderer_reserve_mib'],4952)
        self.assertFalse(parse_nvidia_csv('Synthetic GPU,8192,4096,528.33')[0]['cuda124_conservative_driver_policy_met'])
    def test_nonfinite_negative_overfull_and_extra_fields_are_rejected(self):
        for row in ['GPU,NaN,0,560.94','GPU,Infinity,0,560.94','GPU,1e999,0,560.94','GPU,8192,-1,560.94','GPU,8192,9000,560.94','GPU,8,4,560.94,unexpected']:
            with self.subTest(row=row),self.assertRaises(ValueError):parse_nvidia_csv(row)
    def test_unavailable_and_timeout_are_bounded_without_process_query(self):
        with patch('companion_runtime.device_diagnostics.shutil.which',return_value=None),patch('companion_runtime.device_diagnostics.subprocess.run') as run:
            if sys.platform!='win32':self.assertEqual(_nvidia_snapshot()['reason'],'nvidia_smi_unavailable');run.assert_not_called()
        with tempfile.NamedTemporaryFile() as fixture,patch('companion_runtime.device_diagnostics.shutil.which',return_value=fixture.name),patch('companion_runtime.device_diagnostics.subprocess.run',side_effect=subprocess.TimeoutExpired('probe',3)) as run:
            value=_nvidia_snapshot();self.assertEqual(value['reason'],'nvidia_query_timeout')
            self.assertEqual(run.call_args.args[0][1:],["--query-gpu=name,memory.total,memory.free,driver_version","--format=csv,noheader,nounits"])
            self.assertEqual(run.call_args.kwargs['timeout'],3)

if __name__=='__main__':unittest.main()
