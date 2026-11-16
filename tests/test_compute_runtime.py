"""Exercise compute selection/fallback with fake DLL capability and allocation."""
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4


class ComputeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        spec = importlib.util.spec_from_file_location('compute_' + uuid4().hex, Path(__file__).parents[1] / 'app/server.py')
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.app.DATA = Path(self.temp.name) / 'private'
        self.app.init()
        self.app.MODEL = Path(self.temp.name) / 'fixture.gguf'
        self.app.MODEL.write_bytes(b'synthetic model; never sent to actual llama.cpp')
        self.calls = []
        self.models = []
        self.fail_gpu = False
        def load(**args):
            self.calls.append(args)
            if args['n_gpu_layers'] and self.fail_gpu:raise RuntimeError('fake allocation failure')
            value = SimpleNamespace(closed=False)
            value.close = lambda: setattr(value, 'closed', True)
            self.models.append(value)
            return value
        self.module = SimpleNamespace(Llama=load, llama_supports_gpu_offload=lambda: True)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'llama_cpp': self.module}).start()
        self.app.runtime_diagnostics = lambda: {'nvidia': {'devices': [{
            'cuda124_conservative_driver_policy_met': True, 'memory_free_mib': 7000}]}}

    def test_default_cpu_never_requests_gpu_even_when_library_capable(self):
        self.app.load_model()
        self.assertEqual(self.calls[0]['n_gpu_layers'], 0)
        self.assertEqual(self.app.COMPUTE_STATUS['effective_backend'], 'cpu')

    def test_gpu_request_does_not_claim_allocation_was_verified(self):
        self.app.set_settings({'local_compute': 'cuda', 'local_gpu_layers': 20})
        self.app.load_model()
        self.assertEqual(self.calls[0]['n_gpu_layers'], 20)
        self.assertEqual(self.app.COMPUTE_STATUS['effective_backend'], 'cuda_requested')
        self.assertIs(self.app.COMPUTE_STATUS['actual_gpu_allocation_verified'], False)

    def test_cpu_wheel_reports_fallback_instead_of_fake_cuda(self):
        self.module.llama_supports_gpu_offload = lambda: False
        self.app.set_settings({'local_compute': 'cuda'})
        self.app.load_model()
        self.assertEqual(self.calls[0]['n_gpu_layers'], 0)
        self.assertTrue(self.app.COMPUTE_STATUS['fallback_reason'])

    def test_renderer_reserve_is_respected_when_free_memory_is_low(self):
        self.app.runtime_diagnostics = lambda: {'nvidia': {'devices': [{
            'cuda124_conservative_driver_policy_met': True, 'memory_free_mib': 2500}]}}
        self.app.set_settings({'local_compute': 'auto'})
        self.app.load_model()
        self.assertEqual(self.calls[0]['n_gpu_layers'], 0)

    def test_failed_gpu_allocation_retries_cpu_and_records_reason(self):
        self.fail_gpu = True
        self.app.set_settings({'local_compute': 'cuda'})
        self.app.load_model()
        self.assertEqual([call['n_gpu_layers'] for call in self.calls], [20, 0])
        self.assertEqual(self.app.COMPUTE_STATUS['effective_backend'], 'cpu')
        self.assertIn('失败', self.app.COMPUTE_STATUS['fallback_reason'])

    def test_config_change_closes_previous_instance_before_loading_another(self):
        self.app.load_model();previous = self.models[-1]
        self.app.set_settings({'local_context': 2048})
        self.app.load_model()
        self.assertTrue(previous.closed)
        self.assertEqual([call['n_ctx'] for call in self.calls], [4096, 2048])

    def test_same_config_reuses_instance(self):
        first = self.app.load_model()
        self.assertIs(self.app.load_model(), first)
        self.assertEqual(len(self.calls), 1)


    def test_same_path_weight_replacement_rebuilds_cached_instance(self):
        first=self.app.load_model();identity=self.app.LOCAL_LLM_IDENTITY
        self.app.MODEL.write_bytes(b'different model bytes at the same path')
        second=self.app.load_model()
        self.assertIsNot(second,first);self.assertTrue(first.closed)
        self.assertNotEqual(self.app.LOCAL_LLM_IDENTITY,identity)
        self.assertIs(self.app.load_model(),second);self.assertEqual(len(self.calls),2)

    def test_mid_constructor_replacement_closes_candidate_without_publishing_and_retry_recovers(self):
        original=self.module.Llama
        def changing_load(**args):
            candidate=original(**args);self.app.MODEL.write_bytes(b'changed during model constructor');return candidate
        self.module.Llama=changing_load
        with self.assertRaises(self.app.AppError) as caught:self.app.load_model()
        self.assertEqual(caught.exception.status,409);self.assertIsNone(self.app.LOCAL_LLM)
        self.assertIsNone(self.app.LOCAL_LLM_IDENTITY);self.assertIsNone(self.app.LOCAL_LLM_CONFIG)
        self.assertTrue(self.models[0].closed)
        self.module.Llama=original;second=self.app.load_model()
        self.assertIs(self.app.LOCAL_LLM,second);self.assertEqual(self.app.LOCAL_LLM_IDENTITY,self.app._local_model_identity())

    def test_failed_gpu_fallback_rechecks_identity_before_publication(self):
        original=self.module.Llama;self.fail_gpu=True
        self.app.set_settings({'local_compute':'cuda'})
        def changing_cpu(**args):
            candidate=original(**args);self.app.MODEL.write_bytes(b'changed during CPU fallback constructor');return candidate
        self.module.Llama=changing_cpu
        with self.assertRaises(self.app.AppError):self.app.load_model()
        self.assertEqual([row['n_gpu_layers'] for row in self.calls],[20,0])
        self.assertTrue(self.models[0].closed);self.assertIsNone(self.app.LOCAL_LLM_IDENTITY)


if __name__ == '__main__':unittest.main()
