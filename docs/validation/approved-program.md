# 单条批准节目：开发验证记录

2026-11-15。目标仅Windows PC；本文记录的是Linux Chrome开发验证，不是Windows、OBS、B站、观众接收、审美或学习收益验收。

## 根因与最小修改

| 问题 | 原始证据与区分实验 | 最小修改 | 已有验证 |
|---|---|---|---|
| room样稿与真正输出分离 | 原live-stage无人物；room固定关闭说话/字幕为手填 | live-stage复用CompanionScene；节目仅绑定当前助手已导入的外观，固定既有right/透明底和carbon文字色组 | 真实R3/Core、同job字幕/音频hash/口型；不是所有room草稿布置已接通 |
| 未开始媒体就报playing | 旧版注入audio.play拒绝，audit仍有playing→failed | WebAudio运行且audio.play实际成功后才发playing；媒体图失败明确返回false | play拒绝、resume拒绝、source失败均不报playing |
| 缺少批准人物/资源边界 | 旧job没有scene，private资源只能用cookie读取 | open冻结当前角色清单；批准绑定scene hash、approval_revision、audio_sha256；POST令牌接口只读固定清单并复核hash | question/未知私有金丝雀不进poll/receipt/scene，越界资源、错revision、篡改资源、切外观、撤权拒绝 |
| 加载/媒体晚响应能覆盖后来状态 | 针对pause与playing回包、completed与下一job/停止、暖scene和audio晚包分别故障注入 | epoch、播放世代、媒体启动与回执接受分别处理；加载不阻塞既有心跳 | 全部固定晚响应反例通过；不延长TTL或心跳预算 |
| 完成文字被空poll覆盖 | 第一轮completion的服务audit已经completed，但节目完成UI检查超时；旧9784cfe在丢回包时又把未确认改成等待 | 完成或回执未确认状态保持到新job/明确重启，显式显示；空poll不覆盖 | 同一冻结源码整段播放，节目与主播均completed；另丢弃completed响应后节目保持未确认，不冒充收妥 |
| 字幕遮住杯/手 | browser-probe-fixed/03-stage-playing.png全宽条覆盖杯/手 | 只改既有right布局字幕宽度，角色/素材不移动、不裁切 | 1024/1280宽、720高：caption与character-space边界不交，无横向溢出；播放隐藏状态提示、撤权显示 |

节目资源transport默认不改变私有页面：原URL仍按当前角色和asset校验，再映射为已校验blob；不放token到URL、不用cookie、不加任意文件代理。只有节目页CSP允许固定安装运行库的nonce脚本，以及已校验blob的connect读取；其他页面仍保持原CSP。没有安装记录/许可的生产运行库路径仍拒绝。

节目无形象时明确显示“未设置节目人物”，保留音频/字幕降级；不将placeholder的ready当人物渲染成功。损坏或不支持的形象停止节目准备，不能冒充角色成功。本轮主线成功证据均使用真实R3/Core。

## 素材与证据来源

- 本次使用既有`R3-Study-Companion.zip`，SHA256 `ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d`。它是已存在的上半身候选，不是眼部最新母稿，也不是新的美术认可；没有修改原素材或恢复放杯入口。
- Core真实字节SHA256 `25ae938cb4fe282ce189b357bcc97e603d1e1f7ec78bf04150d401c23cdc792f`；既有owner bundle SHA256 `0f9bfd8af46da18bc3ef15d940d96d66a7aedf05e7edfa49911b2a65b0f7f81d`。
- 本环境缺少旧生产安装记录，浏览器测试用独立fixture读取上述已存在字节并校验；没有下载SDK、伪造许可记录或绕开生产许可门。真实Core执行不等于生产安装链验收。
- 主输入来自本对话原文；确定性生成是明确的机械复述，音频为PCM测试波形；不是AI回答质量、真实TTS、真实弹幕或新编作品。真实模型/TTS入口单独启用并记录冷加载、实际输入输出、finish_reason、阶段耗时和WAV。

本地开发证据目录（不随公开源码提交）包括：

- `.build/program-output/old-red-recovered/`：旧版playing错误与无人物反例。
- `.build/program-output/browser-diagnosis/`：nonce加载Core成功但blob MOC被旧CSP拒绝的控制台/响应。
- `.build/program-output/browser-probe-fixed/`：原全宽字幕遮杯图，保留作布局反例。
- `.build/program-output/browser-completion/`：服务已completed而节目终态检查失败的红记录。
- `.build/program-output/browser-final/`：1024/1280不遮挡与必要取消故障；该轮片段停止实测0.242秒，浏览器音频峰值0.15625，口型值0.4074；不是目标机中断保证。
- `.build/program-output/browser-final-ack/`：最终同冻结字节整段播放和生命周期故障检查，另覆盖completed回包丢失后保持未确认；完整双端视频、Trace、独立浏览器音轨、原始事件与audit。视频本身没有音轨。旧丢包支路Node反例保留在`.build/program-output/old-completion-ack-red.json`，范围为真实旧源码加fake DOM/fetch/media，不冒充Chrome或外部人工验收。
- `.build/program-output/read-overhead.json`：0/1/100任务、audit500的局部读取开销；100任务owner投影中位约0.83ms、JSON约89.7KB。数据仅本机观察，没有虚构Windows预算；没有新增后台轮询或线程。

Trace包含真实角色/SDK响应及已失效本机临时令牌，不公开提交；模型、SDK、用户数据、音频和录像均不进入源码提交。

## 复跑

已有依赖与固定本地资产路径作为参数；不自动安装或下载。

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_live_interaction test_live_output test_platform_integration_http test_local_rehearsal test_program_output_http
node --test tests/test_character_ui.mjs tests/test_live2d_adapter_ui.mjs
PLAYWRIGHT_BROWSERS_PATH="$PWD/.build/p9-host/pw" PYTHONPATH=src:tests python3 tests/program_output_browser.py --chrome /path/to/chrome-headless-shell --model /path/to/R3-Study-Companion.zip --runtime-dir /path/to/existing/owner-local --out evidence/program --completion --faults
```

`PLAYWRIGHT_BROWSERS_PATH`指向已有录像工具目录，本环境的ffmpeg链接到系统`/usr/bin/ffmpeg`。`--runtime-dir`仅用于显式fixture，内含`live2dcubismcore.min.js`及`build/owner-live2d-runtime.js`。

真实模型与语音应在完整回归结束后顺序运行：使用已配置llama_cpp/kokoro环境，在上述命令追加`--real-model /path/to/qwen3-4b-instruct-2507-q4_k_m.gguf --real-tts /path/to/voices --completion`，去掉`--faults`。冷加载单列，事件仍30秒，length等不完整响应拒绝。实际未运行前不得声称真实推理/整段TTS已通过。

## 剩余边界

源码与确定性本地节目闭环有证据；当前可编辑艺术源链、最新眼部修订、美术/声线独立评审、Windows10/11/4060真机、同版安装包、真实音频设备/OBS、观众接收及学习收益仍须独立验收。浏览器音轨与播放状态不证明扬声器或观众收到。节目布局仅本轮固定right与透明输出；没有把独立预览草稿、其他人物、计时器或更多组件自动公开。

## 真实验收被网络审查中止后的测试入口修订

本次`.build/p9-root/real-completion/`仅有审阅/待播截图、`output-0.wav`和部分视频，没有`result.json`。`interrupted-by-network-review.json`记录该轮不被接受；不能由WAV存在推断实际整段播放完成，也没有继续未知旧会话。

产品`synthesize()`原已在创建Kokoro前调用`onnxruntime.disable_telemetry_events()`；本次没有重复增加相同代码，也不将未知Microsoft请求归因为ONNX。只修改`tests/program_output_browser.py`：

- 添加显式Chrome后台网络抑制flags、精确fixture端口的页面route、阻断WebSocket和service worker，以及Python socket审计guard。未知页面目标与Python目标在请求前拒绝并仅记host/port，不记录认证头或完整URL。
- 保存Chrome私有NetLog以观察原生连接；该观察不是操作系统抓包。Python audit只覆盖Python socket调用，不冒充已阻断native ONNX/C的网络调用。
- 初轮flags、IPv6Override、V3禁用、V2禁用的原生HTTP预检均保留failed：唯一公共目标为IPv6 reachability UDP探测，结束`net_error=-109`、未观察到发送字节；不能说已经外传，也不能认定它就是此前Microsoft请求来源。V2禁用确实改为legacy transport，但仍出现该探测，因而没有放宽门槛或白名单公共地址。
- 新增显式`--loopback-fixture-transport`，默认模式不变。仅精确本轮`127.0.0.1:port`请求由测试入口转发到同一真实HTTP服务再fulfill，保持该请求自身的method/body/auth/cookie及响应CSP/nonce/Set-Cookie，不借owner凭据、不创建通用代理服务、不修改系统或产品网络。所有其他目标仍拒绝。
- 在冷加载完成、模型输出、TTS文件、实际媒体开始和终态原子保存`progress.json`。它始终标明`acceptance_report:false`且移除`passed`，被中断时仅表示最后检查点，不是成功报告。

最终无模型预检见`.build/p9-root/offline-preflight/final-transport/offline-preflight.json`：32次严格loopback fulfil，64次Python本机解析/connect，阻断页面和Python外部负控；owner cookie、无cookie节目端401、CSP nonce与检查点原子性均通过；NetLog原生连接列表与外部目标列表均为空。没有加载Qwen或Kokoro，这不是新的真实推理/语音验收。

该显式transport可验证真实Chrome渲染、Core、音轨及真实服务/模型结果；本轮`native_browser_http_verified:false`，不能冒充浏览器原生HTTP传输通过。原确定性直连证据另存。原生NetLog、Trace和临时本机凭据只留私有证据域；对外交付仅脱敏摘要。

预检命令：在原参数后追加`--offline-preflight --loopback-fixture-transport`，输出到新目录。root批准的新真实执行应在原`--real-model/--real-tts/--completion`命令后显式追加`--loopback-fixture-transport`；如果仍出现未授权外连，应停止并保留progress，不放行或改门槛。

本次来源指纹核对仅`tests/program_output_browser.py`变化，`app/`和`src/`与原完整质量报告相同；旧报告不冒充新测试入口的完整验证。新入口Ruff与离线预检通过，完整质量门及真实执行仍由root顺序重跑。

方法来源：[Chrome官方工具flags](https://github.com/GoogleChrome/chrome-launcher/blob/main/docs/chrome-flags-for-tools.md)、[Chromium DNS与IPv6探测](https://github.com/chromium/chromium/blob/main/net/dns/README.md)、[实际V2连接分支](https://github.com/chromium/chromium/blob/main/net/socket/transport_connect_job.cc)。当前本机driver默认禁用feature列表已完整保留；flag出现本身不作为生效或全进程无网络的证明。

## ORT 1DS 初始化前的隐私修复

第二次真实执行`.build/p9-root/real-completion-offline/`仍被未授权Microsoft遥测外连审查中止；只有`progress.json`到`tts_output_recorded`，没有媒体开始、终态或`result.json`。Chrome无模型预检的空native列表不能排除另一个native进程/库，也不能用于声称这次真实闭环通过。

本机实际安装的ONNX Runtime 1.32.0 native二进制包含`OneDsTelemetry`、`ORT_DISABLE_TELEMETRY`及`mobile.events.data.microsoft.com/OneCollector/1.0/`；其同版[官方Privacy.md](https://github.com/microsoft/onnxruntime/blob/v1.32.0/docs/Privacy.md#disabling-telemetry)明确：导入后调用disable API只抑制非必要事件，初始化事件可能更早发生；初始化前设置`ORT_DISABLE_TELEMETRY=1`才禁止1DS uploader、事件和持久ID。CPU provider不排除进程级1DS。该源码/二进制吻合是具体可修的初始化缺口，不是对两次被拦请求的抓包归因；原请求内容仍未知。

最小修改：`desktop/main.cjs`创建owned backend的环境强制设置该值为`1`，覆盖继承的`0`，不改变父环境、CUDA路径规则或attach外部backend。`app/server.py`启动时在项目模块导入前设置，首次Kokoro加载前重申；`companion_runtime.voice`在任何可选native导入前设置，首次ASR/VAD加载前重申。保留两个原有disable API调用作为后续防线，不新增模块、依赖、模型下载、轮询或性能策略。不声称此变量覆盖legacy Windows ETW，不声称能撤回其他程序预先初始化/已发出的事件。

失败反例与复跑：

- `.build/p9-root/ort-privacy/old-ordering-red.txt`：旧版3个Python测试共5个subcase失败，首次fake ORT导入读到`0`或缺失值；旧晚API没有满足“导入前1”的判据。
- `desktop-old-red.txt`：实际backendEnvironment函数旧源码在继承`0`时失败。Node vm执行该真实函数，未启动Electron；这不是Windows真机验收。
- `targeted-green.txt`：`PYTHONPATH=src:tests python3 -m unittest -v test_voice test_voice_http test_default_live2d_voice`，44个通过；fresh subprocess分别执行server与voice入口，首次fake ORT/Kokoro/Whisper初始化读取值均为`1`，包括用户预置`0`和未设置。fake库测试没有引入native联网。
- `desktop-green.txt`：`node --test desktop/test/runtime-profiles.test.cjs`，3个通过；新增用例包含CPU/CUDA、packaged/dev、继承`0`/缺失的组合，其他环境与父进程不变。
- Ruff：`ruff check --no-cache app/server.py src/companion_runtime/voice.py tests/test_voice.py tests/test_default_live2d_voice.py`通过。

真实初始化复跑：`unshare --user --map-root-user --net -- python3 .build/p9-root/ort-privacy/namespace_init_no_ptrace.py .build/p9-root/ort-privacy`。launcher只在新network namespace通过ioctl启用lo，验证`/proc/net/dev`只有lo、IPv4 route只有表头；宿主网络不变。全新Python子进程继承`ORT_DISABLE_TELEMETRY=0`，导入生产voice入口后实际ORT import读到`1`，保留API调用，再创建已有Kokoro权重的CPU Session，无推理/合成/播放。

`native-init-no-ptrace.json`记录ORT1.32.0、CPUExecutionProvider、权重SHA256 `beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a`；本机本轮import约0.224秒、Session初始化约4.153秒。这只证明硬隔离下真实初始化可完成，不代表生产warm TTS或完整端到端延迟。原`strace`因PTRACE_TRACEME/SETOPTIONS不允许而在初始化前失败，保留`ptrace-unavailable.json`及原stderr；没有绕过或增加capability。native网络调用观测为unavailable，不能声称所有native零attempt或全系统无遥测。安全边界为无外网接口/路由、初始化前env1及API防线；真实整段模型/语音验收仍由root在相同隔离域顺序执行。

时限另记：被中止轮的模型warm输出15.159956秒，TTS外层11.349149秒，WAV262127frames/24000Hz=10.921958秒；即使没有人工确认和播放开销，三项下界37.431064秒已超过原30秒。冷模型load16.964秒发生在事件前，未加进该下界。TTS单一外层计时混合import、Session/Kokoro、G2P、推理和编码，不能全部称为推理。该轮未播出，也不因初始化修复自动声称时限通过；下一步须在硬隔离域分解初始化与warm推理，产品TTL、prompt和成功判据保持不变。

初始化后补做一次经授权的隔离语音分解（不与回归并发）：`unshare --user --map-root-user --net -- python3 .build/p9-root/ort-privacy/namespace_tts_profile.py .build/p9-root/ort-privacy`。使用被中止轮真正的公开model输出、既有同权重与`zf_xiaobei`/1.0音色；不加载Qwen、不运行浏览器、不改生产实现。`.build/p9-root/ort-privacy/tts-profile.json`、`tts-profile.{stdout,stderr}`、`namespace-profile.json`和两份实际WAV保留：

| 阶段 | 本轮实际秒数 |
| --- | ---: |
| ORT / Kokoro / misaki import | 0.223 / 0.186 / 0.553 |
| Kokoro构造（含Session） | 2.549 |
| 其中实际CPU Session构造 | 2.544 |
| G2P构造 | 0.000008 |
| 全部初始化 | 3.512 |
| 首文本G2P / create含推理 / PCM-WAV编码 | 0.808 / 4.249 / 0.000766 |
| 首文本调用合计 | 5.057 |
| 紧接warm同文本G2P / create含推理 / 编码 | 0.0732 / 4.474 / 0.000576 |
| warm调用合计 | 4.548 |

实际首轮初始化加文本约8.569秒；两个输出均262127frames/24000Hz=10.921958秒。`create`含ORT推理及库内处理，未进一步拆分；Kokoro构造行包含Session行，不能重复相加。stderr直接记录jieba首文本字典缓存加载约0.800秒；不能把其构造8µs误称G2P已全部warm。两个实际音频SHA分别为`95b78f2ee4b47f64ab53740d2ed0cb83c8d3c627bc8102107feba62a3c3fe173`、`e280030dbc5b04fa9886b24546820971cfdbb925e7afcd47252c7b91c8d2efd7`，没有替换为预合成回答。此测试测时，不是声线质量/播放/Windows验收。

若仅作跨轮诊断估算，原实际模型15.159956秒+本轮warm4.547719秒+音轨10.921958秒仍为30.629633秒，尚未计人工确认/媒体准备；这不是同轮端到端基准，但足以说明“只预热即可保证30秒”缺乏支持。下一步应先用同一完整隔离实测记录过期/终态，再决定最小性能修复，不能改TTL或把此段脱机计时冒充完整节目成功。

## 实际音轨的剩余预算门（不扩大30秒）

上节原长回复仍是失败反例，未改原始输入、生成提示或事件TTL。最小修复只拒绝服务端已知数学上不可能完整播完的起播：`LiveOutput.ready`严格解析实际完整PCM16 WAV，复用`voice.validate_wav`的RIFF/chunk/帧对齐检查，保持原输出20MB上限，并显式采用现有ExternalTTS的0.1–180秒、受支持采样率（含96k）、mono/stereo合同。无效格式/过大文件进入`failed/invalid_audio`，不存音频；没有“解析不了就跳过时长”的分支。

使用真实frames/sample_rate，与server monotonic的`expires_at-now`比较，规则为严格大于（代码用`remaining*rate>frames`）；相等也拒绝。检查位于ready、ready→claimed、claimed→音频字节交付三个边界；每次都在现有输出锁内读取当前时间，不信客户端时长、不根据文字估计、不增加任意margin。预算不足进入`failed/insufficient_playback_budget`、清除音频，owner投影保留`audio_duration_seconds`及该检查时的`playback_budget_remaining_seconds`，供主播辨识。既有C状态标签显示“剩余时限不足，未播放”；B未修改控制台源文件。

`current/reap`仍优先维护stop/session/expiry，晚到TTS不得把cancelled/expired改成预算失败。普通claimed心跳和playing心跳不重算整个音轨预算，避免已播放一部分后误杀；音频请求在尚未发出字节前重新检查。HTTP拒绝不会返回WAV或产生playing回执。网络/解码/设备在最后检查之后的未知开销仍可能导致中途过期；该门是必要的下界检查，不是“任何网络都不会截句”的保证。

固定证据目录`.build/p9-root/playback-budget/`：

- `old-red.txt`：新增同条件真实WAV/假时钟判据在旧版失败（11 failure/1 error）；`unit-green.txt`19项通过。
- `always-fits-mutant-red.txt`：将唯一预算比较故意改成恒true，在独立进程运行**相同**ready/claim/audio三项测试，3项全部失败。测试没有改成新的宽松门槛。
- `suites-green.txt`：交互、输出、平台HTTP、本地演练和节目HTTP合计76项通过。覆盖等于音轨时长、相差一个frame、三边界等待、坏格式/截断/双data/浮点WAV/超20MB、stop/expiry优先以及playing剩余时间小于完整音轨时仍可正常完成。
- 旧共享`tests/test_character_http.wav_fixture`仅0.01秒，不符合早已存在的0.1秒合同。仅把240frame改为2400frame，保持24k/PCM16；0.01秒独立保留为invalid_audio反例。没有为旧夹具放宽生产规则，也没有把夹具自身错误算作产品回归。

最大输入成本见`max-audio-cost.json`：同机Linux Python3.12、20,000,000字节合法stereo48k WAV（104.166秒；仅固定时钟性能夹具，不是生产TTL修改），顺序各7次，旧提交真实ready中位16.05ms，新ready中位22.10ms/最大27.20ms；纯校验中位1.80ms，额外Python分配峰约20.00MB。保留原始样本和旧/新源码指纹；这是本机观测，不是Windows性能门槛或全设备证明。该解析只在ready执行一次，后续预算门O(1)，未新增依赖、后台任务或轮询。

浏览器入口新增显式`--input /path/input.txt`，记录UTF8原文、原字节SHA、绝对来源文件路径及SHA内容版本、实际投递文本SHA；不传时最初长题逐字不变。`--expect-budget-rejection`是独立**负向**验收模式，不能与`--completion/--faults`组合；记录`acceptance_kind:negative_budget_rejection`和`positive_program_completed:false`。确定性负向明确使用31秒机械tone，使其必然不适合原30秒事件；不冒充真实模型/TTS。正向仍要求实际browser media ended→server/host completed，而不是把“成功拒绝”当播放成功。

已有问候输入取自`tests/local_product_browser.py`原QUESTION字面量“刚进直播间，晚上好！”，通过AST提取到`existing-greeting.txt`，原脚本路径/SHA及提取方法另存`existing-greeting-source.json`。它只用于明确合成本地开发验证，不是替换原长回复失败的题目、真实观众或未见学习任务。

仪器先后失败独立保留：`browser-negative`在rehearsal异步start尚未完成时打开token，被后到start按规则取消；现在点击后先等待实际模拟消息输入出现。`browser-negative-stable`未加载Core、画面显示“未设置人物”，当时不能据此认定资产确实缺失或算预算验收；新增初始catalog与节目scene清单观测、提前断言和实际请求字节SHA，不再仅等待60秒或把空角色当成功。`seed-only-lo.json`证明相同硬隔离环境可正确导入真实R3；这些setup失败没有被隐藏或归为预算门通过。

通用硬隔离launcher只在`.build/p9-root/playback-budget/isolated_test_launcher.py`，不进入产品：outer以`subprocess.run(unshare --user --map-root-user --net,close_fds=True)`启动；不持有原netns FD，不继承额外FD或socket stdio。inner验证netns与outer不同、接口只有lo、没有任何外网路由，才以ioctl启lo；`ORT_DISABLE_TELEMETRY=1`后关闭剩余FD并exec指定本地命令。首次smoke因`/proc/net/route`为空而非仅表头触发仪器断言，记录在`launcher-initial-route-precondition.txt`；经root批准仅修正“零route行”的等价表示：空或仅合法Iface表头，任何实际route行仍拒绝。未改宿主、全局代理、网络权限或原生调用观测限制。

测试transport的后续单因素证据纠正了上述表象：初始catalog、服务端scene、浏览器scene SHA一致，MOC字节SHA准确；`browser-load-error`实际捕获`ProgramScene.sync`的`TimeoutError: signal timed out`，而非缺少R3文件。测试桥接原先把大体读入Python再经`fulfill(body=bytes)`传回driver。在仅lo边界和产品原1秒超时均不变的条件下，改为官方`route.fetch`（仅原精确fixture URL、该request自己的method/body/auth/cookie、max_redirects=0/max_retries=0）再`fulfill(response=...)`，避免大体经Python/base64复制。`browser-driver-negative`实读texture5,689,664字节、SHA `b5292100e43884f1341502c20d41e34b81977bc71ce5c6e6f9c45147662b3707`与原清单完全一致，浏览器fetch约494ms（测试fetch97ms/fulfill392ms），真实Core恢复且负向预算门通过；这支持仪器copy开销解释，不把所有超时推广为同因。原Python桥接失败保留，未改产品超时或素材。

已批准的本地302反例进一步检出route边界漏洞：`preflight-final`中driver正确返回真实302，但浏览器redirect链没有再次进入route，strict NetLog门正确拒绝该轮。新namespace仍仅lo、无外网路由；未把另一loopback代理端口加入白名单，也未宣称外站通信成功。根据[Playwright route合同](https://playwright.dev/python/docs/api/class-page#page-route)首URL拦截限制，测试适配器现在在fulfill前拒绝**所有**带Location的3xx（包括本地Location），不支持redirect链、不造通用代理。保留真实302/status、`redirect_response`的已拒目标host和预期负控标识，不把Location中的query/auth写入记录。原Handler在finally恢复，产品server无新路由；没有运行真正跟随外站的mutant。

旧正向`browser-positive-driver-final`的主媒体和前八项故障已通过，但晚completed反例卡在ready；其原native版`time.sleep`等待在同步route桥接时不泵Playwright请求事件。现在仅把仪器等待改成`page.wait_for_timeout`，保持原10秒判据。旧失败收尾的NetLog依赖链表明`POST /api/live-output`→fixture127的原生TCP→IPv6 reachability探测`-109`，不归因为Microsoft请求；失败原件和脱敏`blocked-native-chain.json`保留。此处不增加flags、不放宽native外部attempt门，由最终同字节复跑检验修复。

最终同仪器SHA `0338d15a556662325fced03ad502fdc08291c69e1338e1c96646ff06f3760ffb` 的三个新目录均通过：`positive-drained-final/result.json`（20检查、errors空，完整真实浏览器tone播放及旧故障）、`negative-drained-final/result.json`（8检查，原长输入+明确31秒tone被拒，0play/空字幕/lip0）、`preflight-drained-final/offline-preflight.json`（11检查，含真实302在response边界拒绝、cookie/401/CSP）。三轮NetLog原生连接列表均空、bridge_failures空；仍仅是Chrome观测，不升级为OS-wide native调用证明。它们均使用新通用launcher的不同netns/lo-only证据，真实模型与TTS均未在这三轮运行。

正向收尾drain发生在所有产品断言和媒体证据保存后：停止测试页enabled、递增epoch，泵事件到busy=false且测试计数pending fetch=0才close。`close-native-time-alignment.json`记录旧失败的唯一native POST位于第一个stage.close区间；新轮清除了该fallback，支持夹具关闭时pending route解除拦截的解释。该cleanup只修测试适配器，不是生产pagehide、浏览器硬关闭或真实设备失联通过；原独立stop/expiry/心跳失联判据保留。

最终受影响unit/HTTP 27项通过（`final-affected-green.txt`），其中明确断言共享fixture=2400frames/24kHz/0.1秒/4844bytes；完整76项先前同产品字节通过，root最终完整质量门与真实模型正负路径须在提交后顺序重跑。B修改范围仅`live_output.py`、节目浏览器入口、共享合法WAV夹具、两份输出unit/HTTP测试及本验证记录；没有改C、原图、角色姿态、提示词、30秒时限或生产请求超时。

复跑前缀：`PLAYWRIGHT_BROWSERS_PATH="$PWD/.build/p9-host/pw" PYTHONPATH=src:tests python3 .build/p9-root/playback-budget/isolated_test_launcher.py --evidence NEW_OUT/namespace.json -- python3 tests/program_output_browser.py`，随后带原`--chrome/--model/--runtime-dir/--out NEW_OUT --loopback-fixture-transport`。确定性正向追加`--input .build/p9-root/playback-budget/existing-greeting.txt --completion --faults`；确定性负向使用默认原长题并追加`--expect-budget-rejection`；安全预检追加`--offline-preflight`。每轮新目录，保持旧失败原件。只有root明确go后，真实模式才换为恢复venv Python并追加原固定`--real-model/--real-tts`，正向用已有问候`--input/--completion`且去掉faults，原长题负向独立使用`--expect-budget-rejection`。成功拒绝不算正向成品播放完成。

## 生成期间到期的独立闭环与终态竞态

`.build/p9-root/real-long-negative-final/result.json`仍为FAIL：原长输入实际推理37.853秒，超过原30秒，未进入TTS；等候批准按钮的35秒超时不能解释为预算门通过。原输入、提示词、业务TTL、adapter35秒均未放宽，也没有用已有短问候的成功覆盖该失败。真实模型实时长回复收益仍未解决。

新增独立`--expect-expiry`只允许固定原长题的机械provider延迟31秒，不允许真实模型/TTS、替换input、completion/faults或budget-rejection混用。它在准备回答后先确认同问题generating DOM，再在从提交起30+7秒内确认同job expired DOM、“已过期”与实际HTTP409“生成期间弹幕已过期，结果已丢弃。”；后续两个既有250ms节目poll仍无复活。TTS入口计数和实际stage请求事件分别要求0，实际play/peak/caption/lip/active分别要求0/0/空/0/null。该负向场景没有生成WAV，`positive_program_completed:false`、`actual_wav_budget_validated:false`，不冒充实际长回答、学习收益或音轨预算的真实模型验收。

第一轮`generation-expiry/only-lo/result.json`严格FAIL：31.003秒provider正常返回，HTTP409与零TTS成立，但主播DOM没有出现expired；服务端audit为generating→failed。`classification-old-red.json`对现有源码的假时钟单因素实验确认：同样begin100/expires130/now131，直接fail得到failed，只多一次status/reap再fail却得到expired。原37秒轮恰有reader先reap，掩盖了这个顺序依赖。

最小生产修复仅在`LiveOutput.fail`：对非终态读取当前monotonic；当前时间>=deadline时清除陈旧failure_reason并expired收口、清音频，未到期维持failed，所有已有终态保留。没有从fail调用reap，避免consumer_timeout→fail→reap递归。`old-unit-red.txt`保留23项中的3个实际失败；`new-unit-green.txt`31项通过，覆盖读者有无、到期前/刚好到期/到期后、音频清理、stale consumer reason、四种终态保持以及真正consumer超时。没有新增状态、UI、轮询、线程或模型/时限策略。

中间`fail-deadline-fixed/result.json`虽曾输出passed=true，交付检查发现DOM timeline为空：observer绑到被refresh替换的旧workspace，all(empty)形成空覆盖。该报告原件保留，旁附`coverage-rejected.json`和`coverage-old-red.json`明确accepted=false，不算最终通过。唯一仪器修正是观察稳定contacts panel、每次callback重新查询当前workspace，并强制非空timeline首尾为**同一job**的generating/expired、全程无review或批准按钮；固定31/37/35及原零输出判据完全未改。

最终`generation-expiry/observer-verified/result.json`7项通过，harness SHA256 `8a92291b10d9280d1e71abea28544a2bd3a7d69bf752539ee3fd93c13533174d`：provider31.006秒，提交后32.955秒同job“已过期”可见，非空DOM timeline精确generating→expired，批准按钮未出现，实际409及零TTS/零audio请求/零播放/空字幕/口型0均成立；NetLog native连接列表与bridge_failures均空。保留`01-host-generating.png`、`02-host-expired.png`、`03-stage-expired-no-output.png`、双端Trace及完整无声屏录；ffprobe确认host46.56秒、stage38.80秒，仅VP8视频轨。它们是only-lo中的真实Chrome/HTTP/既有R3/Core回放，不是Windows/OBS/平台/真人学习验收。

复跑沿上文通用isolated_test_launcher前缀与固定Chrome/R3/runtime参数，使用新`--out`并追加`--expect-expiry --loopback-fixture-transport`，不带real-model/real-tts。原真实长题失败和机械预算31秒tone拒绝各自保留，不改变其验收类别。最终全质量门及最终生产字节上的真实短问候完整播放由root另行顺序记录。

残留候选问题：上述主播截图底层私人助手人像明显近裁，且仍显示“正在准备形象”；节目页半身输出不能替它通过。可能需要区分私有scene的scale/expanded与modal可见性、加载/paint早退；当前没有host console采集，stage errors为空不能排除宿主异常。本轮没有改该UI或认定它就是慢推理原因，保留为后续先诊断的问题，不宣称全UI通过。

## 宿主面板加载恢复（只修生命周期）

前节“正在准备形象”残留本轮取得可证伪的控制器根因。C冻结的`tests/test_scene_visibility_ui.mjs`运行真实scene-controller源码、延迟engine/renderer桩：旧版before-model、during-load失败，after-ready正控通过；旧源码SHA `fa0885dd9680abb292bff9a41b708334103997d526b5d298516562afaf8bdc9c`。前者engine在隐藏时返回false却留下同key，show后的sync永久早退；后者模型已load/paint完成，控制器因hidden丢弃ready与scale结算，show只unhide模型，不清loading。模拟隐藏帧增量三项均0，只证明控制器向桩renderer传递隐藏，不冒充真实Core或CPU证明。

最小生产改动限scene-controller：engine当前ticket仍有效且隐藏时仅清key、settlefalse，不在hidden创建活动renderer；load及paint有成功证据后结算ready/原scale与visibility分开，保持renderer.hidden，仅visible恢复speaking/audio。取消、旧ticket、15秒paint等待/可见失败路径保留；没有重复load/create、没有改布局、美术、固定持杯、尺寸、帧率或视觉参数。新同三项3/3通过，source SHA `5761f974e5b8e1f8c5c0e527efc0117e4494574a28d76c65552778e0b3a8f111`，新日志`scene-visibility-new-green.*`；既有private scene/renderer Adapter及该3项合计64/64通过，零skip。

`.build/p9-host/scene_core_modal.py`另走真实宿主入口（非自造UI）：既有R3/Core、runtime-reading fixture、Chrome，在首次private runtime脚本请求前受控延迟，实际点击“相处方式”面板，释放脚本时确认无模型在hidden创建，再实际点击“返回陪伴”。`.build/p9-host/scene-core-modal/result.json`六项通过：Core ready、“正在准备形象”退出；第二次实际开面板期间frames57→57、Core evaluations57→57，关后frames59，同Canvas且模型JSON仅1次；errors、native连接、bridge_failures均空。三张实际UI截图、无声视频、私有Trace、console和环境/源码哈希保留同目录。Core和框架为已有固定字节fixture读取，不是Windows真实安装/许可链验收；未运行语言模型或TTS。

已查看`02-actual-host-ready.png`，此1440×1000 Linux Chrome场景中半身、双手和杯可见；没有将该观察推广为所有裁切/DPI合格、最新眼部审美或用户验收。也没有将loading缺陷或此次隐藏暂停计数当作先前56秒推理的原因；性能竞争解释仍独立。复跑：沿既有only-lo launcher，指定新`--evidence NEW/namespace.json -- python3 .build/p9-host/scene_core_modal.py --out NEW`，设置`PYTHONPATH=src:tests`与已有录像工具路径。该脚本仅.build证据仪器，不是新增产品入口。
