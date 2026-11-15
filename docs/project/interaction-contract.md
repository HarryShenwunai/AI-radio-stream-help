# 单一现场场景契约 · 本地实现 v1

状态：技术作用域已获用户实施授权，B/C代码已实施，最终全量回归、真实媒体与故障回放通过（仅本地开发范围）。视觉方向尚未获最终认可，发布阻断。此文件替换旧“只读草案”，不把授权实施当作验收通过。

## 基线与边界

运行基线为 PR48 的 3af7f876ebe10d814e9c17a793c14879cfb4c7f8，tree dd09e659eff0b812ffd14412d38f12171147393f；隔离实现分支 impl/p9-approved-program 从管理增量 fa278f308e5d2930d4f2176e31549c12f04ac212 开始。最终源码、检查指纹和复跑结果见 [本轮报告](../validation/p9-first-loop.md)。旧报告仅作基线或失败对照。

产品目标仅Windows10/11 PC（RTX4060、32GB）；本轮实际开发环境是Linux CPU与Chrome，不能计为Windows通过。真实B站/OBS测试暂停，无部署、发布或平台发字。保留已有角色、光照、卫衣与固定持杯；不新增美术，不恢复放杯，不展示被拒3D。

## 一个任务，三个界面

本地原始文字 → 选择准备 → 生成候选 → 主播审核 → 单次批准 → 同一节目人物/字幕/实际音频 → 完成或停止 → 主播与节目端终态。

- 主播工作台保留问题、候选、批准、停止和可恢复失败；状态来自权威服务，局部更新不重建凭据、草稿、焦点和选区。
- room继续是私有布置预览，不自动改变发言身份，也不把手填字幕当批准回答。
- live-stage仅呈现当前授权快照及批准媒体。v1固定人物右侧、字幕左侧、透明底；不自动同步room的任意localStorage布置。布局功能连通不等于专业审美或用户认可。

默认现场互动不强制教材；严格答疑须明确允许公开的材料。不读取私人聊天/记忆，无主播音画输入时不假称听见或看见。演练保留local_rehearsal来源，不称真实观众。

## 已实现的接口与数据边界

复用现有job id、session、source、room_id、event_id、generation_id和状态机，没有并行任务队列或独立approval_id/playback_id。

| 字段/资源 | v1实现 | 边界 |
|---|---|---|
| scene_snapshot | 打开输出时冻结当前身份、外观、资源清单及运行库hash；批准时绑定同一快照 | 包含version、character_id、appearance_id、layout_revision=program-v1、layout=right、theme=carbon、asset、runtime_available、runtime_sha256、sha256；不可从独立预览偷换身份 |
| approval_revision | 明确批准时的状态revision | 不是外部审批凭证 |
| audio_sha256 | 完整WAV实际字节hash | 不是扬声器/观众收到凭证 |
| 音频预算 | owner可见audio_duration_seconds、playback_budget_remaining_seconds、failure_reason | 不进入节目内容；失败理由仅映射已知代码 |
| 输出资源 | /api/live-output的POST action scene/resource/runtime/poll/audio/receipt | Bearer只在头中；credentials:omit；资源名必须在冻结清单并匹配scene hash和实际字节hash，不是通用代理 |
| 私有资源 | 原/api/assets及运行库接口仍要求私有授权 | 不给节目页私有cookie；正式安装许可与Core读取校验保留 |

节目job投影采用显式白名单：id、session、event_id、room_id、source、origin、expires_at、state、delivered、text、generation_id、mode、scene_snapshot摘要、approval_revision、audio_sha256。快照摘要仅sha256/character_id/appearance_id/layout_revision；完整资源快照另由受限scene操作读取。未知新增字段不会自动公开。

禁止进入节目投影：question、material、topic、recent、私聊/记忆、完整模型上下文、草稿、凭据、client/heartbeat、任意本机路径。主播审核投影单独定义，不能把整个owner状态转发。delivered/viewer_received不作为观众凭证，当前viewer_received始终false。

## 状态与媒体事实

状态仍为generating → review → synthesizing → ready → claimed → playing → completed；另有cancelled/expired/failed。未经逐条批准不合成公开音频，不进入节目字幕。进程内既有作业记录范围内，重复事件、重认领和状态不匹配不能重播；不是跨重启或跨平台的绝对恰好一次保证。

playing回执必须晚于WebAudio建立且running以及audio.play成功；它仍只是本页启动事实。completed由本页ended后回执；回执丢失须持续显示未确认，不能被空poll改写成成功。源WAV、浏览器WebAudio捕获与未剪辑双端录像分别保留；浏览器录像无音轨，不等于系统声卡、OBS或观众收到。

非终态错误收口在当前单调时钟已达期限时归expired，未达期限仍failed；已有终态保持，不由是否先刷新status决定分类。停止撤销令牌/场次并清理媒体、字幕和口型。异步scene、audio及completed分别检查epoch/播放世代；旧成功/失败回包都不能恢复旧任务或覆盖新任务。字符/外观、话题/模式、主播讲解状态改变沿用已有失效链。加载人物不得占住轮询锁并阻断2秒消费者心跳。

## 时限准入与不能保证的部分

原30秒事件期限不变，包含生成、审核、TTS、准备和播放。服务端使用单调时钟，不能直接与浏览器Date.now相减。

完整PCM16 WAV先由既有验证器检查格式、实际帧数、采样率、声道、长度与体积；在ready、ready→claimed及audio交付三个边界要求：剩余秒数×采样率 > 实际帧数。相等也拒绝，丢弃音频并记录insufficient_playback_budget；无效音频为invalid_audio。已播放期间不把整段时长重复扣算。

这是“必然来不及则不启动”的必要条件，不是未知网络、审核和设备延迟下绝不截断的保证；未增加拍脑袋裕量或延长期限。完整长题与已有短问候分别保留，短题成功不能覆盖长题失败。当前CPU模型/语音性能可能导致较长问题被正确拒绝，产品实用性仍需任务验证。

## 主播更新与开销

复用已有可见页5秒core.refresh和core.on(change)，后端state仅加入受限live_output状态。BroadcastChannel只发changed提示，再读权威服务，不传内容/令牌，不当媒体凭证。无新增轮询、后台线程或产品依赖。兜底状态延迟仍可能约5秒，不能宣传即时或已有真人操作收益。

ONNX Runtime在native初始化前强制ORT_DISABLE_TELEMETRY=1（不能setdefault保留0），保留API关闭作为补充；覆盖owned backend启动和TTS/ASR入口。本轮模型测试在仅loopback的新网络namespace运行。该隔离与启动策略不是Windows全系统零网络证明。

## 验收与回退

旧版audio.play拒绝仍报playing、旧控制台不更新、旧完成回执丢失被覆盖、旧预算缺失、已知坏预算mutant必须被同一判据拒绝。开发样例为确定性音调和已有原始文字，真实模型/TTS另跑；两者均不是未见学习任务或观众证据。

固定失败条件：未批准输出、未知私有字段/资源泄漏、重复播放、停止/过期/换身份后复活、实际媒体失败却报完成、状态更新破坏输入、字幕遮挡手杯、源角色包改变。每项修复独立提交可回退；回退到旧版不等于旧安全问题已解决。

测试夹具的严格本机传输与资源hash保留；外站及重定向拒绝。大资源使用Playwright APIResponse传递以避免Python复制导致撞产品1秒门；产品超时不改。测试页收尾排空pending fetch仅为防context.route关闭重放，不可作为生产硬关闭/pagehide验收。原生HTTP、系统声卡、Windows、OBS、观众接收、独立视觉/声线和学习收益分别待验证。
