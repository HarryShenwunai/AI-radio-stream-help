# 执行看板：动态角色与本地陪伴集成

更新：2026-11-12 UTC。版本暂为 **0.4.0-dev1**，以最终包清单为准。目标是 Windows 10/11 上可自行上传角色的二次元桌面陪伴；角色、关系连续性和自然互动优先，督学可选。用户已自报 RTX4060/32GB，具体 CPU、显存、驱动与实测未知。

## 当前状态

| 工作流 | 当前状态 | 证据/负责人 |
| --- | --- | --- |
| 身份与关系 | 独立 SQLite、同身份换皮、归档/恢复/删除、迁移和记忆控制已实现 | 历史 PNG 子集报告与新增 HTTP；root、QA |
| PNG/VRM | 四状态自然眨眼；VRM 0/1 自包含导入、本地 WebGL、RMS 口型、隐藏释放/回退已实现并有 Chrome 证据 | review/vrm-browser-check.json；assets、frontend、QA |
| Live2D | ZIP 及资源检查、可选运行时安装、真实 Core 初始化；Haru/Hiyori 各12项真实 Chrome 通过，含预乘透明、口型、隐藏/恢复与回退；只代表这两模型本机评估 | review/live2d-browser-check.json、review/live2d-hiyori-holdout.json；docs/implementation/live2d-local-evaluation.json；catalog、frontend、QA |
| 本地语音 | tiny CPU 真转写 HTTP、只填草稿、不暗用在线识别；Kokoro 与可配置 GPT-SoVITS | review/asr-http-real-check.json、review/voice-module-check.json；voice、frontend |
| 对话质量 | 原有人设/短期上下文/相关记忆，反无关记忆与未确认经历检查；真实模型单轮冒烟 | review/conversation-real-smoke.json；voice、root；人工质量尚未接受 |
| 未听内容 | 已有生成失效与晚到拒绝；播放回执、历史TTS、ABA/stale-stop与保守未听尾上下文已完成本机验证 | review/playback-browser-check.json 7项真实Chrome；HTTP/Node回归；root、frontend、QA |
| 平台控制 | 微信私聊绑定/审批/暂停、Bili 官方 Open Live 输入与本机预览；Chrome 控制面板已检查，未连接真实账号 | review/connectors-browser.json；catalog、root、voice |
| Windows 便携包 | 随包 3.12、预编译 CPU/CUDA profile、固定依赖/模型复用、诊断和切换脚本已准备；候选已封包并发布到[GitHub Release](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate)；三卷及11附件SHA已验，目标Windows仍待验 | docs/implementation/windows-portable-runtime.md；desktop、QA |

已收到的选择：微信接受 ClawBot + 音频文件，原生语音条降为可选；Bili 用当前官方路线，用户有可管理房间但尚无本机凭据；Live2D 仅本机开发评估条款已经明确同意，不重复征求这项同意，不将其扩大为发布许可。

## 发布前剩余任务与依赖

| 优先级 | 动作与负责人 | 前置与完成标准 |
| --- | --- | --- |
| P0 | QA 将已通过的 R08 纳入冻结全量 | 本机端到端已过；冻结后保留历史TTS、ABA、迟到/重复/过期回执回归；不把机械回执当真人已听见，Windows多轮另验 |
| P0 | QA 保留已通过 Live2D 双模型回归 | Haru/Hiyori 本机已过；冻结后检查同一 runtime/source ID，保留透明红测与修复记录，不扩大为全 Cubism/Windows兼容或发布许可 |
| P0 | desktop/root 同步最终源码并冻结交付清单（候选发布已完成） | 所有源码冻结后；CPU/CUDA 两 profile 源码 ID、关键文件哈希、模型及 ASR 清单一致，压缩包校验，许可与运行说明同行 |
| P0 | QA 复跑冻结后的本机回归 | 上述改动落盘；新失败修正后复测受影响范围；台账区分受控、本机 HTTP、Chrome 与目标机器，不提前固定总数 |
| P1 | 用户/desktop 在 Windows 实机启动及恢复 | 完整解压、VC/驱动前置提示可执行；记录 Windows 版本/CPU/显存/驱动，CPU 聊天/TTS/麦克风、退出清理、重启持久化、穿透/恢复；CUDA 实际 offload 另有证据 |
| P1 | 用户/QA 验证合法账号互通 | 用户在本机填 Open Live 凭据、ClawBot/测试私聊；开始前明确发送对象/内容与影响；验证输入、断线重连、暂停与文字/音频文件送达，不把适配器交接当送达 |
| P1 | 用户/QA 评估声音/角色与关系 | 确定有权使用的目标素材和声音；在记忆开/关、普通聊天/工具场景比较，确认自然度、角色一致性及视觉表现 |

## 工程与有限形式化门禁

`python scripts/quality_gate.py --full` 已实现关键 Ruff、4模块 strict mypy、6架构规则和违规夹具、Python/Node；冻结全量8步已过：Python417项零跳过、桌面Python9、前端Node76、桌面Node7；最后取证脚本另有默认复测，详见[工具说明](../implementation/engineering-gates.md)及[报告](../../review/quality-gate.json)。[TLA+/TLC有限模型](../../review/formal-model-check.json)与[实际实现边界探索](../../review/formal-implementation-check.json)有真实结果，仍只覆盖定义的有限安全边界，不证明全程序、活性、硬件或人类听感。

## 接下来七天的条件行动

这是行动优先级，不是七天内全部交付承诺。Day 1–2 的本机 R08/Live2D、冻结全量、候选封包与 GitHub 发布已完成；Day 3 做 Windows 启动/硬件诊断，若无法获得真机则保留阻断并继续本机恢复测试；Day 4–5 在用户已授权的测试账号和房间做最小互通，缺凭据时不模拟成成功；Day 6 测目标机 30 分钟完整进程树 RSS/VRAM、帧时间、CPU/GPU占用及后台开销；Day 7 汇总对话/语音/视觉体验和失败清单，更新验收台账。具体日程受真机、凭据和合法资产可用性约束。

资源与质量候选值要在同资产、同窗口尺寸和同推理配置下冻结后评估；小窗 30fps/展开 60fps 仍是候选目标，尚无 RTX4060 证据。单次 Linux 推理/合成语音冒烟不是 p95 或人类自然度结论。Win CUDA 模型推理与 ASR CUDA 是不同能力；当前包 ASR 默认 CPU，不含 cuDNN9。

## 外部阻断与恢复

| 阻断 | 影响与处理 |
| --- | --- |
| 无目标 Windows 实机证据 | 不能宣布目标平台验收。可先交候选和本机诊断脚本，由用户机器产生报告；缺 VC/驱动仅提示官方入口，不静默安装 |
| 无本机平台凭据/真实私聊验收 | 平台模块与 UI 测试继续有效，真实账号、送达和重连保持待验；默认不登录、不发送 |
| Live2D 公开分发许可未确认 | 本机评估继续；默认源码/常规包不带 vendor Core/Framework，不公开发布这些组件或样例 |
| 目标美术/合法声音未验收 | 功能可测试，参考画质/声音质量不判通过；不替用户购买/委托或下载无授权角色 |
| 历史 GitHub Actions 计费锁定 | 无 runner 的旧任务不算编译失败；使用独立便携组装/本机构建，不改计费 |

用户数据/密钥不进入 Git、交付包或自动上传报告。换外观保留修订；错误预览不激活；换身份/停止取消旧生成；完整备份在退出应用后复制数据目录。新增模块失败优先回退到已知可用格式、CPU 或本机文字预览。

详细当前边界见[交付状态](../implementation/completion-release.md)，实际验收以[台账](../../review/completion-status.json)为准。旧计划和旧 PNG 报告保留历史用途，不重新累加旧估算或把源码实现当成目标平台通过。
