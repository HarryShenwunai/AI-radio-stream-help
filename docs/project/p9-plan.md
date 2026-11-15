# P9 项目计划

快照日期：2026-11-15（Europe/London）。状态：**发布阻断**。

跟踪：[Issue49](https://github.com/HarryShenwunai/AI-radio-stream-help/issues/49)；实现：[PR48（草稿）](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/48)。

本轮只交付项目诊断、任务定义、管理快照与展示。三项AI只读调研已完成；A的协议草案已交付，仍待审。其余实施尚未开始。AI复核不能代替独立专业人员或用户认可。

运行基线固定为上述tree；管理文件另存planning分支，不作为新产品版本，也不实时同步PR head。

## 真实目标

Windows PC上的现场助手，处理一条已允许的原始文字，主播确认后由同一节目画面呈现对应人物、字幕与语音，能停止并观察终态。先让这条主线可复现，再扩范围。

## 基线与发布阻断

本地 `dc231bb308c9e79407aaa554b9011bdad0436c72`；远端 `3af7f876ebe10d814e9c17a793c14879cfb4c7f8`；两者tree `dd09e659eff0b812ffd14412d38f12171147393f` 相同。完整开发报告指纹与当前字节相符；PR未合并。

现有room样稿与live-stage实际输出分离；主播状态手动刷新；旧Windows包与源码不同版且缺room模块。当前视觉已被用户退回，不能以颜色/回归通过称审美完成。

## 关键路径与协作

A 审阅冻结 → B输出集成 ∥ C控制台；D先做原素材与声线诊断 → E同版Windows候选 → F真机与独立任务验收。

A冻结后，B输出集成与C控制台按文件域并行；D先只读诊断。后端与live-stage仅B可写；渲染修复由P9另行移交。

文件域移交和契约冻结需记录；未发生的移交不能标已完成。每次并行最多推进有明确接口且无重叠写入的任务。

## 证据状态

- **产品运行基线：已核实**。本地dc231bb与远端3af7f87的tree相同；PR48仍草稿。 限制：未合并、未发布。 依据：`git HEAD / PR48`。
- **开发检查：本地已测**。完整质量报告passed且源码稳定；source_sha256与当前字节无差异。 限制：报告提交标签为父110e562，须用指纹绑定；不能代表Windows或审美。 依据：`.build/color-review/quality/report.json`。
- **现场演练：本地已测 · 合成事件**。真实Qwen3-4B、TTS、批准/停止/完成有记录。 限制：非真实弹幕、非系统声卡/OBS音轨、非观众接收；负载下曾过期。 依据：`.build/product-completion/real-local-isolated/result.json`。
- **视觉专业感：用户退回**。颜色机械边界与Linux/Core有证据。 限制：用户仍否定；AI截图审查不等于独立设计评审。 依据：`.build/color-review/final/report.json；用户本轮反馈`。
- **青春声线：候选 · 待盲评**。已有实际WAV与口型开发观察。 限制：听感、角色契合、用户选择未确认。 依据：`.build/product-completion/real-local-isolated/actual-speech-*.wav`。
- **Windows制品：发布阻断**。解压目录ccee999/r4；实际ZIP 6568ab05/r2，均缺room模块。 限制：不是当前dc231bb同版完整候选；native/CUDA/人工视觉均未通过。 依据：`.build/pc-completion/standalone/character-windows-pc/BUILD-INFO.json；character-windows-pc-r2.zip`。
- **形式化范围：有限旧模型**。曾有有限TLC模型与坏模型反例。 限制：当前实现映射不同，refinement与liveness未证明；非全程序证明。 依据：`.build/pc-completion/formal/report.json`。
- **独立与真机：待验证**。用户将最后执行Windows验收；尚无独立专业评审。 限制：未见真人任务结果、未见题收益或目标设备结果。 依据：`待同版候选与外部原始材料`。

## 六要素任务定义

### A · P0 · 场景与设计冻结

状态：协议草案待审。负责人：P8 场景契约（AI，已下发）。产品实施：尚未开始。前置：无。

#### WHY

先明确一条现场互动如何被操作、审核、播出和接管，避免样稿与真正输出各做一套。

#### WHAT

- 一条本地原始文字的主播操作流、节目流与中断恢复联系表。
- 区分布置器 room 与实际输出 live-stage，记录现有字段与建议字段。
- 同条件任务材料与布局方向评审记录，未获用户认可前不称冻结。

#### WHERE

- docs/project/interaction-contract.md
- docs/project/interaction-acceptance.json
- 现有 app/static/room.* 与 live-stage.* 只读作为输入。

#### HOW MUCH

只冻结一个现场场景；P9协调、一个契约负责人起草；不进行产品代码实施，不编工期。

#### DONE

- 从本地演练输入到准备、审核、单次批准、同一节目声画、停止、两端终态均有明确状态与证据要求。
- 现有 id/session/event_id/source/room_id/generation_id 与建议新增快照/标识逐项区分。
- 评审指出下一步最小实现范围，用户确认布局方向；协议草案不等于冻结通过。

#### DON'T

- 不把带私有cookie的 room 直接公开。
- 不假定独立 approval_id/playback_id 或公开角色/外观/布置快照已存在。
- 不补画、不增加配色、人物或组件，不以测试数量代替方向确认。

依据：[样稿和实际输出的两个入口](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/app/static/connectors-ui.js#L27)；[实际输出页当前内容](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/app/static/live-stage.html#L1)。

### B · P0 · 同一节目声画与安全契约

状态：待 A 冻结。负责人：待分配 · 输出集成负责人。产品实施：尚未开始。前置：A。

#### WHY

让批准的问题、回答、字幕、语音、角色和布置属于同一场次；阻止旧任务和私有上下文进入输出。

#### WHAT

- 复用现有状态机，接通一条批准回答到实际节目画面。
- 定义并实现最小公开快照：绑定现有事件/场次/生成标识；新增字段先作为设计建议评审。
- 保留取消、过期、切身份、晚响应与旧令牌反例；实际媒体结果与回执分开记录。

#### WHERE

- 独占 app/server.py 的输出路由、src/companion_runtime/live_output.py。
- 独占 app/static/live-stage.* 与对应后端/节目页测试。
- room.* 为当前实现的只读参考；A后仅使用获审阅的设计输入，其他负责人不得并写上述文件。

#### HOW MUCH

一条互动、现有 Core/音频/状态机、无新依赖或后台轮询；真实模型实测与完整回归顺序运行。

#### DONE

- 同一批准事件驱动实际节目页对应的人物、字幕和音频；停止后旧响应不得恢复播放。
- 原始输入、状态时间线、实际音轨和双端未剪辑录像可逐项对应。
- 下列回归通过，且旧断点/坏版本仍被拒绝；无观众证据仅声称本地输出。

现有可复跑命令（须配置实际路径；本轮未重跑产品检查）：

- `PYTHONPATH=src:tests python3 -m unittest -v test_live_interaction test_live_output test_platform_integration_http test_local_rehearsal`
- `COMPANION_MODELS=/path/to/models COMPANION_VOICES=/path/to/voices PYTHONPATH=src:tests python3 tests/local_product_browser.py --chrome /path/to/chrome --out evidence/local`

#### DON'T

- 未经批准不自动公开，不读取私聊、记忆或私人历史作为公开上下文。
- 不恢复放杯、不新增美术，不声称已收到观众端证据。
- 不绕过授权运行库或暴露私有资源接口。

依据：[样稿人物固定不说话](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/app/static/room.js#L22)；[手填字幕与实际输出分离](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/app/static/room.js#L33)。

### C · P0 · 主播状态、恢复与负载

状态：待 A 及 B 契约。负责人：待分配 · 控制台负责人。产品实施：尚未开始。前置：A, B-contract。

#### WHY

主播需要在现场知道正在处理、等待批准、实际播放还是失败，并可停止与恢复；不能依赖样稿或过早回执。

#### WHAT

- 按问题、候选回答、批准、播放、失败与停止重排现有流程，后置低频布置。
- 使完成/故障持续可见，核对键盘操作、断线、晚响应和音频拒绝。
- 受控测量模型、角色、语音同负载；先取基线再锁延迟、中断与资源判据。

#### WHERE

- 独占 app/static/connectors-ui.js、相关样式与对应 UI/故障验证。
- 不改 app/server.py、live-stage.*；后端需求提交 B 的单一负责人。

#### HOW MUCH

B契约冻结后可与B分文件并行；不增加通用控制台或后台轮询，不编性能数字。

#### DONE

- 原任务前后记录操作成本、误触、接管错误与恢复步骤；收益不以满意度或停留时长代替。
- 输出状态依据实际媒体事件；playing 回执不冒充已经发声。
- 保留负载下30秒期限耗尽反例；不放宽TTL掩盖失效。

现有可复跑命令（须配置实际路径；本轮未重跑产品检查）：

- `node --test tests/test_connector_settings_ui.mjs`

待固化的人工/实验入口（不是可直接执行命令）：

- 真实浏览器重放完成、故障、停止、恢复与受控负载；命令和固定阈值在基线后登记。

#### DON'T

- 不修改已锁判据追求通过。
- 不把“主播讲解中”手动开关写成自动音画感知。
- 不把真实模型与全套回归竞争资源后的结果混成单一性能结论。

依据：[主播当前仍需手动刷新](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/app/static/connectors-ui.js#L23)；[本地演练负载与限制](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md)。

### D · P1 · 人物合成与声线审查

状态：待 A · 先诊断。负责人：待分配 · 角色/音频审查负责人。产品实施：尚未开始。前置：A。

#### WHY

深底边缘、蒸汽融合和声线契合尚未得到根因或独立审美支持，不能继续靠换背景或AI自评宣布专业。

#### WHAT

- 核对标准原图、分层/蒙版、可编辑Cubism工程与导出模型的来源和缺口；不能凭R3包名认定原始工程齐全。
- 固定同一帧，完成白/灰/黑底边缘ROI与原图、alpha、遮罩的对照。
- 用现有真实WAV制作匿名盲听材料，记录青春感、清晰度与角色契合。
- 竞争解释区分：底图残色、透明混合、羽化遮罩、背景与原光照不协调。

#### WHERE

- review/art-direction 下的专属诊断制品；现有原始素材只读。
- 若证实渲染根因，由P9另行移交对应渲染文件域；不与B争写。

#### HOW MUCH

只诊断现有R3与已有声音，不新增人物、美术、模型或音色下载；盲评人员未到位保持待验证。

#### DONE

- 实验支持具体根因与最小修复建议；脸、手杯和原始素材哈希不变。
- 匿名材料可供未参与制作人员复核；人工结果与AI候选判断分别记录。
- 候选冻结记录明确使用哪个现有模型与音色，不把未认可写成通过。

待固化的人工/实验入口（不是可直接执行命令）：

- 同帧/同参数白灰黑背景ROI对照、素材哈希与分轨WAV检查；具体复跑入口随诊断材料登记。

#### DON'T

- 不通过人物曝光或滤镜掩盖合成问题。
- 不新美术、不补画、不恢复放杯，不展示被拒绝3D。
- AI审查不能代替专业盲评或用户选择。

依据：[现有角色与实音频的证据边界](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/voice-room-original-direction.md)。

### E · P0 · 同版 Windows 候选与恢复

状态：发布阻断 · 包落后。负责人：待分配 · 发布工程负责人。产品实施：尚未开始。前置：B, C, D-candidate。

#### WHY

现有ZIP与已解压目录都落后于当前源码且缺少room模块，用户无法验证一个一致的完整候选。

#### WHAT

- 从同一冻结版本生成候选包与更新/回退材料。
- 对齐源码tree、模型、运行库、包内清单及CPU/CUDA配置指纹。
- 检查真实归档内部字节、用户数据保护、更新与回退；不只看文件名。

#### WHERE

- 独占既有 build/update 脚本及独立 .build 发布输出。
- 产品源码、模型与渲染素材只读；缺陷交回对应负责人，禁止打包时私补。

#### HOW MUCH

复用既有基包与构建机制；不新安装器，不下载模型或SDK；候选不冒充Windows运行验收。

#### DONE

- 归档内包含room.html/js/css/room-design.js，并与冻结源码逐项匹配。
- CPU/CUDA和恢复机制来源一致，更新/回退不覆盖用户材料与设置。
- 候选清单区分Linux组装、文件验证与未完成的Windows native结果。

现有可复跑命令（须配置实际路径；本轮未重跑产品检查）：

- `PYTHONPATH=src:tests python3 -m unittest -v test_app_update test_app_update_commit`

待固化的人工/实验入口（不是可直接执行命令）：

- 真实ZIP中央目录、包内来源清单与逐文件哈希核对；构建命令在冻结版本后登记。

#### DON'T

- 不把旧r2 ZIP、较新的r4目录或零散PR称作同一最新成品。
- 不把有ZIP等同可用，不假称Windows native/CUDA已过。
- 不改产品源码或下载许可运行库来绕开发布门禁。

依据：[源码与更新包机制](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/scripts/app_update.py)；[PR48 当前开发候选](https://github.com/HarryShenwunai/AI-radio-stream-help/pull/48)。

### F · 发布闸门 · 真机与独立任务验收

状态：待 E · 外部验收未到位。负责人：Windows由用户最后执行；独立工程师/目标主播未到位。产品实施：尚未开始。前置：E。

#### WHY

本地AI开发检查不能证明目标Windows体验、专业审美、实际学习收益或用户认可。

#### WHAT

- 固定Windows10/11、RTX4060、32GB，检查DPI、多屏、最小化、睡眠恢复与同负载停止。
- 未参与制作人员复跑、视觉匿名评审及目标用户固定现场任务分别留证。
- 学习收益用未见题、控制已有知识/难度/顺序单独评价。

#### WHERE

- 只针对同版候选与独立验收记录，不直接修改开发评分器。
- 外部人员与用户执行身份、设备、材料和原始结果分别登记。

#### HOW MUCH

先一条完整主线、一个同版候选；没有真实设备或独立人员就保持待验证，不编日期。

#### DONE

- 目标Windows原始录像、设备/版本与性能记录齐全；失败可按固定步骤复现。
- 机械、视觉、声线、学习效果、用户认可逐项独立判定。
- 本轮仍暂停B站/OBS真实环境；实际观众收到必须另有观众端证据。

待固化的人工/实验入口（不是可直接执行命令）：

- 在目标Windows执行候选随附固定验收清单，记录实际命令、设备及原始结果。

#### DON'T

- 不把Linux Chrome模拟当Windows，不由AI补位真人独立验收。
- 不将有限TLC模型结果称当前全程序形式化证明。
- 不部署、不合并、不发布，证据不足不关闭发布阻断。

依据：[现有本地演练的验收限制](https://github.com/HarryShenwunai/AI-radio-stream-help/blob/3af7f876ebe10d814e9c17a793c14879cfb4c7f8/docs/validation/local-product-rehearsal.md)。

## 发布闸门与停止条件

- 实验不能区分原因时不扩大补画或功能范围。
- 同版制品、真机或独立证据缺失时保留发布阻断。
- 不以功能、配色、PR、测试或文档数量作为完成。

可发布必须逐项有当前同版制品证据：安全状态约束、实际节目声画、目标Windows运行、专业/目标用户任务与用户认可。任何一项缺失保持待验证。无观众端证据不声称观众收到；有限模型不等于全程序形式化。

本轮保留边界：Windows PC only；固定持杯、保留原角色与光照；暂停新美术、新人物和小组件扩张；当前不测试B站或OBS真实环境；不虚构感知、在线状态、观众接收或学习效果。

## 后续更新方法

只在获得对应原始证据并记录审阅者后更新状态；同时更新本计划与p9-status.json。保留来源路径、哈希和失败反例。看板是该JSON快照的会话内展示，不是后台自动同步、也不表示团队正在执行所有任务。
