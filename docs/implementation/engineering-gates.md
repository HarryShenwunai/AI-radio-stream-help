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

默认检查：关键运行错误 lint、四个核心模块 strict mypy、架构边界、11 项基线/故意违规 fixture。完整检查再跑 Python 模块/HTTP/协议、桌面 Python、前端 Node 与桌面 Node 回归。它不自动运行浏览器或 TLC。

输出默认为 `review/quality-gate.json` 和 `review/quality-gate-logs/`；`--report PATH` 可另存。JSON 保存实际命令、版本、退出码、耗时、源码 SHA256、跳过项和边界。源码在检查期间变化会总失败，并列出前后 SHA，避免把并行修改前后的结果当成同一版本。缺依赖必须补齐；报告的跳过项仍需审阅，不能算已验证。

严格类型目前覆盖 `lifecycle.py`、`live.py`、`zerolan.py`、`http_payload.py`，不声称遗留服务端全量严格类型通过。Ruff 只启用 E9/F63/F7/F82 关键错误，不为风格重写旧代码。

## 架构规则对应哪些错误

| 规则 | 自动检查 | 防止的已知错误/边界回归 |
| --- | --- | --- |
| A01 | 公开弹幕入口禁止导入应用、私有存储和关系模块 | 公共输入路径绕进私人上下文 |
| A02 | 共享模型装载/公开回复禁止调用私人配置、历史和 prompt；连接字段固定白名单 | 公有生成通过私人 `settings()` 读取角色/历史 |
| A03 | 角色包解析器禁止执行/网络导入与调用 | 上传包触发脚本或联网；ZIP 内容验证另由资产单测覆盖 |
| A04 | 默认静态图和前端依赖图排除可选 Cubism SDK、Core 和角色模型字节 | 把局部评估授权误当默认分发授权 |
| A05 | 插件令牌只进入 inbound/claim/ack，操作前必须有显式认证；禁止主人操作 | 传输令牌获得配置、审批或其他主人权限 |
| A06 | `Handler.reply` 仅委派一次 `encode_http_body`，禁止自行 JSON 序列化 | 已序列化的 Live2D JSON 资产 bytes 被二次序列化 |

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
PYTHONPATH=src:tests python tests/connectors_browser_check.py
PYTHONPATH=src:tests python tests/voice_input_browser_check.py
```

平台 UI 脚本生成 `review/connectors-browser.json` 和 `/workspace/dist/connectors-mobile.png`，不配置/审批真实平台。录音脚本使用合成输入与转写替身，不使用真人麦克风、不证明真实 ASR 准确率。运行需现有 Chrome/Chromium 和 Playwright；如环境缺浏览器应明确失败，不伪造截图。

有现成合法本地模型与 Kokoro 资产时，可选真实生成/播放/打断录屏：

```sh
COMPANION_MODELS=/workspace/companion/models COMPANION_VOICES=/workspace/companion/voices /workspace/companion/.venv/bin/python tests/real_companion_browser_check.py
```

该脚本不下载模型，保存截图、真实响应 WAV、JSON 和 `actual-app-process.webm` 到 `/workspace/dist/evidence-companion-real-*`。屏幕录像不含系统音轨；音频单独留存，软件 WebGL 不代表 RTX4060 性能。此脚本只在明确选择运行时执行，不属于默认/完整质量门禁。

已有本机评估授权与独立合法运行时/模型时，Live2D 专项使用：

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
