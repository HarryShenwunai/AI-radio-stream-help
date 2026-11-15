# 现场互动主线：P7诊断与验收

范围：Windows PC产品，Linux PC Chrome开发验证；不改角色和持杯，不开启自动公开回应。基线为PR43提交0247f1b77caf7674643c76d6aae4875f137b9d69。

## 方案与判据（修改前固定）
目标是观众无需教材也可招呼、追问、换话题。竞争解释：UI表单限制、后端门槛、模型策略。直接检查与同输入旧/新实验确认后两者共同造成强制教材。最小修复集中在公开互动状态与提示构建，既有严格答疑保留为可选模式。

约束：仍逐条确认；30秒事件时效、160输出token不变；长度截断拒绝；不注入私人历史；不伪造音画感知。公开背景最多1200字符，最近最多5条各500字符，限同房间及话题、当前问题之前接收的未过期消息。原接入协议、模型接口和输出回执兼容，无新增运行依赖、定时器或自动请求。

|问题|区分实验/证据|修改|验证及界限|
|---|---|---|---|
|无教材招呼被拒绝|同一事件旧版begin报“请先设置允许公开的教材”，新版generating|默认interactive；strict独立门槛|negative-control.json；HTTP与PC浏览器无教材预览|
|模型只会索要教材|捕获完整公开模型输入|现场/严格策略分开，近期弹幕和背景结构化|真实Qwen招呼、追问、缺失指代、转话题、恶意指令原文；内容正确性需独立评审|
|换话题/主播接管后晚到输出|旧事件、晚finish、暂停prepare反例|取消会话和生成，接收时间下界隔离旧事件|状态/HTTP回归；浏览器暂停隐藏操作、恢复不补答|
|公开上下文可能混入私人数据|私人canary与跨房间/过期输入|只构建允许的公开字段|完整请求不含canary；不以提示词替代数据隔离|
|现场背景重绘丢编辑状态|延迟状态响应时输入并选择字符|保存草稿、焦点和选区|PC浏览器Trace；伪DOM测试补足真实父节点行为|

回退：本PR独立回退；分发更新带原文件哈希和事务备份。关闭后回退，不覆盖用户模型和私人数据。

## 已执行证据

证据包`.build/live-interaction`保留旧失败和修正后结果：
- `negative-control.json`：旧门槛拒绝、新门槛接受，输入相同。
- `scene-browser-fixed`：PC真实交互、现场设置、暂停/恢复、严格模式、换话题，未剪辑录像和Trace。
- `real-speech-browser`：真实Qwen3-4B与Kokoro zf_xiaobei，经人工确认到实际浏览器音频图；实际语音合成5.06/1.49秒，停止观测106.4ms（单样本，非性能上限）。完整播完收到completed回执，delivered保持false。
- `real-scene-cases-fixed.json`：4例真实生成与完整输入。模型有泛化表述，例“轻快民谣节奏舒缓”不能作为普遍事实验收；料理答法也不代表唯一做法。人工确认仍必要。
- `quality`保留首次前端失败，`quality-fixed`为修正后的完整质量入口结果。
- 原HTTP客户端10秒超时与表单折叠定位失败均保留，未冒充产品根因。

开发样例不是未见验收题。Windows真机、真实OpenAI、B站/OBS/观众端、独立自然度/学习收益均待验证。AI自查不能替代这些证据。

## 复跑

```sh
PYTHONPATH=src:tests python3 -m unittest -v test_live_interaction test_live_output test_platform_integration_http
PYTHONPATH=src:tests python3 tests/live_scene_browser.py --chrome /path/to/chrome --out evidence/scene
PYTHONPATH=src:tests python3 tests/live_output_browser_smoke.py --chrome /path/to/chrome --out evidence/strict-regression
python3 scripts/quality_gate.py --bootstrap --full --report evidence/quality.json
```

真实模型/语音脚本、版本及路径映射随证据包提供。将COMPANION_MODELS和COMPANION_VOICES指向完整包内的模型/音色，使用证据中锁定的Linux测试依赖；这些隔离依赖未写入Windows程序。

P7三问：接口兼容（旧教材接口及确认不变）；边界有实验（暂停、晚到、跨话题、期限、私密隔离）；根因得到支持（后端门槛及系统策略同时修复）。不将有限测试说成全程序证明。
