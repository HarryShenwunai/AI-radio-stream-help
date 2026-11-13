# 原创 Live2D 交付

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
