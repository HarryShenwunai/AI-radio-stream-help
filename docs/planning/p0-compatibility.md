# P0 固定版本兼容样例

日期：2026-11-12。状态：**离线设计样例完成，P0 尚未完成，G1 尚未通过。**

本轮遵循交接文件的设计归档边界，只读取公开源码、核对固定版本并运行自编离线样例。没有启动上游服务、下载模型、连接直播间或MC服务器。当前仓库没有v0.2原型源码，因此尚不能修改或重测原应用。

## 固定版本与来源

使用[既有来源登记](../../evidence/zerolan-source-refs.json)中的commit，不跟随分支最新状态：

| 仓库 | commit | 本轮核对内容 |
| --- | --- | --- |
| zerolan-core / main | baefa0f78abe756a91ca231fc2f6439b46ebe266 | LLM HTTP路由、通用TTS占位、GPT-SoVITS模型边界 |
| zerolan-data / main | 647157ddfe043ab89315c31902b0747158c1706d | Query/Prediction基类、LLM、TTS、ZerolanProtocol字段 |
| ZerolanLiveRobot / main | aad29d093295eef351da03a0bbe6ffac5539716d | HTTP流式读取方式 |
| KonekoMinecraftBot / dev | b582ef3073bcb62c2fdfea7a9bfd9dffd472d7bf | WS hello及指令桥接 |

重新获取9份文件，逐份计算Git blob SHA-1并与旧登记比较，全部匹配。[验证清单](../../evidence/p0-source-verification.json)保留固定commit URL和blob哈希。上游代码只留临时目录，不复制入本仓库。这是源码一致性核查，不是上游运行验证。

## 映射与能力边界

| 对象 | 固定版本事实 | 适配决定/未决项 |
| --- | --- | --- |
| Core LLM请求 | POST `/llm/predict` 或 `/llm/stream-predict`；`id/text/history` | 显式创建UUID；history必须由可信频道路由先行裁剪。离线函数不会证明公开/私密隔离 |
| LLM流 | 每次Prediction JSON后加LF；客户端基类按HTTP chunk解析 | 以字节累计至LF再解析，限制单帧64KiB；遇截断/非法输入关闭解析器。禁止拿SSE解析器直接替换 |
| LLM结果 | `id/response/history`；模型具体实现未在本轮执行 | 暂保留每帧response，**不自动拼接为delta，也不把prediction id当request id**；真实提供方须确认增量/累计语义及请求关联 |
| UUID | 基类用`Field(default=str(uuid4()))` | Query由本地显式赋值；Prediction的关联须由可信请求上下文附加，不能凭重复默认ID猜测 |
| 通用TTS | Core通用app及GPT-SoVITS模型包装均未实现推理 | 不宣称通用TTS路由可用；外部fork专用服务另验，保留原型声音基线 |
| TTSStreamPrediction | `seq/is_final/wave_data/audio_type`；audio_type可为raw/ogg/wav | 内部合同需要utterance_id、采样率、声道和resource_id；上游类型不足以补齐。raw格式、字节序列化、OGG编解码均需真实响应核实；禁止猜测raw=pcm_s16le或ogg=opus |
| MC hello | WS子协议`ZerolanProtocol`，version `1.1`，action `koneko.client.hello`；源码连接11007 | 只制作hello格式夹具；源码host/port字段10098与实际连接URL不同，不将字段值当运行地址。默认message仍为server.hello，不按message推导action |
| MC指令 | 存在fetch/push/call instruction事件 | 版本校验不是认证；本轮不处理call_instruction，不授予动作权限。无连接、无工具执行 |
| 取消/重连 | 现有读取文件没有提供统一generation取消契约 | 不伪造cancel_ack；真实播放、取消、迟到帧、重连及上下文截断留待P1/P2验证 |

## 可复现离线检查

在仓库根目录运行，无第三方依赖、无网络：

```sh
python review/test_p0_reference.py
```

[参考实现](../../review/p0_reference.py)仅用于说明分帧和字段边界；[合成夹具](../../review/p0-fixtures.json)并非上游抓包。本轮20项检查通过，包括所有单处分割位置及逐字节分割、中文UTF-8、并包/CRLF、截断、重复键、非法JSON、错误协议版本和UUID显式生成。[结果记录](../../review/p0-offline-results.json)包含输入SHA-256，失败时命令非零退出。

这些检查不产生声音，也不模拟用户体验。它们没有测试上游解析器、真实HTTP/SSE/WS、权限隔离、乱序音频或停止后播放。因此Q01–Q10均继续NOT_RUN，集成执行数仍为0。原文档18项结构检查单独保留。

## 继续实施所缺材料与退出条件

下一步需要取得可运行v0.2源码及原测试入口；当前Git中仅有旧测试结果、截图和发布说明。不要从截图重建应用后宣称延续了原型。

有源码后先确定现有SSE协议与停止行为，再用同一请求上下文连接固定Core版本的本地模拟HTTP响应，最后测真实提供方。只有真实结果能决定response拼接、TTS资源/格式和取消能力。目标系统与声音通路仍需用户设备信息。

G1退出仍要求：Core真实LLM和外部TTS接口验证、MC dev实际协议握手（游戏连接另需对应授权）、旧端支持表、同机基线与A/B/C路线记录。离线样例通过不关闭G1，也不据此把计划工时缩减。当前继续保留方案A作为候选推荐，不宣称已完成路线验证。
