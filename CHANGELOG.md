# 版本日志

更新日期：2026-11-17（Europe/London）。范围：Windows 10/11 PC，目标设备 RTX 4060、32GB RAM。

这是一份已有成果与验收边界的记录，不是新的安装包发布。没有以 PR、功能或测试数量作为完成标准。

## 版本定位

| 对象 | 已核对的版本 | 当前状态 |
| --- | --- | --- |
| 本日志写入前的默认分支 | `main@d12b9dd8c3fafd976eb090d60825bc0868e038a2` | 设计与来源归档；不能据此认定已包含以下开发代码 |
| 当前开发链末端 | [`5c5122889f6d738607b20fd156f72d453d26a61f`](https://github.com/HarryShenwunai/AI-radio-stream-help/commit/5c5122889f6d738607b20fd156f72d453d26a61f)，`fix/live-action-failure-state` | PR #58，未合并的草稿；后续开发记录均需按各自提交复核 |
| 已公开 Windows 基础包 | [v0.4.0-dev1-candidate](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate)，源码 `d01ccc42bbe6795c216afae37dd0e53128ab58d9` | 较早的预发布候选，不包含最新开发链 |
| 已公开历史 Live2D 更新 | [v0.5.0-dev3-live2d](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.5.0-dev3-live2d)，源码 `f1667eaa9d7dc58fb8a3e2328f7b9783fc698534` | 历史预发布，不能替代当前固定持杯方向或最新 R3 验收 |
| v0.5.0-dev2-ui2d | GitHub Release 仍为 draft | 不列为已公开发布 |

截至本次核对，以下所引用的开发 PR 仍未合并。它们与公开安装包不是同一版本。本次只提交日志与交接说明，不合并应用代码、不修改 Release 或默认角色与音色。

## 2026-11-17 · 英文声音试听交付

已向用户私有 Library 交付 Heart（Kokoro `af_heart`）、Bella（`af_bella`）、Emma（`bf_emma`）和 Alba（Pocket TTS）四段试听，以及顺序为 Heart → Bella → Emma → Alba 的约 37.90 秒合集和包含原始音频的 ZIP。

- 四段使用同一段《Alice's Adventures in Wonderland》英文文本。Kokoro 三段由本地 ONNX CPU 实际合成；Alba 由 Kyutai 官方公开演示服务实际合成。
- 比较副本只应用恒定增益对齐音量，未变速或变调；原始版本保留。制作时检查 WAV 可解码、时长、有限采样值、削波和 ZIP 完整性。
- 这是会话内音频交付记录；本次日志整理没有重新合成。音频与制作报告未提交到本仓库，私有下载链接也不公开。
- 尚未替换项目默认声音、完成产品接入、Windows 本地推理测试或独立声线盲评；“青春活力感”仍待听感选择与验证。网络演示耗时不作为本地实时性能成绩。

来源：[Kokoro 音色说明](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)、[Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx)、[Kyutai 官方演示](https://kyutai.org/tts/)。

## 2026-11-16 · 失败恢复、准备状态与 Live2D 渲染

| 问题与最小修改 | 当时的开发验证 | 源码与限制 |
| --- | --- | --- |
| 请求被拒绝后，错误横幅出现但任务仍显示准备中；失败路径只读取一次权威状态并局部更新，保留草稿、焦点和原始错误 | 同条件 Chrome 故障注入：旧版不读取恢复状态、停在 synthesizing；新版读取一次并显示 failed；同一组 Node 判据拒绝旧实现 | [PR #58](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/58)；夹具时钟与静音 PCM，不代表真实语音或直播 |
| 本地模型和音色未准备好就允许输入；增加按场次、角色、公开上下文与文件身份限定的准备资格，停止或变更即撤销 | 准备、晚完成和撤销负控及本地完整质量检查通过；完整 SHA 仍执行，仅移除分块内重复全配置检查 | [PR #57](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/57)；没有证明真实大模型端到端延迟改善 |
| 同路径替换模型或音色后仍复用旧实例；缓存绑定实际加载的文件身份，构造前后检查并成对发布资源 | 模型/声音替换、失败后重试及已知旧缓存坏实现检查通过 | [PR #56](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/56)；文件 stat 是缓存失效条件，不是对抗同 stat 替换的安全保证 |
| Live2D 首帧读取旧 worldTransform，导致放大裁切；通过当前公开变换 API 计算矩阵并在释放时恢复属性 | 同一模型的真实 Core/SDK/GPU 首次与第二帧像素、矩阵一致；旧首帧 630440 像素差的反例仍拒绝 | [PR #55](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/55)；不等于全部角色视觉合格或 Windows 性能通过 |
| authored Idle 与自动眨眼/呼吸同时写同参数；按实际队列确定通道所有权，只过滤冲突通道 | 两段受控轨迹的目标参数偏差归零，受保护手杯顶点与透明度不变；另测自然重入、取消和真实 SDK 错误 | [PR #54](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/54)；只支持固定 SDK 结构，不等于补齐正面美术和缺失关键形 |
| 只看口型参数会误判“人物已经说话”；验收增加实际嘴部 drawable 的同任务可见性及媒体终态 | 原始模型即便参数变化仍被负控拒绝；已录制真实 WAV 的完整播放另作 recorded replay，保留原始失败状态 | [PR #53](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/53)；4.651 秒录音重放不是实时模型到语音通过 |
| 已应用的直播室布置未进入节目输出；白名单冻结展示配置，字幕不适配或准备期窗口变化即撤销本次播放 | 三种 PC 尺寸与三种布局检查；600ms 延迟音频反例中，旧版错误后仍播放，新版零播放并失败 | [PR #52](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/52)；没有观众端接收证据 |

最新 PR #58 记录的本地完整质量门通过，测试树为 `631a56cefae84e633bed1b8f690c7bed6a693afb`，与其远端树一致。该记录不能替代实际执行过的 GitHub Actions：此前运行 [43894710204](https://github.com/HarryShenwunai/AI-radio-stream-help/actions/runs/43894710204) 因账户计费锁定未启动，不声称远端 CI 通过。

### 实时链路仍未过关

[原始诊断与复跑说明](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/public-rehearsal-readiness.md)保留正常绘制下两题的真实记录：生成 / TTS / 音轨时长分别为 19.138 / 5.663 / 6.527 秒及 20.242 / 7.828 / 7.279 秒，顺序下界约 31.328 和 35.349 秒，均超过不变的 30 秒事件期限，实际播放为零。

此前还有生成 26.574 秒、合成 9.546 秒的失败。不能用短题成功、暂停绘制诊断或 4.651 秒录音重放覆盖这些结果。准备状态与缓存修复已经实现，但最新正常绘制、真实模型到语音的可靠实时闭环仍待验证。

## 2026-11-15 · 现场互动、人物库与直播室

| 已实现的变化 | 验证与证据 | 尚未证明 |
| --- | --- | --- |
| 现场招呼、追问和换话题成为默认主线；严格教材答疑保留为选项；只采用允许公开的背景及有限同房间近期消息 | [PR #44](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/44)、[现场互动诊断](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/live-scene-interaction.md)；旧版无教材拒绝、新版进入生成；真实 Qwen/Kokoro 的合成事件演练与取消分别记录 | 回答质量、学习收益；不具备默认麦克风/屏幕感知 |
| 产品内增加本地互动演练入口，沿用接收、生成、逐条审核、字幕/音频和停止链；不需要平台账号 | [PR #45](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/45)、[复跑说明](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/local-product-rehearsal.md)；实际模型/TTS 与完整浏览器流程有记录，同时保留重负载过期失败 | 本地合成事件不等于 B 站、OBS 或观众收到 |
| 增加可选的原角色首启加载和按角色保存的音色；保留已有外观、清空选择与失败重试 | [PR #46](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/46)、[角色与声音说明](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/voice-room-original-direction.md)；实际 Core 与 Kokoro 联动、数据库/导入边界检查 | 需要单独取得模型与合法运行库；不等于发行包开箱可用或最终听感合格 |
| 将控制区移出 16:9 预览，编辑后显式应用；保留草稿，刷新后计时暂停；删除预置问候和示例内容 | [PR #47](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/47)、[UI/UX 审查](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/uiux-room-github-audit.md)；同条件旧版失败、新版通过及实际 PC Chrome 录像 | 未经目标用户验证的布局不能称为专业审美或可用性通过 |
| 接入现有人物目录与手动刷新，独立于对话身份选择预览人物；增加左右/角落布置、组件显隐与用户命名保存 | [PR #48](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/48)、[人物库与布置](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/room-variety.md)；实际 Core 切换、空形象释放、保存/载入/隔离与静态坏版本拒绝 | 没有新增美术人物；新名字或空测试身份不计作新角色 |
| 操作台改为中性深色，节目采用炭灰/杏色、午夜/冰蓝、冷白/墨蓝三组配色，并迁移旧配置 | [配色审查与反例](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/room-colors.md)；计算样式、文字对比度、模式/布局一致性及坏版本检查 | 有限对比度测量不是全产品 WCAG、2026 审美或用户认可 |
| 主播逐条批准后冻结人物/资源，绑定节目字幕、音频及口型；音频实际启动后才报 playing，取消/过期/晚回包按世代隔离 | [PR #50](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/50)、[问题—实验—结果](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/p9-first-loop.md)；真实短问候一轮完整 ended/completed，故障回放与 WAV 剩余预算门有反例 | 短题单次成功不代表稳定实时 SLO、声卡输出、OBS 或观众接收 |
| 感知生成的 URL-safe 引用被下游误拒；仅三个可信引用字段使用生产者的精确契约 | [PR #51](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/51)；固定 -/_ 前缀的真实 HTTP 旧版失败、新版通过；权限和通用动作 ID 边界保留 | 使用合成观察，不证明真实采集或视觉语义正确 |

平台文字发送、自动选择问题和自动公开回复未默认开启。私人历史、密钥与内部字段不进入公开输出。当前产品方向为现场随机应变，教材是明确需要材料依据时的可选模式。

## 2026-11-14 · 学习材料、审核与更新恢复

- [PR #37](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/37)：辅助操作不再覆盖粘贴材料或自动请求；模型配置与实际失败状态分开。真实 HTTP503 对照保留输入、只在发送后请求，不生成虚假回答。
- [PR #38](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/38) / [#39](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/39)：人工审核链保留未发送材料、焦点和选区，拒绝重复批准和旧状态，显示音频失败，停止晚到播放。[故障审查](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/live-adverse-path-audit.md)。
- [PR #40](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/40)：修复 1024×600 PC 窗口主操作不可达，播放检查等待实际完成回执。历史其他尺寸记录不作为当前手机支持或验收。
- [PR #41](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/41)：更新器补齐遗漏的运行文件与依赖来源检查；在真实已发布 Windows 文件集的副本上验证应用、重复执行、回退、重用。此为 Linux 文件事务验证，不是 Windows 原生运行。
- [PR #42](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/42) / [#43](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/43)：按当时已核官方协议调整指定 OpenAI 模型请求参数，拒绝截断回答；本地模型不再把 length 终止当完整回答。OpenAI 使用严格协议夹具验证，没有实际 key 调用，模型可用性、延迟、费用及答案质量仍未测。

## 2026-11-13 · R3 固定持杯与基础可靠性

- [PR #1](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/1) 更新为 R3 方向：取消放杯，固定手、杯和袖子，双眼独立开合、小幅视线、轻微头动与胸肩呼吸。实际 Core 姿态/眨眼检查与导入格式验证分别记录；仍存在画质和源素材限制。
- [PR #35](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/35) / [#36](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/36) 保留透明舞台、双眼与局部眼睑候选的历史开发记录。指定眼区之外零变化只是有限条件下的局部约束；不能推导整体零误差，后续透明漏底和中间插值漂移仍未验收完成。
- 早期 [PR #3](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/3)–[#32](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/32) 涉及录音晚回调、PCM、播放回执、场景资源释放、SSE 终态/UTF-8/缓冲、取消、来源指纹和架构边界；[PR #33](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/33)修正验证入口并记录有限 TLC 模型与故障反例。条目数不是完成标准，有限模型不是全程序形式化证明。
- 历史 Release 中的放杯或手杯动作不属于当前方向。保留原始文件作来源记录，不恢复该行为，不再次使用被拒绝的 3D 画面。

## 验收总表

| 维度 | 截至本日志的结论 |
| --- | --- |
| 源码与机械约束 | 上述冻结版本的本地检查及坏版本反例有历史证据；本次只核对远端版本、文档和日志内容，没有重跑全部产品测试 |
| 实时互动 | 部分真实短题成功；正常绘制与长题超时失败仍在，未达到稳定实时成品条件 |
| 角色视觉 | 固定持杯边界保留；正面候选方向已获用户认可，分层绑定、眼部透明与插值修复及最终自然度尚未验收 |
| 声音 | 四段英文试听已交付，未接入为最终默认，也无独立青春感评价 |
| Windows 10/11、RTX4060 | 原生运行、DPI、多屏、睡眠恢复、模型/角色/语音/OBS 同负载与性能待验证；浏览器和 Linux 文件测试不替代 |
| 实际平台、OBS、观众端 | 待验证；本地节目回执不是观众收到，当前不推进 B 站环境 |
| 学习/主播收益与独立验收 | 未见任务、目标主播/观众、独立工程师复跑与专业盲评待取得 |
| 用户认可 | 仅已明确的人物方向得到认可，不推广为产品或最终视觉/声音认可 |

## 复核与证据使用

先选择上表中的**具体提交**；在独立工作树按对应版本文档准备依赖。当前开发链的[准备与复跑](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/public-rehearsal-readiness.md)、[端到端记录](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/p9-first-loop.md)和[布置复跑](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/5c5122889f6d738607b20fd156f72d453d26a61f/docs/validation/room-variety.md)包含命令、已知失败及回退边界。

原始截图、未剪辑录像、WAV 和脱敏 Trace 审阅副本此前以私有交付提供；本日志不把本地 .build 路径伪装成公共下载，也不上传私人上下文、凭据、SDK、模型权重或角色源文件。拿不到匹配证据、工具或授权素材时，结论应保持未复现。

下一轮先完成最新正常绘制下真实模型到语音的稳定闭环及眼部修复，再制作匹配源码的 Windows 候选。没有同版证据，不将旧安装包称为当前完整产品。
