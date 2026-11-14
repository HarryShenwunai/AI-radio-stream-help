# 设计交接

更新：2026-11-12。执行新任务先阅读本文件及相应目录已有说明。

## 当前方向

项目未命名。目标是自然、有稳定性格、可文字/语音相处的虚拟角色；督学可选，长期记忆不是核心驱动。现有可运行原型与数据操作保留，新增能力通过适配层逐步验证。

本仓库用于设计与来源归档，不代表已经实现B站、弹幕姬、AR或MC集成。真实账号连接、开播、游戏动作、摄像头/屏幕采集、服务购买或部署需要对应明确授权。

当前参考：ZerolanLiveRobot、ZerolanPlayground、zerolan-core、zerolan-data、KonekoMinecraftBot。完整来源与读取版本在evidence/zerolan-source-refs.json。

## 实际踩坑与修正

- MC默认master没有同等Zerolan桥接；dev含src/web/zerolanPlugin.ts。应固定已验证commit，不能只克隆默认分支就宣称可联机。
- Core通用TTS入口是占位；实际文档要求特定GPT-SoVITS fork/zerolan分支/zerolan_api.py。不能将占位解释成整个体系无TTS，也不能把官方api_v2.py当兼容实现。
- Core的逐行JSON、当前原型SSE与WS控制不是同一种传输。网络chunk可能拆并消息，需增量UTF-8与帧缓冲。
- 模型Query/Prediction中Field(default=str(uuid4()))不是每次创建都生成新ID。适配时显式分配或改default_factory。
- 事件5秒超时日志不是取消执行；播放器停止、生成取消、未播放上下文截断和晚到结果丢弃须分别验证。
- Unity异步下载完成才入播放队列，需额外验证乱序与已取消generation的晚到音频。
- 字段类型和协议版本不等于身份与权限；公众事件不能进入私人history或工具执行路径。
- AR根目录未找到独立许可证；Unity、Vuforia、Cubism和素材各自核对。MC master的package许可元数据与LICENSE不同，dev又不同，不能取一个标签覆盖整个体系。
- 页面无横向溢出仍可能PDF架构图被裁切；使用紧凑竖图，并实际查看导出页。
- 搜索有多个仿官网；中文产品只采用已核对官网或发行方商店说明，不以聚合页、评分或宣传规模当需求证据。

## 状态与下一步

新集成测试Q01–Q10均NOT_RUN。已有36项后端/5项模拟模型协议等记录来自旧原型，不是本轮重测。主计划、工时和验收以docs/planning/revised-plan.md为准，历史计划另存history。

先做固定版本兼容样例，再决定适配或迁移。核心P0–P5含储备18–33人日；AR与MC均选则24–45人日，均是8小时/人日的工程估算，不是承诺。

仍未知：目标机器、预算、音色、具体弹幕姬/房间和官方账号条件、AR许可与真机、MC版本和服务器授权、真实集成时延与长期相处质量。

Git历史不放模型、安装包、私聊、数据库、密钥、Cookie或原始用户资料。不复制上游整套源码或未获许可素材；本仓库只提供分析与来源标识。

本轮设计文件/Schema结构检查18项通过；HTML由本地answer-me-with-html CLI生成，STE警告0。Chrome的1440/390宽度检查无页面横向溢出、无JavaScript异常；6页PDF中的架构图已查看。以上是文档交付检查，不是新增集成功能测试。

## 启动批次（用户已批准）

用户批准推荐路线并要求多Agent协作。主Agent集成；protocol负责协议、lifecycle负责取消状态、voice_ui负责前端/Chrome、live_ingress负责公开离线队列、independent_review独立审查。彼此采用文件独占避免写入冲突。当前代码在app/与src/，run.py可启动，计划执行状态以docs/planning/execution-board.md为准。

实际Python回归115项通过，Node竞态8项、Chrome检查12项通过。真实Qwen/Kokoro单次冒烟通过；首段10.790秒，完整17.248秒，语音3.124秒，取消0.091秒，RSS约5.27GiB，非p95/用户验收。完整Q01–Q10尚未验收；旧追踪文件是设计时快照，当前执行见phase1报告。没有真实直播、上游部署、OBS、AR、MC或微信连接。

新增踩坑：已成功rid换text曾静默返回旧cached回答，已预检拒绝409，且无效请求不使旧generation失效；直播字符串孤立surrogate与超大event_at曾抛异常，已统一invalid并加回归。HTTP abort只能阻止客户端接收，不能假称底层TTS停算；合成前后和浏览器serial均须检查。旧Audio回调必须绑定本对象，防误清新URL。

后续先测上游兼容和完整语音轮次；真实房间需明确弹幕姬/官方入口、设备与账号条件。AR/MC仍可选，不因多Agent自动扩大权限或压缩整体估算。


## 2026-11-12 自助角色范围修订（研究与计划）

用户明确二次元桌面陪伴需要可自行导入/上传和配置角色，不能固定几个角色。示例只作测试；支持按格式/版本/能力声明，不按角色名特判。用户已确认“配比”两类都需要：制作分工/预算，以及角色比例/拆件规范。上传先按向自己的应用导入理解，云同步/公开市场尚未确认。

现行增量计划docs/planning/self-service-characters-plan.md（8段），与原修订计划、README、architecture、execution-board已相互链接。本轮未改app/src/tests/run.py，未实现导入、未下载运行模型或SDK、未委托/购买/联系厂商、未commit/push研究。原代码仍5a3189a。

三Agent研究分工：character_import_research（5产品/11官方页）、artist_delivery_research（画师/拆件/绑定/程序交付）、character_acceptance_review（28项NOT_RUN基准与独立审查）。对应研究MD、evidence JSON与review JSON已在仓库。旧115/8/12通过不代表新增导入通过；实际导入运行测试和素材夹具准备均0。

建议A：PNG/状态图建立通用导入与身份隔离，再接固定版本Live2D。U0–6基础16–28人日，加3–5储备19–33（单选OS，8h/日）；PNG阶段不含U4基础12–21+2–3=14–24；B首版仅Live2D不含U3为15–26+3–5=18–31。与旧18–33方案有界面/生命周期/QA交叠，不能相加；总体剩余工时U0合并重排。艺术制作、许可等待、多OS、云市场、真实直播等另估。

必须区分同身份换外观与新增独立角色；现有SQLite只有一套settings/messages/memories/tasks，无角色隔离字段。资产修订/身份/会话/generation联合归属，单音频拥有者；模型包不能改权限/服务凭证/自动注入人格。导入预览/暂存/原子启用与回滚需实现，未称已通过。

具体文件、口型/标准与自定义参数、可选动作降级、源PSD/cmo3/can3与运行model3.json/moc3/贴图分离见artist-rigger-brief。头身比R=总高/头高、显示高/屏高、原画/图集尺寸分开；160/320 CSSpx只是探索起点非行业标准。制作工种按WBS工时/报价核算占比，没有固定预算百分比或虚构市场价。artist-quote-template.csv五行UNQUOTED；character-support-matrix.csv全PLANNED/DEFERRED/NOT_RUN，未知版本不冒充支持。

重要许可事实：Live2D官方SDK许可及expandable细则将通过新增数据扩展不定数量avatar的应用列为可扩展类别，适用所有发布方的审核/特别出版许可及条件/公开价目；项目类别、实际费率与免费条件尚待确认。AI FAQ原则允许条款范围内AI用途，不等于免SDK/Core/资产许可。未联系厂商或购买；PNG通用流程可独立准备，Live2D发布设明确门。见evidence/self-service-role-sources.json及官方 https://www.live2d.com/en/sdk/license/expandable/ 与 https://help.live2d.com/en/other/other_33/ 。

独立21项文档审查通过，修正A/B范围矛盾、单OS口径、包引用越界指标、资源阈值冻结时点、每格式至少两独立包且一套holdout的样本表述；用户确认后主稿SHA已独立刷新。另15项结构/数学/引用检查通过，都是文档检查。资源门槛要U0候选→样例→冻结后U6，不拿ZIP字节数代替解码/GPU实际峰值。28项CI01–28均NOT_RUN/actual_result=null。

交付dist/self-service-characters-plan.pdf（9页）、同名HTML与dist/self-service-characters-research.zip。HTML由answer-me-with-html CLI生成STE0，Chrome1440/390无横溢出/JS异常，PDF画师/工时/风险页已查看完整。ZIP22文件824750bytes，SHA256 61d068a70a147f6a32b0b1de4a9f000c06df209af801ab4bb4ce0b85489c41de；含计划、报价/支持矩阵、研究/来源/审查/未执行规格及被引用已发表源码/许可快照，非应用安装包，无模型/数据/密钥。ZIP CRC与包内Markdown目标检查通过。

踩坑：CI范围缩写CI-20–22/28需同时展开范围与斜杠，不能用只识别CI前缀的正则误报缺CI28。web click应使用上次返回refID而非URL+局部linkID，初次无效参数已改正。veadotube mini2.2手册使用.veado，旧.veadomini不能当新版；AIRI当前ZIP会忽略VTS元数据，旧翻译要求手删不能混用。model3后缀不证明新旧SDK兼容，JSON合法不代表模型能渲染。

下一步按U0冻结首版格式/目标OS/许可边界与合法样本，再实施通用导入和数据迁移；用户仍要求先不改现有UI，本次仅研究计划。不因主题同意而自动公开分享/采购/委托。保留同机性能、角色切换与回退、画师极值姿态/拆件检查，以及云上传定义未定项。

## 2026-11-12 自助角色软件实现与 Windows 交付目标

- 用户已授权从研究进入软件开发，最新目标系统确认为 Windows 10 / 11；Linux 编译结果仅为开发验证，不得当作 Windows 成品。
- 当前 0.4.0-dev1 已实现 PNG 状态图真实解码/预览/启用/修订回滚、自助创建角色、独立 profile SQLite、切换取消旧回复/音频、归档/恢复/永久删除、旧库只读备份迁移；服务连接/API key 全局共享，人设与关系数据分角色隔离。Live2D、微信与真实直播接入尚未实现。
- 实际回归：185 项 Python 全通过、18 项角色 Node 与 8 项语音 Node 全通过；默认沙箱禁止 loopback socket 导致首轮错误，获准在沙箱外重跑解决，不应把环境失败写成产品功能缺陷。Chrome 15 项既有通过记录；最终 native-hide guard 修改后正在复跑。
- Linux PyInstaller 后端已真实 PNG 导入/回滚/关系隔离/重启及本地 Qwen/Kokoro/取消通过。单次观察首字9.206秒、整句15.993秒、TTS3.645秒、取消0.099秒、峰值 RSS约5.31GiB；不是 p95 或 Windows 目标机指标。实际模型回答出现关联旧测试事实的话题漂移，human_quality_accepted=false，不声称自然度已通过。
- Electron 45.3.1 Linux X11 透明/穿透/焦点恢复已实测；整包测试发现 Electron hide 时 document.hidden 不一定更新，因此增加显式主进程可见状态媒体 guard，阻止晚到语音。Windows 由独立原生 CI 构建和验证，不交叉编译或把 Linux 检查冒称 Windows 通过。
- .github/workflows/windows-build.yml 将生成精简运行包与附 SHA256 校验模型的离线包，均只构建/测试/保存制品，无部署、购买、平台登录或真实发信。发布和真机 DPI/独占全屏/性能与人工语音质量仍待实际结果。

## 2026-11-12 Windows 本地构建交付与新增画质目标

- 用户已确认有 Windows 电脑可运行本地构建。已完成 build-windows.cmd + scripts/build_windows_local.ps1；优先兼容Python3.11/3.12，缺少时准备已校验uv与Astral项目内Python3.12，Node22便携工具，官方llama CPUwheel免VS编译，所有缓存/依赖/日志在.build。不自动安装全局VC++运行库；缺DLL给微软官方来源后停止。PowerShell解析、退出码0/1/无法启动保护已实际测试，191项回归通过；Windows原生执行仍待用户电脑报告。
- 已新增10份补充许可/来源文件，collector保留原27包23有文本/4缺失的原始记录；补充源按固定版本/commit核对。eSpeak wheel构建沿latest取原生资产，未复现精确二进制源码对应，不能声称完整法律审查。
- Linux最终真实Electron整包14项通过，含真实host-hidden且document.hidden=false时调用speak，语音请求/Audio创建/系统朗读均0。独立复查曾发现之前只写了主进程flag、app.js未消费，旧nativehide测试只设置document.hidden导致漏检；现已先红后绿修复。app.js最终SHA256 1f9d342f0e8ede57367381459b3ff096da3927119ff1e859acf6233fa41a77a0，Node18+8与Chrome15通过。send_message不会唤醒completed Agent，必须followup_task；不要把已发送修复要求当作已完成。
- Windows嵌入式候选已静态组装官方Python3.13.17+27包+77个AMD64 PE，3模型SHA复核；但Misaki上游声明<3.13，属于显式兼容实验，不作正式交付。Wine基础4项通过；NumPy2.5.4及唯一官方2.2.6对照均被Wine未实现ucrtbase.crealf阻断，未改DLL/未降级/未声称LLM或Kokoro通过。仅留诊断目录，不将未验证包当成品。
- 用户上传新画质参考，要求自然面部比例、细致发丝、柔和窗光与安静表情的高质量二次元表现。记录docs/design/visual-quality-target.md；不能由单图推断3D/Live2D制作方式，也不锁成图中角色。PNG版本仅基础导入验证，未达到动态画质目标。高质量2D绑定/3D渲染须合法独立样本、SDK边界与目标显卡实测；显卡RAM询问仍待答，不虚构性能门槛。
- 新踩坑：Pillow13需要>=3.11；uv Windows默认可写PEP514/bin要显式--no-registry --no-bin；PS5.1内嵌双引号/旧LASTEXITCODE会误判，现探针单引号且先清退出码；大模型文件>2GiB用Python ZIP64而非Compress-Archive；.NET OSVersion有兼容层需只读实际build号；py3-none-win_amd64 wheel可含DLL，不能当纯Python或DLL闭包已齐。
- 最新设备答复已到：用户自报“4060 32G”，按RTX4060/32GB内存作开发基准；未探测实际显存/CPU/驱动/移动桌面型号。视觉目标文档已更新，优先验证3D材质与光照样例，30fps角落/60fps展开仅候选目标而非实测承诺。当前推理构建仍CPU版，不声称已CUDA加速或实现3D。


## 2026-11-12 可执行纠错与证据（收口中）

- 不扩写 AGENTS；新增 requirements-quality.txt、pyproject.toml、scripts/quality_gate.py 与 check_architecture.py，将关键 lint、四模块 strict typing、六类架构约束和负控制夹具变成真实退出码门禁。全量检查前后源码 SHA 不一致时整体验收失败，不能把并发修改前后的绿测混为一版。
- R08 真实 HTTP 已复测15项：历史慢TTS不能夺新播放、ABA角色往返不能复活、非法speech不能抢占、stale generation stop不能终止新音频。真实Chrome7项含先确认上下文前置条件、1.41/4秒停止不猜已听词、后续prompt剔除未确认尾、完整重播后恢复；录像见review/playback-browser-check.json。2048/4096 prompt预算另有3项源码绑定回归。
- Live2D Haru/Hiyori各12项真实Chrome本机评估通过；实修JSON bytes二次序列化、CSP禁止Pixi blob worker、Core污染clearColor、U+3000文件名与官方motion舍入。Core实测5.1/MOC5；SDK/第三方模型/录像不进Git或默认Windows包。参考美术、Windows/4060、真实账号及人工自然度尚未通过。
- 正式形式化材料必须使用review/formal-models，避免.gitignore的**/models/把TLA+/配置/复现脚本整个漏提交；第三方research/vrm-fixtures/*.vrm明确只本机评估。TLC与实码性质测试有界，不宣称全程序、活性或人类实际听见的证明。


## 2026-11-12 GitHub 下载交付：附件认证阻塞

- 用户因云端文件链接无法下载，已明确授权把交付物push GitHub。源码仍是d01ccc4；交付材料另提交9bdfab4到feat/phase1-runtime，deliveries/0.4.0-dev1-candidate含实际运行证据ZIP、完整/分卷SHA清单及下载合并脚本。公开无凭据下载证据ZIP和PS1均HTTP200、SHA与本机一致；没有把它们叫完整软件包。
- GitHub官方about-releases核实每个附件须小于2GiB；4,491,413,065-byte原包准备为三卷(1.5GiB/1.5GiB/1.18GiB)，原包及SHA保持不变。源码Git只新增约3MB证据，避免把4.49GB分卷塞普通Git。Release草稿ID443254620/tag v0.4.0-dev1-candidate绑定原源码；没有发布空Release。
- 阻塞有实证：gh可读写api.github.com并创建草稿，但uploads.github.com小文件和大文件均HTTP401 Bad credentials，草稿assets=[]。现有连接器无Release上传工具，当前无可用浏览器控制工具；不能假称完整包已上传。需用户在环境密钥设置提供允许api.github.com及uploads.github.com的有效上传凭据，不让用户把token贴聊天；待配置后刷新状态再续传。
- download-and-assemble.ps1使用固定HTTPS地址、逐卷/整包SHA、临时文件与原子合并，不覆写已有损坏归档、不自动登录/启动/全局安装。真实PowerShell/.NET五小夹具过（正确拼接、损坏拒绝、缺卷不联网、已有有效ZIP复用、已有坏ZIP保留），这不是Windows实测。云端pwsh需要XDG_CACHE_HOME/CONFIG_HOME/DATA_HOME都指向可写目录，不能为此改HOME。
- 仅公开自有几何模型的实际运行录像/截图；Live2D Core/framework/官方样例及仅本机评估截图视频没有上传。大包临时part01在401后已删，原完整ZIP保留；暂存及复现器在/workspace/dist/github-release与/tmp/upload-companion-parts.py，可在凭据修复后续传。


## 2026-11-12 GitHub 候选下载已发布

- 发布地址：https://github.com/HarryShenwunai/AI-radio-stream-help/releases/tag/v0.4.0-dev1-candidate；pre-release，tag绑定原软件源码d01ccc42bbe6795c216afae37dd0e53128ab58d9。三卷共4,491,413,065bytes；11个Release附件的服务端SHA256和大小均与本机匹配，不把4.49GB写进普通Git历史。
- 可仅下载download-and-assemble.cmd/ps1两文件到同一目录，双击CMD自动下载、逐卷校验和合并；完整解压后运行companion-desktop.exe。各卷保留，下载/合并/解压分别需要约4.18/4.18/6.32GiB磁盘空间。
- 已无登录凭据实测7个小附件完整下载SHA、三卷的6个首尾HTTP206范围与原包字节一致；真实PowerShell7又用小夹具走公开HTTP下载/校验/合并路径通过。没有重新下载整个4.49GB，也没有称为Windows真机测试。证据见deliveries/0.4.0-dev1-candidate/public-download-check.json和release-integrity.json。
- 新坑：GitHub把纯中文说明附件名规范化为default.txt，发布前集合/大小/SHA检查拦下；已改名START-HERE.txt，内容SHA保持不变，并对附件名加入ASCII约束。仓库中文路径与Release附件命名规则不能混为一谈。
- 仓库Secrets仅Actions可读；当前Actions仍billing-lock，最终经用户在GitHub官网确认官方CLI设备授权后上传成功。没有读取/导出仓库secret，也未把token写入源码或聊天。Live2D vendor/官方模型及仅本机评估录像未公开。Windows/4060、实际CUDA、账号互通和人工质量验收仍未通过。


## 2026-11-12 新范围：完整产品/UI与原图角色重建（不可用旧日夜稿冒充完成）

- 用户明确“UIUX全面更新，不要现有任务和UI设置，按2026重新制作，不允许省时间”，并新增指定原图从零建模/动画/目光/表情/口型、性格、自适应偏好、HD摄像头/远场mic/PCVision、日程穿搭晚餐/分析/游戏协助。旧六导航/旧任务页/旧通用settings form不再作为最终UI；底层已验会话/权限/语音仍可复用，用户数据不可删。当前日夜浮层只有内部预览，未发布新版本。
- avatar_from_reference查259张/常见file文件头，原图约1179x1435未找到（3处不可读记录不冒称全盘穷尽）；Blender4.3.2可用。必须向用户重新索取原图文件；不能靠记忆换角色或拿程序占位/官方样例当成品。原图单视角缺的背面/全身属于需记录的设计推断。硬件型号已async询问，未得到实际设备不称5英寸实体显示/远场/摄像头完成。
- 当前7槽：root独占server集成/范围；frontend全新IA与static，允许换UI IDs、新静态模块；QA独占真实UI/原生Linux测试；desktop更新与journal guard；avatar_from_reference资产工程；perception_runtime感知/配置模块；engineering_gates assistance提案模块。都已收到不假实现/不半成品边界。
- root已把ui-kit,companion-core,scene-controller,speech-controller,conversation-view,studio,connection-flow,sound-flow,privacy-flow,assistance-view十JS按精确文件名加入server白名单，py_compile过；不是最终功能验收。frontend核心拆模块正在实施，不得保留隐藏旧form桥。
- Perception合同：status；owner session/start/stop/frame，scope由server(owner,role,appearance,epoch)生成，frame≤1.5MB/1920edge/2.0736MP、单inflight/2s间隔/TTL900；无默认持久化，provider未配明确unavailable，OS媒体授权不能用JSON布尔冒充。真实LLama0.3.36有Qwen25VLChatHandler/mtmd但当前Qwen3-4B纯文本、无Qwen3VL handler；不能假Vision就绪。配置采用新VisionConfigStore(DATA/perception)、owner /api/perception/config，自助固定HTTPS/loopback开发HTTP、密钥0600原子不进state/log，更新取消旧会话；agent正实现。
- Assistance合同：Store(profile.db,role_scope,provider,provider_kinds)；owner proposals{request_id,expected_character_id,kind,inputs} / decision{action_id,decision} / pause；state.assistance。kind schedule/outfit/dinner/brainstorm/data_analysis/game；固定权限read_only或local_schedule；真实provider未配unavailable，CSV只统计，不代码/购买/发信/游戏操控。migrate_connection给tasks加assistance_action_id，messages加task_id(旧消息不猜关联)；root待接scheduler INSERT task_id与state透出。任务取消改对话来源卡，不重建旧管理列表。
- 新范围机读清单docs/planning/product-rebuild-requirements-2026.json overall明确NOT_COMPLETE，各项未假填证据。旧417/Chrome等只证明旧范围。2026官方产品研究在docs/research/uiux-2026-refresh.md及evidence/uiux-2026-product-sources.json；AIRI实际网站Loading，只读固定0.14官方ADR/版本与手册例图，AVA看了宣传图但无硬件实测。所有新软件/硬件/人物质感要分层验收。


## 2026-11-12 感知边界与真实协议验证

- `perception.py` 默认 vision_not_configured；本机 Qwen3-4B 是文本模型，不可当VLM。安装llama-cpp-python0.3.36有Qwen25VL handler+独立投影器要求，没有Qwen3VL handler。本次官方Qwen2.5-VL-3B SHA66285546d2b821cf421d4f5eb2576359d3770cd3的LICENSE是Qwen RESEARCH LICENSE，不能沿用第三方量化页Apache标签。
- owner自助视觉连接只存全局transport配置，不进角色记忆：原子0600/0700、拒绝链接/reparse/超大/非regular；Windows仍须私有AppData ACL。更换base_url未显式新key时清旧key，避免把服务A凭据发给B。配置完成不等于模型确实看懂图。
- 帧真实PNG/JPEG解码后新像素重编码去元数据；单解码/推理槽、全局2秒间隔防重开session绕过、会话/缓存/TTL限制；取消/换role/appearance/epoch后的迟到结果拒交付。供应商不合作可能继续至超时，不能声称能撤回远端已发帧。
- `manager.observation(scope,id)`仅从真实成功帧创建短期server-only provenance；owner/epoch/session/捕获年龄与缓存年龄≤30秒检查，stop/config立即失效。建议接口只收opaque observation_id，不接受前端description冒充来源；模型输出仍标untrusted_context及inference_verified:false，不授予工具权。
- 47模块测试全过，含1296有限trace/5184实际管理器操作；strict mypy需`--python-executable /workspace/companion/.venv/bin/python`以找到真实Pillow类型（quality工具venv本身无PIL），无ignore；关键Ruff通过。review/perception-module-check.json绑定源码SHA。真实loopback HTTP4请求验证multimodal/auth、307拒跟随、响应限额/500脱敏，review/perception-provider-check.json；合成响应不证明VLM理解/摄像/Windows/4060。
- 官方MediaPipe代码及BlazeFace/FaceMeshV2/BlendshapesV2模型卡分别已核Apache2。初次1.5MB抓取截断两张PDF导致解析失败，改有界8MiB完整解析后核实；不要把截断资料当许可缺失。尚未安装具体task/真人测试；面部方向/表情估计不能称专业眼动，远场麦克风/投影效果仍取决硬件。


## 2026-11-12 设备声明持久化边界

- 新 `DevicePreferencesStore(DATA / 'devices')` 仅存 display/camera/microphone 三个布尔声明；默认有设备不代表已检测、已授权或正在采集。display 是额外5英寸角色装置，缺失不可影响PC舞台/PCVision；microphone 缺失不可影响TTS。Root需独立连接停止实际输入会话的逻辑。
- 实际修正：损坏的已有设备配置不能按首次启动恢复全部true，否则可能重新启用此前禁用的输入。当前损坏/不完整/重复JSON键均拒绝，保留原文件；配置只在缺失时采用默认。原子写入/受限模式/符号链接和reparse检查；Windows ACL、物理检测和采集未因此被证明。
- 模块12项测试、strict mypy单模块及关键Ruff已通过；无server/UI改动，未声称Windows/硬件验收。调用API与单写者/可信父目录限制见docs/implementation/devices.md。


## 2026-11-12 新后端真实HTTP验收

- `tests/test_rebuild_http.py` 15项真实loopback Handler集成通过，0skip/0error，18.708s；6文件SHA前后稳定。报告与日志在`.build/rebuild-http-check.json`/`.build/rebuild-http-tests.txt`。覆盖owner/plugin鉴权、scope伪造拒绝、frame session_id与private envelope区分、缺camera仅停camera、缺mic停ASR不禁TTS、声明跨role、迟到视觉拒交付、提案确认幂等与reminder task_id、旧schema迁移和观察ID撤销。模型回复均合成，不证明视觉语义、游戏水平、硬件或Windows。
- 验收修正：非合作协助provider未收尾时，角色/外观切换的正确行为是先取消ledger并返回409；provider结束后重试可成功。测试必须断言旧summary始终为空、迟到建议没有交付、旧role未在409时被谎称切换，而不能硬写每次切换必200。迁移fixture按保留消息ID查找，不能假定messages[0]是夹具（初始化已有消息）。


## 2026-11-12 按需偏好候选与遗忘一致性验收

- 新 preference_learning.py 只按用户明确请求读取当前角色≤12条user/chat（每条≤3000字/总≤12000），真实provider只可选完整单行原句≤300字。带source_message_id/精确原文SHA/角色scope，候选待确认，普通聊天无额外推理；memory_mode=off拒绝collect/confirm且不传源文。缺provider明确unavailable；模型改写/视觉/assistant来源不能直接进memory。
- 实际修正：只删除memories行不够，候选ledger也可能泄漏遗忘原文。reconcile/list/cached request现会redact forgotten或pending源失效候选；confirmed须核对实际memory行/原文/source，重复confirm不可重建删掉的记忆。单清chat但已确认memory仍在可保留。correct删除旧确认memory、忘记旧原句，新真实source候选仍需再确认；root清旧chat保留newsource。SQLite使用mode=rw，stale store不再可重建已删除角色DB；role取消后仍须drain并驱逐缓存。
- 模块27项真实SQLite测试PASS（2.086s），含216有限动作trace/648次实际Store操作；strict mypy/Ruff通过。报告review/preference-learning-check.json，模块SHA47d61b7b48c0b78c808cb130006655247840d7891b72e8a05040d28a526ba06a。该有限安全覆盖不是完整形式证明或偏好语义准确率。
- 新HTTP最终20项PASS/0skip（27.909s），8源码SHA前后稳定，server SHA409f6a2d5fc9f4f85b7cc289e71d79bd2ea9e6af217215170744c522863c3ce2。review/rebuild-http-check.json/log；原15项归档before-preferences。新增真实JSONadapter确认/遗忘/纠正、off不调用、source删除失效、非合作collect先409后恢复删除驱逐、tracking明确synthetic engine的session_id和缺相机隔离。合成回复/engine只证明协议，不证明语义/真人跟踪/Windows/4060。


## 2026-11-12 原生捕获与小更新的实际坑

- Electron45真实负控证明display-capture前置许可先于来源handler，旧GUM chromeMediaSource同许可且可绕过标准picker。不能只把主UI前置许可设true打通测试；现主UI永拒，专用打包本地sandbox捕获窗经native选源+真实点击才开始，限定视频/帧率/分辨率，无外网或任意IPC。主UI桥只取本机帧，手动确认才发后端；close/hide/minimize/导航/role换均停止旧owner。调查临时放宽只在测试flag，不能当产品配置。
- 新main依赖capture模块，不能把全量新host当更新先行bootstrap，否则依赖未写就require失败。v2先写从固定基础host派生的最小无新依赖门禁，journal在场拒启后端，最后装完整host；保留运行租约与SHA/备份/每写点故障恢复。scripts/build_app_update.py/app_update.py是本次程序小更新，早期UI-only v1不适用。静态PNG与新增runtime须明确白名单并绑定最终验证SHA；用户角色单独确认导入。
- Windows交付用Python -I时不自动加脚本目录；app_update/tracking_addon显式只将可信 sibling helper目录放入sys.path，已用-I --help验证。
- optional addon raw manifest带末尾LF的SHA与JSON canonical无LF的SHA不同，不能误认文件被重建；installer同时锁二者并保留原始bytes。v2新文件名84,268,648bytes/233,406,422解压，剔除无用FFmpeg Video I/O插件，旧97MB仅私有审计。
- Native测试页不能依赖window.screen/window.stop隐式ID全局，已改getElementById；Playwright wait_for_function字符串会触严格CSP eval，改函数字面式而不放宽产品CSP。X11连接须先关闭再停Xvfb，否则XIO直接结束Python导致报告未落盘。视频要保留足够真实active采样，不能只抓到新窗口白屏；截图、实际帧时间及有界fps分别断言。
- 实际单屏Xvfb枚举与同一主window输出/恢复已测，不能当第二显示器、5英寸、全息或4060验收。设备declared present默认不授媒体权限；额外显示器没有不禁PCVision。源码/截图/视频路径见docs/implementation/desktop-capture-and-update.md；新UI整体native QA由独立agent负责。


## 2026-11-12 独立后端审查发现并修正恢复误报

- 真HTTP最小反例：schedule proposal确认后restore空tasks备份，tasks已空但旧proposal仍confirmed/local_schedule_created=true，重复确认假称task_id仍在。红证据review/rebuild-restore-orphaned-schedule.json保留。Root修复为restore原事务内cancel旧确认关联、旧ID仅previous_task_id历史、记审计；新恢复task仍paused/无旧关联。
- 新增2项真实HTTP回归：空/含task备份都不再误报，重复confirm409；valid JSON嵌套status=[]在事务中失败400，messages/memories/tasks/proposal和新审计全部回滚。review/rebuild-restore-regression-check.json 2PASS/0skip/1.254s，三源SHA稳定，server4ac4d67523dc57b3060b6f354b84e1b23e294810002d55766850fcecef35c66c。完整HTTP测试现22项，最终全门禁由root运行，不能把原20项报告称覆盖本次修复。
- 独立review/rebuild-server-independent-review.json将该项RESOLVED；未证明新的锁序闭环或owner/plugin越权，记录实际锁边、已释放HOST再等VOICE、provider不持SQLite事务、bounded drain等依据。仅审查范围内无开放阻断，不代表全程序死锁证明、Windows/硬件或模型语义验收。


## 2026-11-12 可选跟踪扩展最终v3纠正

- 最终仅允许发布tracking-addon-cp312-win-x64-v3.zip：83,452,536bytes，SHA4b3f763179bf771cd8466082114f9f9e4c87c0aab0d7caaacdab2fd705fccf21；2043锁文件+manifest共231,680,607bytes解压。perception Agent已完成全部成员、20个native均x64、上游许可证和实际FaceLandmarker有限场景审查；Windows DLL执行仍未验。v1/v2 ZIP保留本机审计，不得作为新Release附件。
- v3再剔除无用ASIO/跨架构binary，仅保留实际路线使用的默认64bit PortAudio和全部相关license。installer/builder CMD均改v3唯一名字与raw/canonical双锁，未改变native host或重复跑其未变化测试。必要事务正负测试及真实2043文件安装/重复/可恢复禁用以review/app-update-check.json和review/tracking-addon-v3-installer-check.json为准，旧v2报告只是历史。


## 2026-11-12 本地面部估计与无pip Windows组件（最终v3已冻结）

- 新runtime只有perception.py/perception_tracking.py/perception_optional.py；perception_addon_build.py仅开发构建器不进入运行白名单。FaceTrackingManager独立camera路径，默认无依赖/固定task就unavailable，status仅元数据/SHA检查不导入启动算法。用户真实选源授权后才start；不识别人脸身份、不称专业眼动，PNG只能有限状态/位移，不能单图独立转眼球。root已接独立tracking routes、camera设无与角色epoch停止；可选5英寸display不是PC screen权限。
- 实际固定官方task3758596bytes SHA64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff，隔离MediaPipe1.2.3 CPU/XNNPACK对官方portrait/空白/恢复/右移/双脸5场景通过，20暖帧P5010.41ms/P9511.43ms，初始化1.653s、进程峰RSS189600KiB，仅云Linux样本。真实禁VideoCapture/VideoWriter/imread/imdecode与Python音频stream负控被检出，正常推理0违规。MediaPipe顶层会import音频辅助模块；不要误说完全不import sounddevice，更不能把导入库与打开录音流混为一谈。
- Linux CPU.so也依赖libGLESv2；sounddevice真实音频禁调用测试还需PortAudio。云apt索引不可用，均从官方Debian下载17KB/65KB到私有dev目录提取，不改系统/语音。LD_LIBRARY_PATH给私有lib，PortAudio find_library不自动发现私有soname，测试显式给真实库路径；不是WindowsDLL执行证明。
- 83感知测试含1296trace/5184实际管理器操作、strict3runtime+mypy真实Pillow解释器、Ruff全绿，前后源码SHA稳定：review/perception-module-check.json。真实CPU/完整包/纯Python导入证据分别review/tracking-real-check.json、tracking-addon-v3-check.json、tracking-addon-import-check.json；实际Win/4060/摄像/头像自然度仍待验。
- 已发布旧WindowsCPU/CUDA都是CP312嵌入无pip。共享固定resources/optional/tracking/python312/site-packages只追加sys.path，复用原numpy2.5.4/Pillow13/flatbuffers25.12.19/packaging26.3，不覆盖原native/模型。15官方Windowswheels总93795778bytes，逐SHA/marker闭包核实；许可原文完整保留，不能笼统说全Apache。
- v1/v2发现实际独立LGPL2.1 FFmpeg插件及ASIO/非x64备用库，均只本机历史审计不外发。官方精确OpenCV40738fb.../第三方06dc20c...readme明确支持省略独立FFmpeg DLL，实际原MD5与官方pin一致；保留默认x64非ASIOPortAudio，最终v3明确省略7个未用binary，其他2041成员字节不变、26份license/notice保持，全部20个native均x64。许可证/来源/省略原SHA在包内manifest+NOTICE；Matplotlib自己公开sample_data仍原样保留，不含本地评估portrait或用户帧，不要扩写成所有wheel无图片。
- 最终只发/workspace/dist/tracking-addon-cp312-win-x64-v3.zip：83452536bytes，SHA4b3f763179bf771cd8466082114f9f9e4c87c0aab0d7caaacdab2fd705fccf21。2043锁payload+manifest共2044成员，解压231680607bytes。raw manifest含末尾LF，SHAde08abac2f341d0cacf2eba38fc89e53bef0252f98cc2f258736b95ed95bad12；canonical去LF SHAa72ef9399f156c76874ccda0357295b9123305e5b923ed7bf3d8673cf5484f8b。安装必须保留原字节，别把两种SHA混为重建。desktop已获最终唯一锚，不覆盖成品。
- optional加载先核代码常量manifestSHA及全部路径/文件SHA/类型，拒链接/reparse、未列文件/目录、.pth/sitecustomize/pyc、排除SDK/外平台二进制；失败不挂聊天。成功设置sys.dont_write_bytecode=True，真实纯Pythonimport后仍全树通过；去保护负控生成12pyc。另实修Matplotlib缓存：不能放model.parent，否则资源模型首次启动就在锁树生陌生目录；改进程级私有临时字体缓存，真实初始化/推理前后资源锁树均过，缓存不含帧/人脸。

## 2026-11-12 Root验收与发布门禁实际纠错

- 首个重建full真PASS：638 Python、9 desktop Python、79前端Node、24桌面Node、0skip，10核心strict类型；248程序/视觉SHA稳定。首源码commit f3e4b105cfc96e6ef3f412c57de5809de7acf53a逐文件与报告SHA相符。此为首冻结快照，不代替下述构建器补丁后的最终报告。
- 原图3D造型被用户明确reject，所有失败模型/渲染只在ignored .build/rejected-3d-reference；不可再展示/对比/交付。当前四图是真PNG状态，局部眼嘴合成不是Live2D/真拆件。实际RMS内部声静音能开闭、区域外像素exact0、4次资源fetch后不重复读，真实Qwen/Kokoro/停止6门亦过，Win4060/真人/真实账号仍未验。
- 强制SwiftShader首次只读Canvas read1→2会出现706个外区RGB差1，read2→3全图0；稳定纯读基线后实际Audio外区exact0、写外区1像素负控检出1。不能为此放宽阈值或误称口型越区已证；报告保存默认/SwiftShader对照和红probe。
- Root首次封小更新误手抄不存在的40hex source commit；builder旧门只验regex，错误包曾生成但未上传，已隔离 .build/rejected-package-metadata。必须自动从git读取真实SHA，并在CLI校验Git对象存在和随包源字节与提交树一致，封ZIP前再复核；禁止外发旧错包。新guard/真实临时repo正负测试由desktop owner补齐。
- 新Perception TLC配置1514 generated/529 distinct/depth11全搜索无反例，3移除owner/consent/迟到保护负控都检出；总14配置=4安全/10负控，report formal-model-rebuild-check.json。只证明有限抽象安全性质，不是Python精化或全程序/无限会话/活性证明。
- Workspace /workspace/HANDOFF.MD和项目HANDOFF.MD是两份不同文件，不是链接；项目发布相关坑需同时记录，不能以为写workspace就自动进入Git仓库。实际修复优先固化为执行门禁，避免仅靠长文记忆。


## 2026-11-12 发布提交标签误报与自动门禁

- Root实际手抄不存在的40hex f3e4b1071d6ac2f735f01cfdbfb5bd9ef3d43120时，旧builder仅regex检查竟产生包；已隔离未上传。不能把40hex格式或质量报告hash匹配等同Git提交存在。
- scripts/build_app_update.py 发布CLI现先用git rev-parse --verify <id>^{commit}确认真实commit，再用ls-tree及Git blob字节hash核对全部PROGRAM_FILES/host/随包installer与当前源码；调用builder/helper的checkout也须匹配。缺文件、symlink、tree对象、旧commit/脏文件、Gitless和不匹配publisher拒绝，创建输出目录前就失败；暂存完封ZIP前再核一次。纯build_folder的a*40夹具用途未改。发布必须先提交这些工具更改并自动读取真实HEAD，不能复用修复前commit。
- 新真实临时Git仓库10项+既有事务/installer21项合计31测试；还以本仓库实际错误SHA重放CLI，验证exit2、无ZIP/part/输出目录。报告review/app-update-check.json与app-update-commit-rejection-check.json；native/optional内容未变，无故不重跑硬件夹具。


## 2026-11-12 完整原创Live2D推进：不能拿PNG或自报参数冒充完成

- 用户明确要求真实完整Live2D，并新增独立手部、手指与可脱离杯子；r3合并持杯body不能满足，不得当full发布。GitHub v0.5.0-dev2-ui2d已核仍draft=true/13附件，保留PNG中间成果，不发布为完整版。
- 新可执行路线已实证：GPL PSD2Live v3.6.7 Linux小release + Java21，从原创分层PSD实际导出CMO3/MOC3/physics/motion/expression。官方Core接受原创几何v2且可见眼嘴像素真实变化；v1曾因PSD层序错误出现顶点动但眼嘴0像素，红图/报告保留。不能把工具链fixture绿当人物美术绿。
- 真runtime旧setLipSyncEnabled?.(true)是不存在的wrapper外层API，会静默不启用lipSync；已改真实startLipSync/stopLipSync并用保留Audio而禁开启的强负控，检查Core嘴参+真实drawable几何。旧stats.mouth>0不足证明MOC口型。
- Pixi8.23 GC看_gcLastUsed，而Jannchie1.4只写旧touched；真实4K活纹理60s可被回收后白屏1282/deleted object。已用真实GC负控定位，adapter通过正常getGlSource/bindSource刷新cache并保留闲置GC，实际66.276s/卸载/恢复新句柄通过。不能全局关闭GC掩盖。
- MCP rig_deform.translate delta是目标localBounds宽/高的倍数，不是canvas像素；delta10使唇飞额头/领口。r1坏修订保留；±0.01实际约0.20源像素仅目标mesh变化，其它exact0，微小中点不对称未假称exact。rect/center也是0..1归一化；旧像素selector可使权重全0，不能以键形存在算绑定成功。
- 美术atlas必须看真实alpha。左手初源5a9425d8灰晕背景实际大面积alpha64，不能归咎viewer；imagegen已修08efe181，alpha0=1,253,945/1,572,864，旧源保留不用。手掌cell越过y512，按实际透明沟槽y560分行，避免截腕/串指。
- 同画布隔离袖/torso只能统一源坐标映射x1.4,y1.4-50，trim后各自fit造成腕袖差200–300px。矩形肘切片会露横线；已获准沿原褶线polygon texture extraction保留28px重叠，不程序画新像素。肩alpha无缺口不代表布纹/明暗接边艺术过关。
- 原画分层由imagegen绘/补被遮挡部分，Node sharp仅标准atlas提取/纹理布局/真实网格区域划分，原生成文件不改。r4 head/body/hands各由独立manifest维护，最终只读manifest列层，不glob历史失败文件。新掌前景遮指根改善贴纸接茬，最终自然度仍需实际Core和近照审查。
- 磁盘仅约1.3GiB空余，已清本任务可重建quality-bootstrap-smoke及powershell-parser.tar.gz压缩包，保留parser解包、已发布base安装包/模型/用户数据/红证据。勿复制4GB基础包；vendor与工具release均私有，不推GitHub。


## 2026-11-12 Windows Live2D owner-run自助构建（不分发vendor）

- 默认Windows包已有CP312，两条已验Core install_official/bundle SHA门禁可复用。新增setup_live2d_owner.py +固定live2d-owner-packages.json +setup-live2d-owner.cmd，只在主人明确许可与信任锁定构建后下载；直接运行官方固定SHA的@esbuild/win32-x64原生CLI，无需Node/npm，不执行package生命周期。默认发行/Git不含Core、Framework或构建bundle，许可仍仅主人本机评估。
- 实际13包闭包+esbuild许可证包+Win原生包共28,859,896下载字节；Linux测试对应28,770,632。@types/earcut的tar顶层是earcut而不是package，已在锁中精确记录archive_prefix，不能通用乱strip。完整解包约101MB；私有短临时目录降低Windows路径长度，不修改机器LongPaths策略。长许可证banner在构建后本机写文件，避免Windows命令行长度限制。
- 真Electron新增--owner-runtime-path仅返回精确DATA/live2d根路径后退出，0窗口/未启动backend；不猜APPDATA。默认/relative overrides均实际Linux通过review/owner-runtime-path-native-check.json；Windows stdout/原生执行未测。helper先核host/路径模块/应用SHA与原runtime源码SHA，旧host无入口不启动；原运行租约要求先退出程序。
- SDK先装独立candidate，Core+bundle均通过既有SHA gate才成对切换；保留原runtime与事务，错误/模拟断电恢复，用户后来改动与坏备份拒覆盖。runtime实际revision中还含record.json，fingerprint必须包含，不能只接受script.js（首轮真实测试检出并已修）。用户角色/聊天/密钥/原模型不改。
- 真HTTP空缓存15包下载→Linux原生esbuild构建→真实官方Core→完整安装/恢复均已通过；当前bundle1,183,739bytes，CoreSHA25ae...仅观测非vendor官方digest。源码/完整报告见docs/implementation/live2d-windows-owner-setup.md；不把结构ready当真Core执行、Windows/4060或美术验收。vendor只留/workspace/.live2d私有，禁止push。


## 2026-11-12 原创Live2D双ZIP安全打包器（格式门不等于角色验收）

- 追加独立开发工具scripts/package_live2d_character.py，不改已冻结runtime/update。输入original-live2d-package-spec-v1精确SHA，runtime仅model3真实引用闭包+项目自有NOTICE；source仅显式原PNG/manifest/PSD/CMO3/PSD2Live/recipe/可选验收索引，不glob整个.build。源码/契约见docs/implementation/package-live2d-character.md。
- PSD2Live内部也可能藏vendor或错源，不能只检查外层扩展名：现限定实际项目结构、精确内部manifest、rig二进制PRIO；内嵌source/original.psd SHA必须等于独立PSD。已知官模hash负控仅防已知样例，origin仍是作者声明，不能宣传自动证明版权/所有官模检测。
- 真AssetStore.import_live2d只说明格式与归一化；synthetic MOC envelope可通过，所以报告永远candidate，Core/可播放/艺术/full均不由工具判过。可选验收index必须绑定实际MOC SHA与每项证据SHA/size，证据不复制、只索引，不把作者claimed_decision当本工具结论。
- 输入及写入中SHA漂移、symlink/junction、路径逃逸/URL/Windows保留名与非法字符、nested vendor/伪装weight、输出覆盖和并发抢占均有负控。独占硬链接发布只清本轮链接，不覆盖他人文件；3输出不具断电原子性，必须三件齐全且sidecar SHA匹配才可release；不支持硬链接的文件系统保守失败。
- review/live2d-character-packager-check.json实际19 unittest+Ruff+CLI help+真实CLI synthetic打包/重复拒覆盖全通过、source SHA前后稳定；测试假PSD/CMO/MOC明确只用于格式门，未对仍在改的r4角色封最终包，未Core/Editor/Windows/美术验收。


## 2026-11-13 小更新必须同步Electron版本元数据

- desktop/package.json原未纳HOST_FILES，小更新只改server会让app.getVersion仍旧版；现加入固定host写集/真实Git COMMIT_FILES/验证report SHA及回滚事务，package.name仍companion-desktop-runtime、main仍main.cjs，绝不因版本更新改变用户DATA身份。构建静态AST核package.version==server.VERSION；loader校负载名称/入口并对server改动再次校版本。
- CPU/CUDA SourceID仍只计backend source_files，server.VERSION既已在其中；host JSON由独立operation SHA与真实发布Git commit绑定，不把不存在的desktop文件路径塞backend profile。
- 新负控验证名称/入口/版本伪造，即使重算JSON负载SHA仍拒；真实temp apply/rollback恢复旧package，未提交JSON变化被Git guard拒。现app-update-check共50单测全过+Ruff/当前源码静态元数据核对，详review/desktop-version-update-check.json。原生capture源码未改，没有重跑或冒称Windows/4060/app.getVersion真机通过。
- 首轮旧stalefixture故意写invalid Python，被新增静态版本门更早拦住；已改为保留有效VERSION再改未测语句，仍确测SHA门。附加runner曾误用不存在test_ui_update.py导致0收集，已明确纠正为实际7项tracking-addon installer；不把0收集当通过，不因测试红放宽门禁。


## 2026-11-13 显式可选CAN3动画源归档

- packager spec新增可选can3:{path,sha256}，只允许.can3和CAFF头，固定source/character.can3，runtime ZIP不含它；仍不glob邻居/改变Core或candidate判断。实际r5/export-candidate7/character.can3只读观察253306bytes、CAFF、SHAecefeec42f78770019e1931e86b68acaa6c98919fcc1b6a37546bcda50acc18f；未实际封此候选或声称Animator重开。最初按r4找不到，已定位真实r5路径，未把缺文件写成已验。
- 3项追加正负控（source-only精确保留+SHA/大小、错suffix/头、固定SHA后漂移）后共22测试+Ruff+真实CLI synthetic CAN3/重复拒覆盖通过，review/live2d-character-packager-check.json已更新。版本更新50门freeze不动，正式模型仍待最终源冻结。


## 2026-11-13 组合姿态与源场插值不能靠角点代替

- 当前candidate7已实际否决：12个肩肘组合（同侧四角、双侧相反）出现可见衣片尖刺/白锯齿，边长比最多64.379；Core/GL无错只证明可渲染。后续修复保持肩±4/肘±6，必须用相同组合检查，不能只验单轴。证据review/original-character-live2d-candidate7-combined-joint-{folds,gl}.json；首轮harness缺neutral baseline错误另存红，不归因产品。
- 持杯486作者角点近精确仍在61离key有3.184px滑掌。独立1350真Core掌点诊断区分源场非线性/杯表示误差，Lean加±5的810格预测0.881705px；预测不是新MOC通过。最终使用额外独立seeded离key，保留1px预算，不用参与选网格的61点充泛化验证。
- 只读视觉复核发现r5中性闭唇过薄、眼睑边硬。原145×42闭唇有体积，优先查实际默认参数/mesh厚度/opacity/UV，不据此重新整脸作画；白底图不能替代同一final rig在morning/forest/evening实际合成光色验收。三个背景主光均右上，与人物边光方向基本一致，不能编成光向相反问题。


## 2026-11-13 原图集切片、实际排序与杯子完整父链

- 眼atlas并非均匀5行。旧y614切到iris，实际左upperlash首边41个alpha>=8像素，进而把iris残片和真lash压入42px。新透明gutter为[0,350,685,960,1230,1536]。scripts/live2d_atlas_cells.mjs现拒切到可见alpha的四边，9个Node正负控和实际旧源负控通过；仅4个iris/lash PNG改变，完整正式源必须重建其alpha网格，不能沿旧mesh贴新图当完成。新输出目录禁止覆盖旧冻结源。
- Node默认文件系统沙箱的child IPC会只显示文件级测试数；负subtest仍确实exit1。正常授权进程与非隔离检查均记录实际9case通过；最终quality使用正常授权进程，不把filecount冒充casecount。
- 新AA underlay若仅anchor在Torso之前，会得到base45，实际在Upperarm30/40前，造成静止贴片盖肩。keyform drawOrder20 API成功仍未改变MOC base45；重新按已证import anchor在旧backfill20后插入实际base25才真在上臂之后。必须检查官方Core renderOrders，不只看请求/作者组织顺序。
- visible:false也不是Core opacity0，exportHiddenDrawables时旧底片曾仍opacity1。旧片停画及技术helper都需要清真实opacity轨（包括复制来的CupVisible0/1），以Core逐值0验证。
- 杯子flatten810在旧61离key过，但独立512仍43个失败/max3.223px；直接挂原BodyZ反事实512全部失败/max41.335px。原因包括零角Rotation子也会把Warp父刚性化，不能当透传。原始min/default/max不是完整作者内部关键格。
- 可行结构已由独立实际Core/产品证明：一个可见ROOT杯，两恒0opacity技术helper，单向NativeGlue先全跟一侧再按t混另侧；完整手动控制外根必须原生Rotation(scale1)，并复制原3BodyWarp+6Shoulder/Elbow/Wrist真实父链。新未参与选择的1000样本最大接触差.005953765源px，H0 visible杯全vertices exact0。此为技术候选证据，不能覆盖正在重放的最终新PSD/MOC。v2合同明确可见杯与技术helper作用域，保留1px握点/.5px指根及物理角色非杯exact0，helper任意非0opacity即拒，旧v1结构红保留。
- 第一轮全量8步虽然各自通过（Python754零skip、desktopPy9、Node97、desktopNode27），但两份manual test源在检查期间改变，整体报告正确false，未改成绿或用于发布。最终必须用稳定源码新全量报告。


## 2026-11-13 实际dev3小更新exactbase文件验收

- 实际已提交084aaf222b54e1828595bde82fc07c58acbb6075程序包character-app-source-update-0.5.0-dev3.zip(7026261bytes/SHA d66259ccbf7c944f5b626c85cfa0a10adb1c1a7a5926787eb522dfcd8a8a3ac6)由产物自身app_update.execute完成82ops真实apply/repeat/rollback；原baseZIP前后exact92d3...，SourceIDd26a...。只复制92源/metadata计4376827bytes、22native只读hardlink，未复制6GB/运行Windowsexe或DLL。
- 两套复制后的CPU/CUDA后端实际loopback返回/stage-actions.js 200且SHAe5813ca2874931452384618d8380a39f5e4d88743b57c84631f4e797daaef5f8(4796bytes)，非白路径404；产物ownerhelper可载入/锁验证、未ack拒安装。13门/19.149s全过，每operation原SHA恢复、所有选定原base文件及synthetic model/data哨兵未变，副本已清。review/app-source-update-dev3-exactbase-check.json含实际脚本重现与SHA。
- 首次正常sandbox不许socket(EPERM)使CPU路由仪器失败，保留.failure.json；按root授权escalated允许127.0.0.1再跑同脚本才完成，不假装初轮全绿或放宽产品门。当前仅Linuxfilesystem+真实HTTP路由，不称Windowscmd/4060/模型推理验收。


## 2026-11-13 当前源码全门与小更新真实产物

- 主舞台动作/表情与硬杯测量CLI冻结后，quality-gate-live2d-mainstage-final.json于03:33:41 UTC实际8步全PASS且源码稳定：Python766/0skip、desktopPy9、Node111、desktopNode27、strict10模块、7架构规则/15负控。此为软件源码门，不冒充尚在私有作者工具写入的新硬杯模型或Windows/4060验收。
- 软件实际commit通过git程序读取为084aaf222b54e1828595bde82fc07c58acbb6075，builder commit guard/CRC均通过，小更新character-app-source-update-0.5.0-dev3.zip为7,026,261bytes、SHA d66259ccbf7c944f5b626c85cfa0a10adb1c1a7a5926787eb522dfcd8a8a3ac6，82白名单操作；分支已push至GitHub。此产物不含模型/SDK/用户数据。
- 盘空间不足时仅将8个冻结formal旧export中完全相同的10,109,209byte atlas做exactSHA硬链，保留所有路径/字节，实际回收70,791,168分配bytes，报告review/live2d-formal-retired-atlas-hardlink-dedup.json。新r2必须使用新export目录，不能对共享旧atlas原地重写；原画、PSD/工程、已发布baseZIP/parts和用户数据未动。


## 2026-11-13 最终作者源落盘的真实容量险情

- rolling大域工程保存中free降至20MiB，不能继续只做10MB小文件去重。仅移除已经过时、由本会话生成的旧Linux安装ZIP `/workspace/dist/XiaoLan-linux-x64.zip`（1,643,010,416bytes、SHA1c6d468f4825d11c146934b8684149682a9e051b7e356c01fb38893bdd195ca9），删除前记录1155个member/CRC/size到review/obsolete-linux-installer-cleanup.json；free恢复1.6GB。用户已选择Windows，保留更新3,023,043,885byte Linux v0.2 ZIP、全部Windowsbase ZIP/parts/unpackedbase、Git源/原画/可编辑项目/权重/媒体证据/用户data。没有删除用户上传资料。
- 作者checkpoint需关注临时保存的展开/历史容量，不能仅按最终压缩40MB推需40MB空闲；IO失败可能局部生效，必须读取actual state/terminal save和SHA后续，不能把ENOSPC当完成。


## 2026-11-13 作者源离线打包容量门：不能提高产品上传门

- root仅解冻开发packager/tests/doc：实际rollingC SHA02d3e704104a7c6ab3d1906ae127b1faac567096b0ec8b740f3bcfbff01193c9在旧8MiB每JSON门真实拒绝，红review/live2d-packager-c15360-old-budget-red.json保留。历史文件名c15360不是当前格数声明；该实际ZIP126777737bytes/expanded730842307，未超旧768MiB aggregate，旧通用error实际由单JSON超8MiB触发。
- 现只对严格document/nodes/journal/[a-f0-9]{64}.json给64MiB，且filename stem==actual流式SHA==独立manifestSHA；nested总2GiB、8192entries，其他内外JSON仍8MiB、source单文件256MiB/selected总512MiB、所有生产runtime/上传/owner/updater门不改。超过最终硬预算应报真实size阻断，不继续盲涨。
- 预算修后实际同源又被127个history/revisions/<64hex>.json拒，红review/live2d-packager-rolling-c-budget-preflight-red.json保留。root授权精确兼容路径后仍8MiB+manifestSHA/CRC。实际127文件stem均非payloadSHA，不能把journal内容寻址规则硬套历史revision身份；真实格式观察另报告。
- 33专属单位正负控+Ruff过：>8MiB/exact64MiB journal绿，64MiB+1红；同大nonjournal/history红、错prefix/hash红、stem/manifest两独立SHA/CRC红、metadata假大2GiB aggregate红(不构造2GB文件)。代码/测试/doc新冻结review/live2d-packager-source-freeze.json。
- 真实C before/after SHA稳定最终预检1180payload逐SHA+CRC/PSD身份过，103journal、最大14842068bytes；1.843s/peakRSS21156KiB，review/live2d-packager-rolling-c-budget-preflight.json。仅离线checkpoint结构预检，不是最终角色/编辑器/Core/完整sourceZIP通过。7MB软件artifact SHA d662...未变，不复测084产品；root另跑新全量gate。


## 2026-11-13 最终作者工程显式project字段320MiB门

- 最终rigid-cup-character.psd2live实际281235238bytes/SHA1dd382af309e1ee15292cc628361e93d52bf9d83cf077fec1c5ab96379202d70，原通用256MiB门真实拒绝；review/live2d-final-project-old-256m-red.json保留，不把新版可过回写旧红。root仅授权开发packager明确project字段到320MiB（约19%实测余量）。
- pinned新增keyword-only source_limit，只有source_members的project行显式传MAX_PROJECT_FILE=320MiB；不按.psd2live扩展名全球放宽。其他源256MiB/selected总512MiB、JSON8MiB/journal64MiB/nested2GiB及所有产品门不动。3追加测试用真正稀疏ZIP，mock仅外层SHA避免读大hole；256MiB+1通过实际source_members字段→check_project，320exact允许/+1拒，generic project/PSD/PNG仍256拒。
- 36专属测试+Ruff过，新freeze review/live2d-packager-source-freeze.json/sourceSHA8795cb7c28bb76e4e7df1ea0e978efdbde97131a7a2a5764a74ffee395f486ab；详情live2d-packager-project-field-limit-check.json。实际最终文件单独无mock真SHA前后稳定，展开1496362356bytes/1579members，1578payload CRC/SHA及118journal/PSD身份均过，3.896s/峰RSS20816KiB，live2d-final-project-size-and-format-preflight.json。
- 以上不是整个sourceZIP selected总量/最终Core/艺术验收，必须正式packager另跑；生产084和7MB更新artifact SHA d662...不变，root另跑新全量gate，勿拿旧sourcegate覆盖当前packager版本。


## 2026-11-13 本机最终功能交付与真实语音恢复通过

- 最终MOC6e34/42mesh41params/47真实点/v1无helpers的13门、547双通道、sealed5000 asm grip.678588px、shape similarity.0001063px/affine.0000857px、Root27、主UI9/表情3/三景与中段均真实通过且public源码未再改。全部327当前源码SHA与780/111最终门一致。547是486所选角点+61离key，不是20655内部全表Core穷举；source/MOC41310键格另有独立证书。
- 实际provider第一次由QA调用，在环境重置后只留三图/WAV/raw视频，无最终stop报告，不能因为已无PID误称未调用；Root不同目录作一次完整恢复，review/real-live2d-rigid-r2-companion.json7门全过：exactZIP23af→Qwen/Kokoro/Analyser/Core、stop.793s、未听尾部排除与UI原文保留。两轮目录各自不覆盖，原interrupted JSON保留；不能声称只调用一次。
- 当前恢复CPU单次首次文字49.54s、语音RMS69.621s、进程peak约5.37GiB，不声称已达实时/Windows4060目标。Playwright录像无音轨，真实WAV另附。Source重导出CLI6GiB heap/RSS约6.2GiB与正常角色运行不同，不混作运行开销。
- 实际双ZIP：runtime11,017,918B SHA23afbd6435a8c548d3cdb3bbe0c8ba19d6161b46d520fa82a297446d961b052e；source345,553,022B SHA1625219f73d99defc82d6b2dbb23bdf90c16113d3293fd632a7320b6cbf8f0dc；source-validation49,477,803B SHAae2e9a61d05e5c475541e7673cf820e5f57c3d374b9cbcd5bdfc40df8cadde41。Root source/index、native/runtime/provider证据分开，SDK/权重/真实会话/禁用3D均不进发布包。


## 2026-11-13 GitHub最终预发布与匿名下载核验

- 最终发布v0.5.0-dev3-live2d/id443847254已实际公开为prerelease，tag源码f1667eaa9d7dc58fb8a3e2328f7b9783fc698534，16附件共635,455,841bytes，GitHub每个server digest/size与本地SHA逐个相同。review/live2d-release-assets-verified.json和live2d-release-publication.json存核验记录，无secret；7个发布页/更新/运行ZIP/截图/视频/WAV/PDF链接匿名HEAD跟随均HTTP200，彻底区别workspace链接下载不可用。SDK/权重/用户会话/禁用3D未进本批。
- GitHub草稿创建成功后GET releases/tags仍404，不能因此重复create；应列owner releases精确tag唯一匹配取得ID。发布后tagGET才成功。上传器已强制draft/唯一ID/同名同SHA幂等、额外文件拒绝和全部16远端digest确认后才publish。
- 旧gh pr edit查询deprecated projectCards而失败，改官方REST PATCH既有PR1 title/body，仍draft/open且不merge；不是产品代码失败。
- Chrome企业策略file://返回ERR_BLOCKED_BY_ADMINISTRATOR，技能页用临时127.0.0.1 HTTP正常预览生成PDF/截图，源策略未改；完成停服务，JS0/外连0。HTML仍用answer-me-with-html CLI，四panel/STE0，PDF可直接阅读，不把说明页当软件。
- 模型和媒体已冻结、代码源327SHA仍与780/111最终全门相同。后续publication receipt独立文档提交不更改release code tag或084软件ZIP；Windows/4060、实体设备/账号、用户E5仍留待目标环境。


## 2026-11-15 学习直播人工确认链路（仅本机冒烟）

- 开始新任务先读本文件，先确认真实目标、约束与可证伪的成功标准。默认 Codex 浏览器/Chrome；使用 Vivaldi 前询问。上线/部署验收包含性能开销。UI 优先通过布局表达，避免重复副标签。
- 下载并阅读 tanweai/pua，固定 e6e6cd237ad17750d179674bff52f8184abea8fd；只应用证据排查流程，未安装全局钩子或遥测。当前环境找不到 answer-me-with-htmi/html 技能或 CLI；历史使用记录不代表现在可用。
- 旧 bili/reply 只含弹幕，没有教材版本绑定及输出消费者。新增公开教材SHA、人工批准、独立字幕/音频页与状态约束。令牌仅访问公开输出，输出页不获取私聊Cookie；不新增平台发弹幕/自动批准。
- 确认的浏览器坑：新令牌放在同页URL片段时，导航不重载旧脚本。run-5 第二条实际超时；增加 hashchange 清理并重载，run-6 相同流程通过。停止会撤销令牌，必须重新打开输出页；已领取的内容不自动重播。
- CSP 下 Playwright wait_for_function 需传函数而非字符串表达式。run-1 是测试脚本错误，不是产品播放失败；不放宽生产CSP。
- 冒烟采用自编A-Level导数/切线教材、合成B站事件、确定性回答和440Hz PCM测试音。Chrome播放进度与WebAudio实际信号、完整视频及Trace均保留；测试音不冒充真实TTS，WebAudio图不冒充系统扬声器、OBS或观众接收。
- 输出内存限一个准备/播放音频（至多20MB），每连接至多100条任务、500条状态记录，轮询250ms；沿用30秒问题TTL，未因CPU模型慢而扩大。真实模型可能超时，不能把本机夹具速度当真实性能。新测试停止预算1.5秒来自1250ms断联截止及轮询/计时余量，并非目标Windows实时承诺。
- 当前未接真实B站、OBS、Windows4060，未评估真实模型依据正确性、真实语音、学习收益或独立验收。下一阶段先接已授权房间和真实模型/音色，再保存主播端/观众端录像与分轨音频；没有这些不能标记MVP完整验收。


## 2026-11-14 直播答疑界面审查与工作方式

- 每轮对话开始先参考 https://github.com/tanweai/pua/blob/main/chatgpt/pua/SKILL.md ，用于内部工作；不向用户展示施压、绩效或羞辱话术。简单问题直接回答，复杂任务先核对目标/约束/验收、读原始证据、用能区分假设的实验排障、交付前验证。此约定不代表已安装全局钩子。
- 用户否定上一轮界面的AI感。原截图暴露设置说明抢占首屏、问题与答案拆成重复卡片、按钮同权。此次围绕直播问题/回答重排，缩短操作词，设置后置，停止按钮固定可见；不改角色或后台授权边界。
- 2026设计依据：Linear官方2026-03-12 UI refresh（https://linear.app/changelog/2026-03-12-ui-refresh），关注信息扫描、一致控件、弱化导航；查阅日期2026-11-14。不能将引用当作审美通过证书，也不能把AI自评当用户认可。

- 深色审图发现主题切换时背景渐变与即时文字颜色不同步，且全局hover可覆盖主操作颜色。直播面板改用同步底色切换和专属hover色，浏览器计算浅/深主题常态与hover对比度须≥4.5；不能仅以无JS报错代替视觉检查。


## 2026-11-14 直播异常路径复审（本地合成事件）

- 刷新重建表单会丢未保存教材；必须保留草稿，编辑后撤销旧公开勾选。晚到的状态响应必须用请求序号拦截。重复点击要以任务键锁定，刷新替换按钮后也要释放。
- TTL不能只靠输出页轮询清理：输出页关闭时，owner读取和批准路径也须清理过期任务与丢失心跳消费者；当前主界面需手动刷新，不宣称推送更新。
- 音频权限拒绝/解码失败必须显示可操作错误并停止；异步音频下载完成后必须验证当前epoch，避免停止后复活。长字幕先测量，无法完整显示则不播放；这不是分句字幕支持。
- 突发问题把待审核答案推到列表后方：答案先呈现，再列问题。键盘进入设置在旧版已通过，不能计作修复。
- 原始红绿日志、旧源码负对照、未剪辑Chrome录像/Trace保存在本地 .build/live-audit；公开报告 docs/validation/live-adverse-path-audit.md。测试使用自编A-Level数学、合成事件/固定回答/测试音，不代表真实模型、B站、OBS、Windows或独立验收。
- 测试模块实际叫 test_platform_integration_http，误写 test_live_output_http 导致的是测试调用错误；改用实际模块后22项状态/HTTP回归通过。
