# 通信适配器（2026-11-12）

已实现可运行的 OpenLive 接收客户端与主人私聊桥接内核。验证使用本机 HTTP/WebSocket 对端和明确标识的 AstrBot API 替身；没有登录、连真实房间、发微信、公开播出或验证平台准入。来源和 Git blob 标识见 sources.json。

## B站：官方 OpenLive → 本机预览

复用现有 LiveIngress，不把弹幕交给私人 chat()、角色记忆或工具。入口固定单房间，公开事件只保留 room_id、msg_id、msg、timestamp 和不作为认证身份的 open_id。API 固定 https://live-open.biliapi.com；服务端返回的长链必须是 HTTPS 对应的 wss、443 端口及 chat.bilibili.com 域内。拒绝 URL 用户信息、重定向和任意服务地址。

实现 start/end/20秒项目心跳、30秒 WS 心跳、原样认证体、认证结果核验、有限指数重连。raw/zlib/Brotli 包最多256KiB、解压深度2、单包256事件；Brotli固定1.2的有界解码API。队列复用200条、8秒过期、4096条去重缓存；满时拒绝新增而非悄悄扩容。断线重新start前尽力end旧场次，end失败单独计数。没有平台文字回发、OBS或广播出口。

可选安装：`python -m pip install -r src/companion_runtime/connectors/requirements.txt`。

`PYTHONPATH=src python -m companion_runtime.connectors` 默认 dryrun，不开网络。主人自行配置后，可显式执行 `--connect --config /绝对路径/owner-openlive.json`。配置严格为 access_key_id、access_key_secret、整数 app_id、anchor_code、字符串 room_id 五项；凭证文件不得提交Git或交给模型。该命令会连接真实平台并打印公开弹幕，仅在主人授权连接后执行。本轮未执行。

服务集成：构造 `BiliOpenLive(OpenLiveCredentials(...), room_id)`；`await client.run(stop_event)`；`client.ingress.pop()` 非阻塞读取 PublicEvent；`client.status()` 返回脱敏统计。默认导入不连网、不下载、不创建账户。连接器只有一个网络任务，不为每条消息创建推理任务。真实RSS/CPU/p95尚未测，不据本机mock耗时声称生产性能。

## 微信：AstrBot weixin_oc → 独立私聊桥接

`WechatBridge(owner_origin, character_id, audio_root, token=None)` 固定一个主人 FriendMessage origin 和角色UUID。每个绑定使用独立随机token，既不是模型API key，也不是微信token。只接收指定来源的文本；附件URL、发件人自称权限、任意收件人、公开scope和角色ID字段都不透传。公开 LiveIngress 与本桥接不共享队列或私人数据。

根HTTP层契约：

| 路径 | 插件Bearer凭证 | 请求/响应 |
| --- | --- | --- |
| POST /api/connectors/wechat/inbound | 必须 | `{platform,origin,event_id,text,timestamp}` → `{status}` |
| POST /api/connectors/wechat/claim | 必须 | `{}` → `{item: object 或 null}` |
| GET /api/connectors/wechat/audio/UUID | 必须 | 仅已领取消息关联的 WAV 字节 |
| POST /api/connectors/wechat/ack | 必须 | `{id,status}` → 状态；status仅handed_to_adapter或failed_or_uncertain |

插件凭证不得获准调用批准、配对、切角色、模型设置等浏览器接口。HTTP层还需限制本机监听、Host/Origin、请求体上限，禁止跨域读密钥；本模块不会自行增加监听端口。`pairing_token` 仅在主人明确配对时显示，不加入普通状态。

`pop_inbound()` 提供固定角色的私有输入，由根服务按该角色固定数据库与generation处理。`stage_audio(WAV bytes)` 接收已有TTS字节，不能传路径或URL；限制8MiB、120秒、PCM16、8–48kHz、1–2声道。`preview_reply(text, character_id=..., generation_id=..., audio_id=None)` 先生成本机预览。根服务获主人明确批准后调用 `approve(id)`，插件才可claim（可手工逐条批准；或由主人预先启用仅此origin的自动回复）；插件 enable_send 默认false，需主人另行打开。不能将token持有本身解释为批准外发。

私聊音频在POSIX使用目录0700/文件0600，拒绝符号链接及内容篡改；Windows ACL仍需目标机验收。取消会立即清理未发送资产，已claimed无法承诺撤回，ACK或TTL后清理本机文件。claim只领取一次；不对失败/不确定结果自动重发，避免重复微信。ACK最多表示交给适配器，永不伪造送达回执。停止generation/切角色时根服务必须 `cancel(generation_id=...)` 或销毁旧桥接；已交给外部适配器的发送无法撤回，需显示不确定状态。队列和音频临时资产有界、120秒过期；进程重启不恢复外发。换绑定/服务关闭时根服务须调用 `bridge.close()` 撤销旧对象并清理本机文件；它不能撤回外部发送。重启后只扫描最多4096项并清理超过TTL的UUID.wav孤儿，每30秒内至多一次；目录异常超量拒绝新增音频。没有静默重放或永久保存聊天副本。

安装插件见 plugins/astrbot_companion_bridge/README.md。微信原生语音条明确不支持；可用音频文件附件降级，不能展示成原生语音已完成。入站本桥只处理文本，微信语音转写由用户现有AstrBot链路决定，尚未账号验证。

## 验证与未完成

tests/test_connectors.py 包含真实loopback HTTP/WS签名、认证、断线重连、双心跳、end清理、去重/错房间、压缩炸弹和主人桥接音频文件往返；AstrBot Context是明确替身，没有真实外发。可选依赖缺失的测试标SKIP，不能当执行通过。

真实B站准入/当前账号与房间、真实AstrBot安装和微信context有效期、长时间重连、目标Windows网络与资源、原生微信语音、具体copyliu弹幕姬插件均未验收。本轮选择OpenLive一条路线，不将通用消息桥冒称已实现某弹幕姬SDK。
