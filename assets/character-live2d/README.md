# 当前 R3 双眼细节修订

当前候选保留母稿审美与背景，手和杯子固定；包含双眼独立开合、同步眨眼、小幅视线、头部轻微侧倾与胸肩呼吸。取消放杯方案。下面的旧版 Release 只作历史记录，不是本次视觉成品。

| 包 | 用途 |
| --- | --- |
| R3-Companion-Import.zip | 现有角色工作室选择 Live2D 后直接导入 ZIP |
| R3-ViewerEX-CubismViewer.zip | 解压后加载 model/model.model3.json；附中文说明 |
| R3-Cubism-Editable.zip | Cubism Editor 打开 character.cmo3；另含 PSD2Live 工程 |

三份文件已交付至用户 Library；本仓库未将私有 Library 下载地址或角色二进制重新公开。包内容、字节数与 SHA256 见 [交付校验](../../review/r3-package-check.json)。项目导入器格式检查通过；Core 播放与逐帧证据见[修订记录](../../docs/implementation/live2d-r3-both-eyes.md)。ViewerEX 实际导入、官方 Editor 复开、Windows/4060 实机及用户最终视觉认可仍待验证。

现有程序无需固定内置角色即可导入新包。查看时先使用预设 Idle，避免额外自动眨眼、跟踪控制覆盖动画；背景仍为原图背景，尚非透明抠图桌宠。

## 历史交付


[下载本批附件](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.5.0-dev3-live2d)。本目录只保存通知与说明，Git中不包含Core/Framework、模型权重或用户资料。

| 文件 | 用途 |
| --- | --- |
| character-app-source-update-0.5.0-dev3.zip | 已发布Windows基础包的小更新，约7MB |
| original-live2d-r2-candidate-runtime.zip | 软件角色工作室导入，11,017,918bytes |
| original-live2d-r2-candidate-source.zip | 42层原画、PSD、完整PSD2Live工程、CMO3、CAN3和配方，345,553,022bytes |
| original-live2d-r2-source-validation.zip | 可复现源证书、实际负控与官方CLI导出记录 |

这是半身角色，包含十根独立手指、手掌、衣袖、完整可脱离杯子、头眼嘴、头发物理、四表情和八动作组。拿杯、移杯、空手、招手由实际包内motion执行。自助上传其他合法角色保留，不依赖固定角色目录。

完整工程由官方PSD2Live3.6.7 CLI实际重开并导出成功；使用6GiB Java heap、峰值约6.2GiB RSS。这是作者工具成本，正常陪伴运行不需要Java。源码包内配方明确推荐已通过的CLI；旧4GiB MCP重开失败记录保留。官方Cubism Editor/Animator GUI重开尚未验证。

[前端与模型实测](../../review/live2d-rigid-r2-frontend-acceptance-summary.json)、[真实语音](../../review/real-live2d-rigid-r2-companion.json)、[软件回归](../../review/quality-gate-live2d-delivery-final.json)。全部当前实测发生在Linux/Chrome，Windows/4060实机与用户画风、听感接受仍待验证。

`candidate`是发布与目标机验收状态；打包器只检查格式、哈希和边界，不自行签发Core或艺术验收。最终功能证据另附，不能把成功压缩当作运行通过。
