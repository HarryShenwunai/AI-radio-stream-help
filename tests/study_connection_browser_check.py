"""Reject configuration-as-connection claims using a real failing loopback API."""

import argparse, json, sys, subprocess, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "src")]
from test_character_http import CharacterHTTPTests

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--baseline-ref")
p.add_argument("--chromium", required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
requests = []


class Unavailable(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        requests.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = b'{"error":{"message":"deliberate service outage"}}'
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


provider = ThreadingHTTPServer(("127.0.0.1", 0), Unavailable)
threading.Thread(target=provider.serve_forever, daemon=True).start()
f = CharacterHTTPTests()
f.setUp()
f.post(
    "settings",
    {
        "engine": "api",
        "api_base": f"http://127.0.0.1:{provider.server_port}/v1",
        "api_model": "unreachable-learning-service",
        "expected_character_id": f.initial_id,
    },
)


# Restore the production generation path, instead of the fixture's fake answer.
def generate(s, messages, on_delta=None, cancel=None, on_status=None):
    return f.app.generate_once(s, messages, on_delta, cancel)


f.app.generate = generate
r = {
    "scope": "Actual app HTTP and Chromium, production remote transport to deliberate loopback HTTP503; no real tutoring or external service",
    "checks": {},
}
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            executable_path=a.chromium, headless=True, args=["--no-sandbox"]
        )
        c = b.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=str(a.output / "video"),
        )
        c.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = c.new_page()
        if a.baseline_ref:
            old = subprocess.check_output(
                ["git", "show", a.baseline_ref + ":app/static/study-room.js"],
                cwd=ROOT,
                text=True,
            )
            page.route(
                "**/study-room.js",
                lambda route: route.fulfill(
                    status=200, content_type="application/javascript", body=old
                ),
            )
        try:
            page.goto(f"http://127.0.0.1:{f.server.server_port}")
            page.wait_for_function(
                "()=>window.CompanionStudy&&CompanionApp.core.get().state"
            )
            r["before_request_label"] = page.locator("#study-ai-state").inner_text()
            assert not requests
            page.screenshot(path=str(a.output / "01-configured-not-probed.png"))
            page.locator("#study-goal").fill("根据我的材料解释单位")
            page.locator("#compose-text").fill(
                "材料：速度单位是 m/s。请解释 s 的含义。"
            )
            page.locator("#study-ai-plan").click()
            assert not requests, (
                "Preparing a question made an unsolicited provider call"
            )
            page.locator("#send-message").click()
            page.wait_for_function(
                "()=>Boolean(CompanionApp.core.get().failed)", timeout=20000
            )
            r["after_failure_label"] = page.locator("#study-ai-state").inner_text()
            r["provider_requests"] = requests
            r["draft"] = page.locator("#compose-text").input_value()
            r["core_failure"] = page.evaluate("CompanionApp.core.get().failed.error")
            page.screenshot(path=str(a.output / "02-service-failure.png"))
            assert requests == ["/v1/chat/completions"], requests
            assert "已连接" not in r["before_request_label"], (
                "Model configuration was falsely presented as a verified connection"
            )
            assert "失败" in r["after_failure_label"], (
                "Known transport failure is absent from the study status"
            )
            expect(page.locator("#study-guidance")).to_contain_text("请求失败")
            expect(page.locator("#study-guidance")).to_be_in_viewport(ratio=1)
            assert not any(
                x["role"] == "assistant" and x.get("kind") == "chat"
                for x in f.state()["messages"]
            ), "Failed request became an invented answer"
            r["saved_user_material"] = [
                x["text"] for x in f.state()["messages"] if x["role"] == "user"
            ][-1]
            assert r["saved_user_material"].startswith("材料：速度单位是 m/s。")
            r["checks"] = {
                "no_implicit_probe": True,
                "no_connection_claim_from_config": True,
                "known_failure_visible": True,
                "material_recovered": True,
                "no_fabricated_answer": True,
            }
            r["status"] = "passed"
        finally:
            c.tracing.stop(path=str(a.output / "trace.zip"))
            c.close()
            b.close()
except Exception as e:
    r["status"] = "failed"
    r["failure"] = str(e)
    raise
finally:
    (a.output / "report.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2) + "\n"
    )
    provider.shutdown()
    provider.server_close()
    f.tearDown()
