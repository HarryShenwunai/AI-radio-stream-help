# 虚拟陪伴项目（未命名）

二次元桌面陪伴，用户可以创建自己的角色、导入PNG形象，并配置性格与相处方式。聊天、记忆和约定按角色隔离；更换同一角色的外观保留相处记录。学习监督是可选能力，长期记忆可关闭。

当前开发版本 **0.4.0-dev1**。自助PNG角色与独立身份数据已实现；Live2D、VRM尚未实现。目标平台是 **Windows 10/11**，Windows构建、安装与真机桌面行为仍待CI和设备验证，不能将Linux结果当作Windows成品验收。

[运行与角色导入](app/README.md) · [本批交付状态](docs/implementation/character-release.md) · [执行看板](docs/planning/execution-board.md)

## 从源码启动

在Python环境中安装图片组件后，从仓库根目录运行：

```sh
python -m pip install -r app/requirements-core.txt
python run.py --no-browser
```

打开终端打印的本机地址。角色管理与图片导入不要求下载大模型；真实聊天需要已有本地模型及可选推理依赖，或在设置中填写兼容模型API。源码不包含模型权重、音色文件、用户数据库或密钥。

桌面壳启动、数据迁移和可选模型安装见[运行说明](app/README.md)。当前没有已核验的Windows安装包下载声明。

## 当前可用

- 创建、切换、归档、恢复和删除独立角色；名字不作为格式白名单。
- 导入一张PNG，或配置待机、说话、眨眼、说话时眨眼四种图片状态。
- 预览后明确启用；保留外观修订并切回旧版；无效图片不覆盖当前形象。
- 角色自己的聊天、性格、记忆与约定分库存储；旧版数据库一次迁移并保留原库。
- 共享模型连接配置，API密钥留在本机；切换角色不会恢复另一套旧提供方连接。
- 流式文字、停止与重试、本地语音或兼容API、按需记忆及可关闭的主动联系。
- 桌面壳提供角落常驻、展开同一会话、鼠标穿透与恢复入口；目前桌面行为证据限Linux X11，Windows待测。

PNG说话状态是图片切换，不是Live2D绑定或音素级口型。上传的角色素材仍按各自授权使用；应用原有SVG只是占位示例。

## 验证与边界

本轮[185项Python回归](review/character-regression.json)通过；前端18项角色竞态、8项语音竞态，以及[15项真实Chrome检查](review/character-browser.json)通过。Chrome使用合成PNG与测试音、本机模型/TTS替身，未验证真实声线质量。

[Linux编译后端](review/character-native-check.json)完成6项检查，包含实际本地Qwen/Kokoro与取消、重启持久化。它是一轮合成输入冒烟，**模型自然度与长期相处质量尚未人工接受**，时延也不是目标设备p95。另有[Linux Electron整包13项检查](desktop/test-results/bundled-app-smoke.json)通过，覆盖内嵌后端和实际应用PNG流程，仍不代表Windows通过。

[独立审查](review/character-implementation-review.json)只覆盖已说明的PNG子集。原28项多格式规格不因这些测试自动全部通过。Windows、Live2D、真实平台/OBS、微信、AR、MC、全屏游戏及目标机能耗仍有未完成项。

开发检查：

```sh
python scripts/check.py
node tests/test_character_ui.mjs
node tests/test_voice_ui.mjs
python tests/character_browser_check.py
```

HTTP/Chrome检查需要允许本机socket；浏览器脚本需要Playwright与Chrome。最终测试以对应JSON的范围、结果和日期为准。

## 项目资料

- [自助角色计划与画师交付基准](docs/planning/self-service-characters-plan.md)
- [产品与技术比较](docs/research/products-and-technology.md)
- [Zerolan五仓库研究](docs/research/zerolan-comparison.md)
- [架构与权限](docs/design/architecture.md)
- [历史原型与证据](docs/design/current-state.md)

旧计划、称呼和估算保留作历史追踪，不作为正式产品名或当前完成证明。角色导入以已实现格式和实际兼容矩阵为准。

模型、安装包、用户数据和凭证不进入Git历史。没有公开部署、登录直播间或游戏服务器。应用代码与可选依赖许可见[NOTICE.md](NOTICE.md)及[应用许可](app/LICENSE)。
