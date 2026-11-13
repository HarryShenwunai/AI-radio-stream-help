# 完成账与逐门验收

历史模块核对日期：2026-11-12。以下原模块工作基线为源码提交 `6fc3dd36d7df28b93903edac934b1d258d7b9b53` 后的实现；本轮新模块已接入并按独立证据逐门复测。此表不能由测试总数推导“全部完成”。机读状态在 [completion-status.json](../../review/completion-status.json)，会随实际证据更新。

## 2026-11-13 原创Live2D当前状态

**本机技术验收已收口，整体仍有目标机、账号与用户接受门未过。** 当前对象为真正同源42层PSD重建出的硬杯r2；原生Core实际读取42个drawable、41个参数，MOC SHA为`6e34e112…5934bd`。不是官模换皮、四帧PNG或假MOC3结构夹具。被拒的3D不展示、不打包。

- **当前公源质量门已过**：`review/quality-gate-live2d-delivery-final.json`，04:28:07 UTC、源码执行期稳定；780 Python/0 skip、111前端Node、9桌面Python、27桌面Node。327个源SHA已再次与当前文件核对无漂移。此报告证明代码快照的检查，不代替模型、目标机或账号验收。02:00:45及更早quality报告只保留历史范围。
- **新r2独立实际Core/GL八个子门已过**：13个参数真实min/mid/max像素、4表情、8动作、物理、no-op负控、2378次Core评价，JS错误0、源SHA执行期稳定。34个布料姿态含8单轴、8同侧四角、4相反双侧及14离key，三角翻转0，最大边长倍率1.222723。实际neutral眼参数均1、嘴Open0/Form0，原画眼mesh重建与半睑关键形确实生效，没有生产pin .65。眼嘴、视线、转头XYZ及布料关键帧均已实看；详见`review/original-character-live2d-rigid-r2-core-gl.json`和`review/original-character-live2d-rigid-r2-cloth-folds.json`。
- **整包已有可审候选，格式不等于完成**：精确runtime ZIP为11,017,918B、SHA`23afbd64…1b052e`；源码ZIP为345,553,022B、SHA`1625219f…f8f0dc`，位于`/workspace/dist/live2d-0.5.0-dev3/`。实际packager与AssetStore格式门通过，packager仍明确candidate/Core=false/full=false；QA另核runtime model3/MOC与新功能合同一致。可编辑项目实际281,235,238B，源身份/CRC由root和packager已有报告证明，不重复大包扫描。
- **新r2同一MOC手杯技术全门已过**：`review/hand-cup-rigid-r2-v1-full.json`真实13门，486个所选角点加61个离key，共547姿态（不是穷举20655个作者keyforms）。另实际5000抓握最大误差0.678589源px，低于原1px门；5000杯形最大similarity残差0.0001063源px，低于事前0.5px门。主舞台四动作/三场景9门、表情UI3门已过并绑定同一6e34模型。旧r1的25.445px软杯反例仍原样保留，不倒改旧红。
- **最终真实provider恢复轮7门已过**：精确`23af…` runtime ZIP、新合同和fullPASS实际接入本地Qwen3-4B→Kokoro→真实Audio/Analyser→独立Core口部反事实；6个实际口部drawable随音频变化，停止0.793秒（事前门2秒）、之后无晚到复活。真实SQLite回执为stopped、已确认前缀为空，下一prompt无未听助手尾文，UI原文仍保留；记忆关闭也能正常回复。7门/JS0/浏览器外连0，执行前后112个源一致，独立审查又核当前112源、327公源及6媒体SHA。
- **明确两次调用事实**：第一次真实Qwen/Kokoro已生成WAV和三图，但环境重置中断，没有最终stop/receipt报告，保留为partial而不计PASS；第二次由root完整恢复验证成功。不能写“只调用一次”或把第一轮片段算完整成功。完整结果见`review/real-live2d-rigid-r2-companion.json`，独立审查见`review/real-live2d-rigid-r2-independent-final-review.json`，旧中断记录见`review/real-live2d-rigid-r2-interrupted-observation.json`。
- **可审媒体与单次观测**：`/workspace/dist/evidence-real-live2d-rigid-r2/`有四张真实过程图、24kHz单声道PCM16 WAV（5.716625秒）和1440×1000 VP8视频（81.64秒、无音轨，实际WAV单独提供）。恢复轮首次文字49.540秒、完整回复62.314秒、首次观测音频RMS69.621秒，Python进程峰RSS5,631,388KiB；是共享Linux CPU的一次恢复观测，不是p95、不是RTX4060成绩，也不代表真人听感通过。
- **外部门仍未过**：Windows10/11及RTX4060、真人麦克风、真实B站/微信账号、用户E5画质/听感接受；另有范围相关未知：官方Editor重开CMO3与等效导出未验证，不把它擅自升格为软件运行的新增必需项。Linux软件GL、source完整和代码测试总数都不能替代这些门。

当前机器状态以`review/completion-status.json`的`current_original_live2d_review`为准。此前candidate7折片、source眼atlas切行错误、双underlay visibility假设、错误drawOrder请求以及r1软杯反例与各自SHA均保留；不倒改旧红，也不把root内部视觉基线接受等同用户E5。

## 真实目标与边界

交付给本人使用的二次元桌面陪伴软件：Windows10/11上角落常驻、按需展开；用户自行上传和替换角色，拥有自然连续的聊天与语音、可关闭的记忆和可控主动联系，并接入所需哔哩哔哩弹幕姬及微信。督学是角色可选能力，不取代陪伴。设备已自报RTX4060、32GB内存；CPU、显存、驱动及实际机型仍未由程序检测。

当前用户已明确转为2D，拒绝的3D候选已隔离，不能再展示或打包。当前原创完整Live2D为主要角色交付目标；PNG及VRM的历史格式支持证据保留其原范围，不等于当前角色美术通过。参考画质需要实际同素材Core呈现、动态可见效果及人工接受，不能用格式支持或几何夹具替代。

AR和MC来自上游研究与可选P6/P7，不因比较过五个仓库就自动成为本次必须完成项。Live2D在旧自助角色计划中写过正式目标，本轮继续保留，不能用完成VRM替代。用户现已明确同意Core与显示框架的本机评估条款；这不等于同意公开发布、代办Expandable许可或向其他用户再分发SDK。

本轮最新范围决定：用户接受**ClawBot与音频文件附件**，因此不再把微信原生语音条列为必需项；原生语音仍明确未支持，不能换个名称声称实现。用户确认有可管理的B站房间，但尚未提供房间ID、相应开发者凭证或真实连接结果。

## 证据等级

| 层 | 证明什么 | 不证明什么 |
| --- | --- | --- |
| E0 设计/源码 | 契约、代码或配置已存在 | 功能可运行 |
| E1 模块/受控原语 | 算法、边界、异常和特定竞态 | 已接UI、真实提供方或账号 |
| E2 本机HTTP/文件 | 真路由、数据库、解码和隔离 | 真实人声、平台权限或目标GPU |
| E3 真浏览器/本机程序 | 实际上传、渲染、音频、窗口流程 | Windows、4060、画质接受或真实房间，除非实在该环境执行 |
| E4 目标机/真实提供方 | 实际Windows设备、GPU/模型、录音、平台连接及失败恢复 | 人工喜欢效果或长期关系质量 |
| E5 用户体验接受 | 同素材视觉评审、自然聊天与听感、实际使用接受 | 没测过的设备、账户或无限兼容 |

只有该需求所需的每一道门均有可复现结果，才标`COMPLETE`。`IMPLEMENTED`、`LOCAL_VERIFIED`、`BLOCKED_EXTERNAL`和`NOT_RUN`分别保留，不相互替代。现有191项Python、26项前端Node、PNG Chrome与Linux整包结果仍有效于各自记录版本和范围，不能覆盖本轮新模块。

## 必需需求与未过的门

| ID / 需求 | 当前已知证据 | 完成必须看到的结果 / 指标依据 | 当前状态 / 负责人 |
| --- | --- | --- | --- |
| R01 Windows10/11可运行 | 本地构建材料、PowerShell解析；GitHub未分配runner | 同一源码完成编译、解压启动、重启、退出无孤儿进程；分别记OS/build/CPU/GPU/显存/驱动、版本及报告；干净环境依赖失败有准确提示 | `BLOCKED_EXTERNAL`：等待实际Windows构建报告；desktopHost+用户 |
| R02 自助PNG与独立身份 | 真PNG模块/HTTP/Chrome、迁移与关系隔离 | 不编辑源码即可导入→预览→启用→换皮保关系→独立身份隔离→回退/删除；失败保留当前角色；Windows再验 | `LOCAL_VERIFIED`：本机PNG层通过，目标机未过；root+QA |
| R03 自助动态VRM | 两份自有不同结构VRM0/1、9项导入/资源HTTP及19项真Chrome；真framebuffer有模型像素，RMS口型/释放/回退通过 | 声明的VRM0/1版本、两份不同结构合法模型可导入预览/启用/回退；真WebGL显示、眨眼/视线/口型/停止收敛；坏包拒绝、context-lost/超预算回退、旧renderer释放；目标机再验 | `LOCAL_VERIFIED_PARTIAL`：SwiftShader并非4060，目标机未过；pngAgent+frontend+root+QA |
| R04 高质量角色表现 | 原创42源同源PSD/硬杯r2；实际34cloth、5000杯形、三景主UI及root内部视觉基线接受；仍无用户E5 | 使用有权运行的同一高质量模型、固定机位和尺寸比较眼/发丝/轮廓/透明边缘/灯光/表情；记录用户接受；小窗/展开/隐藏在4060记录帧时间p50/p95、GPU/VRAM与常驻开销 | `NOT_ACCEPTED`：30/60fps只是候选值，未冻结；frontend+用户 |
| R05 自然聊天与角色一致 | 当前Qwen3-4B记忆off真实恢复轮成功；历史单轮有漂移；当前尚无30场景人工质量评分 | 旧Q01：30条独立场景、记忆关/无关两组，记录接受率、追问/说教/虚构和角色一致性；同提供方A/B；通过门槛先据基线与用户评分冻结 | `NOT_ACCEPTED`：真实生成不等于自然；voiceAgent+root+用户 |
| R06 自然中文语音 | 当前真实Kokoro→实际Audio/Analyser/Core口部通路成功，独立24kHz/5.716625秒WAV可审；真人听感未验 | 真实目标机本地合成/播放，选定合法音色，短句/长句/标点/中英混合/失败重试；听感人工评分；旧Q05至少100轮测话尾到首个可听音频p50/p95，门槛待同机基线 | `PARTIAL`：Windows通路、听感和100轮未过；voiceAgent+desktopHost+用户 |
| R07 本地ASR与语音轮次 | 真实HTTP→faster-whisper tiny CPU已识别2.683秒Kokoro合成WAV，单次HTTP1.762秒；9项应用HTTP及缺模型不采音/不转在线Chrome门通过 | 明确本地提供方/模型与许可；固定WAV真识别、空白/噪声/超长/坏格式拒绝；用户开启麦克风后实采，显示实际听/想/说状态；无未经选择的音频外发 | `LOCAL_VERIFIED_PARTIAL`：非真人、非Windows，无麦克风实测；voiceAgent+frontend+root |
| R08 可打断与晚到拒绝 | nonce/晚到/ABA等15项HTTP历史回归；当前硬杯r2真实恢复轮停止0.793秒、700ms无复活、未听尾不入prompt | 旧Q02：100次目标机真播放，停止后复活0，本机暂停p95候选≤300ms；区分播放暂停/后端取消，丢弃旧代音频；处理未听部分上下文；说话期间新输入/切角色/隐藏/断线均测 | `LOCAL_VERIFIED_PARTIAL`：历史慢TTS迟到、ABA与旧generation停止误伤新播放反例均已修并独立回归；目标机100次未过；所有音频层 |
| R09 记忆可关、关系可控 | 每角色SQLite/遗忘/按需记忆；当前真实Qwen恢复轮memoryoff且memories0，停止后未听助手尾文不入prompt | 关闭长期记忆不检索/不自动新增，用户明确手工保存/删除另按其操作；当前对话仍自然；忘记/备份恢复不复活已遗忘内容；20条私密canary不出公共端；跨角色0串库 | `LOCAL_VERIFIED_PARTIAL`：新入口整合需回归；root+QA |
| R10 主动联系可控 | proactive开关、安静时段、暂停旧约定 | 默认不主动；开关/时区跨日/静默/冷却/未回复次数/重启/离线恢复有实测；关闭后无排队晚发；发送动作按准确渠道和目标授权，不从公开消息取得权限 | `PARTIAL`：新渠道不可用模块测试代替发送验证；root+catalogAgent |
| R11 哔哩哔哩官方接入与弹幕 | 已选当前官方OpenLive路线；接收实现及本机对端测试，公有prompt不含私聊/人格/记忆canary；公开停止/私人接管HTTP已验，输出仍为local_preview | 当前官方接口与授权房间/凭证配置；真实消息/重复/断线/洪峰/停止/重连不过期补播；公开输出与私聊隔离；有界队列报告覆盖率，不能只报“不崩溃”；若另需特定弹幕姬再列其兼容门 | `LOCAL_VERIFIED_PARTIAL`：真实房间/凭证未过，OpenLive不冒充另一个软件SDK；catalogAgent+root+用户 |
| R12 微信ClawBot文字与音频文件 | 用户已接受该降级范围；应用私有worker/批准/claim/音频附件/ACK/去重/轮换/重启已在本机HTTP验证，无实际微信收发 | 固定ClawBot及适配层版本/资格，指定本人可控测试会话；真实文本与音频文件收发、重试去重/离线/关闭/凭证保护；用户明确允许具体目标的实际发送后再测，不用本机自回显冒充微信送达 | `BLOCKED_EXTERNAL`：真实账号接入/目标/凭证未给出；原生语音可选且未支持；catalogAgent+用户 |
| R13 4060/32GB资源与并发 | 用户自报4060/32GB；当前LinuxCPU恢复轮Python进程峰5,631,388KiB，非整机/非Windows；实际首音观测69.621秒非p95 | 真实设备探测；同模型与场景空闲/小窗/展开/LLM+ASR+TTS并发30分钟，完整进程树RSS/VRAM/CPU/GPU、p50/p95首声与帧时间；一份LLM常驻；隐藏暂停渲染；CPU/CUDA实际支持单列 | `BLOCKED_EXTERNAL`：硬件诊断与目标机运行未取得；desktopHost+QA+用户 |
| R14 安全、恢复与可交付包 | 当前780Python/111Node/desktop9+27及327源SHA稳定；runtime/source候选双ZIP格式/源身份与真实Core各自有证据 | 新模块无公网读取/任意执行/路径越界；损坏模型/设备丢失/账号断连只降级模块；旧数据源不改；整包依赖/模型SHA及许可清单，缺许可处理明确；重启不重复发声/发信/执行；可回到上一个可用修订 | `IN_PROGRESS`：模块与整包分别过门；全体+QA |
| R15 自助Live2D运行包 | 当前原创硬杯r2真实Core/新47点/v1无helper、13手杯门与5000形状/抓点、真实语音7门均过；不是官样例或假MOC3头 | 真正Core和固定显示框架+合法可运行模型完成预览/启用/参数/播放/停止/释放/回退；不把自造MOC3头结构夹具当可播放模型；Windows另验 | `LOCAL_VERIFIED_PARTIAL`：本机Core播放通过，任意导出兼容/目标机未过；公开发布/Expandable许可单列不推定；catalogAgent+frontend+QA |

## 准备与测试次序

1. **已完成准备**：阅读旧计划、视觉标准、当前交付与已知缺陷，建立本账；保留历史记录版本和证据等级。两份自有合成VRM、8份结构坏夹具与1份渲染拒绝夹具已生成并实际使用；几何测试不代表最终美术。
2. **模块就绪后**：E1核解析/权限/预算；E2用临时数据库与真HTTP测试预览不启用、跨身份、取消、坏资产、凭证及公开/私密边界。LLM/ASR替身明确标注，不算真实模型门。
3. **UI就绪后**：真Chrome文件选择、GLB加载/WebGL截图、状态驱动、切换释放、context-lost/回退、360/390/1440布局与XSS；记录实际WebGL renderer。SwiftShader只证明软件渲染路径，不证明RTX4060性能/画质。
4. **真实提供方**：有合法样本与本地模型后用固定WAV测ASR/TTS；目标机验证实际麦克风、声音、桌面与并发资源。公开直播/微信实账号动作只在具体入口和目标获准后执行。
5. **最终体验**：同素材视觉与30场景自然度、100次中断/100轮语音指标和30分钟资源对照；未通过项保留失败证据、责任人及回退。没有真实门结果，不签“全部完成”。

本轮独立实际结果：导入/Live2D缺runtime及JSON资源HTTP **9项**、应用ASR/runtime HTTP **9项**、平台边界HTTP **10项**、播放上下文HTTP **15项**、真Chrome/WebGL与设置 **19项**通过；另一次真实ASR HTTP识别通过，真实授权Core的独立Chrome **12项**与动态prompt容量代码绑定 **3项**通过。历史慢TTS乱序及旧代停止反例均保留红测日志，修复后独立15项全绿。平台HTTP全为本机适配器，浏览器AI/声音主流程使用替身和真实测试音，真实Qwen/Kokoro整链已另以未替换推理的真Chrome录像通过；这些数字不是全量项目完成率。证据分别为`review/vrm-browser-check.json`、`review/asr-http-real-check.json`及`/workspace/research/*integration-http-run.log`。

实际修正：失败VRM预览曾在error后被resume重新启动空RAF，已修并以700ms帧数不增长验证；ASR设备/精度分别合法但组合不合法曾被保存，已由真HTTP红测证实，修后9项通过；重启微信自动批准曾与安全默认冲突，现恢复绑定但关闭auto_approve并有真HTTP验证。测试材料也修正过：VRM1的CC0链接应放otherLicenseUrl，licenseUrl使用VRM1规范；Playwright对label内option的is_disabled会指向select，须测原生option.disabled及`:disabled`。这些材料/框架问题没有冒充产品缺陷。

公开生成另修：原先只监听进程关闭，停止B站或私人接管不能取消；现在有独立live generation和取消event，停止后即使提供方不配合也不追加预览，协作提供方可让私人会话接管。若不配合则私人等待上限后明确409，不能声称强制杀停已发生。该三类真实HTTP边界已验。官方入口的本机手动预览使用30秒有界TTL，区别于原离线入口8秒；这是兼顾本机CPU推理等待的工程候选，不是官方平台SLA或目标机性能结果。

## 仍需外部条件的具体事项

- **Windows**：运行完整本机构建脚本，取得实际构建JSON、原生/桌面报告和机器诊断。当前云端没有用户Windows控制通道；脚本存在与用户说有电脑都不是运行成功。
- **高质量视觉**：可合法导入的目标动态模型及可比场景；原参考截图不是已授权可分发模型。自有测试几何能验证加载，不能代替用户画质接受。
- **B站**：用户已确认有可管理房间并选择当前官方接口；仍缺房间ID、该入口的appID/accessKey/secret/anchorCode等实际配置及限定测试动作，凭证应在本机主人界面配置。若另要兼容某个第三方弹幕姬，才需该软件名称版本；不把它当已选官方路线的前置。不能由“可管理”补造凭证或声称已连接。
- **微信**：ClawBot与音频文件范围已选；仍需实际账号的可用接入/适配版本、本人控制的测试会话及对应凭证与具体外发允许。只要能POST到本机适配器不算完成。原生语音条已从必需范围移除，但仍如实显示未支持。
- **动态格式**：Live2D本机评估已获准，本机Haru真实Core播放已验，任意导出兼容与Windows结果仍待验；公开发布/Expandable不在此次许可同意之内。AR/MC仍是候选，不要求额外连接游戏或摄像头。

这些事项阻断对应真实门；其他软件、夹具、回滚及本机测试会继续，不用泛泛“批准继续”代替具体工作。

## 依据与审查

一手项目依据：用户指令与2026-11-12设备自报；[修订计划Q01–Q10](revised-plan.md)、[自助角色计划](self-service-characters-plan.md)、[视觉目标](../design/visual-quality-target.md)、[现行架构](../design/architecture.md)、[Windows准备报告](../../review/windows-local-build-preflight.json)、[原生后端记录](../../review/character-native-check.json)、[PNG独立审查](../../review/character-implementation-review.json)。旧计划中的“设备未知”“尚未实现PNG”保留为当时快照，本账采用已确认的新事实。

独立检查重点：格式支持≠画质接受；CPU/SwiftShader/Wine≠4060/Windows实测；替身与回放≠真实提供方/账号；新增入口必须沿用身份、generation、媒体权限与失败回滚。当前没有足够证据宣称所有用户要求完成。

本轮新增代码绑定容量检查：`tests/test_prompt_budget.py`以确定性替身tokenizer验证2048/4096设置均影响历史裁剪，保留最新用户、预留实际max_tokens+256，单条超容量明确报错而不截断。此项不是Qwen tokenizer精确预算或超长真实模型质量测试。独立授权Core报告见`review/live2d-independent-browser.json`，录像与截图留在本机SDK评估目录，不构成可公开分发素材。

## 最终真实模型整链与证据

已在冻结源码、隔离数据目录、长期记忆关闭下完成一次完整的真实应用HTTP→Qwen3 4B→Kokoro→HTMLAudio→VRM RMS口型→停止→SQLite回执→下一轮prompt验证，6项通过。源码SHA前后相同，未用替身替换生成或合成，浏览器外部请求0，未使用麦克风、真实微信或直播房间。

最后一次单次Linux CPU/SwiftShader观察：首文字22.754秒、回复24.862秒、首次观察到音频/RMS30.898秒、点击停止到媒体静默0.127秒。实际Audio停止回执为0.533333/2.656秒、confirmed_text为空，下一prompt不保留未听回复。推理进程峰值RSS为5,546,508KiB，不包含完整进程树。这些是单次观察，不是p95、目标机预算或4060测量。

实际证据目录：`/workspace/dist/evidence-companion-real-20261112-163732/`；已检查35.4秒1440×1000 VP8真实过程录像与4张截图，实际播放/停止截图已人工查看；原始Kokoro输出为2.656秒PCM16/24kHz/单声道WAV。录像不含系统音轨，原WAV另附。原始几何VRM只是自有蓝色测试块，不能作为最终角色美术或自然度验收。机器报告`review/real-companion-browser-check.json`附可复跑命令、源文件/模型/证据SHA与边界；局部打包为同名目录`.zip`。

两次采集失败都保留：停止后读取旧Response.body得到空文件、再用fetch(blobURL)被现有CSP拒绝；对应功能门与失败原因单独记录，未冒充产品失败或删除红测。最终只在测试init保留createObjectURL的原Blob引用并直接读arrayBuffer，先经192,044字节真实测试音/CSP小测通过，产品CSP未放宽。

最终独立可执行检查以`review/quality-gate.json`及`review/quality-gate-post-harness.json`为准：全门禁与采集harness调整后默认门禁均通过；有界状态穷举证明只覆盖建模范围，不是全程序或真实平台的形式化正确性。Windows、真实房间/ClawBot、目标GPU资源及人工画质/听感/自然度依然未通过，对应需求保持未完成。
