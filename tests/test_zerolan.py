"""Offline contract fixtures; no upstream services, assets or credentials."""
import json
import unittest
from uuid import UUID, uuid4

from companion_runtime.zerolan import (
    NDJSONDecoder, ProtocolError, READ_ONLY_ACTIONS, build_control,
    build_llm_query, compatibility_report, decode_predictions,
    validate_control, validate_prediction,
)


def wire(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class NDJSONTests(unittest.TestCase):
    def test_every_possible_split_of_chinese_multiframe_stream(self):
        values = [{"response": "你好，世界"}, {"response": "第二段🎵"}]
        raw = b"\r\n" + b"\n".join(wire(v) for v in values) + b"\r\n"
        for offset in range(len(raw) + 1):
            with self.subTest(offset=offset):
                decoder = NDJSONDecoder()
                actual = decoder.feed(raw[:offset]) + decoder.feed(raw[offset:])
                self.assertEqual(actual + decoder.finish(), values)

    def test_one_byte_chunks_preserve_multibyte_characters(self):
        value = {"response": "桂花乌龙茶。🌿"}
        raw = wire(value) + b"\n"
        decoder = NDJSONDecoder()
        actual = []
        for byte in raw:
            actual.extend(decoder.feed(bytes([byte])))
        self.assertEqual(actual + decoder.finish(), [value])

    def test_finish_accepts_complete_final_frame_without_lf(self):
        decoder = NDJSONDecoder()
        self.assertEqual(decoder.feed(b'{"response":"done"}'), [])
        self.assertEqual(decoder.finish(), [{"response": "done"}])

    def test_finish_rejects_truncated_json(self):
        decoder = NDJSONDecoder()
        decoder.feed(b'{"response":"unfinished')
        with self.assertRaisesRegex(ProtocolError, "Invalid JSON"):
            decoder.finish()

    def test_finish_rejects_truncated_utf8(self):
        decoder = NDJSONDecoder()
        decoder.feed(b'{"response":"\xe4\xbd')
        with self.assertRaisesRegex(ProtocolError, "Incomplete UTF-8"):
            decoder.finish()

    def test_line_boundary_rejects_truncated_utf8(self):
        decoder = NDJSONDecoder()
        with self.assertRaisesRegex(ProtocolError, "UTF-8"):
            decoder.feed(b'{"response":"\xe4\n')

    def test_invalid_utf8_is_not_replaced(self):
        with self.assertRaisesRegex(ProtocolError, "UTF-8"):
            NDJSONDecoder().feed(b'{"response":"\xff"}\n')

    def test_non_object_frames_rejected(self):
        for raw in [b"null\n", b"[]\n", b'"text"\n', b"1\n"]:
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                NDJSONDecoder().feed(raw)

    def test_malformed_and_ambiguous_json_rejected(self):
        invalid = [b"{\n", b'{"a":1,"a":2}\n', b'{"n":NaN}\n',
                   b'{"n":Infinity}\n', b'{"n":-Infinity}\n',
                   b'{"n":1e9999}\n', b'\xef\xbb\xbf{"a":1}\n']
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                NDJSONDecoder().feed(raw)

    def test_frame_limit_counts_wire_bytes_across_chunks(self):
        raw = wire({"response": "中文"})
        decoder = NDJSONDecoder(max_frame_bytes=len(raw) - 1)
        decoder.feed(raw[:5])
        with self.assertRaisesRegex(ProtocolError, "Frame byte limit"):
            decoder.feed(raw[5:] + b"\n")
        decoder = NDJSONDecoder(max_frame_bytes=len(raw))
        self.assertEqual(decoder.feed(raw + b"\n"), [{"response": "中文"}])

    def test_total_limit_counts_whitespace_and_finished_frames(self):
        decoder = NDJSONDecoder(max_total_bytes=4)
        self.assertEqual(decoder.feed(b"{}\n\n"), [{}])
        with self.assertRaisesRegex(ProtocolError, "Stream byte limit"):
            decoder.feed(b"\n")

    def test_failure_and_finish_are_terminal(self):
        decoder = NDJSONDecoder()
        with self.assertRaises(ProtocolError):
            decoder.feed(b"bad\n")
        with self.assertRaisesRegex(ProtocolError, "closed"):
            decoder.feed(b"{}\n")
        with self.assertRaisesRegex(ProtocolError, "closed"):
            decoder.finish()
        decoder = NDJSONDecoder()
        self.assertEqual(decoder.finish(), [])
        with self.assertRaisesRegex(ProtocolError, "closed"):
            decoder.feed(b"{}\n")

    def test_bad_configuration_and_chunk_types(self):
        for kwargs in [{"max_frame_bytes": 0}, {"max_total_bytes": -1},
                       {"max_frame_bytes": True}, {"max_total_bytes": 1.5}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                NDJSONDecoder(**kwargs)
        with self.assertRaises(ProtocolError):
            NDJSONDecoder().feed("{}")

    def test_error_messages_do_not_echo_input(self):
        with self.assertRaises(ProtocolError) as raised:
            NDJSONDecoder().feed(b'{"private-secret":BROKEN}\n')
        self.assertNotIn("private-secret", str(raised.exception))


class CoreDTOTests(unittest.TestCase):
    def test_each_query_gets_new_explicit_uuid(self):
        queries = [build_llm_query("你好") for _ in range(100)]
        self.assertEqual(len({q["id"] for q in queries}), 100)
        for query in queries:
            self.assertEqual(str(UUID(query["id"])), query["id"])
            self.assertEqual(set(query), {"id", "text", "history"})

    def test_explicit_request_id_and_copied_history(self):
        request_id = str(uuid4())
        history = [{"role": "user", "content": "当前对话", "metadata": "fixture"}]
        query = build_llm_query("继续", history, request_id)
        self.assertEqual(query["id"], request_id)
        history[0]["content"] = "changed"
        self.assertEqual(query["history"][0]["content"], "当前对话")

    def test_invalid_ids_and_query_text(self):
        for request_id in ["", "same-id", 1, str(uuid4()).upper()]:
            with self.subTest(request_id=request_id), self.assertRaises(ProtocolError):
                build_llm_query("你好", request_id=request_id)
        for text in [None, "", " ", "x" * 16001, "\ud800"]:
            with self.subTest(text_type=type(text).__name__), self.assertRaises(ProtocolError):
                build_llm_query(text)

    def test_history_rejects_extra_privilege_fields_or_bad_roles(self):
        invalid = [[{"role": "owner", "content": "test"}],
                   [{"role": ["user"], "content": "test"}],
                   [{"role": "user", "content": "test", "channel": "private"}],
                   [{"role": "user", "content": None}],
                   [{"role": "user", "content": "", "metadata": {}}],
                   [{}] * 65, "not a history"]
        for history in invalid:
            with self.subTest(history_type=type(history).__name__), self.assertRaises(ProtocolError):
                build_llm_query("test", history)

    def test_history_total_budget(self):
        history = [{"role": "user", "content": "x" * 16000}] * 5
        with self.assertRaisesRegex(ProtocolError, "History character limit"):
            build_llm_query("test", history)

    def test_prediction_shape_and_empty_token(self):
        identifier = str(uuid4())
        self.assertEqual(validate_prediction({"id": identifier, "response": ""}),
                         {"id": identifier, "response": "", "history": []})
        for value in [{"id": identifier}, {"response": "text"},
                      {"id": identifier, "response": None},
                      {"id": identifier, "response": "text", "tool": "run"}]:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                validate_prediction(value)

    def test_decode_predictions_offline_fixture(self):
        values = [{"id": str(uuid4()), "response": "你", "history": []},
                  {"id": str(uuid4()), "response": "好", "history": []}]
        raw = b"\n".join(wire(v) for v in values) + b"\n"
        # Arbitrary chunk cuts include Chinese UTF-8 and coalesced JSON lines.
        chunks = [raw[:19], raw[19:71], raw[71:72], raw[72:]]
        self.assertEqual(list(decode_predictions(chunks)), values)


class ControlTests(unittest.TestCase):
    def test_read_only_discovery_actions(self):
        for action in READ_ONLY_ACTIONS:
            with self.subTest(action=action):
                packet = build_control(action)
                self.assertEqual(validate_control(packet), packet)
                self.assertEqual(packet["protocol"], "ZerolanProtocol")
                self.assertEqual(packet["version"], "1.1")

    def test_wrong_version_protocol_and_fields_rejected(self):
        packet = build_control("client_hello")
        for extra in [{"version": "1.2"}, {"protocol": "other"},
                      {"role": "owner"}, {"code": True}, {"message": 3},
                      {"data": "not metadata"}, {"action": []}]:
            with self.subTest(extra=extra), self.assertRaises(ProtocolError):
                validate_control(dict(packet, **extra))
        packet.pop("data")
        with self.assertRaises(ProtocolError):
            validate_control(packet)

    def test_unsupported_side_effects_not_enabled_by_whitelist(self):
        for action in ["cancel", "cancel_request", "play_speech",
                       "koneko.server.call_instruction", "run_shell"]:
            packet = dict(build_control("client_hello"), action=action)
            with self.subTest(action=action), self.assertRaises(ProtocolError):
                validate_control(packet, allowed_actions=[action])

    def test_per_connection_whitelist_can_only_narrow(self):
        packet = build_control("koneko.client.hello")
        self.assertEqual(validate_control(packet, allowed_actions=[packet["action"]]), packet)
        with self.assertRaises(ProtocolError):
            validate_control(packet, allowed_actions=["client_hello"])

    def test_control_payload_copy_and_bounds(self):
        data = {"fixture": [1, 2]}
        packet = build_control("client_hello", data)
        data["fixture"].append(3)
        self.assertEqual(packet["data"], {"fixture": [1, 2]})
        for data in [{"x": "中" * 65536}, {"n": float("nan")}, {"bytes": b"x"}]:
            with self.subTest(value_type=type(data).__name__), self.assertRaises(ProtocolError):
                build_control("client_hello", data)

    def test_report_does_not_claim_connection_cancellation_or_execution(self):
        report = compatibility_report()
        for key in ["transport_io", "generation_cancel_relay", "tool_execution",
                    "upstream_runtime_tested"]:
            self.assertFalse(report[key])
        report["control_actions"].append("unsafe")
        self.assertNotIn("unsafe", compatibility_report()["control_actions"])


if __name__ == "__main__":
    unittest.main()
