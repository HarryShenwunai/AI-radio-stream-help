# 主流直播能力覆盖审查

观察日期：2026-11-15（Europe/London）。本轮是官方文档与项目证据盘点，未安装或实测竞品，未实施新功能。

覆盖已命名的主流工作链与能力，不保证穷尽不断变化的整个市场；官方文档不是竞品实测或好用证据。

## 如何取舍

四类决定：本轮原生必需、外部工具复用、后置评估、本轮排除。决定不是实现状态；必须验收音频路由也不要求重造混音器。所有收益均为需以真实任务验证的假设。

仍沿A–F推进：A协议草案待审、B–F未启动，发布阻断未解除；真实B站/OBS测试、手机、新美术、放杯与自动公开继续不在当前实施范围。

## 覆盖矩阵

### 准备与配置

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| SET-01 开播前预检与可用设备确认 | 局部模块存在，目标环境未验 | 本轮原生必需 / E | 助手须报告自己依赖的缺失，不能假造已连接；验收：固定关闭设备/运行库时应阻止对应路径并显示可恢复原因 | [OBS Windows 下载与支持系统](https://obsproject.com/download)、[Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes) |
| SET-02 场景集合、输出Profile及配置备份 | 本地布置可保存，外部配置未接通 | 外部工具复用 / E | 保留本项目配置，通用制作配置交成熟工具；验收：导入/恢复后核对源、输出参数和公开内容范围，不以导入成功作效果证明 | [OBS Scene Collections](https://obsproject.com/kb/scene-collections)、[OBS Profiles](https://obsproject.com/kb/profiles)、[Companion 导入导出](https://companion.free/user-guide/v4.2/config/import-export/) |
| SET-03 节目流程单与开场/休息/结束状态 | 协议草案待审 | 本轮原生必需 / A | 先定义一个任务的阶段，不堆转场样式；验收：同一事件从接收到终态均能定位责任与恢复步骤 | [OBS 制作功能](https://obsproject.com/)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |

该域项目证据与缺口：
- SET-01：依据：`src/companion_runtime/device_diagnostics.py`、`desktop/test/test_device_diagnostics.py`。缺口：Win10/11、实际音轨与驱动结果待验证。收益假设：减少无声或错误设备开场。
- SET-02：依据：`app/static/room.js`、`docs/validation/room-variety.md`。缺口：外部版本、迁移与配置恢复待验。收益假设：避免布置与推流参数混存。
- SET-03：依据：`docs/project/interaction-contract.md`。缺口：布局方向与用户任务收益未认可。收益假设：让主播理解当前阶段与下一动作。

### 采集与素材

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| CAP-01 窗口、屏幕、游戏、摄像头、采集卡源 | 项目有屏幕/设备模块，节目未接通 | 外部工具复用 / B | 不另造通用捕获系统；只向节目给允许的源；验收：明确选取窗口，取消/最小化/权限拒绝不转捕其他源 | [OBS Sources Guide](https://obsproject.com/kb/sources-guide) |
| CAP-02 浏览器、媒体、文本与课件源 | 节目页有字幕，媒体源方案未接入 | 外部工具复用 / B | 复用现有演示工具和输出页；验收：来源清单固定；私聊、配置和未允许材料不能进入画面/音轨 | [OBS Sources Guide](https://obsproject.com/kb/sources-guide)、[vMix Features](https://www.vmix.com/software/features.aspx) |
| CAP-03 采集授权、隐私提示与源失效处理 | 存在设备权限边界，节目级未联动 | 本轮原生必需 / B | 每个公开源须有明确允许范围；验收：断开指定源后停止该源并显示故障，不静默扩大捕获范围 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[OBS Sources Guide](https://obsproject.com/kb/sources-guide) |

该域项目证据与缺口：
- CAP-01：依据：`desktop/screen-capture.cjs`、`src/companion_runtime/perception.py`。缺口：第三方源与目标Windows未验。收益假设：复用完整采集能力。
- CAP-02：依据：`app/static/live-stage.html`、`docs/project/interaction-contract.md`。缺口：具体素材公开范围与实际捕获待验。收益假设：展示允许材料且不捕入私有界面。
- CAP-03：依据：`desktop/media-policy.cjs`、`desktop/screen-capture.cjs`。缺口：同一公开源快照尚未实现。收益假设：防止误播桌面或丢源后错误替代。

### 场景导播与透明输出

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| SCN-01 Preview/Program隔离与批准后切出 | 样稿与实际输出仍分离 | 本轮原生必需 / B | 接通同一批准快照是P0主线；验收：一条批准回答在同一节目角色/字幕/音频中可对应，未批准内容不输出 | [OBS 制作功能](https://obsproject.com/)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| SCN-02 多画面监看、精确变换/裁切/锁定 | 本地有三种布置，通用导播未接通 | 外部工具复用 / C | 助手只守自身角色/字幕安全区；通用源编辑复用；验收：同分辨率任务核对裁切、安全边距、误操作与恢复 | [OBS Sources Guide](https://obsproject.com/kb/sources-guide)、[OBS 制作功能](https://obsproject.com/) |
| SCN-03 透明输出、alpha一致性、不捕入管理UI | 已有边缘候选问题，根因未确认 | 本轮原生必需 / D | 先做合成链区分实验，不以色键或曝光掩盖；验收：同帧白灰黑底比较alpha/遮罩；节目中无操作控件 | [VTube Studio Windows透明输出](https://github.com/DenchiSoft/VTubeStudio/wiki/Recording-Streaming-with-OBS) |
| SCN-04 淡入淡出、Stinger及高级转场 | 未核实本项目转场能力 | 外部工具复用 / C | 当前先保证停止与正确内容，转场交成熟制作工具；验收：对比清晰度/打断成本，不能延迟紧急停止 | [OBS 制作功能](https://obsproject.com/)、[vMix Features](https://www.vmix.com/software/features.aspx) |
| SCN-05 摄像头抠像、虚拟背景与色彩处理 | 本项目未核实摄像头抠像或背景分割集成 | 外部工具复用 / D | 通用色键/色彩处理复用外部工具；虚拟背景分割后置核实。不得调整R3人物曝光掩盖边缘或原图问题；验收：固定摄像头/灯光/背景，用发丝、服饰与运动边缘反例检验漏抠/误删及额外负载；R3保护素材哈希不变 | [OBS Chroma Key Filter](https://obsproject.com/kb/chroma-key-filter)、[OBS Filters Guide](https://obsproject.com/kb/filters-guide) |

该域项目证据与缺口：
- SCN-01：依据：`app/static/room.js`、`app/static/live-stage.html`。缺口：整合未实施，A未冻结。收益假设：防止草稿和编辑过程上屏。
- SCN-02：依据：`app/static/room.css`、`docs/validation/room-variety.md`。缺口：多源/多屏原生Windows待验。收益假设：减少错误源、位置和安全区误操作。
- SCN-03：依据：`docs/project/interaction-contract.md`、`app/static/room.css`。缺口：Spout2/OBS插件未安装未测；不能认定灰边已确诊。收益假设：保持发丝/半透明部件与节目隔离。
- SCN-04：依据：未核实本项目现有实现。缺口：版本和资源开销未实测。收益假设：在可靠切出基础上减少突兀切换。
- SCN-05：依据：未核实本项目现有实现。缺口：绿幕条件、分割方案、插件与目标Windows负载均未实测；透明节目输出不是普通摄像头抠像。收益假设：在真实摄像头场景中分离背景并保持可辨识性。

### 人物表现

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| AV-01 人物库、外观修订与可回退场景 | 人物库/预览已局部开发验证 | 本轮原生必需 / D | 复用现有人物，禁止新美术扩张；验收：切换/恢复/缺资产不串角色；源图及持杯资产哈希保留 | [VTube Studio 官方手册](https://github.com/DenchiSoft/VTubeStudio/wiki)、[Live2DViewerEX 开发者说明](https://store.steampowered.com/app/616720/)、[本项目人物/布置边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/room-variety.md) |
| AV-02 表情、动画、热键与互斥状态 | 本地参数/动作入口存在，节目未联动 | 后置评估 / D | 基础说话先接通；高级表情需模型与认证条件；验收：仅允许已导出动作；取消或切身份后旧动作不串用 | [VTube Studio 表情](https://github.com/DenchiSoft/VTubeStudio/wiki/Expressions-%28a.k.a.-Stickers-or-Emotes%29)、[VTube Studio API认证](https://github.com/DenchiSoft/VTubeStudio#authentication) |
| AV-03 眨眼、呼吸、口型与实际语音绑定 | Core/口型有本地证据，实际stage未接角色 | 本轮原生必需 / B | 不是增加人物数量，而是可靠联动；验收：同一job音轨/字幕/口型对齐；停止和晚响应不复活 | [现有声音和角色候选](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/voice-room-original-direction.md)、[VTube Studio 官方手册](https://github.com/DenchiSoft/VTubeStudio/wiki) |
| AV-04 PC摄像头跟踪及状态参数输入 | 有感知/跟踪模块，未接现场答疑 | 后置评估 / D | 不宣称已听见/看见主播，也不改当前持杯姿势；验收：权限撤回即停止跟踪；无输入不造表情或理解状态 | [VTube Studio 官方手册](https://github.com/DenchiSoft/VTubeStudio/wiki)、[VTube Studio API认证](https://github.com/DenchiSoft/VTubeStudio#authentication) |

该域项目证据与缺口：
- AV-01：依据：`app/static/studio.js`、`app/static/room.js`。缺口：公开出镜身份与预览仍需契约绑定。收益假设：保留身份与稳定外观。
- AV-02：依据：`app/static/stage-actions.js`。缺口：Expression Groups为public beta；不能恢复放杯。收益假设：在模型支持时表达明确状态。
- AV-03：依据：`app/static/scene-controller.js`、`docs/validation/voice-room-original-direction.md`。缺口：系统音轨、视觉独立验收待取得。收益假设：节目人物与正在播出的声音一致。
- AV-04：依据：`src/companion_runtime/perception_tracking.py`。缺口：授权、导出参数与Windows性能待验。收益假设：在明确授权时增加现场表达。

### 音频路由与同步

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| AUD-01 逐应用音频隔离及防双捕回声 | 已有WAV与浏览器媒体，系统分路未验 | 外部工具复用 / F | 优先OBS，Win10需2004+，个别应用不兼容；验收：分别录助手/麦克风/背景，检查重复采入与回流 | [OBS 应用音频捕获](https://obsproject.com/kb/application-audio-capture-guide) |
| AUD-02 监听与节目混音、电平与静音 | 系统监听/节目混音未核实 | 外部工具复用 / F | Win11可选Wave Link；不得成为Win10共同必需依赖；验收：耳机与节目轨分别采样，错误设备/静音状态可辨认 | [Wave Link 3 技术规格](https://www.elgato.com/us/en/s/wave-link-app)、[OBS Audio Mixer](https://obsproject.com/kb/audio-mixer-guide) |
| AUD-03 降噪、门限、压缩、限幅、ducking与EQ | 现有音色/语速不是DSP链 | 外部工具复用 / D | 按实际音源需要复用，不默认对干净TTS叠满效果；验收：同段原音/处理音对照清晰度、削波、延迟与打断成本 | [OBS Filters Guide](https://obsproject.com/kb/filters-guide)、[Wave Link 3 技术规格](https://www.elgato.com/us/en/s/wave-link-app) |
| AUD-04 实际媒体状态、字幕/口型与延迟同步 | playing回执先于audio.play | 本轮原生必需 / B | 状态应依据实际媒体观察并保留层级；验收：拒绝audio.play/延迟音频时不显示已发声，录音与画面逐帧核对 | [OBS Filters Guide](https://obsproject.com/kb/filters-guide)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| AUD-05 设备切换、音频路径诊断与失效恢复 | 有设备诊断模块，公开输出设备未联动 | 本轮原生必需 / C | 助手原生报告可观察故障；Win11工具可辅助；验收：设备丢失不静默改到未允许目标继续播，故障可恢复 | [Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes)、[Wave Link 3 技术规格](https://www.elgato.com/us/en/s/wave-link-app) |
| AUD-06 音效板、背景音乐与双PC音频 | 未核实本项目能力 | 后置评估 / C | 不为精彩默认加音效或双机依赖；验收：比较打断与资源开销，素材授权、音量和停止可核对 | [Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes) |

该域项目证据与缺口：
- AUD-01：依据：`app/static/live-stage.js`、`docs/validation/local-product-rehearsal.md`。缺口：真实设备、OBS和目标机仍暂停/待验。收益假设：只采入允许的助手/麦克风音频。
- AUD-02：依据：未核实本项目现有实现。缺口：Wave Link3要求Win11、无ASIO，未安装实测。收益假设：区分主播听见和节目收到。
- AUD-03：依据：`src/companion_runtime/voice.py`。缺口：EQ插件、VST3兼容和效果延迟待验。收益假设：处理实际噪声和抢话，避免过度处理。
- AUD-04：依据：`app/static/live-stage.js`。缺口：系统声卡/观众端证据仍缺。收益假设：避免回执绿灯冒充已经发声。
- AUD-05：依据：`src/companion_runtime/device_diagnostics.py`。缺口：Smart Switch不是项目现成能力，Win10需替代。收益假设：设备消失时不给主播错误的完成状态。
- AUD-06：依据：未核实本项目现有实现。缺口：Wave Cast另购且两机版本一致。收益假设：仅在任务收益明确时补现场提示。

### 问题与聊天审核

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| CHAT-01 问题队列、当前问题、单条置顶 | 本地演练可选问题，状态可见性不完整 | 本轮原生必需 / C | 本地选择不等于平台置顶或文字发送；验收：问题/生成/批准/节目始终同一事件，重复点击不重复播 | [YouTube 桌面直播聊天/Q&A/置顶/投票](https://support.google.com/youtube/answer/2524549?co=GENIE.Platform%3DDesktop&hl=en)、[Twitch Mod View](https://help.twitch.tv/s/article/mod-view?language=en_US)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| CHAT-02 人工审核、慢速/屏蔽词/角色限制 | 本地批准已有，真实平台审核未接通 | 外部工具复用 / C | 原生保留批准，平台禁言等优先用官方工具；验收：未批准不公开；错误拦截可恢复，不能仅凭词命中永久丢弃 | [YouTube 聊天审核](https://support.google.com/youtube/answer/9826490?hl=en)、[Twitch Mod View](https://help.twitch.tv/s/article/mod-view?language=en_US) |
| CHAT-03 去重、合并、突发限流与问题过期 | 已有事件/TTL约束，负载下曾过期 | 本轮原生必需 / B | 要修调度根因，不放宽时限掩盖；验收：乱序/重复/重连/突发回放，旧问题过期不补播 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[YouTube 聊天审核](https://support.google.com/youtube/answer/9826490?hl=en) |
| CHAT-04 弹幕/礼物/付费留言/关注/开停播事件 | 本地合成接收可测，真实B站暂停 | 后置评估 / B | 只纳入事件设计，不能从索引推定全部权限；验收：将来经授权记录原始事件/协议版本及失效恢复 | [B站开放平台事件目录](https://openhome.bilibili.com/doc/4/c7b549c9-d5d6-0331-b510-465ed4107e01)、[B站开放平台FAQ](https://open-live.bilibili.com/document/5dffc297-6fd2-41ff-bd45-6e8b89e2a68e) |
| CHAT-05 跨平台聊天聚合、回复与relay | 未核实本项目跨平台聚合，当前B站真实测试暂停 | 后置评估 / C | 先完成单平台人工批准；读、发、relay分别核权限与去重，不能因Custom RTMP推流而声称聊天可用；验收：经授权分别验证读/回复/relay，保留平台来源与事件标识；relay回流不得当新观众问题，未授权目的地不发送 | [Restream 跨平台聊天能力](https://support.restream.io/en/articles/2379624-what-is-restream-chat)、[Restream 收取消息要求](https://support.restream.io/en/articles/2388185-read-incoming-chat-messages) |

该域项目证据与缺口：
- CHAT-01：依据：`app/static/connectors-ui.js`。缺口：平台置顶权限和真实接收未验。收益假设：主播知道当前要审核哪条。
- CHAT-02：依据：`src/companion_runtime/live_output.py`。缺口：账号角色、词表收益与误杀率待验证。收益假设：在突发弹幕时保持可控。
- CHAT-03：依据：`src/companion_runtime/live.py`、`src/companion_runtime/live_output.py`。缺口：合并收益与重负载阈值待基线锁定。收益假设：防止队列积压和过时回答。
- CHAT-04：依据：`src/companion_runtime/integration_service.py`。缺口：官方动态正文未展开，细节与可用性待复核。收益假设：保持事件来源和生命周期可追溯。
- CHAT-05：依据：未核实本项目现有实现。缺口：本轮未连接Restream或目标平台；Custom RTMP不提供聊天API；未授权平台文字发送。收益假设：未来多平台时减少主播切换与遗漏。

### 演示与字幕可达性

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| TEACH-01 课件/屏幕、批注、高亮、撤销与保存 | 有材料/屏幕模块，课堂收益未验 | 外部工具复用 / A | 复用演示软件，不强制教材或自建白板扩界面；验收：只公开允许窗口和批注；任务前后操作负担/理解结果对照 | [Zoom 桌面批注](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0067931)、[OBS Sources Guide](https://obsproject.com/kb/sources-guide) |
| TEACH-02 Q&A公私回答、答复标记和复开 | 本地job状态已有，公私界面仍需统一 | 本轮原生必需 / C | 借状态工作流，不复制全部会议控件；验收：公开/私下通道不串用，失败或复开保留正确事件 | [Zoom Q&A](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065237)、[YouTube 桌面直播聊天/Q&A/置顶/投票](https://support.google.com/youtube/answer/2524549?co=GENIE.Platform%3DDesktop&hl=en) |
| TEACH-03 批准回答字幕、长文本与可达性 | stage有字幕，长文本以拒绝为边界 | 本轮原生必需 / B | 中文/低延迟不能依赖平台自动字幕；TTS字幕与ASR分验；验收：批准文本/字幕/音轨一致，长文本完整可读、键盘/DPI可用 | [YouTube 直播自动字幕](https://support.google.com/youtube/answer/6373554?hl=en)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| TEACH-04 投票、问答反馈与独立理解检验 | 未核实本项目投票/独立学习收益 | 后置评估 / F | 平台反馈可复用，不能把投票率当掌握；验收：未见题控制原有知识/难度/顺序，比较独立作答和操作成本 | [YouTube 桌面直播聊天/Q&A/置顶/投票](https://support.google.com/youtube/answer/2524549?co=GENIE.Platform%3DDesktop&hl=en)、[Zoom Q&A](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065237) |
| TEACH-05 主播实时ASR字幕与多语翻译 | 未核实公共主播ASR或翻译字幕链路 | 后置评估 / B | 与批准回答的TTS字幕分开；先验证内容和隐私边界，不能用翻译字幕冒充助手听懂现场；验收：用未见且获准公开的真实音频核术语/漏词/误译、时间对齐与恢复；对比操作负担和理解，私有声轨不得送识别 | [Zoom 翻译字幕配置](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0059081)、[Zoom 多语字幕使用要求](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060844) |

该域项目证据与缺口：
- TEACH-01：依据：`desktop/screen-capture.cjs`、`docs/project/interaction-contract.md`。缺口：账号/主持权限、材料许可与真实课堂待验。收益假设：讲解真实允许材料。
- TEACH-02：依据：`app/static/connectors-ui.js`、`src/companion_runtime/live_output.py`。缺口：布局和接管负担未获用户认可。收益假设：区分已答、待审和需要恢复的问题。
- TEACH-03：依据：`app/static/live-stage.js`、`docs/validation/live-adverse-path-audit.md`。缺口：分句字幕尚未确认支持，Windows待验。收益假设：让回答可读、可核对且不假设自动字幕可用。
- TEACH-04：依据：未核实本项目现有实现。缺口：账户资格/接口scope与收益均待验证。收益假设：在学习场景收集反馈。
- TEACH-05：依据：未核实本项目现有实现。缺口：账号/附加服务、管理员开关、语言、ASR错误率/延迟和目标机开销待验证；不启用自动公开。收益假设：必要时降低实时听讲或跨语言理解障碍。

### 主持控制与自动化

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| CTRL-01 紧急停止、人工接管与安全热键 | 已有本地停止/撤权，桌面全局入口未验 | 本轮原生必需 / C | 停止不依赖购买硬件；外部热键是可选入口；验收：播放中取消清音轨/字幕/口型，失焦热键不能误控其他应用 | [Stream Deck 热键/配置](https://www.elgato.com/us/en/explorer/products/stream-deck/how-to-use-stream-deck-for-gaming-hotkeys-profiles-and-plugins/)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| CTRL-02 主持/审核/来宾角色与公开权限 | 人工批准已有，完整角色产品未实现 | 本轮原生必需 / A | 先明确单主播权限，不引组织账号系统；验收：外部消息不能改变配置或授予工具权；公开/私人边界有反例 | [Zoom Webinar角色](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065551)、[Twitch Mod View](https://help.twitch.tv/s/article/mod-view?language=en_US) |
| CTRL-03 硬件控制、宏、配置与真实反馈 | 未接通StreamDeck/Companion | 后置评估 / C | 先原生单次批准可靠；模块反馈不总可用；验收：按命令/媒体启动/系统捕获/观众分别取证，宏不得越权公开 | [Stream Deck 热键/配置](https://www.elgato.com/us/en/explorer/products/stream-deck/how-to-use-stream-deck-for-gaming-hotkeys-profiles-and-plugins/)、[Companion 触发器](https://companion.free/user-guide/v4.2/config/triggers/)、[Companion 反馈](https://companion.free/user-guide/v4.2/config/buttons/creating/feedbacks/) |
| CTRL-04 MCP/AI受控动作与配置管理 | 未接通且未获自动执行授权 | 后置评估 / A | 动作触发与配置管理分能力，不给弹幕工具权；验收：未授权动作拒绝，取消/旧会话不能继续执行 | [Stream Deck MCP](https://www.elgato.com/us/en/explorer/products/stream-deck/sd-mcp-setup/) |

该域项目证据与缺口：
- CTRL-01：依据：`app/static/live-stage.js`、`app/static/connectors-ui.js`。缺口：Windows焦点、设备及端到端中断指标待锁定。收益假设：在错误或抢话时立即接管。
- CTRL-02：依据：`docs/project/interaction-contract.md`。缺口：多人权限与账号系统后置。收益假设：防止外部消息拥有主播权限。
- CTRL-03：依据：未核实本项目现有实现。缺口：Companion本轮文档v4.2，设备模块和许可待核。收益假设：减少重复步骤且知道真实结果。
- CTRL-04：依据：未核实本项目现有实现。缺口：7.4桥接和8.0 beta不同，非稳定通用前提。收益假设：在明确白名单时降低控制成本。

### 录制回放

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| REC-01 同时录制、分轨和实际声画证据 | 有实际WAV/Chrome音频，系统分轨未验 | 外部工具复用 / E | 录制/编码交成熟工具，助手保留job关联记录；验收：核对每条音轨/画面/批准文本，普通播放器只播一轨不能误判丢轨 | [OBS Standard Recording](https://obsproject.com/kb/standard-recording-output-guide)、[OBS 多轨录制](https://obsproject.com/kb/advanced-recording-guide-and-multi-track-audio) |
| REC-02 选择性录制与干净节目素材 | 未接通，未核实实际录制配置 | 外部工具复用 / E | 作为复用候选，明确横向与双画布冲突；验收：逐源核对直播/录制包含关系，私有金丝雀不入档 | [Streamlabs 选择性录制](https://support.streamlabs.com/hc/en-us/articles/4413174869915-Selective-Recording-in-Streamlabs-Desktop) |
| REC-03 Replay Buffer、片段标记与会后复盘 | 未核实本项目回放能力 | 后置评估 / C | 主线可靠后评估，不以剪辑数充成果；验收：保存前后时段及原始时间线，对比操作成本和资源 | [OBS Studio Overview](https://obsproject.com/kb/OBS-Studio-Overview)、[vMix 下载/版本29](https://www.vmix.com/software/download.aspx) |
| REC-04 多机位慢动作、体育级回放 | 本轮不适用 | 本轮排除 / A | 当前不自建多机导播或体育回放；验收：只有目标任务改变才重新进入评估，记录排除理由 | [vMix Features](https://www.vmix.com/software/features.aspx)、[vMix 版本比较](https://www.vmix.com/purchase/) |

该域项目证据与缺口：
- REC-01：依据：`docs/validation/local-product-rehearsal.md`。缺口：目标设备、容器与同负载待验。收益假设：保留可复核的节目和独立音轨。
- REC-02：依据：未核实本项目现有实现。缺口：该能力官方限制横向源；不假定兼容Dual Output。收益假设：避免私有操作或不需要的源入档。
- REC-03：依据：未核实本项目现有实现。缺口：缓存磁盘/内存开销、版权与隐私待验。收益假设：保留关键提问/故障而不丢上下文。
- REC-04：依据：未核实本项目现有实现。缺口：vMix版本/机位/资源限制，不承诺用户已购买。收益假设：该类制作有用途但与当前单人主线无关。

### 编码网络与分发

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| DEL-01 硬件编码、帧率/分辨率与资源预算 | 目标RTX/Windows未验收 | 外部工具复用 / F | 编码复用，资源预算必须测；不能由有NVENC推出已通过；验收：固定负载分别记录渲染、编码、CPU/GPU及队列年龄 | [OBS 编码性能排障](https://obsproject.com/kb/encoding-performance-troubleshooting)、[OBS Standard Recording](https://obsproject.com/kb/standard-recording-output-guide) |
| DEL-02 重连、带宽变化与过期不补播 | 已有令牌/TTL，本地故障有证据 | 本轮原生必需 / B | 推流重连外部复用，助手自己撤销旧任务；验收：断线/重连/晚响应后旧任务仍被拒绝；不能靠降码率掩盖根因 | [OBS 推流连接排障](https://obsproject.com/kb/stream-connection-troubleshooting)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| DEL-03 多平台推流与PC横竖双画布 | 本轮未接通 | 后置评估 / A | 单一主线未完成先后置；PC竖版不等于手机开发；验收：分别核权限/目标数/版式和额外编码开销 | [Streamlabs Multistream](https://streamlabs.com/multistream) |
| DEL-04 虚拟摄像头与第三方应用输出 | 未接通该出口 | 外部工具复用 / B | 可选复用，禁止误送Preview或假定音频随视频正确；验收：显式选择Program，草稿/管理UI不出现，音频另采样 | [OBS Virtual Camera](https://obsproject.com/kb/virtual-camera-guide) |

该域项目证据与缺口：
- DEL-01：依据：`docs/project/p9-plan.md`。缺口：编码器/驱动、场景与实机基线待锁定。收益假设：让模型/人物/语音/编码能同跑。
- DEL-02：依据：`src/companion_runtime/live_output.py`。缺口：实际网络与平台保持暂停。收益假设：掉线恢复后不播旧问题。
- DEL-03：依据：未核实本项目现有实现。缺口：免费/Ultra不同；不解除手机开发禁止。收益假设：未来需要时分别适配目标画面。
- DEL-04：依据：未核实本项目现有实现。缺口：第三方应用/设备权限与音频路由待验。收益假设：将批准节目视频送到现有会议工具。

### 远程嘉宾与多机

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| REM-01 远程嘉宾、候场、邀请与移除 | 单人主线，无多人RTC证据 | 后置评估 / C | 复用成熟来宾工具，不自建多人通话；验收：候场/静音/移除/断线/回声逐项录制 | [Twitch Stream Together](https://help.twitch.tv/s/article/stream-together)、[vMix Features](https://www.vmix.com/software/features.aspx) |
| REM-02 NDI/SRT/OMT局域网与多机输出 | 未接通且无多机测试 | 后置评估 / E | 协议复用，主线先单机，不把协议支持当低延迟保证；验收：测网络/丢帧/恢复与音画同步，再比较单机收益 | [vMix Features](https://www.vmix.com/software/features.aspx)、[vMix 下载/版本29](https://www.vmix.com/software/download.aspx)、[vMix 版本比较](https://www.vmix.com/purchase/) |
| REM-03 双PC音频混音与设备路由 | 未接通 | 后置评估 / E | Win11可选工具；不成为Win10必需依赖；验收：两机版本/音轨与停止可核对，不默认跨设备公开 | [Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes)、[Wave Link 3 技术规格](https://www.elgato.com/us/en/s/wave-link-app) |

该域项目证据与缺口：
- REM-01：依据：未核实本项目现有实现。缺口：Twitch为Beta，账号验证与vMix版本有条件。收益假设：未来需要来宾时由主持可控入场。
- REM-02：依据：未核实本项目现有实现。缺口：许可、插件、网络与版本限制待验。收益假设：在多机任务有收益时分担资源。
- REM-03：依据：未核实本项目现有实现。缺口：Wave Cast另购、需相同版本。收益假设：多机时保留独立音轨。

### 诊断恢复与Windows交付

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| OPS-01 渲染/编码/网络故障分诊与日志 | 已有诊断/日志，主线负载未闭环 | 本轮原生必需 / C | 先测阶段耗时与资源，不编延迟指标；验收：区分生成/TTS/审核/播放/编码/网络，保留旧失败，不放宽TTL | [OBS 编码性能排障](https://obsproject.com/kb/encoding-performance-troubleshooting)、[OBS 推流连接排障](https://obsproject.com/kb/stream-connection-troubleshooting)、[本地演练原始证据边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md) |
| OPS-02 同版安装包、更新、备份与回滚 | 现有Windows归档落后且缺room模块 | 本轮原生必需 / E | 第三方配置外部管理，本项目对齐自己所有来源；验收：实际ZIP逐文件哈希、CPU/CUDA来源和更新回滚数据保护 | [Companion 导入导出](https://companion.free/user-guide/v4.2/config/import-export/)、[Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| OPS-03 DPI/多屏、最小化及睡眠恢复 | Linux尺寸检查过，真机待验 | 本轮原生必需 / F | 不能从支持Windows推出任意显示环境可靠；验收：固定缩放/显示器/睡眠恢复任务，检查窗口、音频、停止与源 | [Live2DViewerEX 开发者说明](https://store.steampowered.com/app/616720/)、[OBS Windows 下载与支持系统](https://obsproject.com/download) |
| OPS-04 插件兼容、版本迁移及故障隔离 | 本轮未安装第三方插件 | 外部工具复用 / E | 现有SDK独立许可校验，不新增下载依赖；验收：核插件/运行库/模型版本和失败原因；不靠安装成功称兼容 | [OBS 插件位置迁移](https://obsproject.com/kb/legacy-plugin-locations)、[VTube Studio Windows透明输出](https://github.com/DenchiSoft/VTubeStudio/wiki/Recording-Streaming-with-OBS) |

该域项目证据与缺口：
- OPS-01：依据：`src/companion_runtime/device_diagnostics.py`、`docs/validation/local-product-rehearsal.md`。缺口：目标机并发与p95等基线未取得。收益假设：给可复现原因而非含糊失败状态。
- OPS-02：依据：`docs/project/p9-plan.md`、`scripts/app_update.py`。缺口：Windows运行和最新同版制品未完成。收益假设：用户拿到可测试的完整候选。
- OPS-03：依据：`docs/project/p9-plan.md`、`desktop/window-policy.cjs`。缺口：RTX4060/32GB目标机结果待用户完整候选后验证。收益假设：保证Windows桌面长期可用。
- OPS-04：依据：未核实本项目现有实现。缺口：OBS/Spout2与运行库授权、版本均待实际验证。收益假设：避免升级后源或音轨静默失效。

### 商业激励与排除项

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| COM-01 礼物提示、关注和事件小组件 | 只考虑接收事件，无真实平台验收 | 后置评估 / C | 不伪造人数/礼物，不抢讲解或扩大数据权限；验收：仅真实已授权事件可显示；排队/过期/停止与声轨核对 | [B站开放平台事件目录](https://openhome.bilibili.com/doc/4/c7b549c9-d5d6-0331-b510-465ed4107e01)、[Twitch Mod View](https://help.twitch.tv/s/article/mod-view?language=en_US) |
| COM-02 PK、福袋、红包、电商与广告主线 | 本轮不适用 | 本轮排除 / A | 明确排除是已考虑后的产品取舍；验收：不添加商城/抽奖/PK控件，若目标变化另立收益与权限实验 | [B站PC直播姬](https://live.bilibili.com/liveHime) |
| COM-03 积分竞猜与奖励结算 | 本轮不适用 | 本轮排除 / A | 不把竞猜奖励强塞学习流程；验收：目标变化再核角色/地域与独立学习结果，不伪造完成或中奖 | [Twitch Predictions](https://help.twitch.tv/s/article/channel-points-predictions?language=en_US) |

该域项目证据与缺口：
- COM-01：依据：未核实本项目现有实现。缺口：B站详细事件和权限待复核。收益假设：有真实事件时提供低打断反馈。
- COM-02：依据：未核实本项目现有实现。缺口：账号/地域/合规/接口未核，不能默认启用。收益假设：平台具备但不服务当前学习助手主线。
- COM-03：依据：未核实本项目现有实现。缺口：创作者资格与结算规则有条件。收益假设：有娱乐用途但不能当学习掌握。

### AI现场辅助与公开边界

| 能力 | 项目现状 | 决定 / 任务 | 理由与验证 | 来源 |
|---|---|---|---|---|
| AI-01 明确公共背景、材料可选、来源与不确定性 | 文字背景/近期消息存在，无主播音画理解证据 | 本轮原生必需 / A | 不强制教材，缺信息应询问，私人上下文不公开；验收：同输入分别缺背景/有公开材料，核对回答依据与不确定提示 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[本地演练原始证据边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md) |
| AI-02 流式生成、分句字幕/TTS与可中断回答 | 私聊有流式基础，公共链路完整合成后播放 | 后置评估 / B | 先单次批准声画绑定，再比较分段收益与复杂度；验收：测首可用回答/总时长、中断/晚段清理；未批准片段不公开 | [本地演练原始证据边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md)、[本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md) |
| AI-03 自动选题、自动公开、平台文字发送分授权 | 当前公开路径人工逐条批准 | 后置评估 / A | 三者分别验证授权，不能联带开启；验收：拒绝未授权动作，保留人工路径比较误答/等待/接管成本 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[B站开放平台FAQ](https://open-live.bilibili.com/document/5dffc297-6fd2-41ff-bd45-6e8b89e2a68e) |
| AI-04 语音输入、主播感知与回流隔离 | 有私有语音/感知模块，未接现场答疑 | 后置评估 / B | 模块存在不代表已听见/看见直播；公开输入必须限域；验收：助手输出回放不能再次当新问题；撤权后停止采集 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[VTube Studio 官方手册](https://github.com/DenchiSoft/VTubeStudio/wiki) |
| AI-05 当前任务/身份/会话隔离与可信终态 | 本地取消/隔离有部分证据，整合未实施 | 本轮原生必需 / B | 命令、媒体启动、系统轨、观众分别取证；验收：切身份/场次/话题后旧token/晚响应拒绝；私密金丝雀不入公开输入/DOM/音轨 | [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)、[Companion 反馈](https://companion.free/user-guide/v4.2/config/buttons/creating/feedbacks/) |

该域项目证据与缺口：
- AI-01：依据：`app/server.py`、`docs/project/interaction-contract.md`。缺口：回答正确性与真实用户收益仍需独立评审。收益假设：现场能随机应变但不假装有未提供的信息。
- AI-02：依据：`app/static/companion-core.js`、`app/static/live-stage.js`。缺口：公共分段语义未定义，不能把流式当已实现。收益假设：可能降低等待但不能先播未批准片段。
- AI-03：依据：`src/companion_runtime/live_output.py`、`docs/project/interaction-contract.md`。缺口：本轮未授权自动公开或平台发字；B站发送API待核实。收益假设：未来降低主播负担，先证明收益。
- AI-04：依据：`app/static/voice-input.js`、`src/companion_runtime/perception.py`。缺口：真实麦克风/声卡/ASR和公开授权未验。收益假设：明确允许时减少手工输入。
- AI-05：依据：`src/companion_runtime/live_output.py`、`app/static/live-stage.js`。缺口：整合后还需端到端与目标设备验证。收益假设：避免旧声音接新人物或任务停止后复活。

## 版本、授权与兼容限制

- [OBS Windows 下载与支持系统](https://obsproject.com/download)：本轮33.0.1，Windows10/11；支持系统不等于目标机器通过。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Sources Guide](https://obsproject.com/kb/sources-guide)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 制作功能](https://obsproject.com/)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Studio Overview](https://obsproject.com/kb/OBS-Studio-Overview)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Profiles](https://obsproject.com/kb/profiles)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Scene Collections](https://obsproject.com/kb/scene-collections)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 应用音频捕获](https://obsproject.com/kb/application-audio-capture-guide)：要求Windows10 2004+或11；部分应用不兼容；避免桌面声与应用声双重捕获。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Audio Mixer](https://obsproject.com/kb/audio-mixer-guide)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Filters Guide](https://obsproject.com/kb/filters-guide)：列噪声处理/压缩/限幅/ducking等；EQ可能需要兼容插件，不宣称原生EQ齐全。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 多轨录制](https://obsproject.com/kb/advanced-recording-guide-and-multi-track-audio)：容器须支持多轨；普通播放器常只播一条轨。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Standard Recording](https://obsproject.com/kb/standard-recording-output-guide)：MKV/重封装可改善异常结束恢复，不保证零丢失；独立编码有额外开销。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Virtual Camera](https://obsproject.com/kb/virtual-camera-guide)：可选择节目/预览/场景/源；虚拟视频不自动携带正确音频。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 编码性能排障](https://obsproject.com/kb/encoding-performance-troubleshooting)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 推流连接排障](https://obsproject.com/kb/stream-connection-troubleshooting)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS 插件位置迁移](https://obsproject.com/kb/legacy-plugin-locations)：插件位置迁移有版本边界；安装不等于兼容。 证据级别：official_documentation；观察日期：2026-11-15。
- [Streamlabs 选择性录制](https://support.streamlabs.com/hc/en-us/articles/4413174869915-Selective-Recording-in-Streamlabs-Desktop)：官方描述仅横向源并会禁用竖版场景；不能默认与双画布同时兼容。 证据级别：official_documentation；观察日期：2026-11-15。
- [Streamlabs Multistream](https://streamlabs.com/multistream)：免费与Ultra、目标数量/双输出能力不同；需要按当前账号再核。 证据级别：official_documentation；观察日期：2026-11-15。
- [vMix Features](https://www.vmix.com/software/features.aspx)：NDI/SRT、来宾、回放/输出数量依版本；厂商性能宣传不是本机实测。 证据级别：official_documentation；观察日期：2026-11-15。
- [vMix 下载/版本29](https://www.vmix.com/software/download.aspx)：当前主线29初发2025-10-27；不是2026新发布。 证据级别：official_documentation；观察日期：2026-11-15。
- [vMix 版本比较](https://www.vmix.com/purchase/)：版本/许可决定能力，不承诺本项目用户已购买。 证据级别：official_documentation；观察日期：2026-11-15。
- [YouTube 桌面直播聊天/Q&A/置顶/投票](https://support.google.com/youtube/answer/2524549?co=GENIE.Platform%3DDesktop&hl=en)：置顶/投票/Q&A受角色和平台限制，不代表B站拥有同一授权接口。 证据级别：official_documentation；观察日期：2026-11-15。
- [YouTube 聊天审核](https://support.google.com/youtube/answer/9826490?hl=en)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [YouTube 直播自动字幕](https://support.google.com/youtube/answer/6373554?hl=en)：官方有语言与延迟模式条件；不能假设满足中文低延迟需求。 证据级别：official_documentation；观察日期：2026-11-15。
- [Twitch Mod View](https://help.twitch.tv/s/article/mod-view?language=en_US)：桌面审核工具依角色；不照搬全部奖励或用户追踪能力。 证据级别：official_documentation；观察日期：2026-11-15。
- [Twitch Stream Together](https://help.twitch.tv/s/article/stream-together)：官方仍标Beta，部分来宾需验证；不是当前稳定通用基线。 证据级别：official_documentation；观察日期：2026-11-15。
- [Twitch Predictions](https://help.twitch.tv/s/article/channel-points-predictions?language=en_US)：创作者资格、地域和结算条件。 证据级别：official_documentation；观察日期：2026-11-15。
- [B站PC直播姬](https://live.bilibili.com/liveHime)：PC页面列Win10+、1080p60及福袋红包；UI存在不证明开放接口授权。 证据级别：official_documentation；观察日期：2026-11-15。
- [B站开放平台事件目录](https://openhome.bilibili.com/doc/4/c7b549c9-d5d6-0331-b510-465ed4107e01)：仅官方搜索索引；动态正文未展开，详细协议/权限/事件可用性待复核。 证据级别：official_index_only；观察日期：2026-11-15。
- [B站开放平台FAQ](https://open-live.bilibili.com/document/5dffc297-6fd2-41ff-bd45-6e8b89e2a68e)：仅官方索引；主播授权/应用审核/失效恢复细节待复核，不能推定公开文字发送API。 证据级别：official_index_only；观察日期：2026-11-15。
- [Zoom Webinar角色](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065551)：账号方案、管理员开关、主持权限有条件；未实测。 证据级别：official_documentation；观察日期：2026-11-15。
- [Zoom Q&A](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065237)：账号方案、管理员开关、主持权限有条件；未实测。 证据级别：official_documentation；观察日期：2026-11-15。
- [Zoom 桌面批注](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0067931)：账号方案、管理员开关、主持权限有条件；未实测。 证据级别：official_documentation；观察日期：2026-11-15。
- [VTube Studio 官方手册](https://github.com/DenchiSoft/VTubeStudio/wiki)：PC摄像头驱动Live2D；不是VRM/3D软件，模型导出必须支持相应参数。 证据级别：official_documentation；观察日期：2026-11-15。
- [VTube Studio API认证](https://github.com/DenchiSoft/VTubeStudio#authentication)：需要开启API和用户认证；不意味着本项目已接入。 证据级别：official_documentation；观察日期：2026-11-15。
- [VTube Studio 表情](https://github.com/DenchiSoft/VTubeStudio/wiki/Expressions-%28a.k.a.-Stickers-or-Emotes%29)：Expression Groups为public beta；表情能力受模型导出与物理约束。 证据级别：official_documentation；观察日期：2026-11-15。
- [VTube Studio Windows透明输出](https://github.com/DenchiSoft/VTubeStudio/wiki/Recording-Streaming-with-OBS)：文档2025更新、本轮观察；Spout2插件版本、Premultiplied Alpha和transparent black有要求；不证明本项目灰边根因。 证据级别：official_documentation；观察日期：2026-11-15。
- [Live2DViewerEX 开发者说明](https://store.steampowered.com/app/616720/)：非Live2D官方产品；应用购买不授予模型、Workshop或SDK任意再分发权。 证据级别：official_documentation；观察日期：2026-11-15。
- [Wave Link 3 技术规格](https://www.elgato.com/us/en/s/wave-link-app)：当前要求Windows11；ASIO不支持；Windows VST3效果可增加延迟。不能作为Win10/11共同必需依赖。 证据级别：official_documentation；观察日期：2026-11-15。
- [Wave Link 3.5 Windows发布说明](https://help.elgato.com/hc/en-us/articles/52924923512977-Elgato-Wave-Link-3-5-Windows-Release-Notes)：2026-11-11发布；Audio Flow/Smart Switch/备份。Wave Cast另购、两机版本一致；OBS设置备份有连接前置。 证据级别：official_documentation；观察日期：2026-11-15。
- [Stream Deck 热键/配置](https://www.elgato.com/us/en/explorer/products/stream-deck/how-to-use-stream-deck-for-gaming-hotkeys-profiles-and-plugins/)：热键焦点目标有约束；硬件可选，不应成为停止能力前提。 证据级别：official_documentation；观察日期：2026-11-15。
- [Stream Deck MCP](https://www.elgato.com/us/en/explorer/products/stream-deck/sd-mcp-setup/)：7.4动作触发与8.0 beta键位管理不同；需要桥接及明确授权。 证据级别：official_documentation；观察日期：2026-11-15。
- [Companion 反馈](https://companion.free/user-guide/v4.2/config/buttons/creating/feedbacks/)：本轮文档v4.2，不称最新版；反馈能力依模块。 证据级别：official_documentation；观察日期：2026-11-15。
- [Companion 触发器](https://companion.free/user-guide/v4.2/config/triggers/)：模块/变量/动作权限需单独核实。 证据级别：official_documentation；观察日期：2026-11-15。
- [Companion 导入导出](https://companion.free/user-guide/v4.2/config/import-export/)：官方功能说明，未安装或实测竞品；不证明本项目可用性。 证据级别：official_documentation；观察日期：2026-11-15。
- [本项目现场场景协议草案](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/ae6a6afc7fdbc24cecae07ee00d0b1c486f96c72/docs/project/interaction-contract.md)：协议草案待审，非市场事实、非产品整合已实现。 证据级别：project_source；观察日期：2026-11-15。
- [本地演练原始证据边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md)：真实本地模型/TTS与合成事件；非Windows/声卡/OBS/观众端验收。 证据级别：project_source；观察日期：2026-11-15。
- [本项目人物/布置边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/room-variety.md)：手动预览与真正节目输出尚未接通。 证据级别：project_source；观察日期：2026-11-15。
- [现有声音和角色候选](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/voice-room-original-direction.md)：已有实音频与Core开发观察；审美、声线和Windows待验收。 证据级别：project_source；观察日期：2026-11-15。
- [Restream 跨平台聊天能力](https://support.restream.io/en/articles/2379624-what-is-restream-chat)：读取、回复、relay因目标平台权限不同；Custom RTMP不支持聊天读/发/relay，不能从推流地址推导聊天API。 证据级别：official_documentation；观察日期：2026-11-15。
- [Restream 收取消息要求](https://support.restream.io/en/articles/2388185-read-incoming-chat-messages)：需要受支持并已连接的平台；各平台在线/公开条件不同；不提供B站具体授权证明。 证据级别：official_documentation；观察日期：2026-11-15。
- [Zoom 翻译字幕配置](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0059081)：需指定付费账号方案或Translated Captions附加服务；账号管理员及主持语言设置有条件，翻译可能不准确。 证据级别：official_documentation；观察日期：2026-11-15。
- [Zoom 多语字幕使用要求](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060844)：需要自动字幕/翻译字幕开启及受支持客户端；可选语言由主持设置，不保证术语正确、低延迟或本项目ASR可用。 证据级别：official_documentation；观察日期：2026-11-15。
- [OBS Chroma Key Filter](https://obsproject.com/kb/chroma-key-filter)：普通摄像头绿幕按指定色抠像，阈值可能误删前景；虚拟背景分割需单独核实，不能由alpha输出或色键滤镜推导。 证据级别：official_documentation；观察日期：2026-11-15。

## 关闭本次考虑审查的条件

每个已命名域有能力记录；每项有来源、限制、项目证据或明确缺口、唯一决定、A–F责任和可证伪验收方法；JSON引用无悬空。把Wave Link写成Win10必需或把B站发字写已授权的反例必须被拒绝。此门禁只说明已考虑并取舍，不解除任何产品/Windows/独立验收闸门。

## 未取得的证据

- B站动态文档正文/具体权限/公开文字发送API未核实
- 未安装或实测竞品，操作收益与好用度未验证
- 目标Windows/系统声卡/OBS轨/观众端与独立学习收益未取得
- R3标准原图、分层及可编辑工程来源链还需核对
- 已命名能力之外的市场变化需后续按来源和目标再审
