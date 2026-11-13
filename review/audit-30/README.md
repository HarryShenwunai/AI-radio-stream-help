# 30 项修复与可复现验证

每个修复 PR 包含对应的新回归用例、修复前失败记录、修复后通过记录及源文件哈希。PR 按顺序叠加，第一个基于 `feat/phase1-runtime`，后续各基于前一个修复分支；尚未合并。请按顺序审查，不能把后续分支当作互相独立的发布版本。

## 已执行验证

- 完整质量门：Ruff、10 个核心模块的严格类型检查、可执行架构约束通过。
- Python 回归 798 项、桌面 Python 9 项、前端 JavaScript 133 项、桌面 JavaScript 27 项通过，零跳过。架构测试的直接执行与发现模式均为 19 项；去掉了此前重复继承执行的 60 项旧用例，未用重复计数充实结果。
- TLC：4 个有限状态安全模型通过，10 个错误变体均产生预期反例。详见 `evidence/tlc.json` 和 `../formal-models/logs/`。这不构成全程序等价性、无限状态或活性证明。
- Chromium 实际应用：7 项检查通过，无捕获到的页面 JavaScript 错误。录像复现旧版模型加载失败后卡住；新版提供重试，点击后真实 Core/WebGL 模型恢复。检查左右眼闭合参数分别为 0、手机布局及角色切换释放画布。
- 真实截图和约 14 秒原始录像通过 Library 单独交付。仓库保留哈希和检查报告，不将用户模型、Core 或其他运行时二进制附入本次 PR。

## 可重复运行

质量门（使用已安装的测试依赖，或先安装仓库列出的开发依赖）：

```sh
python scripts/quality_gate.py --bootstrap --full
```

有界形式化检查（需要本机 Java 和已下载的指定 TLC 文件；执行前校验固定 SHA256）：

```sh
python review/formal-models/run_models.py --jar /path/to/tla2tools.jar --output .build/formal-evidence/report.json
```

实际浏览器录像（需要 Playwright 及其录像组件、现有 Chromium、用户提供的模型和获授权的运行时）：

```sh
python tests/browser_audit.py --runtime-dir /path/to/owner-runtime --model-zip /path/to/model.zip --chromium /path/to/chromium --output-dir .build/browser-evidence
```

运行时目录必须包含 `live2dcubismcore.min.js` 和 `build/owner-live2d-runtime.js`。脚本采用隔离数据库和测试 AI，不连接真实账号；使用真实应用 HTTP、DOM、Core 和 WebGL。浏览器采用软件渲染，不代表 RTX 4060 或 Windows 实测。模型导入会操作测试夹具的隔离角色，不会触碰用户数据。

`evidence/quality.json` 保存完整检查命令、源码哈希和原始日志索引；日志实际位于 `evidence/quality-logs/`，报告中的绝对路径为执行时路径。`evidence/browser.json` 与 `evidence/visual-artifacts.json` 记录录像、截图和模型包指纹。`NN-before.txt`、`NN-after.txt`、`NN.json` 为 30 项修复各自的证据。

## 未通过的验收与已知问题

角色背景仍呈明显矩形边界。头发遮挡下的另一只眼睛、闭眼线条与明暗仍需近景视觉审查，参数生效不等于画面获认可。当前不声称 Windows 10/11、RTX 4060、微信/Bilibili 真账号联动或运行时安装器通过。

GitHub Actions 的首个任务未启动，平台账号问题阻止了 runner 执行；没有远端测试通过结果。见 `evidence/github-ci-status.json`。账号恢复后仍须重新运行远端检查。

## PR 索引

| 项 | PR | 修复 |
|---|---|---|
| 01 | [#3](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/3) | Fix stale recorder callbacks stopping a newer microphone |
| 02 | [#4](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/4) | Release recording start state after role changes during permission |
| 03 | [#5](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/5) | Reject invalid PCM rates and nonfinite samples before WAV encoding |
| 04 | [#6](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/6) | Keep system playback start time and deadline stable on duplicate callbacks |
| 05 | [#7](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/7) | Snapshot playback receipt identity at creation |
| 06 | [#8](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/8) | Bound playback headers and reject empty receipt identities |
| 07 | [#9](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/9) | Bound pending playback progress while receipt transport stalls |
| 08 | [#10](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/10) | Show a recoverable scene error when model load returns false |
| 09 | [#11](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/11) | Dispose model resources after a rejected scene load |
| 10 | [#12](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/12) | Prevent disposed scenes from acquiring a new AudioContext |
| 11 | [#13](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/13) | Reject missing renderer registration so script loads remain retryable |
| 12 | [#14](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/14) | Reject missing required model resources before issuing a request |
| 13 | [#15](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/15) | Allow state refresh after an in-flight refresh is invalidated |
| 14 | [#16](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/16) | Seal chat stream after the first terminal event |
| 15 | [#17](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/17) | Bound unterminated chat stream frames |
| 16 | [#18](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/18) | Reject non-text chat deltas instead of coercing them into messages |
| 17 | [#19](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/19) | Fail malformed UTF-8 reply streams instead of displaying replacement characters |
| 18 | [#20](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/20) | Cancel stream readers when parsing or consumption exits |
| 19 | [#21](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/21) | Prevent disposed companion controllers from sending new requests |
| 20 | [#22](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/22) | Propagate abort signals to read-only API requests |
| 21 | [#23](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/23) | Keep system speech usable when optional voice preference storage is blocked |
| 22 | [#24](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/24) | Validate system speech receipt character and appearance before speaking |
| 23 | [#25](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/25) | Preserve completed eye paintings when transfer chunks are absent |
| 24 | [#26](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/26) | Fail full quality checks when regression evidence is missing or stale |
| 25 | [#27](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/27) | Include root startup and build scripts in quality source fingerprints |
| 26 | [#28](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/28) | Preserve partial stdout and stderr when automated checks time out |
| 27 | [#29](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/29) | Require exactly one explicit shared connection field allowlist |
| 28 | [#30](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/30) | Reject qualified builtins execution at asset and proposal boundaries |
| 29 | [#31](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/31) | Reject direct file content access from proposal-only modules |
| 30 | [#32](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/32) | Reject npm vendor aliases in the default dependency graph |
