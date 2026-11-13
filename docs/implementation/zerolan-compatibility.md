# P0：Zerolan 离线协议兼容样例

状态：已实现本地适配与27项单元测试，2026-11-12。没有连接或运行上游服务。

目标是验证原型可以逐步采用契约适配，不先替换现有模型或共享会话。此模块使用Python标准库，不依赖Pydantic、Flask、WebSocket客户端、模型权重或账号。

## 已核实的契约

| 对象 | 静态源码中的格式 | 本轮处理 |
| --- | --- | --- |
| LLMQuery | `id`、`text`、`history`；Conversation有`role/content/metadata` | 每次构建显式分配UUID；复制受限history，不读取任何数据库 |
| LLMPrediction | `id`、`response`、`history` | 验证已知字段和文本；不把返回history自动写入会话 |
| Core stream | `/llm/stream-predict`逐个输出JSON并附加LF | 按行增量解码，不能把任意网络chunk当成一个JSON |
| ZerolanProtocol | `protocol/version/message/action/code/data`，版本`1.1` | 检查完整信封和有限发现/元数据动作；没有网络发送 |
| TTSQuery | `id/text/text_language/refer_wav_path/prompt_text/prompt_language/cut_punc/audio_type` | 仅登记字段；本轮未实现TTS适配 |
| TTS二进制接口 | 主仓库语音客户端依赖作者专用GPT-SoVITS实现 | 沿用现有Kokoro；不把DTO验证当作音频服务已兼容 |

`AbstractModelQuery`和`AbstractModelPrediction`在已读版本使用`Field(default=str(uuid4()))`，默认值于类定义时计算。适配请求显式传入新UUID；上游预测ID仍可能重复，不应被当作唯一的跨频道关联标识。

LLMPrediction的`response`究竟是增量或累计文本，还须对选定模型实现进行运行验证。本轮返回原始预测对象，不将字符串擅自拼接成最终回复。

## 公共API与限制

实现位于[src/companion_runtime/zerolan.py](../../src/companion_runtime/zerolan.py)。

- `NDJSONDecoder(...).feed(bytes)`返回已完整解码的对象；`finish()`检查EOF。
- `build_llm_query(text, history=(), request_id=None)`构造显式ID的请求。
- `validate_prediction(value)`与`decode_predictions(chunks, ...)`验证本地提供的预测字节。
- `build_control(...)`与`validate_control(...)`只处理发现/元数据控制信封。
- `compatibility_report()`明确返回未连接、未支持取消转发、未执行工具的状态。

默认帧上限65536字节、单流总量2000000字节。总量包含空白；帧上限不含LF，含CR。支持CRLF、空行、跨中文字节拆包和多帧合包。完整末帧可省略LF；EOF残缺JSON/UTF-8报错。重复键、非对象、NaN/Infinity和过大数据被拒绝。出错或结束后禁止继续复用同一解码器。

允许的控制动作来自已读源码中的常量与处理器：

| 动作 | 证据 | 范围 |
| --- | --- | --- |
| `client_hello` / `server_hello` | Playground桥接与Unity协议客户端 | 格式兼容；未建立握手连接 |
| `query_gameobjects_info` / `update_gameobjects_info` | Playground桥接 | 仅元数据；未访问设备场景 |
| `koneko.client.hello` / `koneko.server.hello` | MC dev枚举和消息构造 | 枚举格式检查；不声称双方实际交换全部枚举 |
| `koneko.server.fetch_instructions` / `koneko.client.push_instructions` | MC dev插件与Robot MC桥接 | 仅技能描述发现；不注册或执行工具 |

`koneko.server.call_instruction`、`play_speech`和取消动作不在P0允许范围。调用者传入的`allowed_actions`只能收窄默认集合，不能开启这些动作。已读1.1信封没有跨频道generation取消字段，本适配器明确不支持上游取消转发，不能伪造成功回执。

类型和版本校验不是身份认证。调用者必须在构造请求前选择经授权的频道history。元数据中出现工具名也不代表授权。消息`data`只复制为JSON对象/数组/null，不会交给执行器。模块无网络、文件访问、日志内容记录或工具副作用。

## 本地离线回放

在仓库根目录执行；全部输入是合成数据：

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_zerolan.py -v
```

该命令实际通过27项测试。中文多帧用例遍历所有单次切分点，并额外逐字节输入。测试还覆盖非法版本、未知动作、EOF残帧、总量限制、新请求ID和越权字段。

最小DTO回放可直接执行：

```sh
PYTHONPATH=src python - <<'PY'
import json
from companion_runtime.zerolan import build_llm_query, decode_predictions
q = build_llm_query('离线合成测试')
values = [{'id': q['id'], 'response': x, 'history': []} for x in ['你', '好']]
raw = b''.join(json.dumps(v, ensure_ascii=False).encode() + b'\n' for v in values)
received = list(decode_predictions(raw[i:i+1] for i in range(len(raw))))
assert received == values
print({'frames': len(received), 'source': 'synthetic offline fixture'})
PY
```

此回放未启动Flask、Unity、GPT-SoVITS、Mineflayer或WebSocket。它证明的是已读DTO的本地解析与边界处理，不是上游部署连通、语音质量、真实延迟或完整Q04验收。

## 事实、判断与未知

**已核实事实**：上述字段、逐行JSON输出、动作常量和请求ID默认写法来自本地保存的固定版本源码。来源查阅日期为2026-11-12。

**可信但未运行验证**：作者文档指定的GPT-SoVITS fork可以提供该体系预期接口。未下载或运行该fork，不声称音频兼容已通过。

**工程判断**：先测试有限适配比一次性迁移更容易保留原型与回退。本地通过不确定真实迁移成本，后续仍需兼容样例和目标设备数据。

**未知**：上游各LLM实现的增量/累计语义、长流断连行为、实际ID回传关联、Unity取消和音频乱序、MC版本匹配、AR依赖许可，以及目标设备性能。

下一步在用户选定硬件和运行入口后，以固定commit运行实际LLM/TTS契约样例。取消、认证、频道隔离和播放状态继续由内部生命周期协议负责，不能靠1.1信封补猜。

## 已核实来源

固定版本与文件blob标识详见[evidence/zerolan-source-refs.json](../../evidence/zerolan-source-refs.json)。本轮未重新联网。

- [zerolan-data LLM DTO](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/pipeline/llm.py)
- [zerolan-data基础ID](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/pipeline/abs_data.py)
- [zerolan-data 1.1信封](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/protocol/protocol.py)
- [zerolan-data TTS DTO](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/pipeline/tts.py)
- [Core LLM HTTP服务](https://github.com/AkagawaTsurunaki/zerolan-core/blob/baefa0f78abe756a91ca231fc2f6439b46ebe266/llm/app.py)
- [Robot Playground桥接](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/services/playground/bridge.py)
- [Robot MC桥接](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/services/game/minecraft/app.py)
- [MC dev协议插件](https://github.com/AkagawaTsurunaki/KonekoMinecraftBot/blob/b582ef3073bcb62c2fdfea7a9bfd9dffd472d7bf/src/web/zerolanPlugin.ts)
