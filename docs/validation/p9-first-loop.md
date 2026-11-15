# P9 第一条本地节目闭环：实现与证据

状态：本地短场景完整播放已验证；真实长输入验收失败。发布阻断，未交付Windows成品。本报告不以测试/提交数量作为完成标准，也不把正确拒绝等同实时答复成功。

## 冻结范围与来源

运行起点 PR48 3af7f876ebe10d814e9c17a793c14879cfb4c7f8，tree dd09e659eff0b812ffd14412d38f12171147393f；管理起点fa278f308e5d2930d4f2176e31549c12f04ac212。独立实现分支impl/p9-approved-program，原检出/用户未提交材料保留。本轮仅B节目输出、C主播状态及被真实测试发现的初始化隐私问题；技术v1见 [契约](../project/interaction-contract.md)。

产品目标为Windows10/11、RTX4060、32GB。本次实际环境Linux6.18.57、Python3.12.14、Chrome157.0.8103.78/SwiftShader、CPU Qwen3-4B Q4_K_M（llama-cpp-python0.3.36）、Kokoro/ORT1.32.0。没有运行Windows PE、显卡卸载、OBS、B站或观众端。没有OpenAI真实API结果。正式Core安装/许可元数据没有在此环境恢复，测试使用既有来源已记录字节的读取夹具，未绕过生产安装校验，不叫发行许可通过。

| 原始项 | 已取得/直接观察 | 未取得/不能推断 |
|---|---|---|
| 最初标准原图 | 历史Library引用存在；本轮未取得可核验原始字节 | 不声称本轮已亲眼复核标准图，不以R3包或文字描述替代 |
| 角色包R3 | ZIP SHA256 ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d；实际Core/MOC运行 | 不是标准原图、补画前素材或最终眼部可编辑来源；原始PSD/Cubism工程链未核实 |
| 角色动作 | 上半身Idle12秒，CupLower恒0/CupVisible恒1；源包未变 | 不使用放杯包，不证明人体/眼睑审美合格 |
| 用户长输入 | 原对话文字原样回放，模型完整输入/输出及时间线 | 不是实际观众或未见学习任务 |
| 正向问候 | 沿用旧tests/local_product_browser.py的既有QUESTION，来源hash另存 | 独立正向样例，不替换长输入失败，不是学习收益 |
| 模型/声音 | 固定既有3权重SHA；实际WAV、WebAudio分轨、双端未剪辑录像 | 没有系统声卡、OBS或观众收到证据，未作青春感盲评 |

源文件hash、环境恢复、原始事件/输入、服务audit、截图、未剪辑录像和实际音轨在私有证据包内。SDK/模型/权重/数据库/凭据不入GitHub或证据包；原件留原路径。Trace交付为脱敏且省略响应体/源码快照的审查副本，不冒充完整原始Trace。

## 问题—实验—根因—最小修复—结果

| 问题 | 区分实验/可推翻条件 | 证据支持的根因 | 修改与结果 |
|---|---|---|---|
| 批准节目没有人物，样稿不会随回答说话 | 从产品入口跟同job的DOM/Core/字幕/音轨；若原已绑定则推翻 | room私有预览与live-stage节目分离 | v1冻结当前身份/外观与白名单资源，逐条批准绑定job；真实Core、同job字幕/音轨/口型已观察 |
| 未启动音频却报playing | 强制audio.play/AudioContext/source拒绝，核服务audit | 原回执先于实际媒体活动 | 等AudioContext running及play成功才回执；旧红、新故障回放拒绝假playing/completed |
| 暂停/停止后晚回包覆盖状态 | 延迟playing/completed/scene/音频并换job或停止 | 异步边界未统一检查播放世代 | epoch、playSerial、bootEpoch及mediaStarted守护；旧暖场景、晚完成、晚音频不复活 |
| 回执丢失被空poll掩盖 | 丢completed响应，等待后续空poll | terminal提示未持久保留 | 保存lastTerminal，真实新回放持续显示未确认，不伪造成功 |
| 主播需手动刷新，整页重绘会吞草稿 | 同job终态、保留密码/草稿/焦点/选区；注入假BC状态 | 未订阅已有权威state，整render重建表单 | 复用原5秒core.refresh与局部更新；BC只提示重读，浏览器机械检查通过；兜底仍约5秒，无真人收益证据 |
| 字幕挡住手杯 | 同尺度旧截图与新1024/1280真实边界检查 | 旧全宽字幕与人物区域相交 | 字幕限左区；原包不改，新版未遮杯。只是布局机械改善，不是最终审美认可 |
| 已必然播不完仍会起播 | 实际WAV时长与剩余期限对照，等长/±1帧/等待后claim/audio与恒true坏实现 | 只检查“尚未过期”，缺完整音轨下界 | ready/claim/audio严格remaining×rate>frames；无效WAV/不足失败并丢音频，旧红和坏版本仍红；不延TTL、不重复扣playing整段 |
| 同一超期回复有时显示失败、有时显示过期 | 假时钟同begin100/expires130/now131，仅改变是否先status/reap | fail路径不先比较deadline，分类取决于读者刷新与异常收尾谁先执行 | 固定31秒浏览器回放先红，非终态fail在deadline处按expired收口并清音频，未到期仍failed、已有终态保持；23项状态单测与同判据新回放通过，不把failed放宽接受为expired |
| 感知引用随机被下游拒绝 | 固定生成leading -/_的真实HTTP观察，再引用/停止；未授权和action前缀仍须拒绝 | perception允许的URL-safe引用错套首字符必须alnum的action校验 | PR51仅TrustedObservation三字段精确匹配生产者契约、不trim；旧两红、新96项相关回归绿，最终全门绿 |
| ORT初始化产生未授权遥测 | 源码/二进制/[官方同版文档](https://github.com/microsoft/onnxruntime/blob/v1.32.0/docs/Privacy.md)与初始化次序；env0反例 | import后API关闭晚于native初始化，独立CPU/CUDA probe漏入口 | 初始化前强制ORT_DISABLE_TELEMETRY=1，backend/server/voice/probe分别覆盖；旧红/新绿。测试仅lo；不能称Windows全系统零网络 |

每项独立提交可回退。节目白名单不含question/material/topic/recent或未知内部字段；输出令牌仅POST限定场景资源，不放宽私有cookie接口。未批准、取消、过期、身份/外观/话题变化仍用已有状态机失效链，无新后台轮询/线程/产品依赖。

## 当前实测与失败记录

**最终质量门**：`.build/p9-root/quality-observation-contract/report.json` passed=true，164.905秒；909 Python、10桌面Python、161前端Node、28桌面Node全部通过，无跳过；384源码指纹在检查期间稳定，且最终真实播放后再次比对无差异。source_commit为a5b738144825346f9f734a8111f8edebc8314d60，tree0630ff12b78c468eb41582ff96a8d97f1133b8cc。源文件与远端等tree映射在交付清单中。下列旧门禁保留历史，不能合并成同一当前版本。

### 完整质量入口

首个冻结2bc4a68报告 `.build/p9-root/quality-budget-final/report.json`：9类入口全通过，172.28秒，383源码指纹前后不变；901 Python、10桌面Python、158前端Node、28桌面Node均通过且无跳过。负控制子进程故意产生FAIL文本不代表外层质量失败；判定以report的退出码、passed及源码稳定为准。strict typing仅配置的10模块，架构约束/采样不等于全程序形式化证明。

过期修复阶段的质量报告（非最终全部源码）：`.build/p9-root/quality-reviewed/report.json` passed=true，174.164秒，905 Python/10桌面Python/158前端Node/28桌面Node，9入口全部通过、无跳过、383源码指纹稳定。报告source_commit为父2bc4a68，新增修复实际字节由source_sha256及最终源码绑定清单确认，不能只看父标签。

### 真实模型/TTS正向

最终同版独占轮 `.build/p9-root/real-current/result.json` passed=true（产品a5b7381，harness8a92291b）：既有问候“刚进直播间，晚上好！”，模型预加载10.799秒（事件前），推理12.263秒；生成至审核12.706秒；TTS8.846秒；批准至媒体开始9.747秒；WAV111632帧/24000Hz=4.651秒，SHA243ca4dea14439c74c3083a670dd3454493176d32b686a32bc4e3cd60a01f592。实际ended后服务与主播端均completed，native连接/桥接失败均空。测试自动执行主播的逐条批准操作，不等于真人审核成本或用户认可。

另保留同原问候的失败 `.build/p9-root/real-positive-terminal-fixed/result.json`：推理56.717秒超30秒，未TTS，35秒等待批准超时。该轮root并行做了多次源码读取命令；随后安静轮`.build/p9-root/real-positive-quiet`正常绘制、同配置推理14.049秒/TTS7.162秒、完整完成。仅支持隔离编排负载是应控制的实验条件，不能单样本确认精确原因或保证并行负载稳定性。最初短题旧成功12.711秒另存历史摘要，不覆盖失败。

这是合成事件经过真实provider适配器的本机测试；实际模型输入/输出未伪造。测试固定seed42、直接provider适配器不等于正式随机流式推理全部路径，更不等于答复自然度、学习掌握、扬声器或观众收到。Playwright视频无音轨，原WAV与WebAudio捕获单独交付。

### 真实长输入失败，不能叫预算负向通过

`.build/p9-root/real-long-negative-final/result.json` passed=false。原长输入未改；同模型生成30token用了37.853秒，超过原30秒。服务audit为generating→expired，未进入review/TTS/ready/claimed/playing。测试原本等批准按钮35秒，因而超时；收尾出现route TimeoutError。未取得该轮主播过期UI完整观察，不能凭内部job状态补写为UI通过。

之前中断记录另有推理15.160秒、TTS11.349秒、WAV10.922秒，下界37.431秒；那轮因未授权ORT遥测被自动审核拒绝，未有完整result。残留WAV/截图不叫实际播放完成，保留原失败。两个失败都不以短问候成功覆盖。

区分实验 `.build/p9-root/long-provider-diagnosis.json`：原长题完全相同messages、模型参数和seed，移除Chrome/HTTP后单次推理12.170秒，进程CPU75.236秒，加载2.958秒，输出和token数完全一致。支持继续调查浏览器/共享负载/冷热环境差异，不能单因素确认“就是浏览器”或给Windows延迟承诺。尚未找到稳定长题实时收益，不能发布为完整现场应变产品。

### 确定性音轨与故障回放

最终同版`current-faults`：20项通过（原`playback-budget/positive-drained-final`保留历史），真实Core+确定性3秒音调完整ended；`negative-drained-final`：31秒音调被预算门拒绝，playCalls=0、空字幕、口型0，主播显示具体原因，8项通过；`preflight-drained-final`：11项通过，外站/302拒绝，三轮native连接和桥接失败记录为空。真实模型与确定性结果分开。

过期UI独立31秒慢provider回放首轮 `.build/p9-root/generation-expiry/only-lo/result.json` 严格失败：HTTP409已说明过期，但audit为generating→failed，37秒内DOM没有expired。它拒绝了当前代码，不能放宽判据把failed当通过。假时钟单因素支持终态分类竞态，修复与复跑：新`generation-expiry/observer-verified/result.json` passed=true：实际31.006秒provider延迟，32.955秒主播同job显示已过期；连续非空DOM时间线[generating,expired]，无批准按钮，实际409且TTS/audio请求/play均0，字幕空/口型0，晚轮询不复活。中间`fail-deadline-fixed`虽原报告passed=true，但DOM记录为空，被coverage-rejected.json拒绝，不能作为最终通过。测试观察器改绑稳定父节点且强制非空；原判据与31/37/35秒均不改。它不替代真实长题失败，也不是实际WAV预算测试。

测试夹具修复亦保留红：APIResponse传递大纹理避免Python复制跨原1秒门；阻止带Location的3xx在context.route之外跟进；仅在全部产品断言后drain pending poll再关闭。driver-final先前passed=false/原生loopback收尾记录保留。drain不证明生产硬关闭/pagehide或原生HTTP已验证，ptrace被拒未绕过。only-lo新namespace与初始化前禁用提供隔离/策略证据，不宣称native零syscall。

### 开销与尚未证明

20MB最大音频7次Linux夹具：旧ready中位16.05ms，新22.10ms，最高27.20ms；纯验证中位1.80ms，额外Python峰值约20MB。只是单机样本，不是Windows/SLO或部署容量。模型、声音和角色同负载的长题时效仍有限制。

| 维度 | 当前结论 |
|---|---|
| 代码/机械约束 | 冻结质量入口、状态/HTTP/浏览器及坏版本反例有证据；最终报告以上述实际文件为准 |
| 根因解释 | 节目分离、媒体顺序、异步世代、预算缺失、初始化次序、终态分类、加载恢复与引用ID契约有实验支持；长题性能差异未确认单一根因 |
| 视觉/青春声线 | 原包未改、字幕不遮杯；审美和声线没有独立盲评，仍待认可 |
| Windows同版制品 | 未完成；旧ZIP不同版，不能当当前成品或让用户验半成品 |
| 实际播出/观众接收 | 未验证；本地回执不替代OBS/系统轨/观众端 |
| 学习/现场任务收益 | 未见任务、目标主播/观众和外部专业复跑未取得；未证明 |
| 用户认可 | 未取得，发布阻断 |

补充原始截图观察：`generation-expiry/observer-verified/02-host-expired.png` 的主播过期标签和具体409原因可见；同帧宿主页底图中杯子因近裁不可见，且仍有“正在准备形象”提示。节目页半身输出另有图。随后真实controller的deferred engine/load三时点实验支持两条状态断点：模型创建前隐藏阻塞同key重试，load中隐藏跳过ready/缩放结算；after-ready正控通过。Node桩隐藏帧增量0，不支持据此认定隐形渲染；真实Core恢复复测进行中。几何近裁原因仍未确认，不把C的状态控件检查推广成整个UI通过；该项进入后续同负载/宿主形象对照。

### 宿主加载恢复与独立ID修复

`app/static/scene-controller.js`仅7行差异：engine加载时被隐藏而未创建实例，释放可重试key；模型load/首帧成功后的ready/scale结算与visibility分开，隐藏时不接音轨。旧三时点Node2红1正控，新3绿，相关64项Node回归绿。真实宿主`.build/p9-host/scene-core-modal/result.json`六项通过：实际加载前开“相处方式”面板→返回后ready、加载标签退出；已ready开面板frames/Core均57→57，返回后59；同Canvas、模型JSON仅1次。截图中半身/双手/杯可见，只证明此1440×1000 Linux条件，未做全部几何/视觉验收，不把它归因为模型变慢。原始Core/runtime读取仍是fixture，正式安装另验。

`.build/p9-root/quality-scene-recovery/report.json`曾整体失败，来源稳定，唯一失败为观察引用的随机400。PR51通过强制leading -/_的服务端会话/观察生成与真实HTTP引用，确认生产者/消费者契约不匹配；没有改随机数躲问题或放宽限流。三个可信引用字段精确使用`[A-Za-z0-9_-]{1,100}`且不trim，通用action/request/runtime规则及权限保持。96项相关回归通过；一开始共享fixture触发限流的记录亦保留，后分独立fixture而不改产品限流。

## 复跑与回退

先按环境清单准备相同SHA的既有模型、R3、已授权Core/Framework；不从本报告自动下载或接受许可。质量：

```bash
QUALITY_PYTHON=/path/to/quality-venv/bin/python
TEST_PYTHON=/path/to/runtime-venv/bin/python
"$QUALITY_PYTHON" scripts/quality_gate.py --full --test-python "$TEST_PYTHON" --report evidence/quality.json
```

实际本轮完整命令、隔离launcher、环境、输入来源及源码/远端tree映射随证据包交付。模型验收须独占执行并只等待原会话；不要同时跑其他回归、Agent命令、源码导出或证据打包。保留并行负载失败，安静轮不代表并行工作负载通过。Linux隔离验证使用新user/net namespace且仅lo，不改变宿主网络；Windows复跑另需正式安装/运行库与目标机，不能照抄Linux隔离命令当Windows通过。

生产修复逐项独立commit；证据包源码补丁以fa278f3为起点，只含源码/管理文档。使用新工作树应用，先保存本地修改；git revert某项需重跑其相关判据，不假定旧版安全。未合并、部署、发布或修改生产配置。

P7三问：接口默认私有renderer路径保留，可选transport和明确节目白名单有兼容测试；取消/过期/失败/晚回包边界有反例；已证实的结构/时序根因已最小修复，长题性能、专业审美与实际任务价值没有假称消除。后续先D原始素材/声线诊断，再E同版候选，最后F真机与独立任务；证据不足不扩大功能。
