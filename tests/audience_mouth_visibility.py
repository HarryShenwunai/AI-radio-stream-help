"""Diagnostic-only opacity ablation, not a proposed mouth repair."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import urllib.parse
import zipfile

from audience_model_diagnosis import ROOT, compare, digest, roi_diff
from playwright.sync_api import sync_playwright
from program_output_browser import OfflineBoundary, OFFLINE_CHROME_FLAGS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--owner-local', type=Path, required=True)
    parser.add_argument('--chrome', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original = args.model.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        resources = {'/runtime/'+name: archive.read(name) for name in archive.namelist()}
    resources.update({'/': (ROOT/'tests/audience_model_probe.html').read_bytes(),
                      '/owned/core.js': (args.owner_local/'live2dcubismcore.min.js').read_bytes(),
                      '/owned/runtime.js': (args.owner_local/'build/owner-live2d-runtime.js').read_bytes()})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            name = urllib.parse.urlsplit(self.path).path
            body = resources.get(name)
            if body is None:
                self.send_error(404)
                return
            content = 'text/html' if name == '/' else 'application/javascript' if name.endswith('.js') else 'application/json' if name.endswith('.json') else 'image/png' if name.endswith('.png') else 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    boundary = OfflineBoundary(server.server_port, loopback_transport=True)
    report = {'scope': 'Actual Core diagnostic forced drawable opacity, NOT a parameter binding repair',
              'control_model_sha256': digest(original), 'rows': [], 'errors': []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=args.chrome, args=['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader', *OFFLINE_CHROME_FLAGS])
            context = browser.new_context(viewport={'width': 720, 'height': 906}, record_video_dir=str(args.out/'video'), record_video_size={'width': 720, 'height': 906})
            boundary.install(context)
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            try:
                page = context.new_page()
                page.on('pageerror', lambda error: report['errors'].append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.wait_for_function('()=>window.diagnosticReady||window.diagnosticError', timeout=60000)
                assert not page.evaluate('()=>window.diagnosticError')
                bounds = page.locator('canvas').bounding_box()
                assert bounds == {'x': 0, 'y': 0, 'width': 720, 'height': 876}, bounds
                baseline = page.evaluate('()=>diagnosticMouthOpacity(0)')
                page.evaluate('()=>diagnosticLabel("诊断：原嘴补片 opacity 0 · 非修复")')
                pixels = page.screenshot(path=str(args.out/'opacity-0.png'))
                for value in [.5, 1, 0]:
                    actual = page.evaluate('(value)=>diagnosticMouthOpacity(value)', value)
                    page.evaluate('(text)=>diagnosticLabel(text)', f'诊断：原嘴补片 opacity {value} · 非修复')
                    image = page.screenshot(path=str(args.out/f'opacity-{value:g}-comparison.png'))
                    diff = compare(baseline, actual)
                    row = {'requested_drawable_opacity': value, 'mouth': [mesh for mesh in actual['drawables'] if mesh['name'] == 'Mouth_open'],
                           **diff, 'roi': roi_diff(pixels, image, (361, 329, 465, 405))}
                    report['rows'].append(row)
                    page.wait_for_timeout(1200)
                report['instrument_checks'] = {'single_drawable_opacity_changes_only': all(not row['changes'] if row['requested_drawable_opacity'] == 0 else len(row['changes']) == 1 and row['changes'][0]['name'] == 'Mouth_open' and row['changes'][0]['max_vertex_delta'] == 0 for row in report['rows']),
                                               'opacity_one_actually_draws_patch': report['rows'][1]['mouth'][0]['opacity'] == 1 and report['rows'][1]['roi']['different_pixels'] > 0,
                                               'neutral_restores_identical_mouth_pixels': report['rows'][-1]['roi']['different_pixels'] == 0,
                                               'control_zip_unchanged': args.model.read_bytes() == original,
                                               'no_js_error': not report['errors'],
                                               'network_boundary': not boundary.blocked_page_requests and not boundary.blocked_python_connects}
                assert all(report['instrument_checks'].values()), report['instrument_checks']
            finally:
                context.tracing.stop(path=str(args.out/'trace.zip'))
                context.close()
                browser.close()
    finally:
        boundary.enabled = False
        server.shutdown()
        server.server_close()
        worker.join(2)
        (args.out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'instrument_checks': report['instrument_checks'], 'roi': [row['roi'] for row in report['rows']]}))


if __name__ == '__main__':
    main()
