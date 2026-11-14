"""Actual HTTP/DOM regression: material must survive study actions without sending.
AI is an isolated fixture, not a learning-efficacy or Windows acceptance test.
"""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "src")]
from test_character_http import CharacterHTTPTests

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--script-ref")
p.add_argument("--model", type=Path)
p.add_argument("--runtime-dir", type=Path)
p.add_argument("--chromium", default="/usr/bin/chromium")
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
f = CharacterHTTPTests()
f.setUp()
f.post(
    "settings",
    {
        "engine": "api",
        "api_base": "http://127.0.0.1:9/v1",
        "api_model": "isolated-fixture",
        "expected_character_id": f.initial_id,
    },
)
report = {
    "scope": "Linux Chromium, real app HTTP/DOM, isolated AI fixture; no learning efficacy claim",
    "checks": {},
    "errors": [],
}


class Runtime:
    def status(self):
        return {
            "available": True,
            "core_available": True,
            "renderer_available": True,
            "core_url": "/live2d-core.js",
            "runtime_url": "/live2d-runtime.js",
        }

    def read_core(self):
        return (a.runtime_dir / "live2dcubismcore.min.js").read_bytes()

    def read_bundle(self):
        return (a.runtime_dir / "build/owner-live2d-runtime.js").read_bytes()


if a.runtime_dir:
    f.app.live2d_runtime = lambda: Runtime()
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=a.chromium,
            headless=True,
            args=[
                "--no-sandbox",
                "--enable-unsafe-swiftshader",
                "--use-angle=swiftshader",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=str(a.output / "video"),
            record_video_size={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.on("pageerror", lambda e: report["errors"].append(str(e)))
        if a.script_ref:
            old = subprocess.check_output(
                ["git", "show", a.script_ref + ":app/static/study-room.js"],
                cwd=ROOT,
                text=True,
            )
            page.route(
                "**/study-room.js",
                lambda r: r.fulfill(
                    status=200, content_type="application/javascript", body=old
                ),
            )
        try:
            base = f"http://127.0.0.1:{f.server.server_port}"
            page.goto(base)
            page.wait_for_function(
                "()=>window.CompanionStudy&&CompanionApp.core.get().state"
            )
            if a.model:
                headers = {"X-Companion": "local-app"}
                role = page.evaluate("CompanionApp.core.scope().character_id")
                r = page.request.post(
                    base + "/api/characters/assets/import",
                    headers=headers,
                    data={
                        "character_id": role,
                        "format": "live2d",
                        "model": {
                            "filename": a.model.name,
                            "data_base64": base64.b64encode(
                                a.model.read_bytes()
                            ).decode(),
                        },
                    },
                )
                assert r.ok, r.text()
                asset = r.json()["asset"]
                r = page.request.post(
                    base + "/api/characters/assets/activate",
                    headers=headers,
                    data={"character_id": role, "asset_id": asset["id"]},
                )
                assert r.ok, r.text()
                page.evaluate("CompanionApp.core.refresh(true)")
                page.wait_for_function("()=>CompanionApp.scene.ready", timeout=60000)
                report["checks"]["existing_export_loaded"] = True
            requests = []
            page.on(
                "request",
                lambda r: requests.append(r.url) if "/api/chat/" in r.url else None,
            )
            page.locator("#study-goal").fill("理解导数定义，并解释单位")
            material = "教材原文：速度是位移对时间的变化率。\n我的疑问：为什么要取极限？保留符号 Δx/Δt。"
            page.locator("#compose-text").fill(material)
            page.screenshot(path=str(a.output / "01-material-before.png"))
            page.locator("#study-ai-plan").click()
            page.wait_for_timeout(800)
            actual = page.locator("#compose-text").input_value()
            page.screenshot(path=str(a.output / "02-after-plan.png"))
            report["material_before"] = material
            report["draft_after"] = actual
            assert actual.startswith(material), (
                "Study action destroyed the original material"
            )
            assert "理解导数定义" in actual
            report["checks"]["material_preserved"] = True
            page.locator("#study-ai-plan").click()
            assert page.locator("#compose-text").input_value() == actual, (
                "Repeated action duplicates the instruction"
            )
            report["checks"]["repeat_idempotent"] = True
            page.locator("#study-main").click()
            page.wait_for_timeout(1100)
            page.locator("#study-main").click()
            elapsed = page.evaluate("CompanionStudy.snapshot().elapsed")
            page.wait_for_timeout(700)
            assert page.evaluate("CompanionStudy.snapshot().elapsed") == elapsed
            page.locator("#study-ai-review").click()
            assert page.locator("#compose-text").input_value().startswith(material)
            report["checks"]["pause_and_review_preserve_material"] = True
            full = "验收保留材料。" * 499
            full = (full + "余" * 4000)[:4000]
            page.locator("#compose-text").fill(full)
            page.locator("#study-ai-plan").click()
            assert page.locator("#compose-text").input_value() == full, (
                "Full draft was truncated or overwritten"
            )
            report["checks"]["full_draft_preserved"] = True
            assert not requests, requests
            assert not f.model_calls
            report["checks"]["no_unsent_requests"] = True
            page.screenshot(path=str(a.output / "03-full-draft-preserved.png"))
            page.locator("#compose-text").fill("")
            page.locator("#study-ai-plan").click()
            assert "缺少教材" in page.locator("#compose-text").input_value()
            report["checks"]["empty_draft_still_generates_question"] = True
            page.wait_for_timeout(500)
            assert not requests, requests
            assert not f.model_calls
            assert not report["errors"], report["errors"]
            report["status"] = "passed"
        finally:
            ctx.close()
            browser.close()
except Exception as exc:
    report["status"] = "failed"
    report["failure"] = str(exc)
    raise
finally:
    (a.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    f.tearDown()
