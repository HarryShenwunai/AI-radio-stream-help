# 可复跑的并发安全检查

2026-11-12。这里提供实际运行的 TLA+/TLC 有限状态模型，以及**独立的真实 Python 属性回归**。当前runner含14个配置：4个当前安全配置无反例，10个历史/故障配置检出预期反例。最新实证为[重建版TLC报告](../formal-model-rebuild-check.json)，旧10配置报告保留。这不是整个应用的正确性证明，也不代表Windows、GPU、声音设备或真实账号已经验收。

## 单命令复现

从仓库根目录运行，不会下载依赖、连接账号、部署或发送消息：

```sh
python review/formal-models/run_models.py --jar /workspace/.formal-tools/tla2tools-1.7.4.jar --output review/formal-model-rebuild-check.json
python review/formal-models/run_implementation.py
```

第一条需要本机 Java 和官方 `tla2tools.jar`。可用 `--jar` 或 `TLA2TOOLS_JAR` 指定位置；缺工具或 SHA256 不匹配会退出 2 并写入 `preflight_failed` JSON，**不会自动下载**。这里云环境的 Java 监控本地 socket 被默认沙箱禁止，需经工具权限机制批准后原命令运行；普通开发机不需要绕过系统保护。若受限环境不能开 socket，报告应保持失败，不能把解析成功当作验证成功。

依赖来源：[TLA+ 官方 v1.7.4 发布资产](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)，访问日期 2026-11-12。下载文件 2,274,532 字节；工具自报 `TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)`，本次使用 OpenJDK 21.0.13。复现器固定校验本次官方资产的**观测 SHA256**：

```text
936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88
```

官方该 release API 未提供资产 digest，所以这不是声称存在官方发布的签名或校验和。首次取得工具仍需自行核对官方来源；该大文件不放入源码仓库。

产物：

- [TLC JSON 报告](../formal-model-check.json)：每个 case 的完整运行 argv、状态数、配置/模型/实现 SHA256、运行前后源码稳定性、预期反例是否找到。
- [真实实现 JSON 报告](../formal-implementation-check.json)：实际调度结果、动作域、运行前后源码 SHA256、持续时间。
- [原始日志](logs/)：四个安全配置的完整搜索统计、十个负控制的实际反例轨迹、真实Python测试日志。

`python scripts/quality_gate.py --full` 通过 `scripts/check.py` 自动 discover `tests/test_formal_boundaries.py`；不需要把 TLC jar 安装到生产依赖中。独立 TLC 命令保持明确，缺 TLC 不得冒充该形式化步骤已完成。

## 模型与实现的对应关系

| 模型操作/性质 | 对应实现 | 抽象与前提 |
| --- | --- | --- |
| `PublicAcquire` + 原子登记 | `app/server.py` 的 `connector_request('bili/reply')`：同一 `DISPATCH_LOCK` 内检查 `PRIVATE_WAITERS`、取得 `MODEL_LOCK`、登记 `service.public_generation` | OS/Python 互斥原语本身正确；只建模一个公开请求 |
| `PrivateAnnounce` / `PrivateCancelScan` | `chat()` 的等待者计数与 `cancel_public_generations()` | 一个私聊请求；取消是协作式，模型允许等待超时，未证明五秒内成功 |
| `PublicCommit` / `StopPublic` | `service.lock` 内 `GENERATIONS.complete(handle)` 与 append；取消也经同一个 `service.lock` | 模型只保证先失效的生成不会随后提交；已提交后再停止不会撤回既有记录 |
| `PublicClear` + 原子释放 | `bili/reply` finally 的 `DISPATCH_LOCK` 内清登记、释放 `MODEL_LOCK` | 保证私聊不会看到“模型仍被公开请求占用、登记已消失”的窗口 |
| `ReceiveCompleted` | `PlaybackTracker.receipt()` 的 attempt、nonce、scope/current 与终态校验 | 有限凭证值 `{1,2}`，代表相同/不相同；不证明密码学安全或 HTTP 认证 |
| `BeginSecond` / `SwitchScope` | `begin()` 的 retire 与 `invalidate()` | 同一 owner、同一消息的两个 attempt、最多一次切换；未建模 TTL/多 owner 竞争 |
| `Persist` | `merge_receipts()` 保留最长兼容确认前缀 | 已由服务端生成、同角色/消息/文本的回执；模拟持久化提交顺序，不模拟磁盘故障 |
| `Start` / `Capture` | 本机owner HTTP鉴权、`PerceptionManager.start/frame`及设备声明判断 | 声明拥有设备不等于采集授权；有限caller值owner/plugin |
| `Deliver` / `Stop` / `SwitchScope` / `DisableCamera` | `_check()`核role/appearance epoch、session、cancel，`stop/stop_all`及host失效 | 保留未合作provider的在途结果，检查它不能在停用或换角色后交付；不证明远端已发数据可撤回 |

TLA+ 模型不是从 Python 自动抽取的，没有证明两者的 refinement。源码人工映射和下列真实实现测试是额外证据，不能用模型代替代码执行。

## 有限域与观察结果

Dispatch：一个公开 attempt、一个私人 attempt、一个可选 stop，互斥持有者为 none/public/private。检查公开占用可发现、等待者优先、失效后不提交。当前配置 79 个不同状态、120 次状态生成，搜索队列清空，最大搜索深度 9。

Playback：一个 owner、同一完整消息的两个 attempt、一次 scope 切换、两个候选 nonce/请求 scope、任意有限服务端回执持久化顺序；完整文本长度 3，第一个合成前缀分别取 3 或 2。完成回执真正执行状态变更、生成待持久化回执和接受记录；性质从这些状态推导，未用“安全布尔值=true”代替处理流程。两个当前配置各 528 个不同状态、1,489 次状态生成，队列清空，最大搜索深度 13。

这些是 TLC 的 **generated states** 与 **distinct states**，generated 包含初始状态和重复到达的后继；不能称作去重后的图边数。单初始状态下后继生成计数分别为 119、1,488。模型有循环和终止状态，关闭 deadlock 检查；不主张活性或无饥饿。TLC 使用 64 位 fingerprint，原始日志保留其碰撞概率估计。

| 负控制 | 必须暴露的反例 |
| --- | --- |
| `Dispatch-legacy-startup` | 先占 `MODEL_LOCK` → 私聊宣布/扫描 → 公开 handle 尚未登记 |
| `Dispatch-legacy-cleanup` | 公开提交 → 清 handle → 私聊扫描 → `MODEL_LOCK` 尚未释放 |
| `Dispatch-mutant-commit` | 先批准提交 → stop → 再 append 旧结果 |
| `Dispatch-mutant-no-priority` | 私聊宣布 → 公开请求仍抢先取得模型 |
| `Playback-mutant-last-write` | 完成回执已持久化 → 较旧 playing/pending 回执覆盖确认前缀 |
| `Playback-mutant-stale` | 错误 scope/nonce 的完成事件被接受 |
| `Playback-mutant-terminal` | stopped attempt 又收到完成事件并变成 completed |
| `Perception-mutant-late` | 停止、换scope或关闭相机后仍交付旧帧结果 |
| `Perception-mutant-owner` | 插件caller启动私人采集 |
| `Perception-mutant-consent` | 把设备声明拥有当成采集授权 |

以上十个case均是故意保留的历史/故障配置，不表示当前配置仍有这些漏洞。反例日志含具体变量值与动作序列；负控制若没有触发invariant violation，runner总结果失败。

Perception新增范围为两个session启动、最多两次role/appearance epoch改变、一个在途帧、相机启停与owner/plugin caller。模型不包括图像解码、OS授权UI、TTL真实时间、无限会话或网络/模型语义。实际manager有限轨迹/HTTP/算法证据分别见`tests/test_perception_state_space.py`、`tests/test_rebuild_http.py`与`review/tracking-real-check.json`，不能用TLC替代代码、权限或硬件执行。

## 独立的真实实现属性回归

`tests/test_formal_boundaries.py` 直接导入真实 `PlaybackTracker`、`merge_receipts`、`context_for`，并把当前 `server.py` 编译到隔离临时模块/数据根；不改生产源码，不调用真实模型或外部账号。

1. 在公开请求实际获得 `MODEL_LOCK` 和实际清理释放的位置暂停线程；让真实 `chat()` 并发请求，当前两个临界区均要求私聊成功。这里调用真实线程、锁及应用方法，不是只跑抽象模型。
2. 两个独立负控制只对内存 AST 副本去掉相应 `DISPATCH_LOCK`；相同调度必须暴露私聊 409。当前实现测试与负控制分别记录，避免“测试永远通过”的自证。
3. 枚举 11 种动作的全部长度 5 动作词：161,051 条、805,255 次实际模块操作；每个较短前缀也逐步检查。覆盖开始重听、playing/completed/stopped、切换、旧 onended、错误 nonce/owner/角色/外观/message、容量、前缀单调性。非随机抽样；nonce 本身由真实模块随机生成，不依赖某个固定随机 seed。
4. 对 pending/completed/重听 stopped 的全部 6 种提交顺序，真实 merge/context 保留已确认全文。
5. 对原角色完成、重听 playing 后切换的回执，在另一个角色 active 时，调用真实 `app.persist_playback()` 按全部 6 种顺序写 SQLite。验证原消息仍保留全文、最新状态为 stopped、没有写进新角色数据库、nonce 不落库。

未包含的内容：任意长轨迹、任意数量 owner、所有异常线程调度、实时模型服务的协作响应时间、过期/容量全部多 owner 情形、文件系统断电恢复、浏览器与渲染、实际扬声器播放、人类听到/理解、平台账号、Windows/CUDA 性能。其他测试即使覆盖部分上述项目，也应另附其证据，不能归到本模型结论里。
