# Zerolan五仓库设计比较

查阅：2026-11-12。阅读了五个README和41份实现、配置或许可快照，并额外检查MC的dev分支。没有运行上游、加载其模型、打开摄像头或加入MC服务器。

## 总体判断

Zerolan比当前原型覆盖更多设备、展示和工具场景。最值得借鉴的是**事件驱动编排、统一模型管线、独立展示层、独立游戏执行器**。当前原型的优势是已经有可运行的简单本地闭环、明确的停止/重试和记忆关闭操作。

推荐先做兼容适配和共同验收，而不是立即把已有代码全部替换。自然相处、权限隔离和可打断语音必须独立验证，不能从功能数量推导质量。

## 五仓库各做什么

| 仓库与读取版本 | 源码确认的职责 | 对本项目的价值 | 采用条件 |
| --- | --- | --- | --- |
| [ZerolanLiveRobot](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot) main `aad29d093295` | 事件编排；ASR/LLM/TTS管线；B站、OBS、展示和工具连接 | 参考控制面、事件和管线拆分 | 增加有界调度、会话分区、跨端取消与权限门 |
| [zerolan-core](https://github.com/AkagawaTsurunaki/zerolan-core) main `baefa0f78abe` | 按服务包装本地模型；Flask HTTP；LLM等能力接口 | 作为可选模型提供方，不把模型绑定到产品UI | 核对请求字段、流式帧格式、模型ID、TTS特殊接口与资源预算 |
| [zerolan-data](https://github.com/AkagawaTsurunaki/zerolan-data) main `647157ddfe04` | Pydantic模型；管线Query/Prediction；JSON+WS协议1.1 | 契约优先、生成测试夹具与跨语言映射 | 包装版本、作用域、关联ID、取消与严格验证，不能只依赖类型名称 |
| [ZerolanPlayground](https://github.com/AkagawaTsurunaki/ZerolanPlayground) main `fb23d1ed7345` | Unity/Vuforia AR、Live2D/3D、HTTP取资源、WS控制 | 独立呈现端，可作为后续AR客户端 | Unity 6000.0.51f1；缺失依赖/素材与许可逐项补齐；音频中断和顺序验证 |
| [KonekoMinecraftBot](https://github.com/AkagawaTsurunaki/KonekoMinecraftBot) master `6954c50f2d8d` / dev `b582ef3073bc` | Mineflayer+FSM、技能/指令与遥测；dev增加Zerolan桥接 | 保留确定性运动/技能执行，不让LLM逐tick控制 | 选对分支、版本与端口；受限指令、主人授权、结果回执及游戏服务器许可 |

完整标识与文件Git blob SHA见[来源登记](../../evidence/zerolan-source-refs.json)。这里记录读取时的分支状态，不保证将来的默认分支不变。

## 实际数据流

1. 麦克风、直播弹幕等产生类型化事件；主程序调用模型管线。
2. 模型管线通过HTTP访问Core或支持的第三方API。
3. 主程序收到文本后，可做情感分析、分句和TTS，再安排声音/字幕。
4. AR端通过`ZerolanProtocol 1.1`收控制消息，并通过HTTP下载音频/模型资源。
5. MC端在dev分支通过同一协议家族上报工具描述并接收指令，再交给FSM/技能执行。

这是源代码路径，不是本项目部署成功记录。原型的SSE、Core的JSON流、Unity的WebSocket和TTS音频不能当作同一种线协议。

## 与当前原型逐项比较

| 维度 | 当前原型v0.2 | Zerolan所查路径 | 修订决策 |
| --- | --- | --- | --- |
| 产品中心 | 私人陪伴、模式切换、可取消约定 | 主播/多模态/工具编排 | 保留私人相处中心，直播是独立频道 |
| 编排 | 单服务、全局模型锁、HTTP/SSE | TypedEventEmitter、线程池/异步任务、多个服务 | 采用模块边界；默认少量进程，增加优先级/期限/有界队列 |
| 模型 | 本地Qwen+Kokoro，或Chat Completions | HTTP统一管线，多种模型服务 | 适配Query/Prediction，提供方可替换，不同时加载重复LLM |
| 流式 | 本地/远端增量与停止 | Core LLM逐行JSON；主bot常用同步predict | 为不同传输建立解析器，逐句音频另测 |
| 记忆 | 询问相关内容才检索，最多3条，可关闭 | 短期history；Milvus可选；关键词触发回忆 | 不把Milvus作为首阶段必装组件 |
| 形象 | 静态SVG；真实播放驱动简单状态 | Live2D和可选Unity AR/3D | 先完成Web/OBS生命周期；AR独立阶段 |
| 公开/私密 | 当前尚无公开频道 | 所查bot入口共用current_history | 两者都必须补硬隔离，不能直接继承默认路径 |
| 取消 | 已测停止本次生成，但还不是完整全双工 | 事件超时诊断，音频排队；未见完整跨端取消合同 | 取消需贯穿生成、合成、下载、播放和未听部分上下文 |
| B站 | 已有调研，无适配器 | bilibili-api-python网页凭证入口 | 入口与官方open-live路线区分，适配后用同一事件合同 |
| MC | 未实现 | dev有桥接、master以FSM与遥测为主 | MC作为可选扩展；先只读，再受限指令 |

## 关键证据与会改变计划的差距

### 1. 弹幕选择不能只看README

主程序`bot.py`的活动弹幕回调直接调用`emit_llm_prediction`。每5秒挑选弹幕的回调被注释；接收服务自身使用没有maxsize的队列。`select_max_long_one()`在队列只有一条时不进入循环，返回None；当前活动回调并不使用它。

因此不能把“已有挑选能力”当作已经验证的洪峰调度。需要新增有界队列、观众冷却、去重、过期处理，以及单条弹幕/同文不同ID/峰值的回归。

证据：[bot.py](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/bot.py)、[bilibili.py](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/services/live_stream/bilibili.py)。

### 2. 事件超时和“打断说话”是不同问题

`TypedEventEmitter`文档明确5秒超时只写诊断，不取消任务。同步任务提交线程池，异步任务另有取消路径；不能因此认定整个系统完全不可取消，也不能认定超时等于已打断。

Unity的`SpeechController`按列表顺序播放；`SpeechHandler`异步下载后入队。已读路径没有统一的utterance/generation取消标识。要验证下载完成乱序、停止后晚到音频，以及本机已停而远端继续播放的情况。

证据：[event_emitter.py](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/event/event_emitter.py)、[SpeechController](https://github.com/AkagawaTsurunaki/ZerolanPlayground/blob/fb23d1ed7345d51c73e82d72b1f27750c2e62961/Assets/Scripts/Controller/SpeechController.cs)、[SpeechHandler](https://github.com/AkagawaTsurunaki/ZerolanPlayground/blob/fb23d1ed7345d51c73e82d72b1f27750c2e62961/Assets/Scripts/Handlers/SpeechHandler.cs)。

### 3. 类型化数据不自动等于可靠协议

公共WS信封包含protocol/version/message/action/code/data。它没有覆盖频道、权限、期限和取消关联。模型查询另有id，但`AbstractModelQuery`和Prediction使用`Field(default=str(uuid4()))`，表达式在类定义时求值；新请求应显式分配ID，或改用default_factory。

Core LLM流接口输出逐行JSON；客户端通用管线按`iter_content`块解析JSON。网络块可分裂或合并消息，适配器必须做增量UTF-8与行缓冲，不能假定一块就是一条。

这些是静态审查发现的接口风险；没有把它们写成已复现的上游运行故障。

证据：[protocol.py](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/protocol/protocol.py)、[abs_data.py](https://github.com/AkagawaTsurunaki/zerolan-data/blob/647157ddfe043ab89315c31902b0747158c1706d/src/zerolan/data/pipeline/abs_data.py)、[LLM app](https://github.com/AkagawaTsurunaki/zerolan-core/blob/baefa0f78abe756a91ca231fc2f6439b46ebe266/llm/app.py)、[通用管线](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/pipeline/base/base_sync.py)。

### 4. TTS需要特定外部服务

Core的通用TTSApplication是占位实现。不能据此说整个体系没有TTS：文档明确要求作者的GPT-SoVITS fork、zerolan分支和`zerolan_api.py`，机器人TTS管线接收二进制声音。

计划要加音频适配和独立服务验证，不能只启动Core的通用TTS入口，或照搬当前上游GPT-SoVITS的`api_v2.py`就宣称兼容。现有Kokoro仍作为可运行基线。

证据：[Core README](https://github.com/AkagawaTsurunaki/zerolan-core/blob/baefa0f78abe756a91ca231fc2f6439b46ebe266/README.md)、[TTS占位入口](https://github.com/AkagawaTsurunaki/zerolan-core/blob/baefa0f78abe756a91ca231fc2f6439b46ebe266/tts/app.py)、[机器人TTS管线](https://github.com/AkagawaTsurunaki/ZerolanLiveRobot/blob/aad29d093295eef351da03a0bbe6ffac5539716d/pipeline/tts/tts_sync.py)。该外部fork尚未部署验证。

### 5. MC桥接应固定dev而不是只克隆默认分支

master读取时主要提供FSM、技能和状态广播。dev的`src/web/zerolanPlugin.ts`才有hello、推送指令描述和调用指令的WS桥接，协议1.1；连接地址还写死为本机11007，需改成经校验配置。

这是研究中修正过的结论：起初在master未发现桥接，检查dev后确认存在，不能再笼统说MC没有协议。还需验证主程序工具schema、MC指令参数、结果回执与异常状态是否匹配。

证据：[dev桥接](https://github.com/AkagawaTsurunaki/KonekoMinecraftBot/blob/b582ef3073bcb62c2fdfea7a9bfd9dffd472d7bf/src/web/zerolanPlugin.ts)、[dev执行器](https://github.com/AkagawaTsurunaki/KonekoMinecraftBot/blob/b582ef3073bcb62c2fdfea7a9bfd9dffd472d7bf/src/instruction/executor.ts)。

### 6. 记忆、工具和公开上下文必须重新划边界

`bot.py`多个入口向同一current_history查询；麦克风路径包含浏览器、屏幕点击和游戏指令。向量数据库可由配置关闭，并非全部场景强制依赖。

可借鉴可选记忆与工具模块化，但公开弹幕不能进入私人history，也不能因文本含“游戏/点击”等词就进入工具权限。语音识别到的“我是主人”不能作为身份认证。

这只描述所查默认路径，不推断所有插件/分支都没有额外权限控制。

## 采用结论

- 采用：稳定模块边界、共享契约、模型提供方接口、独立呈现与FSM技能执行。
- 先验证：协议1.1映射、NDJSON流、TTS外部fork、MC dev schema、Unity音频顺序。
- 首阶段保持关闭：AR、摄像头、屏幕控制、浏览器自动化、MC写世界工具、向量库。
- 不直接照搬：共享私聊history的直播路径、逐弹幕推理、无界队列、未鉴权的扩展入口和把超时日志当取消的语义。

完整迁移只有在兼容性、质量、性能和恢复成本比适配路线更好时才重新评估。AR没有查到根许可证，MC的master许可元数据也有差异，见[NOTICE](../../NOTICE.md)。
