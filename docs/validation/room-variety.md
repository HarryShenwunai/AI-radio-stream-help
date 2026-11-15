# 人物库与直播室布置

2026-11-15。基线 PR47 / 2ca444a25400890f048d37ce22a4654187e5f5dc；对应本地5161f876ce9cf74313c0262cb76e22b4ae55624d。用户确认先做人物库与切换，不新增美术素材。Windows PC为产品目标，本轮运行环境为Linux PC Chrome。

## 方案与来源

先读 HANDOFF.MD、tanweai/pua ChatGPT Skill与P7协议。沿用现有CharacterStore、AssetStore、CompanionScene与计时状态，保留原图、持杯姿势和用户输入边界。

观察资料（2026-11-15）：[VTube Studio模型设置](https://github.com/DenchiSoft/VTubeStudio/wiki/VTS-Model-Settings)区分模型及其配置；[OBS场景集合](https://obsproject.com/kb/scene-collections)与[输出Profile](https://obsproject.com/kb/profiles)分开保存。这里仅借鉴配置分离方法，没有运行这些第三方程序，也没有复制模型、素材或第三方代码。

| 观察 | 根因与最小修改 | 验证 |
|---|---|---|
| 直播室只能显示助手当前人物 | room接口只给当前资产；补充经过字段白名单筛选的可用人物目录，预览选择只保存在直播室 | 实际Core切到空形象时释放旧画面、切回重新绘制；不改变助手当前身份；HTTP检查所有身份不带私人记忆或规则 |
| 人物站位和文字关系固定 | 单一绝对定位；增加右侧、左侧、右下小窗三种布置 | 3种布置×3种背景×3个PC尺寸的实际交互；原角色不镜像、素材字节不改 |
| 无法控制组件与复用布置 | 增加主题/提问/字幕/计时显隐和用户命名布置 | 草稿不立即生效；隐藏不删原文；保存不含主题、问题、字幕或计时进度；载入仍须应用；刷新保留；删除取消与确认分别检查 |
| 管理人物后直播室目录不更新 | 增加手动刷新，不轮询 | 归档身份退出列表，当前编辑原文保留；已失效预览清空，要求重新选择 |

背景为米白、深绿、石灰。布置最多12份、按直播室所属身份隔离；现有旧配置迁移到原布局。没有预置虚构人物、问题或教材。截图仅采用用户原话“人物更多样”“直播间设置更多样”。第二个空身份仅为切换夹具，不计作新增美术。

## 反例与边界

- 首轮截图发现左侧布置反向淡出削弱手杯边缘；保留原遮罩方向后重拍，素材与模型不改。这不是手部结构重制或独立视觉验收。
- 同脚本旧版对照检查新控件缺失。初次路由夹具把Playwright第二个参数误绑定为body，导致导航超时；该结果不作为产品失败或有效负对照，保留日志后修正夹具重跑。
- 故障注入：让布置按钮保留但画面固定为右侧米白；同一脚本应拒绝其应用、载入和刷新行为。
- 文本溢出沿用预先测量与拒绝规则，不以截断冒充完整显示。所有新布置仍是本地手动预览；没有增加平台、OBS或模型请求。不存在人物发声与对话身份自动联动。
- 直播室复用一个Renderer，布置/背景切换不重建同一模型；新增一次目录读取和手动刷新，无新后台轮询。记录交互耗时是开发观测，不能替代Windows/RTX4060性能验收。
- 目标Windows、DPI、多屏、专业盲评和用户认可均待验证。有限窗口和组合检查不等于任意文本、任意资产或全部显示环境通过。

## 复跑

```sh
PYTHONPATH=src:tests python3 -m unittest test_room_catalog test_default_live2d_voice test_ui_copy_contract
node --test tests/test_room_design.mjs
PYTHONPATH=src:tests python3 tests/room_variety_browser.py --chrome /path/to/chrome --model /path/to/R3-Study-Companion.zip --runtime-dir /path/to/owner-runtime --out evidence/room
# 同一命令加 --baseline-ref 5161f876ce9cf74313c0262cb76e22b4ae55624d 检查基线缺失能力
# 加 --mutant-static-design 检查坏版本，应返回非0；均须使用独立out目录
python3 scripts/quality_gate.py --bootstrap --full --report evidence/quality.json
```

可编辑代码在 app/static/room*、app/server.py；更新清单含新模块。私有Core与原模型不随GitHub源码或证据包重新分发。截图、完整无声浏览器录像、报告与去除SDK响应正文的Trace另随证据包交付；原Trace原样保存在本地。

P7三问：room接口保留旧character字段并新增characters，原调用方继续兼容；配置迁移、无形象、归档、长输入、显隐、刷新与取消分别覆盖；通过目录、状态与布局解除固定耦合，没有把新名字当新人物或把AI自评当独立验收。

最终结果：完整quality_gate通过，881项Python回归与前端/桌面、lint/类型/架构规则均通过，检查期间源码指纹稳定。delivery-run全部浏览器判据通过；baseline-fixed明确因缺少新控件拒绝，rejected-static-final明确拒绝画面不切换的注入版本；settings-regression保留既有长文本、隔离、暂停、刷新和全屏检查通过。证据位于.build/room-variety，原始失败与最终结果分别保留。
