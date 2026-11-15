# UI/UX 与直播室设置核对

日期：2026-11-15。基线PR46，远端076268adecc414ba1fbe0839d93d96282f2ce0c9，本地对应树4fc5a8d432010c6c477ed5163f71589c1781c49c。范围仍是PC本地开发，不安排平台环境测试。

## 先查源，再改流程

| 已读取的原始资料 | 能支持的产品思路 | 本项目观察与修订 |
|---|---|---|
| OBS源码 fe1ed7955f300efd17fc59f65938388e43d8bb06，frontend/widgets/OBSBasic_StudioMode.cpp | Program显示与配置操作分开，切换有明确操作 | 原设置面板覆盖整幅画面；改为独立设置区、16:9画面和单独全屏预览 |
| bitfocus/companion源码/文档 7213ebd729f32446a561bef9c660e4e96fbdbb3f，docs/user-guide/3_config/program/buttons/creating/feedbacks.md | 按实际状态反馈，不以点击意图冒充实际状态 | 原点场景立即改变画面；改为草稿选择、应用和已应用状态；不显示虚构开播状态 |
| Open-LLM-VTuber-Web源码 d176e7df2366952e3bacbf12cf9a8b18a4315932，src/renderer/src/hooks/utils/use-interrupt.ts | 中断时停止音频/口型并清队列，源码只针对Thinking文字清字幕 | 本项目已有停止逻辑，本轮继续实测保留；没有把它说成新实现，也不复制其角色、提示词或SDK |

资料链接：
- https://github.com/obsproject/obs-studio/blob/fe1ed7955f300efd17fc59f65938388e43d8bb06/frontend/widgets/OBSBasic_StudioMode.cpp
- https://github.com/bitfocus/companion/blob/7213ebd729f32446a561bef9c660e4e96fbdbb3f/docs/user-guide/3_config/program/buttons/creating/feedbacks.md
- https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web/blob/d176e7df2366952e3bacbf12cf9a8b18a4315932/src/renderer/src/hooks/utils/use-interrupt.ts

这是代码与文档审阅，不是已运行这三个产品的可用性对比。不以GitHub星数、功能数或最新版标签证明设计收益。

## 同条件复现及根因

实际PC Chrome、同一用户原话、同一项目原角色：
- 初始版会写入固定欢迎消息；空主题和提问显示占位文案；设置区覆盖画面；选择即改变预览；刷新丢失配置。before-character/report.json五项失败，其余结果原样保留。
- 原因分别是init_profile种入消息、画面内静态文案、fixed覆盖布局、按钮直接改生效状态、仅内存保存。
- 新版不再种欢迎消息；新角色对话规则为空；已有用户记录/自定义规则不删除。移除性格预设、固定学习步骤、举例占位和隐私页宣传句。试听只朗读用户输入，空文本不可点击。到期提醒仅引用真实任务标题；空闲提醒描述真实时间条件。
- 编辑区和预览区分开；全屏只包含画面。内容、模式在点击应用后生效；草稿和已应用配置按角色保存；刷新后计时保持暂停；改主题清除旧主题计时；清空画面不删除原文，刷新后仍可恢复草稿。
- 字号按画面容器缩放；应用前测量完整显示范围，过长文本拒绝应用并保留原稿。窗口缩放导致文本不能完整显示时，停止显示该文本并在操作区报错；没有用裁切冒充显示完整，也未隐藏/改变人物图层。

## 禁止虚构示例的执行边界

产品初始内容为空，截图输入仅来自用户实际消息：
- 主题：检查uiux和直播室设置的差异
- 提问：人物你有了吗
- 草稿保留测试输入：禁止ai文案

没有新增虚构教材、观众消息或模型答案。HTML攻击串、重复输入和机械单元夹具仅用于故障注入，不作为演示内容。应用仍能处理真实用户提问和模型回复；本轮禁止的是预置套话、虚构内容和固定性格/学习样例。

scripts/check_ui_copy.py加入正式质量入口，限制已确认套话、示例占位、预览中的交互控件和种入欢迎；tests/test_ui_copy_contract.py保留坏版本反例。这是有限静态规则，不能判定所有文字作者或审美优劣。copy-negative-control.json直接核对旧生产源码被拒、新源码通过。

## 实际测试

- tests/room_settings_browser.py：原生浏览器点击、键盘/填写、刷新、全屏、1024×768/1280×720/1920×1080，检查设置分离、草稿与应用、空状态、暂停、主题切换、长文本拒绝、角色隔离、HTML不可执行。完整录像和Trace保留。
- tests/voice_room_browser.py：用户原话经实际Kokoro/Audio/Analyser/Core，默认角色绘制、口型和停止复位；提问和字幕不使用旧虚构例子。
- 相关HTTP和前端回归，以及scripts/quality_gate.py完整检查。
- 最初删欢迎的替换未匹配原SQL形态，同条件测试仍拒绝；随后删除确切插入块再通过，保留after失败记录。
- 字体原按浏览器宽度而非预览宽度缩放；真实截图出现不合理换行，改为cqw，并增加溢出拒绝/缩放检查。

## 环境与剩余边界

Linux PC Chrome 157开发验证。角色源文件字节未改；原角色仍是待人工审查候选。Core与原模型由本地已取得文件提供，未随公共GitHub源码分发。Windows/DPI/RTX、真实服务、OBS接收与独立人工可用性测试未取得。

room仍是本地手动预览，并未接入自动直播事件。设置按照打开时角色隔离，尚不做跨窗口实时角色切换。新增一个ResizeObserver，合并到一帧测量，停止页面时释放；不增加平台轮询或推理请求。未把有限窗口检查扩写为所有性能通过。

复跑：
```sh
python3 scripts/check_ui_copy.py
PYTHONPATH=src:tests python3 -m unittest test_ui_copy_contract test_character_http
PYTHONPATH=src:tests python3 tests/room_settings_browser.py --chrome /path/to/chrome --with-character --model /path/to/role.zip --runtime-dir /path/to/owner-runtime --out evidence/room
python3 scripts/quality_gate.py --bootstrap --full --report evidence/quality.json
```
--with-character需要已交付原模型和自备运行时路径；所有路径通过参数传入。省略角色参数也可执行纯界面与状态检查。不对用户机器作已通过声明。

P7三问：旧角色/语音/计时API保留；空/长输入、草稿、刷新、暂停、跨角色和全屏边界由实验支持；修复状态与布局根因，未用换配色或新文案替代流程修复。
