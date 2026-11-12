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
