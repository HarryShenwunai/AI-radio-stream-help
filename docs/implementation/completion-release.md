# 动态角色与语音集成交付状态

更新：2026-11-12 UTC；当前版本暂 **0.4.0-dev1**，发布前由维护者统一版本和源码 ID。目标为自助角色、自然且一致的二次元桌面陪伴；督学可选。本批显著扩大了可运行能力，**尚未完成全部项目验收**，不以主观百分比替代未通过的门。

## 已完成的实现与证据

| 能力 | 已落地 | 已有证据与限制 |
| --- | --- | --- |
| 身份/关系/PNG | 角色创建、切换、归档/恢复/删除、独立 SQLite、迁移与外观修订；四状态实际眨眼/说话 | 本机 HTTP/Chrome、历史 Linux 后端/桌面报告；Windows 仍待测 |
| VRM | VRM0/1 自包含规范化、隔离预览、本地 WebGL、RMS 口型、眨眼/呼吸/视线、失效释放与回退 | [真实浏览器报告](../../review/vrm-browser-check.json)通过；软件 WebGL/测试资产，不等于 RTX4060 或参考美术验收 |
| Live2D | 有界 ZIP、依赖/纹理检查、可选运行时安装与原创适配；Core5.1/MOC5 下 Haru/Hiyori 实际预览、播放、启用/回退、口型和生命周期 | [本机评估记录](live2d-local-evaluation.json)；[Haru](../../review/live2d-browser-check.json)与[Hiyori 独立 holdout](../../review/live2d-hiyori-holdout.json)各12项真实 Chrome 通过，含预乘透明背景断言；非Windows或参考画质 |
| 本地 ASR | 严格 PCM16 WAV 校验、tiny CPU 本地识别、诊断、取消迟到拒绝；转写仅草稿 | [真实 HTTP](../../review/asr-http-real-check.json)已用 Kokoro 合成 2.683 秒句子识别，HTTP 约 1.762 秒；非真人/Windows/p95 |
| 声音与对话 | Kokoro 默认、可选固定服务地址 GPT-SoVITS、用户人设/短期上下文/相关记忆；约束检查后可用真实模型修订 | [声音模块](../../review/voice-module-check.json)、[真实对话冒烟](../../review/conversation-real-smoke.json)；不是人工自然度、合法目标声线或长期效果验收 |
| 平台控制与隔离 | 微信私聊角色绑定、一次令牌、逐条审批/暂停、音频文件桥接；Bili 官方 Open Live 输入、公开设定与本机预览 | [Chrome 控制面板](../../review/connectors-browser.json)6项通过，无真实配置/审批POST、无真实发送；模块/HTTP替身测试不证明账号互通 |
| Windows 便携候选 | CPython3.12、官方预编译 CPU/CUDA profile、共享模型/ASR、诊断与切换脚本 | Linux 上组装与静态/脚本检查；完整包不要求 Python/Node/VS，VC/驱动仍需预检；无目标 Windows 运行结论 |

冻结全量实际通过：Python417项且零跳过、桌面Python9项、前端Node76项、桌面Node7项。全量检查期间161份源码SHA不变；最后仅取证脚本修改，另有[默认复测](../../review/quality-gate-post-harness.json)，不声称417项再次运行。证据层约定：E0 源码/设计、E1 受控模块或原语、E2 真实本机 HTTP/文件/SQLite、E3 真实浏览器/本地应用、E4 目标机器/真实提供方或账号、E5 用户质量接受。不同层不能互相替代或简单相加。

## 本机验证已收口与最终交付门

**R08 播放回执与未听上下文**：后端有界 nonce、身份/轮次失效、历史 TTS、ABA 身份往返和过期 stop 拒绝均已接入。真实 Chrome 7项验证了停止后保守裁剪未确认尾部、正常结束后完整段可用于下一轮，以及界面原文仍保留；配套 HTTP/Node 也有回归。见[真实浏览器](../../review/playback-browser-check.json)与[处理语义](playback-receipts.md)。没有可靠 alignment 时只承认完整已确认段或服务端合成前缀，不以播放百分比捏造已听词边界。机械播放回执不证明真人已听见，Windows/100轮打断仍是目标机门。

**Live2D 真模型**：用户已同意仅本机开发评估。Core5.1/MOC5、Haru 与独立 Hiyori 各12项真实 Chrome 检查通过，包含 framebuffer、预乘透明、口型复位、隐藏释放/恢复、上下文丢失重试与身份切换；两份最终图已实际查看。旧机械测试曾漏白底，新增 alpha/RGB 一致性断言先红后修，旧失败/修复证据保留，不能用截图有像素代替透明正确。通过范围是 Linux/Chrome 两份合法样例的本机评估，不是所有 Cubism 导出器、Windows/4060、参考画质或公开分发许可。vendor 运行时仍在私有配置区，不进入默认公开包。

**工程与形式化边界**：`quality_gate.py --full` 已实现 critical Ruff、4核心模块 strict mypy、6条架构规则及违规夹具、Python/Node 全量；[工程说明](engineering-gates.md)和[最终报告](../../review/quality-gate.json)记录冻结源码全量8步通过，最后取证脚本另有默认复测。有限 TLA+/TLC [模型](../../review/formal-model-check.json)和[实际实现边界探索](../../review/formal-implementation-check.json)有真实结果，但不构成全程序 refinement/活性/任意调度或用户听感证明；数字以报告为准。

**最终打包**：Windows 便携候选包已封装并发布到 [GitHub Release](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate)；三卷总计4,491,413,065 bytes，11个附件均按远端大小/SHA256校验。包内BUILD-INFO绑定源码d01ccc42bbe6795c216afae37dd0e53128ab58d9，完整ZIP的13,068个成员已逐项CRC/SHA核验。下载合并脚本、清单与实际运行证据随发布提供；Windows/4060及实际CUDA仍未验收。

## 用户已确认与仍需外部验证

- 已确认 Windows10/11、RTX4060/32GB；具体 CPU、显存、驱动和动态性能待诊断。Win CUDA 模型推理是否真实 offload 待测，ASR 默认 CPU、包内没有 cuDNN9。
- 已确认 Bili 用当前官方接口，用户有可管理房间；本机 roomID/应用密钥/主播身份码及真实连接、重连结果未提供。回复当前只本机预览，不默认公开播出。
- 已接受微信 ClawBot + 音频文件，原生语音条为可选且当前不支持。真实账号版本、私聊、文字/文件送达与恢复仍待指定测试授权和实际证据。
- 已明确 Live2D 仅本机开发评估许可同意，不重复问这项同意。公开发布、Expandable 适用类别/许可/样例分发尚未确认；默认源码/常规包不包含 Core/Framework。
- 角色视觉与合法声音、自然聊天及长期关系需要 E5 用户接受。合法样例是基准材料，不能冒充已经达到参考图或指定角色画质。

## 下一步及验收标准

root/frontend/QA 已收口 R08 和 Live2D 本机真实检查；desktop 在源码冻结后同步候选并产出完整清单/哈希；QA 复跑最终全量和受影响本机回归，更新[总台账](../../review/completion-status.json)。随后在用户 Windows 上记录 CPU/显存/驱动、启动/退出、数据重启、麦克风/TTS、DPI/穿透/恢复和 CUDA 实际运行，再在明确授权的私聊和直播间做最小真实互通。质量和性能需同一素材/模型配置、记录完整进程树并测多轮延迟/帧时间，当前单次 Linux 数据不足以定 p95 或最终阈值。

发生缺依赖、损坏包、超预算或提供方失败时保留当前形象/关系数据，明确报错，允许退回旧修订、PNG、CPU 或文字；不静默下载、切在线 ASR、登录或发送。生产/公开部署和发布 vendor 运行时没有自动授权。

运行操作见[应用说明](../../app/README.md)；剩余负责人、依赖及条件七天行动见[执行看板](../planning/execution-board.md)。这份记录替代旧 PNG 交付口径描述当前批次，历史报告继续保留其原始范围。
