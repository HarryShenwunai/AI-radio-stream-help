# 日常协助与可确认提议

更新：2026-11-12。模块：[assistance.py](../../src/companion_runtime/assistance.py)。它实现本机结构化提议、确认/拒绝/取消、旧约定衔接和 CSV 统计，不包含外部日历、购物、消息或游戏控制执行器。

## 数据与 API 合同

宿主先验证 owner、当前角色及 `expected_character_id`，再使用该角色 catalog 返回的数据库路径构造：

```python
store = AssistanceStore(
    database=profile_database,
    role_scope=character_id,
    provider=actual_provider_or_none,
    provider_kinds={'dinner', 'brainstorm'},
)
```

建议每个 profile 缓存实例。模块不会读取私聊记录、长期记忆、屏幕或其他角色文件。角色 UUID 与数据库内 metadata 绑定，拿另一角色 UUID 打开同一库会拒绝；本机路径由宿主选择，不能接受 HTTP 上传的路径。

提议包含：

```json
{
  "request_id": "client-stable-request-id",
  "action_id": "server-generated-uuid",
  "role_scope": "character-uuid",
  "kind": "schedule",
  "summary": "吃晚饭",
  "inputs": {"title": "吃晚饭", "due_at": "2026-11-12T19:00:00+00:00", "notes": ""},
  "permission_scope": "local_schedule",
  "status": "proposed",
  "source_evidence": [{"source": "user_input", "sha256": "computed-digest", "observed_at": "UTC timestamp"}],
  "result": {"external_actions": false},
  "error": null,
  "created_at": "UTC timestamp",
  "updated_at": "UTC timestamp"
}
```

示例时间仅展示字段格式；实际新提醒必须在当前时间后 1 秒到 7 天内，时间必须带时区。`permission_scope` 由模块固定派生，用户和模型不能提高权限。

| 方法 | 输入 | 作用 |
| --- | --- | --- |
| `create(request_id, kind, inputs)` | 以下白名单字段 | 创建提议；同 request_id/相同规范化输入返回原提议，不重新调用 provider；不同输入返回 409 |
| `get(action_id)` / `list(limit=50)` | 当前角色范围；列表 1–100 | 获取真实持久状态 |
| `decide(action_id, decision)` | `confirm` / `reject` / `cancel` | 确认、拒绝、取消；相同终态重试幂等，不复活已拒绝/取消项 |
| `cancel_generating()` | 无 | 切换角色/停止时取消该角色在途建议，协作发出 Event；迟到结果不能复活 |
| `set_proactive_paused(bool)` | 真布尔值 | 暂停主动联系与当前 pending/quiet 旧约定；恢复主动联系不自动恢复旧约定 |
| `cancel_legacy_task(task_id)` | 正整数 | 取消原 tasks 行及关联提议，已 completed 拒绝改写 |
| `snapshot()` | 无 | `proposals/proactive_paused/legacy_tasks/capabilities/external_execution_enabled` |

宿主建议 owner-only 路由为 `/api/assistance/proposals`、`/decision`、`/pause`；实际 HTTP 路由、角色切换锁与前端联调由服务端/前端负责人集成，模块测试不替代这些验收。

## 六类输入与真实能力

| kind | inputs 字段 | 实际行为 |
| --- | --- | --- |
| `schedule` | `title` 1–100字、带时区 `due_at`、可选 `notes` ≤2000字 | 先提议；明确 confirm 后原子创建一个本机 reminder；无外部日历写入 |
| `outfit` | `query` ≤2000字、可选 `context` ≤6000字 | 仅显式配置真实 provider/capability 后生成；文本上下文不冒充看过照片、天气或衣柜 |
| `dinner` | `query/context` 同上 | 真实 provider 的建议；不下单，不虚构库存或用户偏好 |
| `brainstorm` | `query/context` 同上 | 真实 provider 生成点子，不执行工具 |
| `data_analysis` | `csv_text`、可选 `delimiter`（逗号/分号/tab）、`filename` | 本机纯 CSV 解析与真实数值统计，无模型、公式求值或任意代码 |
| `game` | `query`、非空 `context`、`game` ≤120字、可选 `mode` ≤120字 | 要求真实 provider 显式声明此能力；只依据输入上下文，无隐式读屏、遥测、操控或“顶级队友”结论 |

其他字段拒绝；例如购物令牌、外部日历参数、执行代码和自定义 permission 不会进入执行路径。无 provider 或该 kind 未获配置时，保存 `status=unavailable`、空建议与明确原因，不能填固定模板冒充智能。

Provider 签名为 `(AdviceRequest, threading.Event) -> ProviderReply`。请求仅包含本次 `request_id/role_scope/kind/inputs`；返回 `ProviderReply(summary, provider_id)`。调用方必须提供真实模型适配器、有限网络/模型期限并响应取消 Event。模块不强杀不合作的 provider；它会阻止取消/重启后的迟到回复覆盖状态。多模态感知、游戏上下文来源与用户授权由各自模块提供，不能从本接口推定存在。

建议类 confirm 仅表示接受本机建议；`permission_scope=read_only`。日程为 `local_schedule`，SQLite 同一事务写 tasks 与 confirmed 状态，触发器/磁盘失败时同时回滚，重试不会重复创建。CSV 的 confirm 也不导出文件或执行代码。

## 状态、迁移与恢复

状态为 `generating/proposed/confirmed/rejected/cancelled/unavailable/failed`。只有 proposed 可确认/拒绝；generating/proposed/confirmed/unavailable/failed 可取消，confirmed 日程会取消关联任务。已完成任务不能改写为取消。模型失败只存 `provider_failed`，不把异常里的密钥/路径写进 UI 或事件表。

同后端进程的多个 Store 实例共享运行 epoch 与取消 Event；单后端重启将旧 epoch 的 generating 标为 failed/interrupted_on_restart，不重放模型或外部操作。proposed 保留待确认，confirmed 本机日程保留原 task。这里假设桌面应用只有一个拥有 profile 的后端；不支持两个独立后端同时拥有同一数据库。全局 active-role 校验与角色切换锁仍是宿主职责。

`migrate_connection(conn)` 为增量、可回滚迁移，不使用会隐式提交调用者事务的 `executescript`：

- 原 `tasks` 新增 `assistance_action_id` 与唯一索引，旧任务不删除或重建。
- 原 `messages` 新增可空 `task_id`（删除任务时置空）；旧消息全部保留 NULL，不从文字/时间猜关联。
- 服务端 scheduler 新建 reminder 消息时写真实 task_id；state 可附关联 action_id，使新 UI 从具体提醒卡取消约定，不重建旧任务管理表。
- 备份恢复若重建 task IDs，必须显式映射或将消息关联置空，不能套用旧 ID。
- 新增 proposals、events、controls 与 role metadata 表；日志仅记录 ID、状态、时间，不记录原始 CSV、provider 异常或令牌。

最多同时 200 个 generating/proposed 待决项；确认/拒绝/取消会释放额度。列表有界，历史建议是用户数据，当前不会自动删除历史。暂停是对当前旧约定的明确操作；恢复不静默重启它们。用户之后明确确认的新本机提醒属于新的授权。

## CSV 边界与统计含义

上传上限 256 KiB、5000 数据行、32 列、单格 2048 字符；表头必须唯一非空。支持引用的分隔符/换行与 UTF-8 BOM，行宽不一致、损坏引号、空数据或越界直接失败。

每列返回缺失数、数值数、非数值数、公式形似单元格数以及数值子集的 min/max/sum/mean。数字使用 Decimal、34 位有效数字；空格修剪后判断，NaN/Infinity/超大指数按非数值计，聚合不会变成 JSON NaN。混合列只统计有效数值子集，报告明确方法，不把它当完整业务分析。数字结果以十进制字符串表示，避免 JSON 浮点丢精度。

公式、Python 字符串和 CSV 内容从不求值。原始单元格不持久化，只保存上传 SHA、字节数、文件显示名及统计；表头会出现在统计中。没有文件路径读取、网络上传、依赖安装或代码沙箱执行。

## 已运行检查与待验收边界

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_assistance.py' -v
.build/quality-venv/bin/python -m mypy
python scripts/check_architecture.py
```

29 项模块测试已运行通过，包含真实 SQLite 迁移、事务故障回滚、十线程确认只建一项、实际子进程突然退出后的恢复、取消迟到结果、跨角色访问拒绝、27 种三步决策顺序及 CSV 边界/真实统计。provider 在这些模块测试中为显式受控替身，不能作为真实模型质量证据。

模块已进入 strict typing；架构 A07 与故意违规 fixture 检查直接网络、私聊模块和执行工具不能进入 assistance。它们是有界工程回归，不能证明完整 Python 程序或任意 provider 的行为。真实 HTTP/UI、真实建议质量、目标游戏场景、Windows/4060 和长期体验仍须独立验收；目前无“顶级队友”或专业分析基准通过结论。
