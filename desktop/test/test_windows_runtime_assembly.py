"""Cross-platform storage/configuration regression; does not execute Windows PE."""
from pathlib import Path
import hashlib,importlib.util,io,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('windows_assembly_under_test',ROOT/'scripts/build_windows_embedded.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

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

if __name__=='__main__':unittest.main()
