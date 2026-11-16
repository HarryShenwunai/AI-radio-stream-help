# 本地演练准备：复跑与验收边界

本页仅描述现有 Windows PC 目标产品的准备入口与开发验证。真实记录来自 Linux/Chrome，不代表 Windows 10/11、RTX 4060、OBS、观众接收或声音自然度通过。hash-guard 已合入本地 `25b86ce562c3a76a76ea7975f6648aa59b68674d`；下方真实双题记录仍是旧产品 `34ecb9a64997d6a9953028bb919fe30caa1c3f70`，不能当新版本成绩。已记录的公开草稿57快照 `df9fa5431f9df4e670d01341151abcaa5cb3694b` / tree `f1a4769a6378410cf78da9c429b983be840bee26` 与本地25b目标树一致，但不是同一个Git提交；后续head以新收据为准。本地25b全9阶段检查通过：411源码指纹不变、196.428秒、964项Python回归；这是机械检查记录，不是性能、声音或产品完成标准。

## 入口与操作

在已配置现有依赖、模型/音色及获许可 Live2D 运行库的开发环境运行 `python -B app/server.py --no-browser`，用桌面 Chrome 打开终端给出的本机地址。在“平台连接”选择“本地互动演练”，已有演练可点“重新准备”；不要连接平台账号来替代本地开发验证。

1. 准备时消息输入禁用，没有 ingress、观众题目、回答生成、语音推理或播放。合格默认本地模型会真实构造、整文件 SHA、只预填公开 system，再初始化所选本地音色。未知本地权重只报 `local_provider_only`；API 配置只报 `configured_api`，不冒称远端服务验证或前缀已备妥。
2. 仅 ready 后加入未见过的问题，再点“准备回答”；阅读后由主播确认“播放这条回答”。演练里的自动点击验收不是人类认可，生成 WAV 也不是已播放。
3. 结束演练、换角色/外观、改变相关配置或公开上下文后，旧资格不可复用；须重新准备。重新准备保留当前已应用的公开材料/背景，取消旧任务；原材料文件不覆盖。私人会话不进入公开上下文。

现有 owner/会话校验仍适用于 `connectors/bili/rehearsal` 的 `start/prepare/message`、`bili/reply`、`bili/approve`、`bili/stop`；没有新增 HTTP 入口或权限。节目输出令牌不授予后台操作权限。

## 固定判据

| 项目 | 必须保留的判据 |
| --- | --- |
| 准备 | 模型身份/真实 capabilities 与当前 scope 相符；准备前无题目及推理；不把构造或 system eval 当回答。 |
| 哈希 | 每次仍完整读取/更新 SHA，未缓存、跳过或缩小真实权重。仅循环快查移除重复 scope I/O；hash 前后、prefix/voice/finish 全核保留。四参 Python 入口兼容普通 callable。 |
| 撤销 | owner stop、配置 A→B→A、场次和角色变更撤销 ticket/epoch；下一块快查拒绝，旧 finish 不得晚变 ready。阻塞 read/native 调用不能承诺被抢占。 |
| 外部文件 | 没有 owner 事件的持久配置/文件变化在 hash 后 stat/full 边界拒绝，不能声称下一块发现。瞬时外部 ABA、同 stat 伪装不在已证明范围。 |
| 输出 | 保留原 1 秒资源/poll 门、30 秒事件期限与“剩余时间严格足以播完完整 WAV”条件；过期/预算不足不得开播或恢复后补播。 |
| 实际完成 | 同一任务字幕、可见嘴图层、实际浏览器音频、play/ended 与两端 completed 对应；终态清除。`local_preview/delivered=false` 不表示观众收到；network 红不能改绿。 |

## 已有证据与尚未证明

34ec 在正常可见绘制下的两题真实记录均命中 `insufficient_playback_budget`，play 为 0：

| 问题标识 | 生成秒 | 合成秒 | WAV秒 | 三项顺序下界秒 |
| --- | ---: | ---: | ---: | ---: |
| missing_step | 19.137643 | 5.662604 | 6.527292 | 31.327539 |
| derivative | 20.242033 | 7.828094 | 7.278625 | 35.348751 |

该下界已超过 30 秒，还未计人工审核、传输和其他等待。报告 functional/network/overall 均 false，两个实际 WAV 不构成播出或声线验收。生成期暂停 rAF 是改变绘制负载的诊断条件，不是产品修复或正常绘制性能通过；不能用它替换上述失败。

新 hash-guard 的假文件验证：2 块与9块实际 read/SHA 字节完整、摘要与输入不变，full scope 均12次；旧每块 full scope 及回退 mutant 被调用门拒绝。它只证明消除了重复工作，**真实2.5GB哈希提速及完整演练收益尚未测量**；31秒阶段还含 I/O、SHA、观测器和调度，不能全部归因 scope。

开发证据索引（本地相对路径，不随公开源码发布；第三方复核须取得相应私有证据或自行复跑）：

- [正常绘制原报告](../../.build/audience-root/draw-diagnostic-normal-terminal-v2/result.json)、[暂停绘制诊断原报告](../../.build/audience-root/draw-diagnostic-suspend-generation-terminal-v2/result.json)：原输入、各阶段、WAV哈希、0播放与终态。
- hash-guard 隔离测试工作树的 [调用计数/摘要记录](../../../preparation-hash-fastpath/.build/hash-guard/focused-report.json)、[旧坏路径拒绝](../../../preparation-hash-fastpath/.build/hash-guard/per-chunk-mutant.json) 和 [针对性检查](../../../preparation-hash-fastpath/.build/hash-guard/targeted-checks.json)。这些不冒充真实性能报告。

## 复跑命令

不加载模型的回归，先在仓库根目录执行；类型/架构检查按现有质量工具环境运行，不为复跑全局安装依赖：

```sh
PYTHONPATH=src:tests python -B -m unittest test_public_preparation_hash_guard test_public_runtime_bootstrap test_public_preparation test_public_prefix test_public_rehearsal_preparation test_compute_runtime test_formal_boundaries.FormalSourceInterleavingTests
python -B scripts/check_architecture.py
```

对应[哈希/撤销坏例](../../tests/test_public_preparation_hash_guard.py)、[四参兼容/身份边界](../../tests/test_public_runtime_bootstrap.py)、[旧 ticket 晚完成反例](../../tests/test_public_preparation.py)与[实际入口回归](../../tests/test_public_rehearsal_preparation.py)。以上是 fake/local 验证，不是声音或真机成绩。

真实复跑须在质量检查结束后的独占资源窗口，固定源码/工具/模型/材料 hash。原 prepared command 位于测试工作树 `.build/production-readiness/draw-diagnostic-v2/run-normal-prepared.sh`，其同目录 `dependencies.json` / `frozen-source.json` 保留当时版本。已核 parser：harness 使用 `--project-root` / `--expected-project-sha`；namespace launcher 使用 `--evidence FILE -- COMMAND`。

必须用原 `isolated_test_launcher.py` 创建 only-lo user/net namespace，不直接启动裸 harness。launcher 在产品测试根 `.build/p9-root/playback-budget/isolated_test_launcher.py`，不是新下载的工具。它是Linux开发验证包装，不是Windows验收方法；所有路径和解释器须按已有收据核对。

下面变量均为本机已核对的路径/实际冻结SHA，`NEW_OUT` 及其新 sibling evidence 文件都必须不存在，不能把 evidence 放进 `NEW_OUT` 而使 harness 的 fresh-output 条件失效：

```sh
NEW_NAMESPACE_EVIDENCE="${NEW_OUT}.ns.json"
test ! -e "$NEW_OUT" && test ! -e "$NEW_NAMESPACE_EVIDENCE" || exit 1
PYTHONDONTWRITEBYTECODE=1 ORT_DISABLE_TELEMETRY=1 \
PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS" \
"$LAUNCHER_PYTHON" -B "$ISOLATED_TEST_LAUNCHER" \
  --evidence "$NEW_NAMESPACE_EVIDENCE" -- \
  "$RUNTIME_PYTHON" -B "$HARNESS/tests/production_draw_diagnostic_browser.py" \
  --draw-mode normal --project-root "$PROJECT" --expected-project-sha "$FROZEN_PRODUCT_SHA" \
  --chrome "$CHROME" --avatar "$AVATAR" --runtime-dir "$RUNTIME" \
  --model-dir "$MODELS" --voice-dir "$VOICES" --out "$NEW_OUT"
```

`PROJECT` 必须是独立、真实且干净的目标checkout。复核旧结果须取得34ec源码/证据；开发机已有独立baseline，不能在活动诊断根切换版本或拿25b结果冒称34ec。复跑公开df9时预期SHA应填实际df9，而不是本机25b；还要记录同tree映射。拿不到原源码或匹配harness时保持未复现，不复用旧 WAV/截图。原始 Trace/NetLog 可能含 SDK 与临时授权信息，仅留本机；分享另导出审阅副本。

## 停止与回退

先“结束演练”，确认资格和旧输出已撤销；正在执行的 native 操作可晚返回，但不能晚发布 ready。

- 本地Git库确实拥有单独guard提交25b时，可单独 `git revert 25b86ce562c3a76a76ea7975f6648aa59b68674d`。
- 公开df9是以公开35cc为父提交、合并14个文件的不同提交；直接整体revert会撤掉准备入口等改动，**不是只回退guard**，也不保证公开clone拥有本地25b对象。
- 只回退guard可审查[精确三文件补丁](public-rehearsal-hash-guard.patch)：它是原字节 `git diff34ec→25b`，使用反向应用，仅涉及server、typed preparation与新增guard测试。已在副本上验证反向恢复34ec三文件内容；旧准备入口、此前身份修复、材料和失败证据不动。

```sh
git apply --check --reverse docs/validation/public-rehearsal-hash-guard.patch
git apply --reverse docs/validation/public-rehearsal-hash-guard.patch
```

只在三个目标文件仍匹配且无待保留本地改动时操作；check失败须停下审查，不强制套补丁。反向后新增guard测试文件被删除，改跑既有bootstrap/preparation/prefix/rehearsal/compute/formal回归与架构检查，并记录真实版本；旧每块scope开销会恢复。不要用reset、删除模型/音色/数据或放宽时限制造通过。代码回退与Windows、独立审美/声音/学习收益验收分别记录。
