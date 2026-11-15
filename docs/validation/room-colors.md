# 直播室配色修订

2026-11-15。基线PR48，远端e7284789e1652ccbd3851b0a0bbdb66d78af6e4c，本地110e56266a5a6d40216992890187f99b146a99a2。用户否定米绿/灰绿方案，本轮只改直播室配色及其兼容处理，不新增美术、业务控件或功能。

## 资料与判断

先读HANDOFF.MD、tanweai/pua ChatGPT Skill与P7协议，再查官方资料：

- [Elgato Wave Link 3官方界面](https://www.elgato.com/us/en/explorer/products/wave/wave-link-3-0-software-overview/)：实际取得并查看Input & Monitoring官方截图，观察到中性白/灰表面与局部蓝色操作强调。不是已运行其软件。
- [Streamlabs教程](https://support.streamlabs.com/hc/en-us/articles/46362056951451-How-to-Add-an-Overlay-to-Your-Stream)：直接页面日期2026-02-06，说明组件与整套叠加画面的协调。教程截图下载403，不能据此声称亲眼看过该截图或照搬其配色。
- [OBS主题说明](https://obsproject.com/kb/themes-guide)：原文2022-01-13，不把它包装成2026新设计；仅作为操作软件可用不同主题的背景资料。
- [WCAG文字对比度](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)：修改前固定普通文字4.5:1；本轮对所有检查的文字统一使用4.5，不用大字例外放宽。输入边界单独检查3:1。这些局部检查不构成完整WCAG认证。

资料观察日期均为2026-11-15。控制台与播出画面应分开管理是本项目的设计判断；三组颜色不是行业统一“2026标准”，审美自然度仍待用户审阅和独立评价。

## 问题—原因—修改—验证

| 问题 | 原因 | 修改 | 证据 |
|---|---|---|---|
| 米绿控制区与画面颜色黏在一起 | 各组件写死绿色/米色，主次不明确 | 控制区改深灰中性表面、浅蓝操作强调；播出画面使用独立色组 | 同一人物、用户原话和布局的前后截图 |
| 换背景后次要字和状态文字不跟随 | 前景、标签、状态分别有硬编码色值 | RoomDesign单一调色板，经CSS变量同时应用前景/次要字/强调/背景端点 | 浏览器读取真实computed style，与调色板端点核对；悬停和默认状态分别测量 |
| 休息时覆盖所选背景 | data-mode=break另写背景和强调色 | 删除模式对配色的覆盖，模式只控制内容和计时 | 三组配色×三种布局×三个状态检查 |
| 已存布置使用旧theme值 | 配色标识已存入config与draft | paper→carbon、forest→midnight、slate→daylight；分别迁移已应用配置与草稿 | Node约束与浏览器重载，原输入、布局和显隐保留 |

三组实际色值：

| 名称 | 底色 | 局部环境色 | 正文 | 次要文字 | 强调色 |
|---|---|---|---|---|---|
| 炭黑 · 杏橙 | #17191f | #2b2b30 | #f6f4f1 | #c1c3cc | #ffaf7e |
| 午夜蓝 · 冰蓝 | #101e30 | #253b51 | #f4f8fc | #bdcedf | #89ccf4 |
| 冷白 · 墨蓝 | #f2f4f7 | #e7ecf3 | #202936 | #505d6f | #274e9c |

没有人物滤镜、混合或透明度改动，没有镜像或修改原模型/纹理/手杯姿势。静态径向背景不增加动画、轮询、模型或平台请求；计时刷新时相同调色板不会重复写CSS变量。尚无目标Windows/RTX的性能证据。

## 可复现检查与反例

- tests/room_color_browser.py：原角色与真实Core；检查真实渐变端点、正文及可见次要字、三种状态/布局、操作区默认和hover、输入边界、旧配置/草稿分别迁移；提供全程无声录像、全屏及操作区截图。
- --css-ref 110e56266a5a6d40216992890187f99b146a99a2只替换旧生产CSS，保持其余条件固定；会被新对比度契约拒绝。这是单因素CSS对照，不是假称整版旧产品已执行所有新功能。
- --mutant-muted把标签文字改成背景色，仍须被拒绝。有限端点检查覆盖所定义的整块色彩范围，不等同每个真实显示器、视频压缩后画面或全部用户输入都通过。
- 首次迁移夹具在reload前改localStorage，被产品原有pagehide保存覆盖，因而失败；将旧数据注入放到下一页面初始化后，同一验收通过。没有改产品保存行为或放宽阈值。
- 原始失败、单因素对照、坏版本、最终颜色检查和既有人物/布置回归分开保存于.build/color-review。

复跑：

```sh
node --test tests/test_room_design.mjs
PYTHONPATH=src:tests python3 tests/room_color_browser.py --chrome /path/to/chrome --model /path/to/original.zip --runtime-dir /path/to/owner-runtime --out evidence/colors
# 加 --css-ref <上述本地基线提交> 或 --mutant-muted，应失败；每次用独立out目录
PYTHONPATH=src:tests python3 tests/room_variety_browser.py --chrome /path/to/chrome --model /path/to/original.zip --runtime-dir /path/to/owner-runtime --out evidence/room
python3 scripts/quality_gate.py --bootstrap --full --report evidence/quality.json
```

范围：Linux PC Chrome开发检查，产品仍仅面向Windows PC。未执行Windows/DPI/多屏、OBS、真实直播和独立审美验收。只使用用户已发出的“直播间设置更多样”“人物更多样”，不填虚构问题或答案。私有模型、SDK和第三方参考截图不随公共源码与证据包分发；Trace交付副本移除其响应正文与认证cookie，原件本地保留。

P7三问：旧色组有明确迁移、原控制接口保留；覆盖草稿/已应用、模式、布局、悬停和坏颜色反例；根因是分散固定颜色与模式覆盖，统一调色板后消除冲突，未用改人物曝光掩盖背景问题。

最终开发结果：完整质量入口通过，检查期间源码指纹稳定；颜色浏览器检查与既有人物/布置回归通过。所检查节目文字在全部所测背景端点上的最低比值为5.6403，操作区所测默认/hover文字最低10.4967。它们是上述有限检查的测量值，不是审美分数、旧画面所有局部像素的测量，或全产品/全环境认证。
