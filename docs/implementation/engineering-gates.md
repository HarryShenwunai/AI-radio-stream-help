# 可执行工程门禁与复现

更新：2026-11-12。目标是把已定位的错误变成自动失败条件。质量工具仅供开发，不进入用户运行包；不增加 `AGENTS.md` 规则。

## 一条命令运行

在仓库根、Python 3.12 环境执行，Windows 与 Linux 使用相同命令：

```sh
python scripts/quality_gate.py --bootstrap
```

`--bootstrap` 显式创建/复用 `.build/quality-venv`，必要时从官方 PyPI 安装 `requirements-quality.txt` 固定的 Ruff 0.17.4、mypy 2.4.1，然后检查。已安装对应版本时直接复用。不带此开关的检查不安装工具、不下载模型、不连接账号、不发送消息。

完整本机回归还需要调用者 Python 已安装轻量测试依赖：

```sh
python -m pip install -r app/requirements-core.txt -r requirements-dev.txt -r src/companion_runtime/connectors/requirements.txt
python scripts/quality_gate.py --bootstrap --full
```

`--full` 的 Python 测试默认使用调用者原环境，质量工具保留在隔离环境；也可传 `--test-python PATH` 指定另一个已有测试环境。需要 Node.js 22+，没有下载大模型或 Electron 的要求。受限沙箱需允许本机 HTTP/WebSocket 监听，拒绝监听是环境失败，不应跳过认证/协议测试。

默认检查：关键运行错误 lint、`pyproject.toml` 明列的十个核心模块 strict mypy、架构边界和故意违规 fixture。完整检查再跑 Python 模块/HTTP/协议、桌面 Python、前端 Node 与桌面 Node 回归。它不自动运行浏览器或 TLC。

输出默认为 `review/quality-gate.json` 和 `review/quality-gate-logs/`；`--report PATH` 可另存。JSON 保存实际命令、版本、退出码、耗时、源码 SHA256、跳过项和边界。源码在检查期间变化会总失败，并列出前后 SHA，避免把并行修改前后的结果当成同一版本。缺依赖必须补齐；报告的跳过项仍需审阅，不能算已验证。

严格类型覆盖 `lifecycle.py`、`live.py`、`zerolan.py`、`http_payload.py`、`assistance.py`、`devices.py`、`perception.py`、`preference_learning.py`、`perception_tracking.py`、`perception_optional.py`，不声称遗留服务端全量严格类型通过。mypy 使用 `--test-python` 对应的实际依赖环境；例如 Pillow 类型不在质量工具隔离环境里。Ruff 只启用 E9/F63/F7/F82 关键错误，不为风格重写旧代码。

源码指纹包含实际静态背景与角色图像，不仅检查JavaScript和Python。增量包必须由通过且源码未变的报告绑定程序与场景SHA；不能在改图后沿用旧报告。角色导入包独立交付，需要用户先预览再确认，不自动改用户角色。

## 架构规则对应哪些错误

| 规则 | 自动检查 | 防止的已知错误/边界回归 |
| --- | --- | --- |
| A01 | 公开弹幕入口禁止导入应用、私有存储和关系模块 | 公共输入路径绕进私人上下文 |
| A02 | 共享模型装载/公开回复禁止调用私人配置、历史和 prompt；连接字段固定白名单 | 公有生成通过私人 `settings()` 读取角色/历史 |
| A03 | PNG、VRM、Live2D及原创分层2D解析器禁止执行/网络导入与调用 | 上传包触发脚本或联网；ZIP 内容验证另由资产单测覆盖 |
| A04 | 默认静态图和前端依赖图排除可选 Cubism SDK、Core 和角色模型字节 | 把局部评估授权误当默认分发授权 |
| A05 | 插件令牌只进入 inbound/claim/ack，操作前必须有显式认证；禁止主人操作 | 传输令牌获得配置、审批、感知、设备、协助或偏好学习权限 |
| A06 | `Handler.reply` 仅委派一次 `encode_http_body`，禁止自行 JSON 序列化 | 已序列化的 Live2D JSON 资产 bytes 被二次序列化 |
| A07 | 协助和偏好候选模块禁止直接网络、执行脚本或调用应用历史/工具辅助函数 | 把只读提议升级为外部操作；偏好只按显式请求查询本角色来源原文，模型不能改写事实 |

实现：[AST 检查器](../../scripts/check_architecture.py)；[违规 fixture](../../tests/test_architecture_rules.py)。fixture 只改内存/临时目录，实际验证各规则拒绝违规，其中一项真实启动 CLI，要求退出码 1。生产源码不会为了制造失败被修改。

这些是有限的 AST、调用和依赖图契约，不能穷尽 Python 动态调用或证明完整程序信息流。真实 HTTP 认证/隔离与资产单测补充运行时验证；合法 SDK、模型许可和 Windows 真机仍需各自验收。

## 启动产品与保留视觉证据

源码启动，不自动打开浏览器：

```sh
python -m pip install -r app/requirements-core.txt
python run.py --no-browser
```

打开打印的 localhost 地址。该命令使用正常数据目录；隔离实验可先通过 `COMPANION_DATA` 指向新临时目录，勿指向用户已有数据库做破坏性测试。详细设置见[应用说明](../../app/README.md)。

现有浏览器脚本自行启动临时本机服务并使用合成用户数据，以下命令适用于本项目云端 Linux 环境（脚本显式使用 `/usr/bin/chromium`），不能把其结果当成 Windows 实测：

```sh
PYTHONPATH=src:tests python tests/uiux_2026_browser_check.py --phase after --native
PYTHONPATH=src:tests python tests/png_region_stage_check.py
```

新UI脚本覆盖角色、用途流程、设备声明、权限、布局及实际Linux Electron；替身模型不证明真人对话或平台送达。区域动画脚本用真实Chrome/HTMLAudio和合成的有声/静音波形，检查中间静音闭嘴、区域外像素不变、资源只读取一次以及停止释放，不证明人声或音素口型。运行需现有Chrome/Chromium、Playwright，原生选项还需本机Electron/X11；缺环境应明确失败，不伪造截图。

有现成合法本地模型与 Kokoro 资产时，可选真实生成/播放/打断录屏：

```sh
COMPANION_MODELS=/workspace/companion/models COMPANION_VOICES=/workspace/companion/voices /workspace/companion/.venv/bin/python tests/real_companion_browser_check.py
```

该脚本不下载模型，使用当前2D角色/区域元数据，保存截图、真实响应WAV、JSON和录像到 `/workspace/dist/evidence-real-2d-*`。屏幕录像不含系统音轨；音频单独留存，不代表Windows/RTX4060或人类听感验收。此脚本只在明确选择运行时执行，不属于默认/完整质量门禁。另有 `tests/real_product_services_check.py`，实际本地Qwen核实来源偏好候选、确认、关闭记忆及只读建议，不替换推理函数。

已有本机评估授权与独立合法运行时/模型时，历史Live2D专项命令如下。完整UI重建后的当前集成应以新UI导入/停止测试为准，旧专用采集脚本若依赖旧UI需先迁移，不能沿用旧报告声称本版完成：

```sh
PYTHONPATH=src:tests python tests/live2d_browser_check.py --model-zip /absolute/path/model.zip --runtime-dir /absolute/path/runtime --label local-check
```

保存报告 `review/live2d-browser-check.json`、截图与 `acceptance.webm` 至 `/workspace/.live2d/evaluation/local-check/`。脚本不会取得 SDK/模型或授予分发许可；评估资产/运行时不进入默认包或公开 Git。

## 独立形式验证与 CI

有限状态 TLA+/TLC 模型、执行器位于 [review/formal-models](../../review/formal-models/README.md)，与真实实现属性/调度测试 `tests/test_formal_boundaries.py` 分开。已有官方 TLC v1.7.4 JAR 和 Java 时：

```sh
python review/formal-models/run_models.py --jar /absolute/path/tla2tools.jar
python review/formal-models/run_implementation.py
```

执行器不自动下载 Java/JAR，缺工具或官方 JAR SHA 不匹配会失败。模型输出 `review/formal-model-check.json` 和 `review/formal-models/logs/`，真实实现检查输出 `review/formal-implementation-check.json`。模型范围为有界公开/私人/停止调度及两次播放尝试的身份与回执顺序，验证安全性；未证明 Python 到 TLA+ 的精化、活性、全部输入/调度或完整程序。

[quality.yml](../../.github/workflows/quality.yml) 仅安装检查依赖、运行门禁并上传检查证据，不部署、不连接用户账号、不含平台密钥。工作流配置存在不等于 CI 已运行；本项目历史 Actions 计费锁定导致 runner 未启动，必须以实际任务记录为准。本机报告与截图也不自动获得外发授权。
