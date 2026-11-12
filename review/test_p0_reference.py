"""Synthetic offline contract checks; NOT Q04 integration acceptance."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from p0_reference import ContractError, NDJSON, llm_query, llm_prediction, mc_hello

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'review/p0-fixtures.json').read_text())
WIRE = ''.join(json.dumps(x, ensure_ascii=False) + '\n'
               for x in FIXTURES['predictions']).encode()


class OfflineContractTests(unittest.TestCase):
    def decode(self, chunks):
        parser, values = NDJSON(), []
        for chunk in chunks:
            values.extend(parser.feed(chunk))
        parser.finish()
        return values

    def test_every_byte_boundary(self):
        for boundary in range(len(WIRE) + 1):
            with self.subTest(boundary=boundary):
                self.assertEqual(self.decode([WIRE[:boundary], WIRE[boundary:]]), FIXTURES['predictions'])

    def test_single_bytes(self):
        self.assertEqual(self.decode([WIRE[i:i+1] for i in range(len(WIRE))]), FIXTURES['predictions'])

    def test_coalesced_frames(self):
        self.assertEqual(self.decode([WIRE]), FIXTURES['predictions'])

    def test_crlf_and_blank_lines(self):
        self.assertEqual(self.decode([b'\r\n' + WIRE.replace(b'\n', b'\r\n')]), FIXTURES['predictions'])

    def test_truncated_eof(self):
        with self.assertRaises(ContractError):
            self.decode([WIRE[:-1]])

    def test_invalid_utf8(self):
        with self.assertRaises(ContractError):
            self.decode([b'{"response":"\xff"}\n'])

    def test_duplicate_keys(self):
        with self.assertRaises(ContractError):
            self.decode([b'{"id":"a","id":"b"}\n'])

    def test_invalid_json_and_non_objects(self):
        for wire in [b'[]\n', b'null\n', b'{bad}\n', b'{"x":NaN}\n']:
            with self.subTest(wire=wire), self.assertRaises(ContractError):
                self.decode([wire])

    def test_sse_is_not_ndjson(self):
        with self.assertRaises(ContractError):
            self.decode([b'data: {}\n\n'])

    def test_frame_limit_combined_and_split(self):
        for chunks in [[b'{"x":12345}\n'], [b'{"x":', b'12345}\n']]:
            with self.subTest(chunks=chunks), self.assertRaises(ContractError):
                parser = NDJSON(max_frame_bytes=8)
                for chunk in chunks:
                    parser.feed(chunk)

    def test_limit_is_per_frame(self):
        parser = NDJSON(max_frame_bytes=2)
        self.assertEqual(parser.feed(b'{}\n{}\n'), [{}, {}])
        parser.finish()

    def test_error_and_finish_close_parser(self):
        for wire in [b'bad\n', b'{}\n']:
            parser = NDJSON()
            try:
                parser.feed(wire)
                parser.finish()
            except ContractError:
                pass
            with self.assertRaises(ContractError):
                parser.feed(b'{}\n')

    def test_explicit_unique_query_ids(self):
        queries = [llm_query('合成输入', []) for _ in range(1000)]
        self.assertEqual(len({q['id'] for q in queries}), 1000)

    def test_history_not_aliased(self):
        history = [{'role': 'user', 'content': '合成事实'}]
        query = llm_query('你好', history)
        history[0]['content'] = 'changed'
        self.assertEqual(query['history'][0]['content'], '合成事实')

    def test_history_rejects_tool_or_extra_fields(self):
        for history in [[{'role': 'function', 'content': 'run'}],
                        [{'role': 'user', 'content': 'x', 'metadata': 'private'}]]:
            with self.subTest(history=history), self.assertRaises(ContractError):
                llm_query('x', history)

    def test_predictions_preserved_not_concatenated(self):
        self.assertEqual([llm_prediction(x) for x in self.decode([WIRE])],
                         [x['response'] for x in FIXTURES['predictions']])

    def test_null_predictions_rejected(self):
        for key in ['id', 'response', 'history']:
            value = dict(FIXTURES['predictions'][0], **{key: None})
            with self.subTest(key=key), self.assertRaises(ContractError):
                llm_prediction(value)

    def test_mc_hello(self):
        self.assertEqual(mc_hello(json.dumps(FIXTURES['mc_hello'])), FIXTURES['mc_hello'])

    def test_mc_wrong_version_protocol_or_action(self):
        for key, value in [('version', '1.0'), ('protocol', 'other'),
                           ('action', 'koneko.server.call_instruction'), ('code', True), ('data', None)]:
            hello = dict(FIXTURES['mc_hello'], **{key: value})
            with self.subTest(key=key), self.assertRaises(ContractError):
                mc_hello(json.dumps(hello))

    def test_mc_claimed_authority_rejected(self):
        hello = dict(FIXTURES['mc_hello'], role='owner')
        with self.assertRaises(ContractError):
            mc_hello(json.dumps(hello))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OfflineContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    paths = ['review/p0_reference.py', 'review/test_p0_reference.py', 'review/p0-fixtures.json',
             'evidence/p0-source-verification.json']
    report = {
        'scope': 'synthetic offline design-reference checks only; no upstream runtime execution',
        'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'passed': result.wasSuccessful(), 'integration_tests_executed': 0,
        'inputs_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        'not_verified': ['real Core HTTP', 'SSE adapter', 'TTS audio decoding and metadata',
                         'MC WebSocket handshake or game', 'cancellation and playback',
                         'public/private isolation', 'delta versus cumulative response semantics']
    }
    (ROOT / 'review/p0-offline-results.json').write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)
