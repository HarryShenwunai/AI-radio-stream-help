# 二次元桌面陪伴：Electron 与 Tauri 宿主核查

查阅：2026-11-12，Europe/London。用户已选择桌面陪伴并强调二次元主题；“先不改应用UI”继续有效。本轮只读官方文档，没有安装、运行、打包桌面壳或连接账号。

## 结论

两条路线都有桌面窗口所需的基础能力，尚不能只凭API列表选定宿主。Electron可作为复用现有Web与Chromium验证的候选；Tauri可作为系统WebView路线候选。选型应由目标OS、角色渲染兼容、输入命中与同机资源观测决定，不虚构工期、安装体积或节省百分比。

透明、置顶、鼠标穿透、键盘焦点、跨工作区和全屏都是不同能力。对独占全屏游戏、受保护内容、管理员窗口、窗口管理器行为，没有本轮运行证据，不保证覆盖。

## 已核实的 Electron 能力

[BrowserWindow API](https://www.electronjs.org/docs/latest/api/browser-window)支持`setAlwaysOnTop`、`setIgnoreMouseEvents`；后者忽略整个窗口鼠标输入，不表示按透明像素自动命中。窗口有焦点时仍可能接收键盘。`forward`仅标macOS/Windows，Windows较高完整性级别窗口会影响转发。`setFocusable`标macOS/Windows，macOS不会因此自动移除当前焦点。跨工作区API在Windows无效，macOS另有全屏可见选项；这不是全屏游戏覆盖保证。

[窗口样式文档](https://www.electronjs.org/docs/latest/tutorial/custom-window-styles)说明无框与透明设置，也列出透明窗口调整大小等限制；透明区域本身不能自动点击穿过。文档的透明图是示例，不是本轮实机测试。

[交互文档](https://www.electronjs.org/docs/latest/tutorial/custom-window-interactions)给出显式穿透与拖动区域方案。拖动区会吞指针事件，按钮要排除出拖动区。不能把整个人物画布设为拖动区后假定眼睛、菜单、输入都能正常点击。

[进程模型](https://www.electronjs.org/docs/latest/tutorial/process-model)是主进程管理窗口、renderer显示Web内容；窗口数量会影响进程与生命周期。[安全文档](https://www.electronjs.org/docs/latest/tutorial/security)要求控制本地能力、隔离不可信内容。复用现有页面不能等于让模型输出获得Node或Shell权限。

## 已核实的 Tauri v2 能力

[当前配置参考](https://v2.tauri.app/reference/config/)提供`transparent`、`alwaysOnTop`、`focusable`、`skipTaskbar`。Windows透明创建可能出现白闪，文档列出`noRedirectionBitmap`相关提示；`skipTaskbar`配置针对Windows/Linux。不能把任务栏隐藏当成macOS Dock隐藏。

[窗口API](https://v2.tauri.app/reference/javascript/api/namespacewindow/)提供`setIgnoreCursorEvents`、`setFocusable`、`setSkipTaskbar`等方法。穿透和焦点设置需相应独立权限，并非`core:window:default`自动开放。macOS已聚焦窗口不能靠`setFocusable(false)`自动失焦，`setSkipTaskbar`在macOS不支持；跨工作区在Windows不支持。`setFullscreen`改变自己的窗口全屏状态，不证明可覆盖别人的全屏窗口。

**版本纠正**：[Tauri 2.12.1官方发布说明](https://v2.tauri.app/release/tauri/v2.12.1/)日期为2026-09-30，明确macOS透明/全屏不再要求`macos-private-api`标志。部分旧或翻译资料仍保留旧描述。后续必须固定选定版本，不能沿用旧教程断言当前一定需要该私有API；本轮也没有验证商店分发、签名或具体macOS版本兼容。

[Tauri WebView说明](https://v2.tauri.app/reference/webview-versions/)区分Windows WebView2、macOS WKWebView、Linux WebKitGTK。因此现有Chrome测试不能代替macOS/Linux内嵌WebView的音频、WebGL与布局验证。

[Tauri Sidecar指导](https://v2.tauri.app/develop/sidecar/)允许打包外部二进制，并有目标平台文件与执行权限配置。这为复用Python后端提供可行路线，不表示现有Linux原生程序可直接在Windows/macOS运行。

## 两条宿主路线比较

下表为基于文档与本项目现状的工程判断，尚未实机验证。

| 项目 | Electron 候选 | Tauri 候选 |
| --- | --- | --- |
| 现有Web复用 | 通过受控本机URL加载页面，Chromium行为与已测环境较接近；仍要专门验收壳内行为 | 可复用Web内容，但各平台WebView不同，不能继承全部Chrome结论 |
| Python后端 | 主进程启动/监督单个本地后端进程 | Rust侧/受限sidecar启动同一后端进程 |
| 系统窗口 | 已读API覆盖透明、置顶、穿透与焦点；平台差异需验收 | 已读配置/API覆盖相应能力；需最小capability与平台验证 |
| 工程新增 | Electron主进程/preload、窗口路由、打包更新与本地权限边界 | Rust/Tauri命令与capability、目标平台sidecar、系统WebView兼容 |
| 资源判断 | 内含Chromium/Node且多进程；开销必须测，不用经验数值代替 | 使用系统WebView不等于零开销；总量仍包括Python、模型与图形资源 |
| 目前选择条件 | 若首要任务是在已测Web基础上验证窗口行为，值得先做宿主样例 | 若目标设备明确并愿意验证不同WebView，值得做对照样例 |

目前只能决定先做有限宿主验证，不能决定最终Electron/Tauri，也不能把“更轻”作为未经测量的结论。桌面方向已选定，不再把它当作未决体验方向。

## 保留现有后端的约束

现有`app/server.py`是单用户本机HTTP/SQLite，校验Origin、Host与Cookie。桌面壳应复用一份后端和模型；多个角色/聊天窗口不应各自加载模型或同时写不同版本数据库。

候选做法是受控本机页面加可信宿主启动流程。若用Tauri自定义协议或`file://`页面，Origin/Cookie/CSP与现有本机HTTP路径不同，须明确配对和验证；不能为“接上了”直接放开通配CORS或去掉认证。本文未实现任何新传输。

窗口控制与后端调用分别授予最小权限。模型文本只作为内容，不直接调用Shell、文件系统或窗口能力。宿主应有单实例/重复启动、端口冲突、后端健康检查、崩溃恢复与退出清理；关闭角色窗口、隐藏、结束通话和退出整个应用要有不同语义。

角色窗口与完整聊天窗口需共用当前generation和一个音频输出所有者。否则两个窗口各自轮询提醒或自动朗读，可能重复播放。口型与听到的声音共用实际播放器状态；新窗口打开不应重播旧队列。

## 二次元桌面角色的验证要点

“二次元”属于角色形象与表现要求，不能仅用透明窗口或波形代替。宿主不自动提供角色素材、Live2D/VRM许可、口型映射或表情策略。这些仍需独立选型与授权。

| 层面 | 需要验证 | 可记录的量或确定结果 |
| --- | --- | --- |
| 透明/命中 | 人物可交互区、空白穿透、拖动、菜单和输入框 | 错误拦截底层点击次数；窗口/人物命中区域日志；不可操作状态能否恢复 |
| 焦点 | 待机不抢焦点；用户明确输入时可聚焦 | 意外抢焦点次数、键盘输入去向、退出后焦点恢复 |
| 场景 | 桌面、普通应用、最大化、无边框全屏与独占全屏分别测 | 每种场景的可见性/置顶/输入结果，不统一写“支持游戏覆盖” |
| 多屏 | 混合DPI、缩放、拔屏、工作区切换 | 位置/尺寸偏差，字幕和人物是否离屏，可否回收至可见区域 |
| 动画 | 静态、待机、表情、口型、隐藏/最小化逐项对照 | 实际FPS、帧时间p50/p95、CPU/GPU、内存/显存增量 |
| 声音与口型 | 以实际输出音频驱动；停止、迟到与设备切换 | 停声到口型停止时差；旧generation动作复活次数；重复音频次数 |
| 常驻 | 前台空闲、隐藏、屏幕锁定与电池状态 | 唤醒/绘制频率、总进程RSS、能耗趋势与系统睡眠行为 |

性能应测完整进程树，并分离“后端基线→加宿主→加静态角色→加待机动画→加口型/特效”的增量。固定同一设备、资产、显示尺寸与会话，不能拿另一个模型或分辨率的数据比较宿主。

口型若只由音量包络驱动，应说明是开合反馈，不冒充已实现音素级同步；若要音素对齐，另验证时间戳、延迟和具体渲染器。停止音频后仍播动作、隐藏窗口仍高速绘制，都应进入失败用例。帧率、资源与能耗门槛待设备和角色素材确定，不在本轮编造。

## 状态与未解决项

- 已核实：上文列出的官方窗口API、平台备注、WebView差异与Tauri版本修正；访问日期均为2026-11-12。
- 可信待验证：在所选版本与目标机器上按这些API组合出稳定桌面壳；官方API存在不等于组合行为已通过。
- 工程推断：可保留Python后端与单音频所有者，用有限宿主样例检验选择；没有虚构工期。
- 未知：用户目标OS/设备、Electron与Tauri最终固定版本、窗口管理器/显示协议、角色素材/渲染器、签名分发条件、全屏与屏幕共享行为、真实性能。

本轮运行测试数为0。没有修改应用UI或安装桌面宿主；后续实现、分发和真实设备测试另按已批准计划推进。交接由主Agent统一更新。
