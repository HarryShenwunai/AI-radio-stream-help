"""Cross-platform storage/configuration regression; does not execute Windows PE."""
from pathlib import Path
import contextlib,hashlib,importlib.util,io,os,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('windows_assembly_under_test',ROOT/'scripts/build_windows_embedded.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
switch_spec=importlib.util.spec_from_file_location('runtime_switch_under_test',ROOT/'desktop/switch_runtime_profile.py');switch=importlib.util.module_from_spec(switch_spec);switch_spec.loader.exec_module(switch)

class RuntimeAssembly(unittest.TestCase):
    def test_same_official_wheel_filename_cannot_overwrite_another_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory);cpu=b'synthetic CPU bytes';cuda=b'synthetic CUDA bytes'
            with patch.object(module.urllib.request,'urlopen',side_effect=[io.BytesIO(cpu),io.BytesIO(cuda)]):
                first=module.download('https://example.invalid/cpu/same.whl',hashlib.sha256(cpu).hexdigest(),cache)
                second=module.download('https://example.invalid/cuda/same.whl',hashlib.sha256(cuda).hexdigest(),cache)
            self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),cpu);self.assertEqual(second.read_bytes(),cuda)
    def test_supported_interpreter_and_official_compute_variants_are_explicit(self):
        module.configure_runtime('standalone312','cuda')
        self.assertEqual(module.PYTHON_MINOR,(3,12));self.assertIn('/v0.3.36-cu124/',module.LLAMA_URL)
        cuda=module.LLAMA_SHA256;module.configure_runtime('standalone312','cpu')
        self.assertIn('/v0.3.36/',module.LLAMA_URL);self.assertNotEqual(cuda,module.LLAMA_SHA256)
        self.assertEqual(module.PYTHON_DISTRIBUTION['distributor'],'Astral python-build-standalone')

class RuntimeSwitchPrivacy(unittest.TestCase):
    def test_native_probe_receives_early_opt_out_without_changing_parent(self):
        for profile in ('cpu','cuda'):
            for inherited in ('0',None):
                with self.subTest(profile=profile,inherited=inherited),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'KEEP_PROBE_SETTING':'preserved','CUDA_PATH':'user-cuda','HIP_PATH':'user-hip'}):
                    if inherited is None:os.environ.pop('ORT_DISABLE_TELEMETRY',None)
                    else:os.environ['ORT_DISABLE_TELEMETRY']=inherited
                    local_os=types.SimpleNamespace(name='nt',environ=os.environ)
                    with patch.object(switch,'os',local_os),patch.object(switch,'__file__',str(Path(directory)/'resources/app/switch_runtime_profile.py')),patch.object(switch,'verify'),patch.object(switch,'select') as select,patch.object(switch.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as probe,patch.object(sys,'argv',['switch','--profile',profile]),contextlib.redirect_stdout(io.StringIO()):
                        switch.main()
                    probe.assert_called_once();child=probe.call_args.kwargs['env']
                    self.assertEqual(child.get('ORT_DISABLE_TELEMETRY'),'1')
                    self.assertEqual(child['KEEP_PROBE_SETTING'],'preserved')
                    self.assertNotIn('CUDA_PATH',child);self.assertNotIn('HIP_PATH',child)
                    self.assertEqual(os.environ.get('ORT_DISABLE_TELEMETRY'),inherited)
                    self.assertEqual(os.environ['CUDA_PATH'],'user-cuda');self.assertEqual(os.environ['HIP_PATH'],'user-hip')
                    self.assertIn('onnxruntime',probe.call_args.args[0][-1]);self.assertIn('-I',probe.call_args.args[0])
                    self.assertEqual(select.call_args.args[1],profile)

if __name__=='__main__':unittest.main()
