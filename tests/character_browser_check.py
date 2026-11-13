"""Real Chrome acceptance of self-service PNG roles with local AI/audio fixtures.

PNG files are synthetic geometric images. Audio is a synthetic test tone. This
checks actual browser/HTTP/media behavior, not artwork, voice or model quality.
"""
from pathlib import Path
import io
import json
import math
import struct
import sys
import time
import traceback
import wave

from playwright.sync_api import sync_playwright

from test_character_http import CharacterHTTPTests, png_fixture

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('/workspace/dist')


def tone():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b''.join(struct.pack('<h', int(600*math.sin(2*math.pi*440*i/24000))) for i in range(24000*4)))
    return out.getvalue()


def main():
    fixture = CharacterHTTPTests('test_new_identity_has_separate_memories_chat_tasks_and_personality')
    report = {'date': '2026-11-12', 'scope': 'real Chrome, HTTP, SQLite and PNG decoder; synthetic PNG/tone and fake LLM/TTS',
              'status': 'RUNNING', 'checks': {}, 'product_connections': 0,
              'not_tested': ['Live2D', 'native desktop host/window controls', 'microphone', 'real voice/model quality', 'target-user hardware/p95', 'default autoplay restriction'],
              'autoplay': 'test launch allows autoplay for deterministic HTMLAudio lifecycle checks'}
    fixture.setUp()
    app = fixture.app
    original_state = app.state
    app.state = lambda: {**original_state(), 'local_voice_available': True}
    app.synthesize = lambda text: tone()
    base = f'http://127.0.0.1:{fixture.server.server_port}'
    png1 = png_fixture((70, 100, 200, 200))
    png2 = png_fixture((190, 70, 100, 210))
    talk = png_fixture((210, 180, 50, 230))
    errors, alerts = [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            def dialog(dialog):
                if dialog.type == 'alert':
                    alerts.append(dialog.message)
                dialog.accept()
            page.on('dialog', dialog)
            loaded = page.goto(base, wait_until='networkidle')
            policy = loaded.headers.get('content-security-policy', '')
            img_policy = next(part for part in policy.split(';') if part.strip().startswith('img-src'))
            assert 'blob:' in img_policy, 'local file previews require blob: in img-src'
            report['checks']['csp_allows_local_blob_image_preview'] = 'passed'
            page.wait_for_function('()=>app?.active_character_id && !polling')
            first_id = page.evaluate('()=>app.active_character_id')
            page.request.post(base+'/api/settings', data={'voice': False, 'expected_character_id': first_id}, headers={'X-Companion': 'local-app'})
            page.evaluate('()=>refresh(true)')
            def state():
                return page.request.get(base+'/api/state').json()
            def upload(data, filename='任意角色名.png', talk_data=None):
                page.locator('#asset-idle').set_input_files({'name': filename, 'mimeType': 'image/png', 'buffer': data})
                if talk_data is not None:
                    page.locator('#asset-talk').set_input_files({'name': '说话状态.png', 'mimeType': 'image/png', 'buffer': talk_data})
                page.locator('#appearance-preview').wait_for(state='visible')
                page.wait_for_function('()=>document.querySelector("#appearance-preview-image").naturalWidth>0')
                before = state()['active_character'].get('appearance_id')
                page.locator('#preview-appearance').click()
                page.wait_for_function('()=>document.querySelector("#appearance-status").textContent.includes("已检查") && !document.querySelector("#activate-appearance").disabled')
                assert state()['active_character'].get('appearance_id') == before
                return page.evaluate('()=>pendingAsset.id')
            page.locator('[data-view=characters]').click()
            asset1 = upload(png1, talk_data=talk)
            assert page.locator('#appearance-preview-image').get_attribute('src').find(asset1) >= 0
            report['checks']['real_file_upload_preview_without_activation'] = 'passed'
            page.locator('#activate-appearance').click()
            page.wait_for_function('(id)=>(app.active_character.appearance_id||app.active_character.avatar_revision)===id', arg=asset1)
            page.wait_for_function('(id)=>document.querySelector("#portrait-avatar").src.includes(id) && document.querySelector("#portrait-avatar").naturalWidth===96', arg=asset1)
            report['checks']['confirmed_activation_uses_decoded_uploaded_png'] = 'passed'
            asset2 = upload(png2, filename='第二套独立结构.png')
            page.locator('#activate-appearance').click()
            page.wait_for_function('(id)=>(app.active_character.appearance_id||app.active_character.avatar_revision)===id', arg=asset2)
            old_card = page.locator('#appearance-list .appearance-card').filter(has=page.locator('img[src*="'+asset1+'"]'))
            old_card.get_by_role('button', name='使用', exact=True).click()
            page.wait_for_function('(id)=>(app.active_character.appearance_id||app.active_character.avatar_revision)===id', arg=asset1)
            report['checks']['second_revision_and_user_rollback'] = 'passed'
            page.locator('[data-view=memory]').click()
            page.locator('#memory-input').fill('ALPHA_BROWSER_MEMORY')
            page.locator('#memory-form button').click()
            page.locator('#memory-list').filter(has_text='ALPHA_BROWSER_MEMORY').wait_for()
            page.locator('[data-view=chat]').click()
            page.locator('#message-input').fill('ALPHA_BROWSER_CHAT')
            page.locator('#send').click()
            page.wait_for_function('()=>!busy && app.messages.some(m=>m.role==="assistant"&&m.kind==="chat")')
            page.locator('#message-input').fill('ALPHA_UNSENT_DRAFT')
            page.locator('[data-view=characters]').click()
            xss_name = '<img src=x onerror=alert(1)>乙'
            page.locator('#character-name').fill(xss_name)
            page.locator('#character-create-form button').click()
            page.wait_for_function('(id)=>app.active_character_id!==id && !charactersBusy', arg=first_id)
            second_id = page.evaluate('()=>app.active_character_id')
            assert page.locator('#message-input').input_value() == ''
            assert 'ALPHA_BROWSER' not in json.dumps(state(), ensure_ascii=False)
            assert page.locator('#character-list img[src=x]').count() == 0
            assert alerts == []
            report['checks']['new_identity_isolated_and_name_is_plain_text'] = 'passed'
            page.locator('[data-view=memory]').click()
            page.locator('#memory-input').fill('BETA_BROWSER_MEMORY')
            page.locator('#memory-form button').click()
            page.locator('#memory-list').filter(has_text='BETA_BROWSER_MEMORY').wait_for()
            page.locator('#character-select').select_option(first_id)
            page.wait_for_function('(id)=>app.active_character_id===id&&!charactersBusy', arg=first_id)
            assert page.locator('#message-input').input_value() == 'ALPHA_UNSENT_DRAFT'
            assert 'ALPHA_BROWSER_MEMORY' in str(state()['memories'])
            assert 'BETA_BROWSER_MEMORY' not in str(state()['memories'])
            assert 'ALPHA_BROWSER_CHAT' in str(state()['messages'])
            report['checks']['switch_back_preserves_own_draft_chat_memory_and_appearance'] = 'passed'
            page.reload(wait_until='networkidle')
            page.wait_for_function('(id)=>app?.active_character_id===id', arg=first_id)
            assert state()['active_character'].get('appearance_id', state()['active_character'].get('avatar_revision')) == asset1
            assert asset1 in page.locator('#portrait-avatar').get_attribute('src')
            report['checks']['selection_and_appearance_persist_on_reload'] = 'passed'
            page.locator('[data-view=characters]').click()
            discarded = upload(png2, filename='取消这份.png')
            page.locator('#cancel-appearance').click()
            page.wait_for_function('()=>document.querySelector("#appearance-preview").hidden')
            page.wait_for_function('(id)=>!appearanceAssets.some(a=>a.id===id)', arg=discarded)
            assert (state()['active_character'].get('appearance_id') or state()['active_character'].get('avatar_revision')) == asset1
            report['checks']['cancel_preview_discards_only_candidate'] = 'passed'
            page.locator('#asset-idle').set_input_files({'name': 'fake.png', 'mimeType': 'image/png', 'buffer': b'not a png'})
            page.locator('#character-error').wait_for(state='visible')
            assert (state()['active_character'].get('appearance_id') or state()['active_character'].get('avatar_revision')) == asset1
            report['checks']['invalid_png_does_not_change_current_character'] = 'passed'
            page.locator('[data-view=chat]').click()
            page.request.post(base+'/api/settings', data={'voice': True, 'expected_character_id': first_id}, headers={'X-Companion': 'local-app'})
            page.evaluate('()=>refresh(true)')
            page.locator('.message.assistant .read-button').last.click()
            page.wait_for_function('()=>localAudio && localAudio.currentTime>.03 && document.querySelector("#portrait-avatar").src.includes("talk.png")')
            page.locator('#stop-voice').click()
            page.wait_for_function('()=>!localAudio && document.querySelector("#portrait-avatar").src.includes("idle.png")')
            report['checks']['real_htmlaudio_drives_talk_state_and_stop_restores_idle'] = 'passed'
            page.locator('.message.assistant .read-button').last.click()
            page.wait_for_function('()=>localAudio&&localAudio.currentTime>.03')
            page2 = context.new_page()
            page2.on('pageerror', lambda error: errors.append(str(error)))
            page2.goto(base, wait_until='networkidle')
            page2.wait_for_function('()=>app?.active_character_id')
            page2.locator('.message.assistant .read-button').last.click()
            page2.wait_for_function('()=>localAudio&&localAudio.currentTime>.03')
            page.wait_for_function('()=>!localAudio||localAudio.paused')
            page2.locator('#stop-voice').click()
            page2.close()
            report['checks']['two_browser_views_have_single_audio_owner'] = 'passed'
            page.locator('.message.assistant .read-button').last.click()
            page.wait_for_function('()=>localAudio&&localAudio.currentTime>.03')
            page.locator('#character-select').select_option(second_id)
            page.wait_for_function('(id)=>app.active_character_id===id&&!charactersBusy', arg=second_id)
            assert page.evaluate('()=>!localAudio&&!document.body.classList.contains("is-speaking")')
            assert 'ALPHA_BROWSER_CHAT' not in str(state()['messages'])
            report['checks']['switch_identity_stops_audio_and_old_mouth_state'] = 'passed'
            page.locator('[data-view=characters]').click()
            for width in [1440, 390, 360]:
                page.set_viewport_size({'width': width, 'height': 900})
                assert not page.evaluate('()=>document.documentElement.scrollWidth>innerWidth+2'), width
            report['checks']['layout_1440_390_360'] = 'passed'
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.locator('[data-view=chat]').click()
            page.screenshot(path=str(OUT/'characters-desktop.png'), full_page=False)
            page.locator('#toggle-chat').click()
            assert page.locator('body').evaluate('(el)=>el.classList.contains("chat-collapsed")')
            page.locator('#toggle-chat').click()
            assert not page.locator('body').evaluate('(el)=>el.classList.contains("chat-collapsed")')
            report['checks']['character_stage_collapses_and_expands_without_identity_change'] = 'passed'
            page.set_viewport_size({'width': 390, 'height': 900})
            page.locator('[data-view=characters]').click()
            page.screenshot(path=str(OUT/'characters-mobile.png'), full_page=False)
            assert errors == [], errors
            report['javascript_errors'] = errors
            report['checks']['javascript_runtime'] = 'passed'
            browser.close()
        report['status'] = 'passed'
    except Exception as error:
        report.update({'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc(), 'javascript_errors': errors})
        raise
    finally:
        fixture.tearDown()
        (ROOT/'review/character-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
