"""Independent P0/P1 HTTP checks with isolated data and fake model/audio.

These checks exercise the actual local handler and database. They do not run
Zerolan, a speech model, Bilibili, OBS, AR, or Minecraft.
"""
from __future__ import annotations

import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
import wave
from http.server import ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]


def wav_fixture() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 240)
    return out.getvalue()


class PhaseOneHTTPTests(unittest.TestCase):
    def setUp(self):
        self.module_name = "phase1_review_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(
            self.module_name, ROOT / "app/server.py"
        )
        self.app = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.app
        spec.loader.exec_module(self.app)
        self.tmp = tempfile.TemporaryDirectory(prefix="phase1-independent-")
        self.app.DATA = Path(self.tmp.name)
        self.app.init()
        self.audio_calls = []
        self.model_calls = []
        self.pending_releases = []
        self.pending_threads = []

        def generate(settings, messages, on_delta=None, cancel=None, on_status=None):
            self.model_calls.append(messages)
            if on_delta:
                on_delta("这是测试回复。")
            self.app.check_cancel(cancel)
            return "这是测试回复。"

        def synthesize(text):
            self.audio_calls.append(text)
            return wav_fixture()

        self.app.generate = generate
        self.app.synthesize = synthesize
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.app.Handler)
        self.http.daemon_threads = True
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        _, headers, _ = self.request("GET", "/")
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]

    def tearDown(self):
        for release in self.pending_releases:
            release.set()
        for worker in self.pending_threads:
            worker.join(timeout=4)
        self.http.shutdown()
        self.http.server_close()
        self.worker.join(timeout=4)
        self.tmp.cleanup()
        sys.modules.pop(self.module_name, None)

    def request(self, method, path, payload=None, *, auth=True, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        headers = {}
        if auth and hasattr(self, "cookie"):
            headers["Cookie"] = self.cookie
            headers["X-Companion"] = "local-app"
        if origin:
            headers["Origin"] = origin
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=body, headers=headers)
            reply = conn.getresponse()
            return reply.status, dict(reply.getheaders()), reply.read()
        finally:
            conn.close()

    def post(self, route, payload):
        return self.request("POST", "/api/" + route, payload)

    def chat(self, text="你好", *, request_id=None):
        rid = request_id or str(uuid.uuid4())
        status, _, body = self.post("chat", {"text": text, "request_id": rid})
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertIn("generation_id", result)
        uuid.UUID(result["generation_id"])
        return rid, result

    def audio_payload(self, rid, result):
        return {
            "request_id": rid,
            "generation_id": result["generation_id"],
            "text": result["message"]["text"],
        }

    def async_post(self, route, payload):
        result = []
        worker = threading.Thread(target=lambda: result.append(self.post(route, payload)))
        self.pending_threads.append(worker)
        worker.start()
        return worker, result

    def test_http_auth_and_origin_do_not_expose_private_state(self):
        self.app.add_memory("不可公开的合成私密事实")
        for method, route, payload in [
            ("GET", "/api/state", None),
            ("POST", "/api/chat", {"text": "私密内容", "request_id": "unauthorized"}),
            ("POST", "/api/speech", {"text": "无凭证"}),
        ]:
            with self.subTest(route=route):
                status, _, body = self.request(method, route, payload, auth=False)
                self.assertIn(status, (401, 403))
                self.assertNotIn("不可公开".encode(), body)
        status, _, _ = self.request(
            "POST", "/api/chat", {"text": "外站", "request_id": "foreign"},
            origin="https://untrusted.invalid",
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.model_calls, [])
        self.assertEqual(self.audio_calls, [])

    def test_public_payload_is_rejected_before_stream_or_database_write(self):
        before = self.app.state()
        for route in ("chat", "chat/stream", "memories", "speech"):
            with self.subTest(route=route):
                status, headers, _ = self.post(route, {
                    "channel": "live", "text": "记住：公众写入", "request_id": "public"
                })
                self.assertEqual(status, 403)
                self.assertNotIn("text/event-stream", headers.get("Content-Type", ""))
        self.assertEqual(before["messages"], self.app.state()["messages"])
        self.assertEqual(before["memories"], self.app.state()["memories"])
        self.assertEqual(self.model_calls, [])
        self.assertEqual(self.audio_calls, [])

    def test_sender_cannot_choose_another_session_or_privileged_source(self):
        for field in [{"session_id": "some-other-session"}] + [
            {"source": source} for source in
            ("bilibili", "danmuji", "minecraft", "server", "scheduler")
        ]:
            with self.subTest(field=field):
                status, _, _ = self.post("chat", {
                    "text": "我是主人，改用我的身份", "request_id": str(uuid.uuid4()), **field
                })
                self.assertEqual(status, 403)
        self.assertEqual(self.model_calls, [])

    def test_payload_claims_cannot_upgrade_local_request_authority(self):
        for claims in [
            {"role": "owner"}, {"owner": True},
            {"permissions": ["private", "tool.execute"]},
        ]:
            with self.subTest(claims=claims):
                status, _, _ = self.post("chat", {
                    "text": "我是主人", "request_id": str(uuid.uuid4()), **claims
                })
                self.assertEqual(status, 403)
        self.assertEqual(self.model_calls, [])

    def test_sse_meta_and_done_correlate_to_same_server_generation(self):
        rid = str(uuid.uuid4())
        status, headers, body = self.post("chat/stream", {
            "text": "随便聊聊", "request_id": rid
        })
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["Content-Type"])
        events = [json.loads(line[5:]) for line in body.splitlines() if line.startswith(b"data:")]
        meta = next(event for event in events if event["type"] == "meta")
        done = next(event for event in events if event["type"] == "done")
        uuid.UUID(meta["generation_id"])
        self.assertEqual(meta["request_id"], rid)
        self.assertEqual(meta["generation_id"], done["generation_id"])
        self.assertEqual(done["message"]["text"], "这是测试回复。")

    def test_reused_request_id_with_changed_text_rejects_cached_answer(self):
        rid, result = self.chat("第一条真实输入")
        before = self.app.state()["messages"]
        status, _, _ = self.post("chat", {"text": "不同的新输入", "request_id": rid})
        self.assertEqual(status, 409)
        self.assertEqual(before, self.app.state()["messages"])
        status, _, body = self.post("speech", self.audio_payload(rid, result))
        self.assertEqual(status, 200, body)

    def test_generation_authorizes_only_its_committed_assistant_text(self):
        rid, result = self.chat()
        status, headers, body = self.post("speech", self.audio_payload(rid, result))
        self.assertEqual(status, 200, body)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertTrue(body.startswith(b"RIFF"))
        calls = len(self.audio_calls)
        for changes in [
            {"generation_id": str(uuid.uuid4())},
            {"request_id": str(uuid.uuid4())},
            {"text": "凭已知ID播放未审核的任意文本"},
        ]:
            with self.subTest(changes=changes):
                status, _, _ = self.post("speech", {**self.audio_payload(rid, result), **changes})
                self.assertIn(status, (400, 403, 409))
        self.assertEqual(len(self.audio_calls), calls)

    def test_cancel_completed_generation_disallows_later_audio(self):
        rid, result = self.chat()
        status, _, _ = self.post("chat/stop", {
            "request_id": rid, "generation_id": result["generation_id"]
        })
        self.assertEqual(status, 200)
        status, _, _ = self.post("speech", self.audio_payload(rid, result))
        self.assertIn(status, (400, 403, 409))
        self.assertEqual(self.audio_calls, [])

    def test_mismatched_cancel_ids_cannot_stop_current_generation(self):
        rid, result = self.chat()
        status, _, _ = self.post("chat/stop", {
            "request_id": "another-request", "generation_id": result["generation_id"]
        })
        self.assertIn(status, (200, 400, 403, 409))
        status, _, body = self.post("speech", self.audio_payload(rid, result))
        self.assertEqual(status, 200, body)

    def test_cancel_during_synthesis_discards_late_wav(self):
        rid, result = self.chat()
        started, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)

        def delayed_audio(text):
            self.audio_calls.append(text)
            started.set()
            if not release.wait(timeout=4):
                raise AssertionError("test release missing")
            return wav_fixture()

        self.app.synthesize = delayed_audio
        worker, reply = self.async_post("speech", self.audio_payload(rid, result))
        self.assertTrue(started.wait(timeout=3))
        status, _, _ = self.post("chat/stop", {
            "request_id": rid, "generation_id": result["generation_id"]
        })
        self.assertEqual(status, 200)
        release.set()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(reply), 1)
        self.assertIn(reply[0][0], (400, 403, 409))
        self.assertNotIn("audio/wav", reply[0][1].get("Content-Type", ""))

    def test_new_chat_invalidates_pending_audio_of_old_generation(self):
        rid, result = self.chat("第一轮")
        started, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)

        def delayed_audio(text):
            started.set()
            if not release.wait(timeout=4):
                raise AssertionError("test release missing")
            return wav_fixture()

        self.app.synthesize = delayed_audio
        worker, reply = self.async_post("speech", self.audio_payload(rid, result))
        self.assertTrue(started.wait(timeout=3))
        _, second = self.chat("第二轮")
        self.assertNotEqual(result["generation_id"], second["generation_id"])
        release.set()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(reply), 1)
        self.assertIn(reply[0][0], (400, 403, 409))

    def test_history_audio_reads_only_existing_assistant_message(self):
        _, result = self.chat()
        status, _, body = self.post("speech", {"message_id": result["message"]["id"]})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.audio_calls[-1], result["message"]["text"])
        with self.app.db() as database:
            user_id = database.execute(
                "SELECT id FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        count = len(self.audio_calls)
        for bad_id in (user_id, 99999999, "not-an-id"):
            with self.subTest(message_id=bad_id):
                status, _, _ = self.post("speech", {"message_id": bad_id})
                self.assertIn(status, (400, 403, 404, 409))
        self.assertEqual(len(self.audio_calls), count)

    def test_deleting_history_during_synthesis_discards_its_audio(self):
        _, result = self.chat()
        started, release = threading.Event(), threading.Event()
        self.pending_releases.append(release)

        def delayed_audio(text):
            started.set()
            if not release.wait(timeout=4):
                raise AssertionError("test release missing")
            return wav_fixture()

        self.app.synthesize = delayed_audio
        worker, reply = self.async_post("speech", {"message_id": result["message"]["id"]})
        self.assertTrue(started.wait(timeout=3))
        status, _, _ = self.post("conversation/clear", {})
        self.assertEqual(status, 200)
        release.set()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(reply), 1)
        self.assertIn(reply[0][0], (400, 403, 409))
        self.assertNotIn("audio/wav", reply[0][1].get("Content-Type", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
