---
title: 未命名虚拟陪伴项目 · 产品、架构与修订计划
subtitle: 2026-11-12 · Europe/London · 设计归档版
file: design-comparison
lang: zh
template: doc
theme: paper
---
建议保留已运行原型，借鉴Zerolan的事件与模型接口拆分。先验证跨端协议、语音中断和公开/私密隔离，再接B站与弹幕姬。AR和MC单独验收，不作为所有用户的启动依赖。

项目不命名。新集成尚未运行；本轮完成的是资料核查、设计比较和计划修订。

## A 类似产品：先看什么

| 对象 | 最接近的部分 | 对本项目的启发 | 需要保留的限制 |
| --- | --- | --- | --- |
| Zerolan体系 | 多模态、直播、AR与游戏角色 | 事件、模型管线、展示、执行器分离 | 分支与接口不是天然全兼容 |
| AIRI | 二次元多端角色、Live2D/VRM、语音 | 形象与声音生命周期 | README仍有WIP能力；未做目标机实测 |
| Open-LLM-VTuber | 实时语音与Live2D | 通话、打断和呈现 | 当前README称长期记忆暂移除 |
| SillyTavern | 角色配置与可控聊天 | 人设、上下文和TTS控制 | 是界面，仍需模型；AGPL-3.0 |
| 星野、猫箱 | 中文角色与语音剧情 | 自然进入相处场景 | 只有官网/发行方说明，未付费体验 |
| Character.AI | 双向角色通话 | 聊天与通话切换 | 文档不是当前账号资格保证 |
| Kindroid | 通话、重生成、可控主动联系 | Quiet hours与频率控制 | 套餐、中文效果和持续成本未实测 |
| Replika | 关系状态、形象、语音/AR | 稳定相处入口 | 闭源能力不能直接复用 |

商业能力取自官方或发行方说明，不等于已验证效果。没有证据表明某个产品已满足本项目全部微信、B站、弹幕姬和隐私要求。

当前技术可选级联语音或原生实时语音。级联可复用本地LLM/TTS并先审查文本；原生实时语音由提供方处理连续音频，客户端仍要处理取消和播放。先做同场景对照，不默认双开模型，也不报价未知服务。

## B 用户提供的五仓库如何协作

| 仓库 | 已核实的边界 | 关键采用条件 |
| --- | --- | --- |
| ZerolanLiveRobot | 事件编排；模型调用；直播、OBS和展示连接 | 补有界队列、频道分区、取消与权限 |
| zerolan-core | HTTP模型服务与统一管线封装 | JSON流解析、模型ID和TTS接口逐项验证 |
| zerolan-data | Pydantic数据模型与WS协议1.1 | 显式请求ID、作用域和取消关联 |
| ZerolanPlayground | Unity/Vuforia、AR与Live2D/3D | Unity 6000.0.51f1；依赖/许可/真机验证 |
| KonekoMinecraftBot | Mineflayer、FSM与技能；dev含桥接 | 固定dev、游戏版本、权限和结果回执 |

已核查五个README和41份实现、配置或许可文件。未运行上游、打开摄像头或进入游戏。

关键发现：

- 活动弹幕回调逐条触发回复；5秒挑选回调被注释。不能从README认定已具峰值调度。
- 事件5秒超时用于诊断，不等于任务已取消。Unity下载后入播放队列，需验证晚到与乱序。
- 模型数据默认UUID表达式在类定义时求值。新请求须显式分配ID或用default_factory。
- Core返回逐行JSON，网络chunk不等于消息；适配器要处理拆包、并包和UTF-8分割。
- 通用TTS入口是占位，但体系有TTS。文档要求特定GPT-SoVITS fork与zerolan_api.py。
- MC协议桥接在dev，不在读取的默认master。不能笼统断言没有，也不能直接用master承诺联机。

AR根许可证未确认；MC master的package许可标签与LICENSE不同。主体MIT不能覆盖Unity、Vuforia、Cubism和全部素材。

## C 推荐架构与权限

```flow TB
私人输入 -> 频道与权限
B站与弹幕姬 -> 频道与权限
频道与权限 -> 分区会话与调度
分区会话与调度 -> 可替换模型接口
可替换模型接口 -> 媒体与取消
媒体与取消 -> 私人视图
媒体与取消 -> 专用直播预览
媒体与取消 --> AR显示端: 可选
分区会话与调度 --> MC受限网关: 单独授权
```

同一模型服务可以复用；私人和公开上下文不能共用。默认少量进程，不为每个入口再加载一份LLM。

角色设定、当前对话、真实运行状态、长期记忆分开处理。记忆可关闭；公众输入不能读取私聊或修改人设。

用户打断时先停本机声音，再取消模型/TTS并清理队列。丢弃旧generation的晚到输出；未听内容不能当作已经说完。旧端不支持取消时明确报告，不伪造回执。

公开页只接受检查后的最终内容。MC先只读，再开放受限技能；观众没有桌面、浏览器或游戏控制权。

## D 方案取舍与执行顺序

| 方案 | 优势 | 代价与条件 |
| --- | --- | --- |
| 保留原型并适配 | 复用现有行为、数据、测试和回退 | 当前推荐；先补契约与生命周期 |
| 迁移Zerolan编排 | 多模态和扩展结构较丰富 | 先做2–3人日兼容样例，再重估迁移；仍需权限与隔离 |
| 换AIRI/VTuber呈现壳 | 更贴近动态角色与语音 | 先验证会话/配置/素材兼容，不能按截图决定 |

| 包 | 交付 | 前置 | 工程估算 |
| --- | --- | --- | --- |
| P0 | 固定commit、协议/TTS/MC dev兼容样例 | 目标设备与范围 | 2–3人日 |
| P1 | 公私分区、事件合同与取消 | P0 | 2–4人日 |
| P2 | 提供方与语音轮次、播放进度 | P1 | 2–4人日 |
| P3 | 一条直播主入口与弹幕姬调度 | P1与账号条件 | 4–7人日 |
| P4 | 私人界面、专用OBS预览与接管 | P2/P3 | 2–4人日 |
| P5 | 同机质量/资源/恢复验收 | P1–P4 | 3–5人日 |
| P6/P7 | 可选AR、可选MC | 核心通过及相应授权 | 各3–6人日 |

核心基础15–27人日；加储备为18–33人日。AR和MC均选则24–45人日。按8小时/人日，非报价或交期承诺。旧直播专项估算不再重复相加。

七天最有价值的顺序：确认条件 → 兼容样例 → 语音中断基线 → 公私隔离 → 直播本机预览 → 资源/故障对照 → 用户复核。任务均为未来计划，不能理解为七天完成全部扩展。

## E 如何验收与计成本

| 检查 | 数据与初始条件 |
| --- | --- |
| 自然相处 | 30条独立场景；关闭记忆/无关记忆两组；人工接受率门槛待基线 |
| 中断 | 100次目标机操作；旧声音复活0；本机暂停拟定p95≤300ms |
| 隐私与权限 | 20条私密诱导+10类越权；泄漏与越权副作用均0 |
| 协议 | 错版本、重复ID、拆并包、中文分割、乱序与晚到均有确定结果 |
| 语音与资源 | 至少100轮首声p50/p95；30分钟同机CPU/RSS/VRAM与OBS对照 |
| 直播洪峰 | 合成200事件/秒×60秒；队列有界，同时报告丢弃与回应覆盖率 |
| 恢复 | 断线、提供方失败、重启不重复播报或执行；旧数据可回退 |

这些是设计目标或待校准条件，新集成执行数0。不能用旧原型测试或上游README填通过。

已有原型单次Linux观测：首段文字9.229秒、完整回复11.205秒、语音合成3.419秒，进程约5.31GiB。不是首声p95，也不能与上游显存表直接比较。

人工预算为实际小时×约定费率；API按真实文本/音频用量和官方单价计。硬件、套餐、许可和审核时间未知。按需情感分析/翻译/改写分别记录额外耗时与调用，不隐藏性能开销。

## F 交付、证据与未解决项

当前GitHub目标是已有仓库 [HarryShenwunai/AI-radio-stream-help](https://github.com/HarryShenwunai/AI-radio-stream-help)。设计按未命名项目归档，旧称呼仅作历史占位。

仓库保存产品比较、五仓库审查、目标架构、修订计划、协议草案、需求追踪、历史计划和原型截图。模型、安装包、数据库、私聊和凭证不入Git历史。没有部署工作流。

实际完成：文档与源码核查、分支/接口差异登记、方案和验收修订、设计文件校验。未做新集成、采购、登录、开播、摄像头采集或游戏动作。

仍未知：用户设备、预算、音色、弹幕姬版本与房间条件。AR许可与真机、MC版本与服务器授权也需确认。集成时延和长期相处质量需实测。

资料均于2026-11-12查阅。主要来源：[Zerolan主仓库](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot)、[AR](https://github.com/AkagawaTsurunaki/ZerolanPlayground)、[Core](https://github.com/AkagawaTsurunaki/zerolan-core)、[Data](https://github.com/AkagawaTsurunaki/zerolan-data)、[MC dev](https://github.com/AkagawaTsurunaki/KonekoMinecraftBot/tree/dev)、[AIRI](https://github.com/moeru-ai/airi)、[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)、[SillyTavern](https://docs.sillytavern.app/)、[星野](https://www.xingyeai.com/)、[猫箱发行方页面](https://apps.apple.com/cn/app/id6475000292)、[Character.AI](https://support.character.ai/hc/en-us/articles/23957274129691-Character-Calls-Voice-FAQ)、[Kindroid](https://kindroid.ai/v2/docs/voice-calls-and-video-calls/)、[Replika](https://help.replika.com/hc/en-us/articles/360032500052-What-is-Replika-Pro)、[OpenAI音频中断](https://developers.openai.com/api/docs/guides/realtime-conversations)、[Gemini Live](https://ai.google.dev/gemini-api/docs/live)。

商业说明属于可信但未体验验证的信息；“优先适配”是工程建议。固定版本和文件标识在仓库evidence，未执行测试与审查结果在review。保留旧IEEE计划结构，不宣称付费标准全文审查或认证。
