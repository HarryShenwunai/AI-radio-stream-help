# 可选 Live2D 运行时：来源、许可门与本机安装

核查日期：2026-11-12。安装器初始完成20项合成夹具测试后，用户明确同意仅本机开发评估，已据此取得Core并构建、安装可选renderer；真实Core下Haru和独立Hiyori各12项检查现已通过，并已实看最终截图确认透明透底；此前透明合成缺陷的红测和录屏保留。后续完整模型结果见[本机评估记录](live2d-local-evaluation.json)及[浏览器报告](../../review/live2d-browser-check.json)。默认软件包仍不含Core/Framework/样例；没有可选运行时也不阻断PNG、VRM。

## 已核实事实和仍未知的事项

- 官方 [CubismWebSamples](https://github.com/Live2D/CubismWebSamples/blob/develop/README.md) 明确仓库不管理 Core，要求从官方SDK获取；其 [CHANGELOG](https://github.com/Live2D/CubismWebSamples/blob/develop/CHANGELOG.md) 当前首项为5-r.5、2026-04-02，README说明Cubism5.3兼容。没有据此猜测本机Core的二进制版本。
- 官方 [Framework LICENSE](https://github.com/Live2D/CubismWebFramework/blob/develop/LICENSE.md) 将 Cubism Components 与 Core 的许可证分开；wrapper的MIT不涵盖所有内嵌Framework内容，也不能推出GPL分发兼容。
- [官方Web下载页](https://www.live2d.com/en/sdk/download/web/) 明确下载前须同意两个协议，并警告Latest链接可能失去功能兼容。页面和官方Core URI的HEAD未找到厂商公开SHA256；只读取了HTTP头，未取Core本体。维护fork `omniwaifu/pixi-live2d5` 的setup.js也明示其ZIP checksum是本地观测，非Live2D发布。我们不把第三方或本机观测hash写成厂商认证。
- 已确认：用户授权本机开发评估；固定官方URI本次取得的Core，经真实Chrome API观测为5.1.0、latestMocVersion=5，不等同SDK R5/Core6.0.1。仍未知：所有Cubism导出的兼容性、实际显存/帧耗时和Windows行为、本项目发布许可/GPL与专有组件组合的法律适用。以下软件机制不是法律批准。

## 需要主人理解并明确授权的动作

[Core Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html) 将“by downloading, installing or using the Software”列为接受行为；[Framework Open Software License](https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html) 还有取得源码仓库等接受行为。官方[下载页](https://www.live2d.com/en/sdk/download/web/)原句：

> Downloading or launching this software shall constitute consent to the Software License Agreement.

因此不由Agent先取Core、拉Framework或执行测试，再把接受协议当成事后手续。CLI的 `--accept-official-license` 必须由有权的主人明确使用。初始测试仅验证此门；其后本项目主人已明确同意仅本机开发评估，我们已按该授权执行固定官方Core获取和本机bundle构建安装，不重复要求同一授权。

获准后可审查的本机动作如下：

1. 固定官方HTTPS Core URI，正常TLS验证，拒绝所有重定向/最终URL变化，最多8MiB；原始字节不改写，保存来源、时间和观测SHA256。此hash用于本机pin，不是官方发布的digest。
2. 或读取主人已合法取得的本地SDK ZIP/Core文件；要求主人提供预期Core SHA256、`--trust-local-sdk`和同一许可确认。来源标为主人声明，不能冒称已独立认证官方文件。
3. 可选renderer由主人已合法取得的固定依赖在本机构建，使用frontend/build-live2d-runtime.mjs；安装已有bundle还要求预期SHA256、`--trust-local-bundle`和许可确认。安装器不执行JS，不从角色包寻找JS，也不运行npm生命周期脚本。
4. 安装只写独立runtime目录；浏览器随后从固定同源端点加载时才执行这些库。可用remove删除本机副本，不改变角色/PNG/VRM数据。没有后台更新任务。

这些动作只覆盖本机开发评估。官方[Expandable Applications条款](https://www.live2d.com/en/sdk/license/expandable/)要求可扩展应用发布前审查和特别出版协议，普通个人/小企业的常规豁免不能自动套用。用户自装Core不能自动解决应用发布、SDK组合、素材或模型许可。分发/公开播出仍另设门，不在这次确认范围。

## 安装与服务接口

默认只查状态，不会下载或创建runtime目录：

```sh
python scripts/install_live2d_runtime.py status
```

默认目录与服务统一：`COMPANION_LIVE2D_RUNTIME`；否则 `COMPANION_DATA/live2d-runtime`；未指定DATA则源码的app/data/live2d-runtime。自定义目录用全局 `--runtime-root`。其他尚未确认许可的使用者只运行status/inspect-local，不应执行安装动作；本项目主人已确认的本机评估授权继续有效。

主人确认后应关闭应用再安装，完成后重新打开，避免浏览器保留旧Core全局对象。可选择的命令（本次已执行install-official及install-bundle；install-local是未执行示例）：

```sh
python scripts/install_live2d_runtime.py install-official --accept-official-license
python scripts/install_live2d_runtime.py inspect-local /path/to/owner-sdk.zip
python scripts/install_live2d_runtime.py install-local /path/to/owner-sdk.zip --expected-sha256 CORE_SHA256 --trust-local-sdk --accept-official-license
python scripts/install_live2d_runtime.py install-bundle /path/to/owner-runtime.js --expected-sha256 BUNDLE_SHA256 --trust-local-bundle --accept-official-license
python scripts/install_live2d_runtime.py remove
```

ZIP只读取一个Core成员，优先min.js，多个候选拒绝；不展开模型/样例/其它JS。SDK最多256MiB，ZIP中央目录在解析前限制10000项，禁止穿越/绝对路径/链接Core，读取Core最多8MiB。目录0700、文件0600适用于POSIX；Windows ACL仍待用户目标机检验。每次安装使用独立修订和原子指针，失败保留旧active；正常只保留当前Core与renderer两份脚本。成功写入后清理失败会暴露cleanup_pending。

Python：`Live2DRuntime(root).status()`、`read_core()`、`read_bundle()`。读取前校验安装来源记录、主人声明和SHA，篡改/链接/不明来源失败关闭；错误类型Live2DRuntimeError，消息为固定code。status只在两个artifact均有效时available=true，并分别给出core_available/renderer_available。实际Core版本未知返回null，runtime_execution_verified和publication_permission_verified保持false；不凭安装成功伪造运行/法律验收。

根HTTP层只提供主人认证的GET `/api/live2d/runtime` 与固定 `/live2d-core.js`、`/live2d-runtime.js`。不增加HTTP安装/上传/任意URL接口。Core暴露window.Live2DCubismCore，renderer bundle暴露window.CompanionLive2DRuntime。所有model3资源URL由资产库清单同源重写，角色包JS永不执行；这部分由资产导入器与原创renderer adapter负责。

## renderer候选比较（文档声明，不是运行验收）

| 代码来源 | 文档所述Core/模型 | Pixi | 取舍 |
| --- | --- | --- | --- |
| guansss主库 | Core2.1/4，Cubism3/4走cubism4入口；未证实5 | README写6，master peer实际7 | 原文“所有版本”不能当5支持，存在文档漂移 |
| Jannchie维护fork1.4.0 | 仍明确Core2.1/4，Cubism3/4；本项目只取cubism4入口 | 8 | 当前适配目标；没有宣称5新特性已通过 |
| naari3维护fork1.2.5 | 声明Core5/Cubism5 | 8 | 不能由声明推导5.3/R5实际兼容 |
| omniwaifu/pixi-live2d5 | 声明R5/Core6.0.1、Cubism5，3/4仅best-effort | 8.19+/WebGL2 | 另需13个GLSL资源；setup会下载Core，本轮未运行 |

具体来源blob和访问时间见 live2d-runtime-sources.json。本项目采用的original adapter不内嵌任何SDK。wrapper包名MIT不代表其Framework及Core许可齐备，默认发行不含这些可选库。

## 已完成与下一道验收

已完成20项合成测试：许可门先于网络、固定HTTPS/TLS上下文、拒重定向、体积/截断、真实loopback HTTP搬运、只提取Core、ZIP目录预限、路径与链接拒绝、SHA/声明篡改、原子失败恢复、修订清理和无runtime状态。测试从未执行合成JS，也没有真实Live2D代码或TLS平台验收。

本次主人许可已确认，真实Core下Haru和Hiyori各12项已通过，包含真实模型像素、RMS口型、停止、隐藏释放、恢复、WebGL丢失重试、身份切换及新增premultiplied透明检查，JS异常均0。两份stage截图已分别实看，无白矩形。Haru旧11项曾漏掉alpha0/RGB255的白底错误，现修复GL缓存清屏并保留真实红测；Hiyori在同一adapter首次通过，未用于追加调修。两者均为有限抽样，不等于全部导出器、Windows/4060或参考美术质量验收。无需为初始化放宽CSP，不为方便开放任意JS unsafe-eval；Windows/4060性能仍待目标机测量。安装解析有显式资源上限；status/serve的SHA验证最多各读取两份8MiB脚本，实际耗时/缓存是否必要待目标设备测量，尚无p95或帧率结论。
