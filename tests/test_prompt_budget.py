"""Code-bound capacity regression with a deterministic fake tokenizer, not GGUF quality."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4


class PromptBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        spec = importlib.util.spec_from_file_location('budget_' + uuid4().hex, Path(__file__).parents[1] / 'app/server.py')
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.app.DATA = Path(self.temp.name)
        self.app.init()
        self.calls = []
        owner = self
        class FakeModel:
            def tokenize(self, data):return list(data.decode('utf-8'))
            def create_chat_completion(self, **kwargs):
                owner.calls.append(copy.deepcopy(kwargs))
                return iter([{'choices': [{'delta': {'content': '收到。'}}]}])
        self.model = FakeModel()
        self.app.load_model = lambda: self.model

    def run_local(self, context, messages, max_tokens=240):
        self.app.generate_once({'engine': 'local', 'local_context': context}, copy.deepcopy(messages), max_tokens=max_tokens)
        return self.calls[-1]

    def test_2048_and_4096_use_selected_capacity_and_keep_latest_user(self):
        messages = [{'role': 'system', 'content': 's' * 80},
                    {'role': 'user', 'content': 'old' * 250},
                    {'role': 'assistant', 'content': 'a' * 750},
                    {'role': 'user', 'content': 'latest' * 140}]
        small = self.run_local(2048, messages)
        large = self.run_local(4096, messages)
        self.assertEqual(small['messages'], [messages[0], messages[-1]])
        self.assertEqual(large['messages'], messages)
        self.assertEqual(small['messages'][-1], messages[-1])
        self.assertEqual(len(messages), 4, 'Caller fixture must not be trimmed in place by this test helper.')

    def test_output_allowance_is_reserved_before_completion(self):
        messages = [{'role': 'system', 'content': 's' * 80},
                    {'role': 'user', 'content': 'old' * 60},
                    {'role': 'assistant', 'content': 'a' * 150},
                    {'role': 'user', 'content': 'current' * 80}]
        ordinary = self.run_local(2048, messages, 240)
        reserved = self.run_local(2048, messages, 1000)
        self.assertEqual(ordinary['messages'], messages)
        self.assertEqual(reserved['messages'], [messages[0], messages[-1]])
        self.assertEqual(reserved['max_tokens'], 1000)
        import json
        count = len(self.model.tokenize(json.dumps(reserved['messages'], ensure_ascii=False).encode()))
        self.assertLessEqual(count + reserved['max_tokens'] + 256, 2048)

    def test_oversized_single_user_is_explicit_error_and_never_truncated(self):
        for context in (2048, 4096):
            with self.subTest(context=context):
                messages = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'x' * context}]
                before = copy.deepcopy(messages)
                with self.assertRaisesRegex(self.app.AppError, '超出本地模型容量'):
                    self.run_local(context, messages)
                self.assertEqual(messages, before)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':unittest.main()
