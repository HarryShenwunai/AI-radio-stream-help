# 虚拟陪伴项目（未命名）

用户可以创建自己的二次元角色、上传有权使用的形象，并配置性格与相处方式。聊天、记忆和约定按身份隔离；同一角色换外观保留关系。学习监督是可选能力，长期记忆可关闭。

开发版本 **0.5.0-dev3**，目标 **Windows 10/11 x64**。本批已完成原创半身 Live2D：独立十指、手掌、硬质杯子、四种手杯动作，以及自助导入、主舞台操作和真实本地语音联动。PNG、VRM、录音转写及平台桥接保留各自的验收范围。**完整项目尚未验收完成**，最新状态见[交付状态](docs/implementation/completion-release.md)与[验收台账](review/completion-status.json)。

[运行与角色导入](app/README.md) · [执行看板](docs/planning/execution-board.md) · [视觉质量目标](docs/design/visual-quality-target.md)

[工程门禁与截图/录像复现](docs/implementation/engineering-gates.md) · [原创 Live2D 制作状态](docs/implementation/avatar-original-live2d-status.md) · [本机运行库安装](docs/implementation/live2d-windows-owner-setup.md)

## Windows 运行

[本批软件更新、Live2D 模型、完整编辑源与实际录像](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.5.0-dev3-live2d)。已有基础包时，只需约7MB程序更新和约11MB运行模型；完整源文件约346MB，供编辑使用，不是软件导入包。

先退出软件并应用 `character-app-source-update-0.5.0-dev3.zip` 中的 `apply-ui-update.cmd`；再按[本机运行库安装](docs/implementation/live2d-windows-owner-setup.md)运行 `setup-live2d-owner.cmd`；打开角色工作室，导入 `original-live2d-r2-candidate-runtime.zip`，预览并确认。安装运行库复用原包Python，无需Node/npm，明确接受条款后才下载约29MB固定依赖及官方Core。


[下载 Windows 便携候选包](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate)。下载页面中的 `download-and-assemble.cmd` 和 `download-and-assemble.ps1`，放在同一文件夹后双击 CMD，自动下载三卷、校验并合并；完整解压后运行程序。合计下载约 4.18 GiB，候选包尚待 Windows 真机验收。

基础包的 `BUILD-INFO` 保留 0.4.0-dev1 组装记录；小型程序更新独立记录后续源码提交，不要求重新下载模型。新增主舞台动作脚本需要同时更新后端静态路由，不能只复制 HTML。更新步骤见[应用更新说明](docs/implementation/desktop-capture-and-update.md)。

完整便携目录采用随包 CPython 3.12 和预编译依赖，运行时不需要预装 Python、Node.js 或 Visual Studio。完整解压后双击 `companion-desktop.exe` 或 `start.cmd`；CPU 为默认模式，可在退出后通过 `使用CPU.cmd` / `使用CUDA.cmd`切换。是否包含模型、语音和 ASR 资产，以实际交付清单为准。

微软 VC++ x64 运行库和兼容的 NVIDIA 驱动仍可能是前置条件。预检会提示缺项，不静默修改系统；CUDA 模式失败可退回 CPU。CUDA ASR 所需 cuDNN9 未随包提供，录音识别默认 CPU。候选目录在 Linux 上组装，**尚无 Windows/RTX4060 真机运行、性能或最终画质验收结论**。

[便携运行时与诊断](docs/implementation/windows-portable-runtime.md)说明布局、资源报告与边界。若从源码自行准备，双击根目录 `build-windows.cmd`；这是重建路径，详见[本机构建说明](docs/implementation/windows-local-build.md)。GitHub Actions 历史任务因账户计费锁定未获 runner，不能把它记为代码编译失败，也不能以组装成功代替 Windows 运行通过。

## 当前能力与实际边界

| 能力 | 当前实现与验证范围 |
| --- | --- |
| 自助身份与 PNG | 创建、切换、归档、恢复、删除；预览后启用、修订回退；四状态自然眨眼/说话切换，本机 HTTP 与真实 Chrome 已验证 |
| VRM 0/1 | 自包含运行资产导入、本地 WebGL、眨眼/呼吸/视线、音频 RMS 口型及隐藏释放；本机 Chrome 已验证，非音素级口型/目标美术验收 |
| Live2D | 42网格/41参数原创半身模型、十指独立弯曲、手掌与衣袖、杯子独立位移/旋转/隐藏及持杯跟随；四种动作/四表情/三种场景主UI通过；547组合双通道与独立5000持杯/杯形实测通过，见[最终汇总](review/live2d-rigid-r2-frontend-acceptance-summary.json) |
| 对话与关系 | 流式回复、相关记忆、记忆关闭、短期上下文和可控约定；真实本地模型已冒烟，人工自然度与长期关系体验未验收 |
| 语音 | 最终模型和运行ZIP已真实走通Qwen→Kokoro→HTMLAudio/Analyser→Core口型与停止/上下文回执，见[实测](review/real-live2d-rigid-r2-companion.json)；录音识别及Windows真人麦克风为独立验收 |
| 打断 | 生成取消、旧身份/旧媒体拒绝已有本机证据；播放回执、历史 TTS、过期停止拒绝及未听尾部的保守上下文处理已完成本机验证；7项真实 Chrome 通过，不证明真人已听见 |
| 微信 | AstrBot ClawBot 私聊桥接、逐条审核/自动回复控制和音频文件路径已实现；用户接受音频文件，原生语音条非必做；真实账号与送达待验 |
| 哔哩哔哩 | 官方 Open Live 输入、独立公开设定、停止/重连与本机弹幕回复预览已实现；用户有可管理房间，凭据与真实连接待验；无默认公开播出 |
| 桌面 | 角落常驻、展开、透明/穿透/恢复与本机后端生命周期；已有 Linux/X11 证据，Windows 多屏、DPI 和游戏场景仍待验 |

PSD 不会自动绑定为 Live2D；上传模型元数据不会自动变成人设、声音或工具权限。用户提供的素材仍按其原授权使用。默认源码与常规包不包含 Live2D Core/Framework，当前本机评估同意不等于公开分发/Expandable 许可。

## 从源码启动

推荐独立 Python 3.12 环境，在仓库根运行：

```sh
python -m pip install -r app/requirements-core.txt
python run.py --no-browser
```

打开终端打印的本机地址。角色管理不要求先下载大模型；生成需配置已有本地模型及依赖，或自己的兼容模型 API。可选安装、资产下载与本地识别见[应用说明](app/README.md)。模型、用户数据库和密钥不进入 Git。

## 如何读验证结果

[验收台账](review/completion-status.json)区分源码/受控测试、本机 HTTP、真实浏览器、目标机器/账号及用户质量验收。不同层级不能相加成“完成率”。历史 PNG 报告是当时子集，新功能以对应日期、范围与 JSON 为准；回归总数在最终冻结后统一汇总。

可查阅[VRM 浏览器](review/vrm-browser-check.json)、[平台浏览器](review/connectors-browser.json)、[真实 ASR HTTP](review/asr-http-real-check.json)、[对话冒烟](review/conversation-real-smoke.json)、[Live2D Haru](review/live2d-browser-check.json)/[Hiyori 独立模型](review/live2d-hiyori-holdout.json)及[播放回执](review/playback-browser-check.json)。合成音、替身提供方和软件 WebGL 不证明真实声线、账号互通或 RTX4060 性能。参考图表现仍需合法目标资产和用户确认。

## 工具与工程检查

按[工程门禁说明](docs/implementation/engineering-gates.md)准备工具后，运行 `python scripts/quality_gate.py --full`：关键 bug lint、十个模块 strict mypy、七项架构规则和违规夹具，再跑 Python/Node。报告同时绑定检查前后的源码 SHA；测试逐项通过但源码变化，整体仍失败。历史 [0.4 工程报告](review/quality-gate.json)与 [Live2D 主舞台前快照](review/quality-gate-live2d-final.json)各自保留原范围，当前[交付完整门禁](review/quality-gate-live2d-delivery-final.json)于 2026-11-13 04:28 UTC 通过，Python780项零跳过、桌面Python9项、前端Node111项、桌面Node27项；检查期间源码 SHA 不变。浏览器、模型几何和目标机器各有独立验收。

[TLA+/TLC 有限模型](review/formal-model-check.json)和[实际实现边界探索](review/formal-implementation-check.json)有独立报告；只覆盖明确的有限安全边界，不是整程序形式化正确性、活性、性能或人类听感证明。

## 项目资料

- [自助角色计划与画师交付基准](docs/planning/self-service-characters-plan.md)
- [产品与技术比较](docs/research/products-and-technology.md)及[Zerolan 五仓库研究](docs/research/zerolan-comparison.md)
- [架构与权限](docs/design/architecture.md)、[当前批次执行与阻断](docs/planning/execution-board.md)
- [许可通知](NOTICE.md)、[应用许可](app/LICENSE)与[依赖说明](app/ATTRIBUTIONS.md)

没有因本机开发授权自动登录真实账号、发送消息、公开播出或发布 Live2D 运行时。云同步、公开角色市场、AR、MC 和第三方弹幕姬互通需另行明确范围，不能从旧研究文档推定已实现。
