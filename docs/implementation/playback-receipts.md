# 播放回执与下一轮语音上下文

2026-11-12。播放回执只代表本机播放器声明的播放状态，**不证明人真实听见**。

## 行为

- WAV 响应保持原接口，`X-Companion-Playback` 绑定本次身份、外观、消息、文本摘要、音频时长和随机凭证。前端只向认证的本机 receipt 接口回报，不把凭证放入UI、广播、state/export或测试报告。
- Audio真实开始/约1秒节流timeupdate报告进度；只有实际ended且位置到末尾才completed。pause/error/stop/隐藏/切角色/退出先捕获当前位置，再取消和清资源。迟到header或正文不会播放，仍向原scope报stopped。终态keepalive立即发送，待发旧progress丢弃；已在途的旧progress由后端sealed nonce拒绝，不能恢复终态。
- 无音素/分句alignment时，停止不按时间比例猜已听文字；整段完成只确认服务端真正合成的前缀（当前最多700字）。界面保留完整聊天原文，播放状态只写“朗读已停止/播放完成/已播放合成部分”，不造“听过几成”或估算内容。
- 系统SpeechSynthesis在朗读前绑定消息；有回执时保留完整原文，不在客户端删URL/Markdown后还确认原文。其总时长未知，仅在真实开始到结束/停止的elapsed最终上报；中途不报伪总时长。超过180秒保守停止并不确认全文。迟到的旧metadata和旧事件均不会播放或确认新角色内容。
- 下一轮服务器原子失效旧会话，并从模型上下文排除未确认的assistant尾部；数据库/UI原文不删除。网络回执未确认时显示对应状态，用户可再次明确朗读，不自动猜成功。
- UI状态按角色+消息隔离，最多512条，旧项淘汰。持久化与合并以服务端消息/文本摘要为准。

## 已执行

- `node tests/test_playback_ui.mjs`：**11项通过**，含实际发布控制器的625条长度4有界事件路径；检查单终态、位置范围、提前ended不完成、stop前捕获、延迟队列、未知系统时长和失败保守处理。这是有界状态探索，不是全程序/浏览器/操作系统或人类听觉的形式化证明。
- `node tests/test_voice_ui.mjs`：**13项通过**；额外验证真实app.js接线的系统原文、metadata迟到、正文下载中止、清资源前position和状态缓存上限。
- `python tests/playback_browser_check.py`：真实Chrome **7项通过**，真实Audio/HTTP/SQLite/prompt构建，合成4秒音、假LLM。控制基线先证明待测assistant原文原本进入上下文；在1.41/4秒中止→确认文字0→下一轮prompt无尾部，UI原文保留；再次真实播完→完整确认→之后prompt有原文。JS异常0、外部连接0。
- 视频及playing/stopped/next-turn/completed截图在 `/workspace/.live2d/evaluation/playback/`；JSON证据 `review/playback-browser-check.json` 已剔除凭证。视频约8秒，FFprobe确认有效，并已抽帧查看。

测试纠正：首次夹具只种了开头assistant，原对话规范本就会丢弃无前置user的开头内容，不能用来证明回执过滤。已补前置user和播放前prompt可进入的基线断言，再完成上述真实验证；旧失败视频/JSON留私人评估目录，不把夹具问题伪称产品修复。

真实TTS听感、音素级已听片段、系统音色真机、Windows后台播放和用户设备性能仍需分别验收。
