"""PC Chrome check for owner status recovery; injected media receipts are synthetic.

No model, TTS, public broadcast, Bili account or audience result is established.
Uses the product's existing five-second state refresh, not a test polling loop
to change the page. Browser assertions wait for observable DOM changes only.
"""
import argparse
import contextlib
import json
from pathlib import Path
import platform
import time
import threading

from playwright.sync_api import sync_playwright
from test_character_http import CharacterHTTPTests, wav_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chrome', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ui-source', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    f = CharacterHTTPTests()
    f.setUp()
    output = f.app.integrations().output
    result = {'scope': 'PC Chrome owner-state UI with synthetic backend media receipts',
              'real_model': False, 'real_tts': False, 'real_bili': False,
              'real_obs': False, 'windows': False, 'viewer_received': False,
              'checks': {}, 'latencies_ms': {}, 'requests': [], 'errors': []}
    context = browser = pw = None
    consumer_stop = threading.Event()
    consumer = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(executable_path=args.chrome, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1280, 'height': 960},
                                      record_video_dir=str(args.out / 'video'))
        context.add_init_script('''(()=>{const Native=BroadcastChannel;window.hostChannels={opened:0,closed:0};window.BroadcastChannel=class extends Native{constructor(name){super(name);this.hostTracked=name==='companion-live-output';if(this.hostTracked)window.hostChannels.opened++;}close(){if(this.hostTracked){window.hostChannels.closed++;this.hostTracked=false;}return super.close();}}})()''')
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on('pageerror', lambda error: result['errors'].append(str(error)))
        page.on('request', lambda request: result['requests'].append({
            'method': request.method, 'path': request.url.split(f'http://127.0.0.1:{f.server.server_port}')[-1]}))
        if args.ui_source:
            source = args.ui_source.read_text()
            page.route('**/connectors-ui.js', lambda route: route.fulfill(body=source, content_type='application/javascript'))
        base = f'http://127.0.0.1:{f.server.server_port}'
        page.goto(base)
        page.wait_for_function('()=>window.CompanionApp?.core.get().state')
        page.evaluate('()=>window.CompanionApp.openConnections()')
        page.get_by_role('button', name='哔哩哔哩直播预览', exact=True).click()

        def job(ident):
            now = time.monotonic()
            item = output.begin({'event_id': ident, 'room_id': 'owner-ui-fixture',
                                 'source': 'local_rehearsal', 'origin': 'local_rehearsal',
                                 'text': '跟直播的互动怎么做 · '+ident, 'received_at': now, 'expires_at': now + 30})
            return output.finish(item['id'], '状态机测试回放；不是模型作答。', 'fixture-' + ident)

        def wait_state(ident, state, key):
            started = time.monotonic()
            page.locator(f'.live-answer[data-state="{state}"]').filter(has=page.get_by_role('heading', name=output.jobs[ident]['question'], exact=True)).wait_for(timeout=7000)
            result['latencies_ms'][key] = round((time.monotonic() - started) * 1000, 1)

        item = job('completion')
        page.get_by_role('button', name='刷新', exact=True).click()  # Common initial fixture; no further manual refresh.
        wait_state(item['id'], 'review', 'review_initial_fixture')
        approve = page.get_by_role('button', name='播放这条回答', exact=True)
        approve.focus()
        approve.evaluate('(node)=>node.dataset.focusGuard="original"')
        page.wait_for_timeout(5300)
        result['checks']['unchanged_refresh_preserves_action_focus'] = approve.evaluate(
            '(node)=>document.activeElement===node&&node.dataset.focusGuard==="original"')

        # Fill all unrelated forms, then observe real owner-state HTTP updates.
        page.locator('.live-context > summary').click()
        page.locator('.live-material > summary').click()
        page.get_by_text('直播间设置', exact=True).click()
        values = {'本场公开背景': '未发送背景', '本场公开教材': '未发送材料',
                  'Access Key ID': 'not-submitted', 'Access Key Secret': 'not-submitted-secret',
                  '应用ID': 'not-submitted-app', '直播间ID': 'not-submitted-room',
                  '主播身份码': 'not-submitted-anchor', '公开表达方式': '未发送设置'}
        for label, value in values.items():
            page.get_by_label(label, exact=True).fill(value)
        focused = page.get_by_label('本场公开背景', exact=True)
        focused.focus()
        focused.evaluate('(node)=>{node.dataset.focusGuard="draft";node.setSelectionRange(1,4)}')
        before = focused.evaluate('(node)=>({value:node.value,start:node.selectionStart,end:node.selectionEnd,focused:document.activeElement===node})')
        requests_start = len(result['requests'])
        auth = 'Bearer ' + output.open()
        output.prepare(item['id'], True)
        output.ready(item['id'], wav_fixture())
        client = 'synthetic-owner-consumer'
        output.poll(auth, client)
        def heartbeat():
            while not consumer_stop.wait(.25):
                try:
                    output.poll(auth, client)
                    result['synthetic_consumer_heartbeats'] = result.get('synthetic_consumer_heartbeats', 0) + 1
                except ValueError:
                    break
        consumer = threading.Thread(target=heartbeat, daemon=True)
        consumer.start()
        output.receipt(auth, item['id'], client, 'playing')
        wait_state(item['id'], 'playing', 'playing_existing_refresh')
        output.receipt(auth, item['id'], client, 'completed')
        wait_state(item['id'], 'completed', 'completed_existing_refresh')
        after = focused.evaluate('(node)=>({value:node.value,start:node.selectionStart,end:node.selectionEnd,focused:document.activeElement===node})')
        result['checks']['draft_focus_selection_unchanged'] = before == after
        result['checks']['all_unsent_fields_unchanged'] = all(page.get_by_label(label, exact=True).input_value() == value for label, value in values.items())
        result['checks']['settings_stay_open'] = page.locator('.live-context').evaluate('(node)=>node.open') and page.locator('.live-material').evaluate('(node)=>node.open')
        result['checks']['automatic_status_is_read_only'] = all(r['method'] == 'GET' for r in result['requests'][requests_start:])
        page.screenshot(path=str(args.out / 'completed-with-drafts.png'), full_page=True)

        failed = job('failure')
        output.fail(failed['id'])
        wait_state(failed['id'], 'failed', 'failure_existing_refresh')
        cancelled = job('cancel')
        output.cancel()
        wait_state(cancelled['id'], 'cancelled', 'cancel_existing_refresh')
        result['checks']['terminal_states_without_manual_refresh'] = True

        # Keyboard activation of the real product stop route remains available.
        stop = page.get_by_role('button', name='停止播放', exact=True)
        stop.focus()
        with page.expect_request(lambda request: request.url.endswith('/api/connectors/bili/output/stop')):
            page.keyboard.press('Enter')
        result['checks']['stop_keyboard_reachable'] = True

        # Local rehearsal has its own unsent field; use a real product start.
        result['previous_session_audit'] = list(output.audit)
        page.get_by_role('button', name='本地演练', exact=True).click()
        output = f.app.integrations().output
        message = page.get_by_label('模拟观众消息', exact=True)
        message.fill('未发送的观众消息')
        message.focus()
        message.evaluate('(node)=>{node.dataset.focusGuard="message";node.setSelectionRange(2,5)}')
        local = job('local-field')
        wait_state(local['id'], 'review', 'local_review_existing_refresh')
        result['checks']['rehearsal_draft_preserved'] = message.evaluate('(node)=>node.value==="未发送的观众消息"&&node.dataset.focusGuard==="message"&&document.activeElement===node&&node.selectionStart===2&&node.selectionEnd===5')
        page.screenshot(path=str(args.out / 'local-message-draft.png'), full_page=True)

        # Instrument authority: untrusted BC state never paints; only a GET is triggered.
        requests_start = len(result['requests'])
        page.evaluate('()=>{const c=new BroadcastChannel("companion-live-output");c.postMessage({type:"changed",state:"completed",token:"not-a-credential"});c.close()}')
        page.wait_for_timeout(500)
        result['checks']['broadcast_does_not_paint_claimed_state'] = page.locator('.live-answer').filter(has=page.get_by_role('heading', name=output.jobs[local['id']]['question'], exact=True)).get_attribute('data-state') == 'review'
        result['checks']['broadcast_only_reads_authority'] = all(r['method'] == 'GET' for r in result['requests'][requests_start:])
        page.locator('.close-layer').click()
        page.wait_for_timeout(200)
        requests_start = len(result['requests'])
        page.evaluate('()=>{const c=new BroadcastChannel("companion-live-output");c.postMessage({type:"changed"});c.close()}')
        page.wait_for_timeout(500)
        result['checks']['closed_panel_broadcast_makes_no_request'] = len(result['requests']) == requests_start
        # Temporary sender channels above are tracked too and explicitly closed.
        result['checks']['closed_panel_disposes_channel'] = page.evaluate('()=>window.hostChannels.opened===window.hostChannels.closed')
        page.evaluate('()=>window.CompanionApp.openConnections()')
        page.get_by_role('button', name='哔哩哔哩直播预览', exact=True).click()
        held = []
        def hold_old_state(route):
            response = route.fetch()
            held.append((route, response))
        page.route('**/api/state', hold_old_state)
        page.evaluate('()=>{window.CompanionApp.core.refresh(true);return true}')
        page.wait_for_timeout(200)
        assert held, 'old owner state must be captured before switching identity'
        page.evaluate('()=>window.CompanionApp.core.character("create",{name:"状态隔离验收"})')
        for route, response in held:
            route.fulfill(response=response)
        page.unroute('**/api/state', hold_old_state)
        page.wait_for_timeout(200)
        result['checks']['identity_change_closes_panel_and_subscription'] = page.evaluate('()=>window.CompanionApp.ui.active!=="contacts"&&window.hostChannels.opened===window.hostChannels.closed')
        result['checks']['late_old_state_does_not_reopen_old_output'] = page.locator('.live-answer').count() == 0
        result['checks']['no_browser_error'] = not result['errors']
        result['environment'] = {'platform': platform.platform(), 'chrome': browser.version}
        result['audit'] = list(output.audit)
        result['automatic_get_count'] = sum(r['path'] == '/api/state' for r in result['requests'])
        result['passed'] = all(result['checks'].values())
    except Exception as error:
        result['failure'] = str(error)
        raise
    finally:
        consumer_stop.set()
        if consumer:
            consumer.join(1)
        if context:
            with contextlib.suppress(Exception):
                context.tracing.stop(path=str(args.out / 'trace.zip'))
            with contextlib.suppress(Exception):
                context.close()
        if browser:
            with contextlib.suppress(Exception):
                browser.close()
        if pw:
            pw.stop()
        f.tearDown()
        (args.out / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': result.get('passed'), 'checks': result['checks'], 'latencies_ms': result['latencies_ms']}, ensure_ascii=False))
    assert result['passed'], result['checks']


if __name__ == '__main__':
    main()
