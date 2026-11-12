# 类似产品与当前技术

查阅：2026-11-12，Europe/London。未给项目取名。以下是功能与设计比较，没有安装、购买或登录这些商业产品做体验评测。

## 结论

最值得优先研究的开源路线是 **Zerolan、AIRI、Open-LLM-VTuber**。SillyTavern适合研究角色配置与可控上下文。中文互动体验参考星野、猫箱；语音通话、主动联系和关系呈现参考Character.AI、Kindroid、Replika。

这些产品分别解决角色互动、实时语音、展示或直播的一部分。没有证据表明其中某一个已完整满足本项目的微信、B站、弹幕姬、自然相处、可控主动联系与本地隐私全部要求。

## 现有产品与框架

| 对象 | 已读取资料说明的能力 | 最适合借鉴什么 | 不能据此推导什么 | 来源 |
| --- | --- | --- | --- | --- |
| Zerolan五仓库体系 | 事件驱动机器人、HTTP模型管线、Live2D/Unity AR、直播输入、MC桥接 | 多入口/模型/展示/执行器分离 | 默认分支全部兼容、账号可用或质量已通过 | [详细源码比较](zerolan-comparison.md) |
| AIRI | Web/桌面角色、Live2D/VRM、多提供方语音；README仍将Memory Alaya标WIP | 形象与语音交互、多端角色呈现 | 实验功能已经稳定；整套记忆可直接商用 | [README](https://github.com/moeru-ai/airi)、[MIT许可](https://github.com/moeru-ai/airi/blob/main/LICENSE) |
| Open-LLM-VTuber | 实时语音、打断、Live2D、多模型后端；当前README称长期记忆暂移除 | 语音会话与展示生命周期 | 聊天日志等于长期记忆；B站可回发文字 | [README](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)、[B站代码](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/src/open_llm_vtuber/live/bilibili_live.py) |
| SillyTavern | 可本地安装的LLM界面、角色配置、多个本地/云端TTS选项 | 可修改人设、上下文、回复与声音的用户控制 | 它本身提供推理，或已是可直播的完整虚拟角色系统 | [官方文档](https://docs.sillytavern.app/)、[TTS](https://docs.sillytavern.app/extensions/tts/) |
| 星野 | 官方网站描述角色定制与开放剧情；发行方App Store说明包含声音模型交互 | 中文角色表达、轻量进入相处场景 | 中文听感、长期稳定性、开放API或直播权限已验证 | [官网](https://www.xingyeai.com/)、[发行方页面](https://apps.apple.com/cn/app/id6463076337) |
| 猫箱 | 发行方App Store说明多角色剧情和语音畅聊，通话时长等受会员权益影响 | 故事氛围与语音交互入口 | 已开放可供本项目使用的模型或B站API | [发行方App Store页面](https://apps.apple.com/cn/app/id6475000292) |
| Character.AI | 官方FAQ描述双向通话、角色音色与文字记录 | 角色与声音绑定、聊天到通话的切换 | 2024版FAQ代表所有账号当前资格；声音样本可任意复制 | [Calls & Voice FAQ](https://support.character.ai/hc/en-us/articles/23957274129691-Character-Calls-Voice-FAQ) |
| Kindroid | 2026-10/11文档描述语音/视频通话、重生成、主动联系及Quiet hours | 中断与重试体验、主动联系的频率/安静时段控制 | 实时中文质量、套餐成本或任何跨平台自动化已验证 | [Voice](https://kindroid.ai/v2/docs/voice-calls-and-video-calls/)、[Chat features](https://kindroid.ai/v2/docs/chat-features-and-tools/) |
| Replika | 官方Pro说明关系状态、形象、语音消息、后台通话和AR通话 | 稳定关系入口、形象与相处节奏 | 其闭源实现可复用，或微信/B站已接入 | [官方Pro说明](https://help.replika.com/hc/en-us/articles/360032500052-What-is-Replika-Pro) |

商业产品的文档属于可信功能声明，并非本项目实测。地区、年龄、系统、账号资格与套餐可能影响可用性。本轮不报价、不用用户评分或厂商规模宣传替代质量证据。

AIRI和Open-LLM-VTuber主体MIT；SillyTavern是AGPL-3.0。角色模型、声音和SDK须分别核对许可，不把主体代码许可扩大到素材。

## 语音技术：两条路线都可行

| 维度 | 级联：VAD/ASR → LLM → TTS | 原生实时语音模型 |
| --- | --- | --- |
| 现有基础 | 原型已有LLM与Kokoro，可逐步加入真正的流式输入/输出 | 需要新的会话和音频传输适配器 |
| 角色与音色控制 | 文本可审查，TTS可替换，音色与模型较独立 | 由提供方支持的指令、声音与会话约束决定 |
| 时延 | 有识别、推理、合成多段等待，可分句流水并测量 | 官方接口提供低延迟双向音频能力；实际设备/网络未测 |
| 本地与隐私 | 可全部本地，也可混合；需控制模型常驻资源 | 云服务通常要上传音频；需用户选择与会话边界 |
| 公开直播 | 可以先检查文本，再播出 | 原生音频输出的播出审核策略需另做，不能直接套文本过滤 |
| 成本 | CPU/GPU、内存、维护；云调用另计 | 按提供方音频/文本计费和会话策略；本轮价格待验证 |
| 中断 | 应用负责取消模型、TTS、播放队列与未播放上下文 | 提供方有中断事件，但客户端仍承担播放清理等责任 |

官方资料：[OpenAI Realtime会话与截断](https://developers.openai.com/api/docs/guides/realtime-conversations)、[Gemini Live](https://ai.google.dev/gemini-api/docs/live)。Google旧链接本次跳转到AI Studio文档。模型ID与资格按实际接入日核验，不把搜索到的模型名称硬编码进计划。

**推荐**：先保持级联为可审查基线，并把语音提供方做成可替换接口。用同一组真实场景对比原生实时语音，然后按中文自然度、时延、成本和隐私决定是否启用。两条路径不默认同时常驻，不为了试验加载第二份LLM。

## 真正要补的是会话与行为设计

- 当前话题与可观察状态优先；角色偏好是稳定设定，长期记忆只是可关闭的补充。
- “正在听/想/说”应来自实际音频和请求状态，不由模型任意宣称。
- 用户打断时，先停止本机声音，再取消生成；处理晚到音频，删除未播放部分的上下文。
- 主动联系受用户授权、时区、安静时段、频率和未回复次数约束。督学沿用同一规则，不提升为产品核心。
- 私人相处与公开直播分别构建上下文。公众内容没有读取私聊、写记忆、控桌面或调用游戏工具的权限。

OpenAI文档明确区分取消回复和截断用户未听到的音频。WebRTC/SIP与WebSocket的职责不同。当前“点停止生成”不能直接等同已完成完整的可打断通话。

## 已核实、推断与未知

已核实的是上述文档/代码实际存在、API或字段的描述，以及现有原型测试记录。厂商声称的体验、上游作者声称的设备支持仍待本项目验证。

“优先改善音频会话、角色一致性和状态调度”是工程建议，不是已经通过的实验结论。未知项包括用户机器、最终音色、账号与预算、长期相处质量及目标系统性能。

本轮不新建向量数据库或训练声线。只有明确证明现有上下文检索不足且收益值得增加资源时，再单独评估。
