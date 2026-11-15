# 主播端终态与草稿保护

本轮只修复现有直播互动工作台的状态可见性。沿用已有的可见页每五秒 `core.refresh()`，订阅其 `change`；节目页的同源 `companion-live-output` 消息只作为读取权威状态的提示，不携带任务内容、令牌或可信状态。未新增定时器、平台连接或后台线程。

## 根因与最小修复

旧 `connectors-ui.js` 只在操作或手动刷新后重建界面，未订阅已有的状态刷新。因此服务端已经完成或失败，工作台仍可停在旧状态。直接把完整表单接入周期重绘会清除未提交凭据、替换输入节点并丢失焦点。

修复仅更新问题/回答区、讲解按钮和失效的输出链接。相同版本不重绘；同场次较旧版本和已经退出的场次不能覆盖当前状态。状态变化后，同一操作仍存在时保留键盘焦点；批准操作消失时焦点落到现有停止按钮，不自动执行任何操作。表单节点、草稿、折叠状态及选区保持不变。关闭面板或切换身份后释放订阅与广播通道。

本次未改配色、布局、美术、持杯姿势或平台发送规则。新弹幕仍由现有演练提交/刷新路径取得；本修复不声称增加了全平台实时接收。

## 复跑

从仓库根执行；Chrome 和录制编码器使用已经安装的本机路径。录制需要当前 Playwright 所要求的 ffmpeg，不能把缺编码器的失败当作产品失败或取消录像要求。

```bash
node --test tests/test_connector_settings_ui.mjs
/workspace/scratch/3bf0f6d52932/runtime-restored/quality-venv/bin/python -m ruff check tests/host_recovery_browser.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.build/p9-host/pw" PYTHONPATH=src:tests python3 tests/host_recovery_browser.py --chrome /workspace/scratch/3bf0f6d52932/AI-radio-stream-help/.build/r3-motion-revision/owner-local/chrome-headless-shell-linux64/chrome-headless-shell --out .build/p9-host/browser-final
```

该工作区的 `.build/p9-host/pw/ffmpeg-1011/ffmpeg-linux` 指向系统已有的 `/usr/bin/ffmpeg`，未下载编码器。其他环境应设置自己的有效编码器路径，不能照抄当前环境路径作为可移植安装保证。

旧版反例使用同一个新后端、相同脚本、相同初始刷新与合成事件；仅替换浏览器取得的旧 UI：

```bash
git show fa278f308e5d2930d4f2176e31549c12f04ac212:app/static/connectors-ui.js > .build/p9-host/old-connectors-ui.js
PLAYWRIGHT_BROWSERS_PATH="$PWD/.build/p9-host/pw" PYTHONPATH=src:tests python3 tests/host_recovery_browser.py --chrome /workspace/scratch/3bf0f6d52932/AI-radio-stream-help/.build/r3-motion-revision/owner-local/chrome-headless-shell-linux64/chrome-headless-shell --ui-source .build/p9-host/old-connectors-ui.js --out .build/p9-host/old-ui-rejected
```

旧版在相同输入下仍停留审核状态，七秒内没有显示服务端 `playing`，脚本退出 1。选择器依靠已有的状态属性和问题标题，不以新版增加的任务属性作为反例失败原因。

## 已取得的证据

- `browser-final/report.json`：状态、草稿、焦点、未发送凭据、折叠状态、键盘停止、广播权威边界、关闭释放、实际身份切换和旧响应检查通过，无浏览器错误。
- `browser-final/trace.zip`、`video/*.webm`：本机完整操作轨迹和录像；录像无音轨，不作为声音已经播出的证明。
- `completed-with-drafts.png`、`local-message-draft.png`：实际 Chrome 截图，已经目视检查。截图包含明确标记的机械状态回放，不是模型内容质量或直播美术展示。
- `old-ui-rejected/report.json` 及其录像/Trace：旧 UI 反例被拒绝。
- `source-freeze.json`：本次 C 源码、测试与证据哈希，供后续整体验收核对。

无广播提示时，本机观测的状态变更至工作台显示分别约为：playing 3.82 秒、completed 4.83 秒、failed 4.86 秒、cancelled 4.89 秒。它们是已有五秒刷新兜底的单轮观测，不是延迟保证、扬声器输出或观众收到的证据。广播路径仅触发额外的权威 GET；关闭后广播未造成请求。

## 保留的失败与边界

首次录制发现默认 Playwright ffmpeg 缺失；随后复用系统编码器。第一版回放夹具没有持续输出心跳，正确触发产品既有两秒消费者超时；第二版夹具在演练创建新 `LiveOutput` 后还握着旧实例。两者均通过查原始源码修正夹具，未放宽产品的心跳或三十秒期限，原记录保留在 `.build/p9-host/browser*`。

本测试通过合成消费者持续心跳及媒体回执检验工作台状态，并未播放真实声音。模型、TTS、人物声画联动由节目集成的另一组证据验收。Windows、OBS、真实 B 站、观众端和独立可用性/学习效果保持待验证；AI 开发检查不能代替这些结果。


## 起播前拒绝的状态语义

服务端的 `insufficient_playback_budget` 和 `invalid_audio` 仅在任务为 `failed` 时分别显示“剩余时限不足，未播放”和“音频无效，未播放”。其他内部原因、原型属性名或不同状态不通过这张白名单直接外显。这样不会把已经在起播前被拒绝的任务描述成播放过程中失败。

该小范围增量由 Node 受控原因测试验证；实际剩余预算不足与零播放调用由节目集成的预算浏览器验证，不能仅凭标签反推声音没有播放。既有状态更新、草稿、焦点和订阅机制未改变。
