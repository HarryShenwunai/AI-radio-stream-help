# 本地应用与自助角色

开发版本 **0.4.0-dev1**；目标 Windows 10/11 x64。已实现独立角色、PNG/VRM/Live2D 运行资产导入、本地录音和平台控制面板。当前功能、验证程度与外部阻断见[本批交付状态](../docs/implementation/completion-release.md)。完整产品、目标画质和 Windows 真机仍待验收。

## Windows 便携目录

完整解压后双击 `companion-desktop.exe` 或 `start.cmd`，不要在压缩包内直接运行。运行完整目录不要求安装 Python、Node 或 Visual Studio；CPU/CUDA 两套预编译运行配置共享模型。先退出软件，再运行 `使用CPU.cmd` 或 `使用CUDA.cmd`；CPU 默认可用路径，CUDA 真机 offload 仍需证据。缺 VC++ x64 运行库或 NVIDIA 驱动时按预检提示处理，程序不会静默安装系统组件。

`诊断本机.cmd` 和 `测量运行资源.cmd`生成本机报告，不自动上传。候选包是在 Linux 上组装，不是已完成 Windows 运行验收；包含模型/音色/ASR 与否以交付清单为准。ASR 默认 CPU，CUDA-ASR 所需 cuDNN9 不在包内。布局与限制见[便携运行时](../docs/implementation/windows-portable-runtime.md)。源码重建另用根目录 `build-windows.cmd`，见[本机构建](../docs/implementation/windows-local-build.md)。

## 从源码启动

推荐独立 Python 3.12 环境，在仓库根运行：

```sh
python -m pip install -r app/requirements-core.txt
python run.py --no-browser --port 8765
```

打开打印的 `http://127.0.0.1:8765`。没有大模型时仍能管理和导入角色，生成会明确提示配置模型。可选本地推理/声音依赖和现有模型下载：

```sh
python -m pip install -r app/requirements.txt
python app/download_models.py
```

下载会联网并校验模型 SHA256，权重不在源码中。已有合法模型/声音可用 `COMPANION_MODELS`、`COMPANION_VOICES`复用。可选 ASR 依赖是 `app/requirements-asr.txt`；tiny 模型只在显式准备步骤下载，录音时不下载。模型路径可用 `COMPANION_ASR_MODELS`指定，细节见[语音与对话实现](../docs/implementation/voice-and-conversation.md)。

所有身份共用模型连接和运行配置。连接自己的模型 API 时，当前请求所需聊天/相关记忆会发送给该提供方；更换域名要填对应新密钥。使用外部 TTS 时，合成文本会发送到用户配置的服务；模型不能自行决定服务 URL。模型 API、外部 TTS 和本地 ASR 是不同设置。

## 导入自己的角色

1. 在“角色”创建身份；在“设置”填写性格和相处方式。新身份不复制旧角色的私聊、记忆和约定。
2. 选择有权使用的格式，执行隔离预览。预览成功不等于已启用。
3. 明确选择“使用这个形象”；失败保留原外观。可重新启用旧修订，或删除非当前修订。

| 格式 | 接受范围与边界 |
| --- | --- |
| PNG | 单图或待机/说话/眨眼/说话时眨眼四状态；可选图尺寸一致。单图 4MiB、整组 8MiB、单边 4096、合计 800 万像素；不支持动画/16bit PNG。自然眨眼和说话切换已实际接入，仍是状态图 |
| VRM | 自包含 VRM0/1 GLB，实际纹理解码和引用检查，限明确支持的扩展；拒绝外链、脚本及需要额外解码器的压缩资源。WebGL、RMS 口型、眨眼/呼吸/视线已在本机 Chrome 验证，不承诺所有 VRM 导出兼容 |
| Live2D | 一个 `.model3.json`根的 ZIP，包含受支持引用依赖；ZIP、展开体积、路径、JSON 和纹理分别限额。可选动作/物理/表情按受支持能力加载；未配置可选能力时降级，已声明依赖缺失则拒绝。需要用户合法安装 Core/运行时；Core5.1/MOC5 下 Haru/Hiyori 各12项真实 Chrome 检查通过；任意导出器、Windows性能与参考画质仍待验 |

详见[VRM 接受范围](../docs/implementation/vrm-assets.md)、[Live2D 资产边界](../docs/implementation/live2d-assets.md)和[运行时许可/本机评估](../docs/implementation/live2d-runtime.md)。PSD、绑定工程和运行包是不同交付物；软件不会把任意原画自动绑定成动态角色。素材元数据不自动授予声音、人格或工具权限。

当前最多 50 个身份、每身份 30 个外观修订；它们是工程限制，名字没有固定白名单。同一身份换外观保留关系；归档/删除/切换会失效旧输出。HTTP 中止不等于底层解码或模型内核即时停止，未启用修订可在列表清理。上传来源/许可标记不等于软件已核实权利。

## 对话、录音与打断

记忆可关闭；普通对话优先当前问题、性格和短期上下文，不用无关长期事实抢占话题。工具执行应有真实结果才声称完成。当前真实模型已做合成场景冒烟，仍需人工评估自然度、角色一致性及长期关系效果。

按录音按钮开始/结束，最长 60 秒。前端把声音转为单声道 PCM16 WAV，经同源本地接口交给 faster-whisper，结果只填入草稿，不自动发消息。默认本地识别缺组件时明确报错，不悄悄改成浏览器在线识别。已验证合成音真实 HTTP，真人口音/噪声、Windows 麦克风权限和目标机准确率待测。

声音可选 Kokoro、用户配置的 GPT-SoVITS 或系统声音；外部参考音频必须有使用权，软件不擅自克隆声音。RMS 口型是音量驱动，不是音素对齐；系统声音的活动近似也不能冒充音素口型。停止和身份切换已有晚到媒体拒绝；播放回执与未听上下文已做本机端到端验证：真实 HTMLAudio 停止/结束分别确认保守上下文，未确认尾部不进入下一轮提示，界面完整文本仍保留。历史 TTS、身份往返切换（ABA）和过期 stop 亦有 HTTP/Node 回归。7项真实 Chrome 通过不证明真人已听见，Windows多轮打断仍待测。见[播放回执说明](../docs/implementation/playback-receipts.md)与[报告](../review/playback-browser-check.json)。

## 平台连接

“平台”页默认只读本机状态，不自动登录/连接账号。微信使用 AstrBot weixin_oc / ClawBot：填写自己的私聊来源，绑定当前角色；配对令牌仅本次显示，离页/隐藏/换身份清空，需手动填入本机桥接插件。默认先审核，自动回复需显式确认；“暂停自动发送并取消待发”保留配对与收件预览。音频以文件附件交接，当前不支持原生语音条；批准/交给适配器不表示已送达。

Bili 按官方 Open Live 路线填写应用凭据、直播间和主播身份码，确认才连接。公开设定单独填写，输入不进入私人记忆；按钮只生成本机回复预览，无默认弹幕发送或公开播出。用户已确认有可管理房间，真实凭据与账号检查尚未完成。控制面板 Chrome 已验证，不等于平台互通已通过。

桥接部署与消息边界见[连接器说明](../src/companion_runtime/connectors/README.md)。账号连接、测试发送和公开播出仍须遵守具体授权，不从研究或计划自动获得许可。

## 桌面与数据

源码桌面壳在 `desktop/`：安装 Node 依赖，令 `COMPANION_PYTHON`指向已安装应用依赖的解释器后运行 `npm ci`、`npm start`。完整便携目录不需要这些开发步骤。展开与收起复用同一会话；恢复快捷键 `Ctrl+Shift+Space`，穿透最长 60 秒自动恢复。注册恢复入口失败时拒绝隐藏，避免失联。Linux/X11 已有实际窗口证据；Windows 多屏/DPI、游戏、权限和退出进程树仍需真机验收。摄像头、屏幕采集、任意新窗口没有默认权限。

源码默认数据在 `app/data`，可用 `COMPANION_DATA`改目录；桌面壳使用系统用户数据目录的 `profile-data`。两个版本不要同时写同一目录。

- `characters.sqlite3`保存身份和外观指针，各 `profiles/<UUID>/companion.db`保存关系数据，`assets`保存规范化运行资产。
- 连接配置/密钥、`runtime.json`及平台配置在根数据目录，都是本机私密配置；勿放入源码包、截图或公开仓库。
- 旧根数据库首次通过 SQLite 备份迁入首个身份，原文件保留；后续不重复合并旧版新增数据。
- 页面导出/恢复针对当前身份的关系与设定，不包含服务密钥或完整模型资产。退出后复制整个数据目录才能完整备份。删除清理失败会保留待重试记录，不承诺安全擦除；恢复遵守遗忘记录。

## 工程检查与验收

按[工程门禁](../docs/implementation/engineering-gates.md)准备工具后运行 `python scripts/quality_gate.py --full`，覆盖关键 lint、4核心模块 strict mypy、6架构规则及反例夹具、Python/Node。最终全量以[报告](../review/quality-gate.json)为准。有限 TLA+/TLC 模型与实际实现边界探索见[模型检查](../review/formal-model-check.json)及[实现检查](../review/formal-implementation-check.json)，范围仅有限安全性质，不是整程序/活性/质量证明。

## 许可与质量边界

[验收台账](../review/completion-status.json)区分受控模块、本机 HTTP、Chrome、目标机器/真实账号与用户体验。当前不报固定总数，最终冻结后按各报告范围汇总；旧 PNG 数字不是新增动态格式/语音/账号的通过证明。

用户已明确同意 Live2D 仅本机开发评估。默认源码/常规包不含 Core/Framework，本机同意不等于公开分发/商业/Expandable 许可。模型/样例不作为固定角色或无条件可传播素材。应用许可见[LICENSE](LICENSE)，第三方与模型来源见[ATTRIBUTIONS.md](ATTRIBUTIONS.md)、`licenses/`。保留通知不代表完整法律审查已完成。
