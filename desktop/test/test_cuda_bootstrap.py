"""Synthetic preflight control-flow tests; not Windows/native GPU execution."""
from pathlib import Path
import contextlib,io,sys,types,unittest
from unittest.mock import Mock,patch

FILE=Path(__file__).resolve().parents[1]/'desktop_backend.py'

class CUDAStartup(unittest.TestCase):
    def execute(self, dll_failure=False):
        llama=types.SimpleNamespace(llama_backend_init=Mock(),llama_supports_gpu_offload=Mock(return_value=True),Llama=Mock(side_effect=AssertionError('No model should be loaded')))
        modules={'llama_cpp':llama,'onnxruntime':types.SimpleNamespace(),'ctranslate2':types.SimpleNamespace()}
        with patch.dict(sys.modules,modules),patch('ctypes.WinDLL',create=True,side_effect=OSError('missing dependency') if dll_failure else None) as dll,patch('runpy.run_path') as run,contextlib.redirect_stdout(io.StringIO()) as output,contextlib.redirect_stderr(io.StringIO()):
            if dll_failure:
                with self.assertRaises(SystemExit) as error:exec(compile(FILE.read_text(),str(FILE),'exec'),{'__name__':'__main__','__file__':str(FILE)})
                self.assertEqual(error.exception.code,72);run.assert_not_called();self.assertNotIn('http://',output.getvalue())
            else:
                exec(compile(FILE.read_text(),str(FILE),'exec'),{'__name__':'__main__','__file__':str(FILE)})
                run.assert_called_once_with(str(FILE.with_name('server.py')),run_name='__main__')
                llama.Llama.assert_not_called();self.assertTrue(str(dll.call_args.args[0]).replace('\\','/').endswith('/python/Lib/site-packages/llama_cpp/lib/ggml-cuda.dll'))
    def test_missing_cuda_native_dependency_exits_before_http(self):self.execute(True)
    def test_successful_preflight_runs_server_without_model_loading(self):self.execute(False)

if __name__=='__main__':unittest.main()
