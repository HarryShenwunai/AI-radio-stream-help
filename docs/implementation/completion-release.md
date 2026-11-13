# 0.5.0-dev3 实际交付状态

更新：2026-11-13 UTC。本次已完成原创半身Live2D、完整手部与独立杯子，并完成最终运行包的本机真实语音验证。整项目的Windows目标机、真实账号、实体设备及用户质量验收仍未完成。

## 下载与运行

[GitHub本批发布](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.5.0-dev3-live2d)提供程序小更新、模型运行ZIP、完整编辑源、截图、录像与独立WAV。

已有0.4.0-dev1便携基础包时：

1. 退出软件，解压约7MB程序更新，运行apply-ui-update.cmd并选择原软件目录。
2. 同目录运行setup-live2d-owner.cmd，按条款完成本机评估运行库安装。依赖约29MB加官方Core，不需要Node/npm；SDK不随默认包分发。
3. 打开角色工作室，上传original-live2d-r2-candidate-runtime.zip，预览并确认。主舞台动作入口提供拿杯、移杯、招手、空手和包内表情。

没有基础包时，先按[原基础包](https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate)的下载合并脚本安装。基础包BUILD-INFO保留0.4组装记录，程序与server更新为0.5.0-dev3；实际小更新程序源码为084aaf222b54e1828595bde82fc07c58acbb6075。后续提交只补源包工具及验收材料，不冒称重新构建Windowsexe。

## 实现与实际验收

| 项目 | 结果与证据 |
| --- | --- |
| 原创角色 | 42个实际网格、41参数、四表情、八动作组；42层PNG与外部/内嵌同源PSD，完整可编辑工程及CMO3/CAN3已交付 |
| 手部与杯子 | [完整13门](../../review/hand-cup-rigid-r2-v1-full.json)通过：十指真弯曲、指根漂移0、手掌/衣身保护、杯子独立位移旋转隐藏、四真实动作、Core/产品/GL/Studio生命周期 |
| 持杯 | 547姿态含486所选角点+61离key组合，raw/product双通道；另[独立5000](../../review/hand-cup-rigid-r2-actual5000-grip-asm.json)最大误差0.678588源px，预算1px |
| 硬杯 | [同5000杯形](../../review/hand-cup-rigid-r2-shape5000.json)154个三角形使用顶点，最大affine残差0.0000857、similarity0.0001063源px，均低于0.5；旧r1同域25.4447px软杯红保留 |
| 衣袖与脸 | [独立Core/GL](../../review/original-character-live2d-rigid-r2-core-gl.json)8门、13参数、2378次评价通过；34cloth姿态0翻转，最大edge1.222722；中性眼1/嘴0及头眼嘴/侧件已实看 |
| 主舞台 | [9门动作与三景](../../review/live2d-rigid-r2-mainstage-actions-ui.json)、[3门表情](../../review/live2d-rigid-r2-mainstage-expression-controls.json)、390键盘/Esc/焦点与角色隔离通过；正常录像与诊断暂停中段分开 |
| 真实声音 | [恢复轮7门](../../review/real-live2d-rigid-r2-companion.json)通过：exact最终ZIP→Qwen→Kokoro真实WAV→HTMLAudio/Analyser→Core口型；停止0.793s，未确认尾部不进入后续prompt |
| 程序更新 | [真实产物13门](../../review/app-source-update-dev3-exactbase-check.json)：82操作、重复执行和完整回滚、CPU/CUDA后端新脚本200、数据哨兵与原基础包不变；Linux文件系统验证，未执行Windowscmd |
| 工程门禁 | [780Python零跳过、111Node、桌面9Python/27Node](../../review/quality-gate-live2d-delivery-final.json)，strict10模块、7架构规则及15负控，源码SHA检查前后稳定 |

547或5000均不是穷举全部20655内部keyforms。完整41310源键格、7轴实际MOC表、Root27与H0恒等由独立源/二进制证书核验；这不构成专有Core全程序形式化证明。

## 性能与真实边界

32次预热后5000次纯Core.update：p50 0.2ms、p95 0.4ms、最大14.7ms，Linux共享AMD EPYC/Chrome asm.js。此范围不包含GPU绘制、AI或音频，不等于FPS或Windows/4060数据。

真实CPU语音恢复轮单次首次文字49.54秒、回复完成62.314秒、观察到语音RMS69.621秒；峰值进程RSS约5.37GiB。冷启动/共享CPU与本地提供方成本包含其中，未测多轮p95，不能称已达到实时交流目标。GPU profile已提供但Windows CUDA/offload仍需实机确认。

第一次真实语音因环境重置在口型截图后中断，保留原WAV/三图/视频，没有最终stop报告，不能算PASS；第二次是独立目录中的完整恢复验证，不能宣称只调用过一次。WAV独立提供，Playwright屏幕录像没有系统音轨；机械播放回执不证明真人听见。

## 保留的外部验收

- Windows10/11启动退出、驱动/VC、CPU/CUDA真实推理、多屏DPI/穿透与游戏场景、4060显存与延迟。
- 用户实际5英寸显示、摄像头/眼动与远场麦克风；声明有设备不等于已实测。
- 微信ClawBot文字/音频文件送达、Bili Open Live真实房间/重连；模块和本机模拟通过不等于账号联通。无实际登录、发信或公开播出。
- 官方Cubism Editor/Animator GUI打开CMO3/CAN3、用户对画风、声音与长期关系体验的接受。

遇到失败保留当前角色与聊天，支持形象重载、修订回退、CPU或文字路径。没有因开发授权购买服务、分发SDK、静默切在线ASR或操作真实账号。当前台账见[completion-status](../../review/completion-status.json)。
