---
title: 2D角色更新与验收
lang: zh
---
## A 实际运行

新2D角色已接入软件，支持自助导入与预览。
人物保留短发、暖白毛衣和深色杯子。
场景可选晨光、林荫和傍晚。

![真实软件播放本机语音时的2D角色](/workspace/dist/evidence-real-2d-20261112-210218/03-real-kokoro-mouth-playing.png)

四张PNG保持原样。
运行时只切换眼嘴区域，衣服与手部保持稳定。
它是PNG状态动画，尚无完整Live2D拆件。

## B 下载与启用

[打开GitHub下载页](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.5.0-dev2-ui2d)

| 文件 | 用途 |
| --- | --- |
| companion-update-0.5.0-dev2-ui2d.zip | 约6.7MiB，更新已解压的基础程序 |
| character-2d.companion.json | 约9.9MiB，一次导入人物与动画区域 |
| tracking-addon-cp312-win-x64-v3.zip | 可选约79.6MiB，本地面部方向估计 |

1. 从托盘退出软件，再解压更新包。
2. 把旧程序EXE拖到apply-ui-update.cmd。
3. 启动软件，打开角色工作室。
4. 选择PNG角色包，检查预览后启用。

原模型沿用，用户角色和聊天数据保留。
首次使用先下载原Windows基础包。
更新中断可重跑同一更新器，或使用回退脚本。

## C 已执行的验证

| 检查 | 实际结果 |
| --- | --- |
| 完整Python回归 | 648项通过，0跳过 |
| 桌面Python | 9项通过 |
| 前端与桌面Node | 79项与24项通过 |
| 源码与视觉素材 | 249文件SHA稳定并匹配提交 |
| 独立UI与布局 | 16流程、13种布局通过 |
| 实际模型整链 | Qwen、Kokoro、2D、播放停止6门通过 |
| 有限TLC模型 | 4安全配置无反例，10负控检出反例 |
| 最终更新包 | 安装、重复、回退、重新安装通过 |

眼嘴外像素变化为零，真实静音段能闭嘴。
停止后未听完的尾句不会写入下一轮上下文。

云端单次观察：首文17.982秒，首声23.877秒。
停止耗时0.079秒；这些不是Windows性能承诺。
TLC只检查有限模型，不是全程序正确性证明。

## D 录像与证据

[实际程序录像](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/download/v0.5.0-dev2-ui2d/companion-2d-actual-run.mp4)

[实际Kokoro语音](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/download/v0.5.0-dev2-ui2d/companion-2d-actual-response.wav)

录像为30.88秒、772帧，未添加虚构画面。
录像没有系统音轨，实际语音另附WAV。
截图、原录像和机器报告另附证据ZIP。

[完整自动验收报告](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/feat/phase1-runtime/review/quality-gate-rebuild-publish.json)

[独立验收汇总](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/feat/phase1-runtime/review/uiux-2026-independent-summary.json)

## E 尚未验收与下一步

Windows与RTX4060真机尚未运行验收。
实体5英寸显示、真人摄像头和远场距离待测。
真实B站与微信账号、长期人格表现也待验收。
当前PNG不能独立转动眼球。
PC Vision需配置图像模型；内置Qwen只能处理文字。

下一步是在目标电脑运行更新与诊断。
再检查角色显示、录音播放、停止和可选摄像头。
本页不把尚未验收的能力写成全部完成。

资料日期：2026-11-12。
2026设计来源和访问边界保存在仓库研究文档中。
