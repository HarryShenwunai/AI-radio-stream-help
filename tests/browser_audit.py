from pathlib import Path
import sys, json, base64, hashlib, subprocess, traceback, argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from quality_gate import source_hashes
from test_character_http import CharacterHTTPTests
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(
    description="Record actual app/Live2D browser regression evidence using user-provided runtime and model files. No downloads or account connections."
)
parser.add_argument(
    "--runtime-dir",
    type=Path,
    required=True,
    help="Directory containing live2dcubismcore.min.js and build/owner-live2d-runtime.js",
)
parser.add_argument("--model-zip", type=Path, required=True)
parser.add_argument("--chromium", type=Path, required=True)
parser.add_argument(
    "--baseline-ref", default="564ea22a1be84c28d71b968f658574f4bbdf297c"
)
parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/audit-30/browser")
parser.add_argument(
    "--idle-video-seconds",
    type=float,
    default=0,
    help="Hold the actual app idle pose in the recording (0..30 seconds)",
)
parser.add_argument("--study-room", action="store_true")
args = parser.parse_args()
if not 0 <= args.idle_video_seconds <= 30:
    parser.error("idle-video-seconds must be within 0..30")
out = args.output_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
owned = args.runtime_dir.resolve()
for required in [
    owned / "live2dcubismcore.min.js",
    owned / "build/owner-live2d-runtime.js",
    args.model_zip,
    args.chromium,
]:
    if not required.is_file():
        parser.error("Missing required local file: " + str(required))


class ExistingRuntime:
    def status(self):
        return {
            "available": True,
            "core_available": True,
            "renderer_available": True,
            "core_url": "/live2d-core.js",
            "runtime_url": "/live2d-runtime.js",
        }

    def read_core(self):
        return (owned / "live2dcubismcore.min.js").read_bytes()

    def read_bundle(self):
        return (owned / "build/owner-live2d-runtime.js").read_bytes()


source_before = source_hashes()
commit_before = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()
dirty_before = bool(
    subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
)
f = CharacterHTTPTests(
    "test_new_identity_has_separate_memories_chat_tasks_and_personality"
)
f.setUp()
f.app.live2d_runtime = lambda: ExistingRuntime()
report = {
    "scope": "Real app HTTP, DOM, existing owner-local Core/WebGL; injected model-load failure. Fixture AI, isolated database. Runtime installer not tested. No Windows/hardware claim.",
    "checks": {},
    "errors": [],
}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=str(args.chromium.resolve()),
            headless=True,
            args=[
                "--no-sandbox",
                "--enable-unsafe-swiftshader",
                "--use-angle=swiftshader",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=str(out / "video"),
            record_video_size={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.on("pageerror", lambda e: report["errors"].append(str(e)))
        base = f"http://127.0.0.1:{f.server.server_port}"
        page.add_init_script(
            "(()=>{let exposed;Object.defineProperty(window,'CompanionLive2D',{configurable:true,get:()=>exposed,set:library=>{exposed={...library,create(options){const instance=library.create(options);if(window.__auditFailLoad)instance.load=async()=>false;return instance;}};}});})();"
        )
        page.goto(base)
        page.wait_for_function("()=>window.CompanionApp?.core.get().state!==null")
        role = page.evaluate("CompanionApp.core.scope().character_id")
        headers = {"X-Companion": "local-app"}
        package = args.model_zip.resolve()
        r = page.request.post(
            base + "/api/characters/assets/import",
            headers=headers,
            data={
                "character_id": role,
                "format": "live2d",
                "model": {
                    "filename": package.name,
                    "data_base64": base64.b64encode(package.read_bytes()).decode(),
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
        page.wait_for_function(
            "()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2",
            timeout=60000,
        )
        report["checks"]["actual_model_import_and_gl_ready"] = True
        page.screenshot(path=str(out / "01-actual-model-ready.png"))
        if args.idle_video_seconds:
            page.wait_for_timeout(args.idle_video_seconds * 1000)
        baseline = subprocess.check_output(
            ["git", "show", args.baseline_ref + ":app/static/scene-controller.js"],
            cwd=ROOT,
            text=True,
        )
        page.route(
            "**/scene-controller.js",
            lambda route: route.fulfill(
                status=200, content_type="application/javascript", body=baseline
            ),
        )
        page.reload()
        page.wait_for_function("()=>CompanionApp.scene.ready", timeout=60000)
        inject = "()=>{window.__auditFailLoad=true;return CompanionApp.scene.retry();}"
        assert page.evaluate(inject) is False
        assert page.locator("#scene-retry").is_hidden()
        assert "正在准备" in page.locator("#scene-status").inner_text()
        page.screenshot(path=str(out / "02-before-false-load-stuck.png"))
        report["checks"]["baseline_false_load_stuck_reproduced"] = True
        page.wait_for_timeout(1000)
        page.unroute("**/scene-controller.js")
        page.reload()
        page.wait_for_function("()=>CompanionApp.scene.ready", timeout=60000)
        assert page.evaluate(inject) is False
        assert page.locator("#scene-retry").is_visible()
        assert "加载失败" in page.locator("#scene-status").inner_text()
        page.screenshot(path=str(out / "03-after-visible-retry.png"))
        report["checks"]["fixed_false_load_visible_retry"] = True
        page.wait_for_timeout(1000)
        page.evaluate("window.__auditFailLoad=false")
        page.locator("#scene-retry").click()
        page.wait_for_function(
            "()=>CompanionApp.scene.ready&&CompanionApp.scene.getDiagnostics().coreEvaluations>2",
            timeout=60000,
        )
        page.screenshot(path=str(out / "04-real-model-recovered.png"))
        report["checks"]["actual_retry_recovers_model"] = True
        if args.study_room:
            from study_room_browser_cases import check_study_room

            check_study_room(page, out, report)
        # Actual shipped scene controls, not CSS or replacement screenshots.
        page.evaluate(
            "CompanionApp.scene.applyControls({idleMotion:false,autoBlink:false,breath:false,parameters:[{id:'ParamEyeLOpen',value:0},{id:'ParamEyeROpen',value:0}]})"
        )
        page.wait_for_function(
            "()=>CompanionApp.scene.getDiagnostics().parameters.filter(p=>['ParamEyeLOpen','ParamEyeROpen'].includes(p.id)).every(p=>p.value===0)"
        )
        eyes = page.evaluate(
            "CompanionApp.scene.getDiagnostics().parameters.filter(p=>['ParamEyeLOpen','ParamEyeROpen'].includes(p.id))"
        )
        assert len(eyes) == 2 and all(p["value"] == 0 for p in eyes)
        report["checks"]["both_eye_parameters_close"] = True
        report["eye_parameters"] = eyes
        page.screenshot(path=str(out / "05-both-eyes-closed.png"))
        page.wait_for_timeout(600)
        page.evaluate("CompanionApp.scene.applyControls({reset:true,idleMotion:true})")
        page.wait_for_timeout(1800)
        page.set_viewport_size({"width": 390, "height": 844})
        # ResizeObserver and the next Core draw are asynchronous. A screenshot
        # immediately after set_viewport_size can capture the old GPU viewport.
        page.wait_for_function("""() => {
          const canvas=document.querySelector('#character-canvas canvas');
          if(!canvas)return false;
          const box=canvas.getBoundingClientRect();
          const ratio=Math.min(devicePixelRatio||1,2,2048/Math.max(box.width,box.height));
          return Math.abs(canvas.width-box.width*ratio)<=2 &&
                 Math.abs(canvas.height-box.height*ratio)<=2 && box.width<=innerWidth;
        }""")
        before_resize_frame = page.evaluate("CompanionApp.scene.getStats().frames")
        page.wait_for_function(
            "previous=>CompanionApp.scene.getStats().frames>previous+1",
            arg=before_resize_frame,
        )
        report["mobile_canvas"] = page.evaluate("""() => {
          const c=document.querySelector('#character-canvas canvas'),b=c.getBoundingClientRect();
          return {width:c.width,height:c.height,cssWidth:b.width,cssHeight:b.height};
        }""")
        report["checks"]["mobile_canvas_resized_and_redrawn"] = True
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(out / "06-mobile-layout.png"))
        report["checks"]["mobile_no_horizontal_overflow"] = True
        r = page.request.post(
            base + "/api/characters/create",
            headers=headers,
            data={"name": "隔离回归角色"},
        )
        assert r.ok
        page.evaluate("CompanionApp.core.refresh(true)")
        page.wait_for_function(
            '()=>document.querySelectorAll("#character-canvas canvas").length===0'
        )
        page.screenshot(path=str(out / "07-role-switch-released.png"))
        report["checks"]["role_switch_releases_webgl_canvas"] = True
        if args.study_room:
            assert page.locator("#study-goal").input_value() == ""
            assert page.evaluate("CompanionStudy.snapshot().rounds") == 0
            report["checks"]["study_role_switch_isolates_goals_and_progress"] = True
        assert not report["errors"], report["errors"]
        report["passed"] = True
        video = page.video
        context.close()
        video.save_as(str(out / "actual-browser-regression.webm"))
        browser.close()
except Exception as e:
    report.update(passed=False, error=str(e), traceback=traceback.format_exc())
    print(report["traceback"])
    try:
        page.screenshot(path=str(out / "FAILED.png"))
    except Exception:
        pass
finally:
    f.tearDown()
    report["files"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.glob("*")
        if p.is_file() and p.name != "report.json"
    }
    after = source_hashes()
    report["tested_source_commit"] = commit_before
    report["working_tree_dirty_at_start"] = dirty_before
    report["source_sha256"] = source_before
    report["sources_unchanged_during_check"] = source_before == after
    if source_before != after:
        report["passed"] = False
        report["source_mutations"] = sorted(
            name
            for name in source_before.keys() | after.keys()
            if source_before.get(name) != after.get(name)
        )
    report["model_sha256"] = hashlib.sha256(args.model_zip.read_bytes()).hexdigest()
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report.get("passed") else 1)
