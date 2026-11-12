# Generation 生命周期实现

日期：2026-11-12。代码仅管理本机生命周期，不建立平台连接。

## 已实现

- HTTP 层先通过鉴权并产生可信 `Scope(channel, session_id)`，再调用 registry。
- 每次 `begin` 分配新 UUID；同一 request 的重试也属于新的生成尝试。
- 同一 scope 的新生成会使旧结果失效。其他频道或会话不受影响。
- `complete` 结束生成阶段，但保留 TTS、播放检查所需的有效 generation。
- `cancel` 同时检查 scope 和提供的 ID；已完成媒体仍可取消。
- `resolve` 和 `is_current` 只能取得当前、未取消、未过期的结果。
- 存储有界，运行中和仍有效的其他 scope 不为腾缓存而被取消。

## 关键接口

`GenerationRegistry.begin(scope, request_id)` 返回 `GenerationHandle`。
handle 包含 `generation_id`、`id` 别名、`request_id`、`scope`、`cancel_event`。

`current(scope)` 或 `resolve(scope, generation_id=..., request_id=...)` 返回当前 handle 或 `None`。
提供两个 ID 时，必须同时匹配。`is_current(handle)` 还核对对象身份。

`complete(handle)` 返回是否成功完成当前 generation。
它不会延长已完成媒体的保留期，也不会让旧结果复活。

`cancel(scope, generation_id=..., request_id=...)` 返回：

| 结果 | 含义 |
| --- | --- |
| `accepted` | 本机 generation 及媒体许可已失效 |
| `already_done` | 此 scope 中保留的 generation 已经失效 |
| `not_found` | 不存在、已清理、已过期，或属于其他 scope |

至少提供一个 ID；不支持从未知请求中隐式“取消所有”。

## 边界与恢复

默认最大 256 条记录。完成后保留 600 秒媒体许可；取消/替代的状态也保留最多 600 秒。
600 秒是本地初始资源策略，需在目标设备验收后调整，不是平台限制。
运行中的 generation 不按该缓存期限自动终止。

到期完成结果会失效；容量压力可提前清理已经取消的 tombstone。
因此重复取消的 `already_done` 不是永久承诺；清理后返回 `not_found`。
所有非当前 ID 都必须拒绝媒体投递，不论 tombstone 是否还存在。

缓存满且所有记录仍有效时，`GenerationCapacityError` 明确拒绝新 scope。
同一 scope 的显式新生成仍可替代旧生成，不驱逐其他有效会话。

registry 使用 `RLock` 串行化转换。媒体检查到提交仍需调用方协调锁或再次检查。
持有句柄不是鉴权，也不能让“检查通过”与之后的数据库提交自动原子化。
`cancel_event` 是协作信号，不能证明不可取消的模型或 TTS 已停止计算。
输出端必须检查 generation；前端仍要先静音并清理队列。

当前状态仅在进程内。重启丢弃全部 generation，不允许恢复旧播放许可。
尚未验证真实提供方取消、跨进程播放确认和未听内容截断。

## 本地测试

在项目根目录运行 `PYTHONPATH=src python -m unittest discover -s tests -p test_lifecycle.py -v`。
测试使用合成 scope、假时钟和线程同步；没有模型、账号、游戏或公开播出操作。
覆盖跨频道/会话取消、晚到完成、并发替代、对象伪造、重复取消、完成媒体过期及容量边界。
