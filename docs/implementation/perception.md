# 摄像头与 PC Vision：实现、权限与验收

更新：2026-11-12。此文档记录本轮实际实现与未完成条件。摄像头硬件、专业眼动、真实游戏建议、真实 VLM 推理尚未验收。本地面部算法与 Windows 离线依赖包另见 `perception-tracking.md`。

## 当前结果

已实现 `src/companion_runtime/perception.py`：真实 OpenAI-compatible 图片请求适配器、默认不可用能力状态、全局连接配置安全存储、有界易失会话、角色/外观/epoch 隔离、立即停止后的迟到结果丢弃。模块本身不会调用摄像头、截图或写入角色记忆。

已运行 47 项单元测试，包含 1,296 条有限动作序列及 5,184 次真实管理器操作。另运行真实 loopback HTTP 协议测试：图片格式/认证、拒绝跳转、响应大小限制、错误脱敏均通过。测试服务的回复明确为合成夹具，不是模型看懂图片的证据。

未配置图片模型时返回 `vision_not_configured`。现有 Qwen3-4B 文本模型不被自动当成视觉模型。`configured:true` 仅代表连接已填写；`inference_verified:false` 不因 HTTP 请求格式正确而改为“已验证”。

## 事实、待验证资料、推断与未知

| 类别 | 内容 | 依据 |
| --- | --- | --- |
| 已核实 | 当前模型清单是 Qwen3-4B-Instruct-2507 的约 2.50GB GGUF，没有视觉投影器。 | `app/models-manifest.json`，2026-11-12 本机读取。 |
| 已核实 | 安装的 llama-cpp-python 0.3.36 有 `Qwen25VLChatHandler`；未发现 `Qwen3VLChatHandler`。父类要求独立 `clip_model_path`，并通过 mtmd 初始化投影器。 | 本机 distribution 元数据及 `llama_chat_format.py` 源码，2026-11-12。 |
| 已核实 | 官方 Qwen2.5-VL-3B 当前仓库的 LICENSE 是 Qwen RESEARCH LICENSE，而非 Apache-2.0。 | 官方 HF 仓库 SHA `66285546d2b821cf421d4f5eb2576359d3770cd3` 的 LICENSE，2026-11-12。 |
| 已核实 | MediaPipe 代码及官方 BlazeFace / Face Mesh V2 / Blendshapes V2 模型卡分别标 Apache-2.0。 | 官方源码 LICENSE 与三个官方模型卡，2026-11-12。 |
| 可信但待本机验证 | 官方 Face Landmarker 输出 478 面部点、52 表情系数与变换矩阵，可用于角色表情/面部方向估计。 | 官方任务文档；未在本产品设备上运行。 |
| 推断 | 在 CPU 上独立运行轻量面部估计，可避免与文本模型争抢 4060 显存。 | 架构判断；必须实测帧时、CPU 和温度。 |
| 未知 | 用户 4060 的实际可用显存、摄像头/远场麦克风型号、目标游戏、真人交互质量。 | 只有用户自述“4060、32G”；没有设备诊断与实测。 |
| 未知 | 自定义视觉服务的图片支持、输出可靠性、价格与远端保留政策。 | 必须由所选服务资料和实际图片测试确认。 |

## 两条可行模型路径

| 项目 | 本机独立多模态服务 | 远程图片模型服务 |
| --- | --- | --- |
| 接入 | 用户启动经过验证的本机 OpenAI-compatible 视觉服务，填写 loopback URL/model。 | 用户选择 HTTPS 服务并填写支持图片的 model/key。 |
| 现有适配器 | 同一真实 HTTP adapter。 | 同一 adapter；每次远程会话另确认发送画面。 |
| 优势 | 原始帧可限制在本机；无按 token 远端计费。 | 无需另装数 GB 视觉权重；减轻本地显存压力。 |
| 局限 | GGUF 与投影器必须匹配；与当前文本模型争用 GPU；需单模型复用或按需卸载调度。 | 网络延迟、服务计费、第三方保留规则；离线不可用。 |
| 主要风险 | 4060 型号/显存未知；不能把文本 GGUF 当 VLM；模型许可须逐个核验。 | 画面可能含私人内容；API 接受图片字段也不保证模型实际使用图片。 |
| 资源/费用 | 权重大小、峰值 VRAM/RAM、加载时间待选模型实测；电费未估价。 | 价格待选服务官方报价；次数×每图/token 用量决定持续成本。 |
| 当前验收 | 未安装或下载 VLM，不声称已跑通。 | 未连接外部付费服务，不声称已跑通。 |

建议先保留可自助切换的适配器与明确不可用状态。不要自动下载 GB 权重，也不要因“有 4060”承诺目标画质。若采用单一多模态模型同时聊天/看图，必须重新验证人物语言表现、并发所有权、上下文和显存预算；本轮没有替换现有聊天后端。

## HTTP 与 Python 合同

HTTP 适配由 `app/server.py` 管理；本模块是宿主内部服务。所有路径只给 owner Cookie + `X-Companion: local-app`，加 Host/Origin 校验。插件 bearer 不能获得这些权限。owner/character/appearance/epoch 由服务器产生，客户端字段只作预期检查。

| HTTP | 请求 | Python 调用/响应 |
| --- | --- | --- |
| GET `/api/perception/status` | 无 | `manager.status(owner_id)` 返回脱敏 vision、当前 owner 会话、限制、`retains_frames:false`。宿主附加 `store.load().public()`。 |
| POST `/api/perception/config` | `enabled/base_url/model/api_key`，可局部更新 | `config=store.save(payload)`；`manager.configure(config.provider())`。更新取消所有旧会话。 |
| POST `/api/perception/session/start` | `kind:camera\|screen`、`consent_confirmed:true`；远程另 `remote_processing_confirmed:true` | `manager.start(scope,kind,...)`，返回新随机 session_id、限制和脱敏 scope。 |
| POST `/api/perception/session/stop` | `session_id` | `manager.stop(owner_id,session_id)`；同 owner 可清理旧角色会话，不能停止另一 session。 |
| POST `/api/perception/frame` | `session_id/request_id/image_base64/mime_type/captured_at_ms/prompt` | `manager.frame(scope,...)`，成功返回 request/session、observation_id、description、processing、`retained:false`。 |

Python 接口：

```python
scope = PerceptionScope(owner_id, character_id, appearance_id, epoch)
store = VisionConfigStore(application_global_data / 'perception')
manager = PerceptionManager(store.load().provider(), is_scope_current=host_scope_checker)
```

`is_scope_current(scope)` 必须比较服务器当前 owner/role/appearance/epoch，不能仅比较显示角色名。角色 A→B→A 也要改变 epoch。宿主在角色切换、退出、重新加载、隐藏时调用 `stop_all(owner_id)`；前端同时 stop tracks。该回调是同步检查，应避免与宿主锁形成逆序死锁。

配置字段省略则保留。显式 `api_key:''` 清除密钥。**更换 base_url 且没有显式新 key 时清空旧 key**，避免旧服务密钥被转发给新域。public 只有 enabled/model/has_api_key/processing/provider，不返回 URL/key。错误不包含配置正文、路径或供应商响应。

存储用原子替换、文件 fsync、POSIX 0600/0700，拒绝 symlink/reparse、非普通文件、超大 JSON。Windows 必须使用当前用户私有应用数据目录及正确 ACL；0600 不能替代 Windows ACL。没有声称防住能控制父目录/当前用户账户的攻击者。

## 同意与会话流程

1. 用户点击“摄像头”或“分享画面”，先明确用途和本地/远端处理位置。
2. 浏览器调用 `getUserMedia` 或 `getDisplayMedia`。分享屏幕必须由用户在系统窗口选择来源。
3. 授权成功后在原界面显示来源预览，再创建会话。请求内一个 true 不能代替系统权限。
4. 前端每次最多一帧在途，响应前不再发送。用户可随时停止；隐藏、角色切换、track ended 均停止来源和服务端会话。
5. 服务端在解码前和推理完成后检查会话/epoch。供应商不配合取消时仍拒绝交付其迟到结果。
6. 图像、EXIF、屏幕文字不自动进入长期记忆。若将来要保存用户明确选择的事实，须另做可见确认和删除流程。

停止是撤销结果交付权。已发往远端的请求可能继续计算至网络超时，不能承诺撤回已经发送的画面或远端擦除。

## 建议功能如何使用真实画面来源

frame 成功响应增加随机 `observation_id`。建议接口只能接收该引用；服务器通过 `manager.observation(scope, observation_id)` 读取 `PerceptionObservation`，不能接受前端自称的 description/hash/source。

该对象绑定 owner/角色/外观/epoch/session/request/source kind，含采集时间、规范化图像 SHA256、模型描述、local/remote 处理位置。只在当前会话活跃，且捕获年龄与缓存年龄均≤30秒时可读。stop、配置变更、角色切换会使其失效。`.evidence()` 标为 `vision_model_observation`、`untrusted_context:true`、`inference_verified:false`，不是用户亲述、视觉事实证明或系统指令。回复不自动发到微信/B站，也不自动写入长期记忆。

## 限制与性能验收

| 约束 | 当前值 | 意义 |
| --- | --- | --- |
| 原始/重编码帧 | ≤1,500,000 bytes | 仅 PNG/JPEG，真正解码并新建 RGB JPEG 去元数据。 |
| 图像尺寸 | 最长边 1920；≤2,073,600 像素 | 在像素解压前拒绝尺寸超限，不接受动画。 |
| JSON HTTP body | 宿主应为 frame 单独设约 2,200,000 bytes | 普通小请求限制不能直接用于 base64 帧。 |
| 推理与解码 | 各最多 1 个在途 | 避免重复并发解码或 GPU/服务请求堆积。 |
| 速率 | 全局及会话最少间隔 2 秒 | 重开会话不能绕过；是产品保护阈值，不是机器性能实测。 |
| 会话/缓存 | 最多 8 会话；每会话 32 个 request 记录；900 秒 TTL | 成功文本结果只作短期易失去重，帧不进缓存。 |
| 时效 | 捕获年龄≤10秒、未来≤2秒；推理结果≤30秒 | 防止旧画面继续影响新状态；不是实时游戏延迟承诺。 |
| 供应商 | 超时≤30秒，默认15秒；响应≤512KiB，回复≤2000字 | 无跳转、无工具执行，不把画面指令当系统权限。 |

理论原始图像发送上限约 0.75MB/s，base64 约再增加三分之一；这是上限计算，不是实际平均流量。默认关闭、预览/单帧、限帧优先。对竞技策略不能承诺 2 秒采样提供实时优势。

上线前要在 Windows/4060 记录基线与开启前后 CPU、GPU、RAM/VRAM、浏览器帧时、推理 P50/P95、上传量、停止后活跃 tracks。验收目标是界面不受推理长任务阻塞、无队列积压、隐藏后帧发送归零、无跨角色结果；具体 CPU/显存阈值需实测基线后定，不捏造数字。

## 错误码

| 状态 | code | 用户可恢复方式 |
| --- | --- | --- |
| 503 | `vision_not_configured` | 连接真实图片模型。 |
| 403 | `consent_required` | 明确同意捕获/远端传输。 |
| 409 | `scope_changed/session_expired/session_unavailable/cancelled/frame_expired` | 停止旧来源；需要时重新选源建会话。 |
| 409 | `request_conflict` | 不复用 request_id 提交不同帧。 |
| 429 | `rate_limited/inflight/session_capacity` | 等当前帧结束或停止空闲会话；不自动无限重试。 |
| 413 | `frame_too_large` | 缩小帧/降低编码大小。 |
| 400 | `invalid_frame/invalid_request` | 只提交合法 PNG/JPEG 和字段。 |
| 502 | `provider_failed` | 保留本地聊天，显示视觉请求失败；不输出假观察。 |
| 400 | `invalid_saved_config/unsafe_config_storage/config_write_failed` | 修复私有存储路径或重新配置；旧原子文件可保留。 |

## MediaPipe 可行性与尚未安装的跟随功能

官方模型卡已分别核实 Apache-2.0；仍应固定具体 `.task` 版本/SHA，列出包内组件与第三方声明后再随安装包分发。未下载该权重，避免把研究文件错误加入发布包。首轮抓取 PDF 上限 1.5MB 截断了两个模型卡，后续以 ≤8MiB 重取完整 PDF 并成功解析；不能把截断文件解析失败当作许可缺失。

Face Landmarker 可测面部方向/表情/眨眼估计，不是专业眼动仪。官方 Web API 同步执行，需要 Worker 或严格降采样，不能逐动画帧堵主线程。适合先单人、低分辨率、只保留最新帧的本地 CPU 原型，再测遮挡、背光、眼镜、无人/多人、不同面部角度；无人应平滑回待机，不能继续锁定历史脸。

官方 BlazeFace 模型卡的 Pixel 2 单核 CPU 指标不能当本机完整 FaceLandmarker 的性能，也不能当 Windows/4060 验收。默认缺依赖/权重时 `face_tracking.available:false`。安装并校验可选组件后可用面部方向估计；算法加载成功仍不是专业眼动或真人设备验收。远场麦克风阵列/HD 摄像头/5英寸投影属于硬件能力，本软件不能从普通输入设备制造相同硬件性能。

## 测试与复现

```sh
PYTHONPATH=src /workspace/companion/.venv/bin/python -m unittest discover -s tests -p 'test_perception*.py'
.build/quality-venv/bin/mypy --strict --python-executable /workspace/companion/.venv/bin/python src/companion_runtime/perception.py
.build/quality-venv/bin/ruff check src/companion_runtime/perception.py tests/test_perception*.py
PYTHONPATH=src /workspace/companion/.venv/bin/python tests/test_perception_http.py
```

最后一项启动临时 loopback 服务器，需要环境允许本地 sockets，不连接外部服务。报告见 `review/perception-provider-check.json`。前面单测使用明确合成适配器。有限状态遍历检查 owner/epoch/stop/config 边界，未证明任意线程交错、完整程序安全、活性或真实模型语义。

已验证：默认不可用、显式布尔同意、远端单独同意、非法 start 不取消旧会话、错 scope 不取消新会话、ABA、旧 stop 不能停止新 session、未配/更换配置、到期、速率/容量/缓存、非法/超大/动画图像、元数据剥离、重复/冲突请求、慢供应商停止/epoch丢弃、响应截止与脱敏、原子失败恢复、文件/父目录链接拒绝、密钥不回显、变更域清旧密钥、可信观察引用的 owner/epoch/stop/时效/容量边界、真实 HTTP 拒绝跳转。

待完成：宿主 owner-only 路由集成验收、真实浏览器 capture 撤销/分享选择录像、Windows/4060 资源、实际图片模型对 holdout 图的准确性、摄像头算法安装及真人跟随表现、真实游戏延迟与建议质量、第三方隐私条款确认。

## 已核实来源

访问日期均为 **2026-11-12**。价格未查询，未产生外部计费请求。

- llama-cpp-python 官方多模态示例：<https://github.com/abetlen/llama-cpp-python/blob/main/README.md>；安装能力以本机 0.3.36 源码为准。
- Qwen2.5-VL-3B 官方许可证：<https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/66285546d2b821cf421d4f5eb2576359d3770cd3/LICENSE>。
- MediaPipe 官方任务说明：<https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker>。
- MediaPipe 官方代码许可：<https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE>。
- BlazeFace 官方模型卡：<https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20(Short%20Range).pdf>。
- Face Mesh V2 官方模型卡：<https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf>；本次 PDF SHA256 `c6add060f4ebfb37b2690136b6c711c7e5fcb7038baa2649ae3338b83979565a`。
- Blendshapes V2 官方模型卡：<https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf>；本次 PDF SHA256 `c8e9cf60a39998f4b341740623917590e050d1c97004e2de4568d84e026445ae`。
