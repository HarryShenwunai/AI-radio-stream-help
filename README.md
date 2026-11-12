# 虚拟陪伴项目（未命名）

目标是自然、有稳定性格、能文字和语音相处的虚拟角色。学习监督是可选能力。长期记忆按需使用，不能代替对当前话题的理解。

**已获准启动实施，仓库现包含本地应用和首批协议/取消/离线直播模块。B站、弹幕姬、AR、Minecraft联调尚未完成。**

[当前执行看板](docs/planning/execution-board.md) · [本地运行说明](app/README.md)

```sh
python run.py --no-browser
```

聊天需可选模型资产/依赖或用户配置的模型API；源码不含权重。当前开发版本0.3.0-dev1。

[直接阅读PDF报告](docs/report/comparison.pdf) · [HTML文件](docs/report/comparison.html)（下载后在浏览器打开）

## 从这里阅读

- [类似产品与当前技术](docs/research/products-and-technology.md)：商业体验、开源框架与语音路线。
- [Zerolan五仓库设计比较](docs/research/zerolan-comparison.md)：实现证据、分支差异、复用建议。
- [修订项目计划](docs/planning/revised-plan.md)：范围、方案、工作包、预算假设、风险和七日行动。
- [目标架构与权限](docs/design/architecture.md)：会话隔离、中断、协议适配和模型资源边界。
- [现有设计与实际状态](docs/design/current-state.md)：已有原型、实测记录与未完成项。
- [协议设计草案](contracts/interaction-v1.schema.json)和[验收追踪](review/traceability.csv)。

## 当前验证

115项Python回归、8项Node竞态、12项Chrome检查通过。真实本地Qwen/Kokoro另做一次冒烟；语音质量、真实上游兼容和用户设备性能仍待验收。详见执行看板和review/phase1报告。

开发检查：`python scripts/check.py`；前端竞态：`node tests/test_voice_ui.mjs`（Node 20+）；浏览器：`python tests/phase1_browser_check.py`（需Playwright与Chrome）。

## 当前判断

Zerolan的事件驱动、统一模型管线、独立展示与MC执行器值得参考。推荐保留已经能运行的原型，先建立可替换适配层与中断协议，再决定迁移范围。不能因为同一作者维护五个仓库，就假定所有默认分支可直接组成兼容版本。

体验参考：AIRI、Open-LLM-VTuber、SillyTavern、星野、猫箱、Character.AI、Kindroid、Replika。它们的产品定位、开放程度与可接入能力不同，详见调研。

## 证据与状态

查阅日期：2026-11-12，Europe/London。能力描述区分源码事实、作者/产品文档声明、工程判断与未知；没有付费登录体验或上游部署实测，也没有购买服务、连接直播间或加入MC服务器。

已有v0.2原型记录包括36项后端测试、5项本机模拟模型协议测试，以及Linux编译程序、真实本地模型与语音验证。旧记录不代表本轮重测，不代表Zerolan集成已通过。模型表达仍存在错误，长期相处质量尚未用户验收。

旧稿和原型中的称呼仅为历史占位，不作为正式产品名称。本轮不新增产品名。

## 仓库内容边界

保留轻量设计、历史规划、原型截图、来源索引与脱敏验收记录。模型权重、安装包、数据库、私聊、Cookie、密钥和开发虚拟环境不放入Git历史。没有新增部署工作流。

历史文档在[docs/history](docs/history)，其名称和估算以历史记录理解。新范围与估算以[修订计划](docs/planning/revised-plan.md)为准。用户已批准推荐路线启动，当前完成范围以执行看板为准；未把估算当作承诺。

来源、许可和专业确认事项见[NOTICE.md](NOTICE.md)。
