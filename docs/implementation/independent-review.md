# 第一轮独立 Agent 审查

日期：2026-11-12。由与实现者不同的 AI Agent `/root/independent_review` 设计验收、审查并执行测试，不属于独立人员 V&V 或 IEEE 认证。

结论：已审查范围内没有未修复的阻断项，可以继续本地开发。本结论不批准生产发布，也不代表直播、AR、MC 或自然相处体验已经验收。

## 实际执行

| 范围 | 命令 | 结果 | 证明边界 |
| --- | --- | --- | --- |
| Generation 生命周期 | `PYTHONPATH=src python -m unittest discover -s tests -p 'test_lifecycle.py' -v` | 15 通过 | 内存中的跨 scope、取消、并发、有界保留 |
| Zerolan 协议 | `PYTHONPATH=src python -m unittest discover -s tests -p 'test_zerolan.py' -v` | 27 通过 | 离线 UTF-8/NDJSON、DTO 和控制信封；没有上游服务 |
| 公开入口 | `PYTHONPATH=src python -m unittest discover -s tests -p 'test_live.py' -v` | 19 通过 | 合成事件、去重、TTL、队列界限；没有真实平台 |
| 私人 HTTP 与音频权限 | `PYTHONPATH=src python -m unittest discover -s tests -p 'test_phase1_http.py' -v` | 13 通过 | 实际 loopback Handler/SQLite，临时数据；生成与 WAV 是替身 |
| 前端音频竞态 | `node tests/test_voice_ui.mjs` | 8 通过 | 实际 app.js、受控 DOM/Audio/fetch；没有实际声卡或浏览器性能 |

独立执行合计为 74 项 Python、8 项 Node。父 Agent 的旧原型、浏览器或真实模型结果不计入这里。机器可读记录及被审源码哈希见 [phase1-independent-review.json](../../review/phase1-independent-review.json)。

## 发现与修复

1. 已完成的请求 ID 可带不同文本返回旧缓存答案，导致新输入被静默忽略。初次 HTTP 回归实际出现 `200 != 409`。父 Agent 将缓存/重试/重复 ID 的预检放在创建 generation 前，并校验原用户消息。复测冲突返回 409，而且原 generation 仍可朗读。
2. 公开事件 ID 的孤立 Unicode surrogate 会在去重哈希时抛 `UnicodeEncodeError`。公开入口实现者增加严格 UTF-8 校验，覆盖 ID、文本和 actor。新增回归验证拒绝后仍能处理正常事件。
3. 过大的整数时间戳会在 `math.isfinite` 抛 `OverflowError`。实现者捕获转换异常并返回固定 `invalid`。新增回归已通过。

没有通过删除失败用例或缩小断言掩盖这些问题。

## 审查确认的边界

私人 HTTP 的 channel、session 和权限来自服务端。伪造字段在开 SSE 和写库之前被拒绝。音频 generation 与 request 同时校验，自动语音内容绑定已完成的 assistant 记录；合成后再次核验，历史删除也会丢弃晚到音频。

registry、事件队列和去重记录有容量边界。协议适配器不执行工具或联网，不伪造旧端取消回执。公开事件模块没有导入私人数据库、角色设定、记忆、Cookie 或工具。前端使用 generation 序号及每个 Audio 自己的清理函数防止旧结果复活。

## 未解决检查

- Zerolan/Core、作者 GPT-SoVITS 分支和 MC 的真实握手仍待隔离运行。协议夹具通过不能关闭 G1 运行兼容阶段门。
- 公开入口仍是离线模块；配对凭证、真实 SDK 字段映射、专用公开模型上下文还未完成。不能把拒绝 `channel=live` 当成实际直播身份认证完成。
- 取消回执证明本地失效，不保证上游计算停止；网络等待还可能延迟释放模型锁。需实际测量提供方行为。
- 已播放毫秒与未听内容截断尚未实现。当前文字消息提交不证明相同音频已被听完。
- 目标设备的首声、p95、CPU/RSS/显存、OBS 掉帧和真实浏览器声音通路需要同机验收。合成时间回放不是实时负载与播出指标。
- B站、弹幕姬、OBS、微信、AR、MC 的账号、许可和真实环境仍需对应阶段处理；本次审查没有执行这些连接。
- 自然度、幻觉与长期相处效果需独立对话集及用户体验验收；模型替身不能证明质量提升。

后续先完成 G1 的实际提供方兼容和资源基线，再扩展真实入口。所有未完成项保留，不以文档或单测总数替代。
