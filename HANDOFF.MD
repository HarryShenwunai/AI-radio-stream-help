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
