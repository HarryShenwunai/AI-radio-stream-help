"""Actual DOM/session probes, using the browser audit's isolated HTTP fixture."""


def check_study_room(page, out, report):
    page.wait_for_function("()=>Boolean(window.CompanionStudy)")
    assert page.locator("#study-main").is_disabled()
    page.locator("#study-goal").fill("理解导数定义，独立完成三道例题")
    page.locator('[data-study-duration="15"]').click()
    assert page.locator("#study-timer").inner_text() == "15:00"
    page.locator("#study-main").click()
    page.wait_for_timeout(1150)
    assert page.evaluate("CompanionStudy.isQuiet()")
    assert page.locator("#study-goal").is_disabled()
    page.screenshot(path=str(out / "study-01-focusing.png"))
    page.locator("#study-main").click()
    elapsed = page.evaluate("CompanionStudy.snapshot().elapsed")
    page.wait_for_timeout(500)
    assert page.evaluate("CompanionStudy.snapshot().elapsed") == elapsed
    report["checks"]["study_start_pause_preserves_elapsed"] = True
    page.reload()
    page.wait_for_function("()=>window.CompanionStudy?.snapshot().phase==='paused'")
    assert page.locator("#study-goal").input_value() == "理解导数定义，独立完成三道例题"
    assert page.evaluate("CompanionStudy.snapshot().elapsed") == elapsed
    report["checks"]["study_reload_is_paused_without_offline_credit"] = True
    page.locator("#study-main").click()
    page.evaluate("""() => {
      window.__studySpoken=0;window.__studySpeak=CompanionApp.speech.speak;
      CompanionApp.speech.speak=()=>{window.__studySpoken++;};
      const s=CompanionApp.core.get().state;
      const id=Math.max(0,...s.messages.map(m=>m.id))+1;
      CompanionApp.core.adopt({...s,settings:{...s.settings,voice:true},messages:[...s.messages,{id,role:'assistant',kind:'reminder',text:'隔离测试提醒'}]});
    }""")
    assert page.evaluate("window.__studySpoken") == 0
    page.evaluate("CompanionApp.speech.speak=window.__studySpeak")
    report["checks"]["study_focus_suppresses_incoming_auto_speech"] = True
    page.locator("#study-finish").click()
    assert page.evaluate("CompanionStudy.snapshot().phase") == "review"
    page.locator("#study-step-0").check()
    page.locator("#study-main").click()
    assert page.evaluate("CompanionStudy.snapshot().rounds") == 1
    assert page.evaluate("CompanionStudy.snapshot().phase") == "break"
    page.locator("#study-main").click()
    assert page.evaluate("CompanionStudy.snapshot().phase") == "idle"
    report["checks"]["study_review_break_next_round"] = True
    requests = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/chat/" in request.url else None
        ),
    )
    page.evaluate("""() => {const s=CompanionApp.core.get().state;
      CompanionApp.core.adopt({...s,settings:{...s.settings,engine:'api',api_model:'isolated-study-fixture'}});
    }""")
    page.locator("#study-ai-plan").click()
    assert "理解导数定义" in page.locator("#compose-text").input_value()
    assert not requests, requests
    report["checks"]["study_plan_is_editable_draft_not_auto_send"] = True
    page.locator("#compose-text").fill("")
    page.locator("#study-main").scroll_into_view_if_needed()
    page.evaluate("document.querySelector('.study-desk').scrollTop=0")
    page.wait_for_function("()=>CompanionApp.scene.ready")
    boxes = page.evaluate(
        """() => {const c=document.querySelector('#character-canvas').getBoundingClientRect(),d=document.querySelector('.study-desk').getBoundingClientRect();return {portraitRight:c.right,deskLeft:d.left,gap:d.left-c.right};}"""
    )
    assert boxes["gap"] >= 16, boxes
    action_box = page.locator(".study-ai-actions").bounding_box()
    desk_box = page.locator(".study-desk").bounding_box()
    assert (
        action_box["y"] + action_box["height"] <= desk_box["y"] + desk_box["height"]
    ), (action_box, desk_box)
    report["checks"]["study_primary_actions_not_clipped"] = True
    chat_box = page.locator(".interaction-area").bounding_box()
    footer_box = page.locator(".scene-bottom").bounding_box()
    assert (
        footer_box["y"] + footer_box["height"] <= chat_box["y"] + chat_box["height"]
    ), (footer_box, chat_box)
    report["checks"]["study_chat_controls_not_clipped"] = True
    report["study_layout"] = boxes
    report["checks"]["study_portrait_controls_have_no_overlap"] = True
    page.screenshot(path=str(out / "study-02-desktop.png"))
    page.locator("#theme-switch").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "night"
    assert "scene-forest.png" in page.evaluate(
        "getComputedStyle(document.querySelector('.companion-scene'),'::before').backgroundImage"
    )
    night_bounds = page.evaluate(
        """() => {const s=getComputedStyle(document.querySelector('.companion-scene'),'::before');return {top:s.top,left:s.left,right:s.right};}"""
    )
    assert night_bounds == {"top": "80px", "left": "24px", "right": "478px"}, (
        night_bounds
    )
    page.screenshot(path=str(out / "study-03-night.png"))
    page.locator("#theme-switch").click()
    report["checks"]["study_day_night_mode"] = True
    page.locator("#study-view").click()
    assert page.locator(".study-desk").is_hidden()
    assert page.locator("#study-view").is_visible()
    page.locator("#study-view").click()
    assert page.locator(".study-desk").is_visible()
    report["checks"]["study_immersive_mode_has_return_control"] = True
    for width in [320, 390, 768, 1440]:
        page.set_viewport_size({"width": width, "height": 900 if width > 700 else 844})
        page.wait_for_timeout(350)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
        assert page.locator("#study-main").is_visible()
        page.screenshot(path=str(out / f"study-layout-{width}.png"), full_page=True)
    report["checks"]["study_four_viewports_no_horizontal_overflow"] = True
    page.set_viewport_size({"width": 1280, "height": 900})
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(350)
