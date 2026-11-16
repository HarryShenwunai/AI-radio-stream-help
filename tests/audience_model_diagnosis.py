"""Actual existing R3/Core ablation; no inference, new artwork, or production edits."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import time
import urllib.parse
import zipfile

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from program_output_browser import OfflineBoundary, OFFLINE_CHROME_FLAGS


ROOT = Path(__file__).resolve().parents[1]
PROTECTED = ('Cup', 'Near_', 'Far_', 'Sleeve_')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compare(before, after):
    changes = []
    protected = 0.
    for old, new in zip(before['drawables'], after['drawables'], strict=True):
        assert old['id'] == new['id']
        delta = max((abs(a-b) for a, b in zip(old['vertices'], new['vertices'], strict=True)), default=0.)
        opacity = abs(old['opacity']-new['opacity'])
        if delta or opacity:
            changes.append({'id': new['id'], 'name': new['name'], 'max_vertex_delta': delta, 'opacity_delta': opacity})
        if old['name'].startswith(PROTECTED):
            protected = max(protected, delta, opacity)
    return {'changes': changes, 'max_protected_delta': protected}


def roi_diff(before, after, box):
    old = np.asarray(Image.open(io.BytesIO(before)).convert('RGB').crop(box), dtype=np.int16)
    new = np.asarray(Image.open(io.BytesIO(after)).convert('RGB').crop(box), dtype=np.int16)
    delta = np.abs(old-new)
    return {'different_pixels': int(np.any(delta != 0, axis=2).sum()), 'max_channel_delta': int(delta.max()), 'mean_channel_delta': float(delta.mean())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--owner-local', type=Path, required=True)
    parser.add_argument('--chrome', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--require-visible-mouth', action='store_true')
    parser.add_argument('--baseline-evidence', type=Path)
    parser.add_argument('--skip-drivers', action='store_true')
    parser.add_argument('--mouth-cycle', action='store_true')
    parser.add_argument('--label', default='原R3')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original_model = args.model.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original_model)) as archive:
        resources = {'/runtime/'+n: archive.read(n) for n in archive.namelist()}
    core = (args.owner_local/'live2dcubismcore.min.js').read_bytes()
    runtime = (args.owner_local/'build/owner-live2d-runtime.js').read_bytes()
    resources.update({'/': (ROOT/'tests/audience_model_probe.html').read_bytes(), '/owned/core.js': core, '/owned/runtime.js': runtime})
    report = {'scope': 'Actual R3 baseline/candidate and installed Core, parameter/driver ablation; not Windows or independent aesthetic review',
              'run_label': args.label,
              'real_core': True, 'model_inference': False, 'new_artwork': False, 'production_modified': False,
              'model_sha256': digest(original_model), 'moc_sha256': digest(resources['/runtime/original.moc3']),
              'core_sha256': digest(core), 'runtime_sha256': digest(runtime), 'poses': [], 'errors': [], 'checks': {}, 'candidate_checks': {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            body = resources.get(path)
            if body is None:
                self.send_error(404)
                return
            content = 'text/html' if path == '/' else 'application/javascript' if path.endswith('.js') else 'application/json' if path.endswith('.json') else 'image/png' if path.endswith('.png') else 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    boundary = OfflineBoundary(server.server_port, loopback_transport=True)
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
                report['meta'] = page.evaluate('()=>window.diagnosticMeta')
                baseline = page.evaluate('()=>diagnosticPose({})')
                page.evaluate('(text)=>diagnosticLabel(text)', args.label+' · 所有外部驱动关闭 · 中性')
                neutral = page.screenshot(path=str(args.out/'neutral.png'))
                (args.out/'baseline.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2))
                # Boxes are source-art coordinates mapped to the fixed 720×876 canvas.
                scale = min(720/1137, 876/1383)
                canvas_bounds = page.locator('canvas').bounding_box()
                assert canvas_bounds and canvas_bounds['x'] == 0 and canvas_bounds['y'] == 0
                assert canvas_bounds['width'] == 720 and canvas_bounds['height'] == 876
                report['canvas_bounds_css_pixels'] = canvas_bounds
                offset_x, offset_y = (720-1137*scale)/2, (876-1383*scale)/2
                def map_box(box):
                    return tuple(round(value*scale+(offset_x if i%2 == 0 else offset_y)) for i, value in enumerate(box))
                boxes = {'mouth': map_box((570, 520, 735, 640)),
                         'eyes': map_box((550, 360, 825, 510)),
                         'face': map_box((340, 300, 840, 820))}
                report['roi_boxes_canvas_pixels'] = boxes
                cases = [('neutral-repeat', {}), ('mouth-half', {'ParamMouthOpenY': .5}), ('mouth-open', {'ParamMouthOpenY': 1}),
                         ('eyes-closed-positive', {'ParamEyeLOpen': 0, 'ParamEyeROpen': 0})]
                cases.extend((f'{axis}-{value:+g}', {axis: value}) for axis, values in [('ParamAngleX', [-15, 15]), ('ParamAngleY', [-10, 10]), ('ParamAngleZ', [-2, 2]), ('ParamEyeBallX', [-1, 1]), ('ParamEyeBallY', [-1, 1])] for value in values)
                for name, values in cases:
                    page.evaluate('(text)=>diagnosticLabel(text)', args.label+' · 单因素 '+name)
                    current = page.evaluate('(values)=>diagnosticPose(values)', values)
                    pixels = page.screenshot(path=str(args.out/(name+'.png')))
                    row = {'case': name, 'requested': values, 'applied': {key: current['parameters'][key] for key in values},
                           **compare(baseline, current), 'roi': {key: roi_diff(neutral, pixels, box) for key, box in boxes.items()},
                           'mouth_mesh': [{k: drawable[k] for k in ('id', 'name', 'opacity')} for drawable in current['drawables'] if drawable['name'] == 'Mouth_open']}
                    report['poses'].append(row)
                    (args.out/(name+'.core.json')).write_text(json.dumps(current, ensure_ascii=False))
                    page.wait_for_timeout(350)
                by_name = {row['case']: row for row in report['poses']}
                repeat = by_name['neutral-repeat']
                report['checks']['same_pose_pixel_and_geometry_negative_control'] = not repeat['changes'] and all(x['different_pixels'] == 0 for x in repeat['roi'].values())
                positive = by_name['eyes-closed-positive']
                report['checks']['eye_close_geometry_and_pixel_positive_control'] = bool(positive['changes']) and positive['roi']['eyes']['different_pixels'] > 0
                report['checks']['protected_hand_cup_pose_samples_unchanged'] = all(row['max_protected_delta'] == 0 for row in report['poses'])
                mouth = [by_name['mouth-half'], by_name['mouth-open']]
                mouth_moves = all(row['roi']['mouth']['different_pixels'] > 0 and any(x['name'] in {'Mouth_open', 'Neck_face'} for x in row['changes']) for row in mouth)
                report['asset_acceptance'] = {'visible_mouth_response': mouth_moves, 'criterion': 'Both half/full inputs must alter fixed mouth ROI AND mouth/face drawable, not merely a parameter'}
                if args.baseline_evidence:
                    original_report = json.loads((args.baseline_evidence/'report.json').read_text())
                    report['baseline_model_sha256'] = original_report['model_sha256']
                    original_neutral = (args.baseline_evidence/'neutral.png').read_bytes()
                    original_core = json.loads((args.baseline_evidence/'baseline.json').read_text())
                    neutral_comparison = {**compare(original_core, baseline), 'canvas_pixels': roi_diff(original_neutral, neutral, (0, 0, 720, 876))}
                    report['baseline_neutral_comparison'] = neutral_comparison
                    report['candidate_checks']['candidate_neutral_matches_baseline_exactly'] = not neutral_comparison['changes'] and neutral_comparison['canvas_pixels']['different_pixels'] == 0
                    protected_comparisons = []
                    for row in report['poses']:
                        if row['case'] in {'mouth-half', 'mouth-open'}:
                            continue
                        old_core = json.loads((args.baseline_evidence/(row['case']+'.core.json')).read_text())
                        new_core = json.loads((args.out/(row['case']+'.core.json')).read_text())
                        old_pixels = (args.baseline_evidence/(row['case']+'.png')).read_bytes()
                        new_pixels = (args.out/(row['case']+'.png')).read_bytes()
                        protected_comparisons.append({'case': row['case'], **compare(old_core, new_core), 'canvas_pixels': roi_diff(old_pixels, new_pixels, (0, 0, 720, 876))})
                    report['baseline_nonmouth_pose_comparisons'] = protected_comparisons
                    report['candidate_checks']['candidate_nonmouth_poses_match_baseline_exactly'] = all(not row['changes'] and row['canvas_pixels']['different_pixels'] == 0 for row in protected_comparisons)
                if args.mouth_cycle:
                    cycle = []
                    values = [n/20 for n in range(21)]+[n/20 for n in range(19, -1, -1)]
                    for frame, value in enumerate(values):
                        page.evaluate('(text)=>diagnosticLabel(text)', args.label+' · 连续闭开闭 '+str(value))
                        actual = page.evaluate('(value)=>diagnosticPose({ParamMouthOpenY:value})', value)
                        image = page.screenshot(path=str(args.out/f'cycle-{frame:02d}.png'))
                        changes = compare(baseline, actual)
                        opacity = next(mesh['opacity'] for mesh in actual['drawables'] if mesh['name'] == 'Mouth_open')
                        cycle.append({'frame': frame, 'requested': value, 'applied': actual['parameters']['ParamMouthOpenY'], 'mouth_opacity': opacity, **changes, 'roi': roi_diff(neutral, image, boxes['mouth'])})
                        page.wait_for_timeout(33)
                    report['mouth_cycle'] = cycle
                    report['candidate_checks']['mouth_cycle_only_changes_mouth_opacity'] = all(all(change['name'] == 'Mouth_open' and change['max_vertex_delta'] == 0 for change in row['changes']) for row in cycle)
                    report['candidate_checks']['mouth_cycle_opacity_tracks_input_float32'] = all(abs(row['mouth_opacity']-row['requested']) <= 2*float(np.finfo(np.float32).eps) for row in cycle)
                    report['candidate_checks']['mouth_cycle_returns_to_identical_closed_pixels'] = cycle[-1]['roi']['different_pixels'] == 0 and not cycle[-1]['changes']
                    report['candidate_checks']['mouth_cycle_roi_monotonic_open_close'] = all(cycle[i]['roi']['mean_channel_delta'] <= cycle[i+1]['roi']['mean_channel_delta'] for i in range(20)) and all(cycle[i]['roi']['mean_channel_delta'] >= cycle[i+1]['roi']['mean_channel_delta'] for i in range(20, 40))
                report['drivers'] = {}
                for mode in ([] if args.skip_drivers else ['idle-only', 'auto-only', 'both']):
                    started = time.monotonic()
                    report['drivers'][mode] = page.evaluate('(mode)=>diagnosticDriver(mode)', mode)
                    page.screenshot(path=str(args.out/(mode+'-last.png')))
                    report.setdefault('driver_wall_seconds', {})[mode] = time.monotonic()-started
                pairs = [] if args.skip_drivers else [('both', 'idle-only'), ('both', 'auto-only')]
                report['driver_differences'] = {a+'_versus_'+b: {key: max(abs(x['parameters'][key]-y['parameters'][key]) for x, y in zip(report['drivers'][a], report['drivers'][b], strict=True)) for key in ['ParamEyeLOpen', 'ParamEyeROpen', 'ParamBreath', 'ParamAngleZ', 'ParamEyeBallX']} for a, b in pairs}
                report['checks']['no_javascript_error'] = not report['errors']
                report['checks']['original_zip_unchanged'] = digest(args.model.read_bytes()) == report['model_sha256']
                report['network'] = {'scope': 'page/Python fixture boundary; network namespace recorded separately',
                                     'blocked_page_requests': boundary.blocked_page_requests,
                                     'blocked_python_connects': boundary.blocked_python_connects}
                report['checks']['fixture_network_boundary'] = not boundary.blocked_page_requests and not boundary.blocked_python_connects
                report['environment'] = {'chrome': browser.version, 'canvas': [720, 876], 'video_has_audio': False}
                report['diagnostic_completed'] = True
                report['instrument_checks_passed'] = all(report['checks'].values())
                report['input_model_rejected_by_visible_mouth_contract'] = not mouth_moves
            finally:
                context.tracing.stop(path=str(args.out/'trace.zip'))
                context.close()
                browser.close()
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        boundary.enabled = False
        server.shutdown()
        server.server_close()
        worker.join(2)
        (args.out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ['diagnostic_completed', 'instrument_checks_passed', 'candidate_checks', 'asset_acceptance', 'driver_differences']}, ensure_ascii=False))
    if not report['instrument_checks_passed'] or not all(report['candidate_checks'].values()) or (args.require_visible_mouth and not report['asset_acceptance']['visible_mouth_response']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
