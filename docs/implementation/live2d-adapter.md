# Live2D 自助导入与本机真实评估

2026-11-12。用户已明确授权官方 Core、Framework 的**本机开发评估**；官方免费样例按其具体素材条款仅用于这次本机兼容测试。默认分发包仍只含本项目原创适配器，不含厂商代码或样例。不据此推断商业、可扩展 Avatar 应用或 SDK/素材再分发许可。

## 已实现

- ZIP 上传沿用独立角色与资产修订：服务端受控检查/重编码 → 本机预览 → 用户确认 → 启用；旧修订可回退，换皮保留关系。缺合法运行时不能确认；库中的 Live2D“使用”也先进入真实预览。
- `/api/live2d/runtime` 返回经过本机 SHA 记录复核的固定 `/live2d-core.js` 与 `/live2d-runtime.js`。模型包不能提供脚本。`frontend/live2d-renderer.mjs` / `app/static/live2d-renderer.js` 是原创代码；可选厂商 runtime 仅由 owner 明确许可后另行安装。
- 所有 model3 的 Moc、Textures、Physics、Pose、DisplayInfo、Expressions、Motions 引用改为 manifest 的完整同源鉴权 URL，并验证资产/角色范围。可选包内声音/标签会被安全忽略并提示，由应用管理唯一声音拥有者；外链、越界路径和脚本仍拒绝。
- 透明舞台、缩放、真实 Audio RMS 活动口型、轻微呼吸/眨眼/视线；隐藏、切角色、退出释放，WebGL 丢失可重新加载。系统语音只有活动近似，不是音素级口型或面捕。
- 真实执行首次绘制成功后才报告预览 ready。Core 最高 MOC 版本在加载前检查，新版本模型不能冒称已支持。小窗30/展开60是可配置调度上限，不是 Windows/RTX4060性能证明。

## 已核实的运行栈

- 官方 HTTPS alias 实际 Core API：`csmGetVersion()=83951616=0x05010000`，即 **5.1.0**；`csmGetLatestMocVersion()=5`。该 alias 不等于 SDK 网站当前发行版，不支持据此推断 MOC6 或 Cubism5.3所有特性。
- Core 原文件 SHA256：`25ae938cb4fe282ce189b357bcc97e603d1e1f7ec78bf04150d401c23cdc792f`。这是本机观测摘要，不是厂商发布的摘要。
- owner runtime：Pixi **8.23.0**、`@jannchie/pixi-live2d-display` **1.4.0**；带版权/许可声明的本机 bundle SHA256：`74e1eda8be15f0c6f9f33a5a4e84f64eac7586fdd4b1ecec19322672997eb149`。
- 源许可证和条款、原始/派生模型与来源摘要在 `/workspace/.live2d/` 私人评估目录。`frontend/build-live2d-runtime.mjs` 不下载或接受协议、不由默认 build 调用，只从用户给定的已合法安装依赖生成本机文件，并保留上游 MIT/框架归属 banner 与 NOTICE。

## 真实缺陷、修复和证据

1. 官方 Haru 的日文显示名有 U+3000 全角空格，原 `isprintable()` 误拒。资产模块现允许 Unicode Zs，继续拒控制字符/代理码点。官方动作 Duration 两位、末端三位产生0.003秒差异；现仅容许至多0.01秒且不超一帧的舍入差，保留有限值/单调/预算检查。未改官方显示名或曲线掩盖兼容问题。
2. JSON 资源已经是 bytes，HTTP reply 误作对象再次序列化，导致真实 model3/physics/motion 请求断开。根服务已修 bytes 原样响应，API对象照常序列化。
3. Pixi 默认用 blob Worker 解码纹理，违反现有 `script-src 'self'` 回退的 `worker-src`，造成预览挂起。适配器使用公开 `Assets.setPreferences({preferWorkers:false,preferCreateImageBitmap:false})`，不放宽 CSP。首次真实失败 console 保留在 `/workspace/.live2d/evaluation/observed-csp-worker-failure.json`；受控恢复旧配置后的截图/视频及原始 directive 证据在 `before-worker-reproduction/`，明确标注是复现，不冒充最初历史截图。
4. 初轮 GL alpha 断言通过，但实际截图是白矩形。加强检查发现 premultiplied canvas 的透明像素是 `[255,255,255,0]`：Cubism直接GL写入白色 clearColor，绕过Pixi缓存。每次绘制前显式复位透明黑，修后 `[0,0,0,0]`，透明RGB非零数量0，实际截图舞台底色正确透出。红测截图/视频/JSON保留于 `before-transparency-fix/`，没有仅凭alpha数值宣称视觉通过。

## 实际验收

| 材料 | 实际结果 | 证据 |
| --- | --- | --- |
| 官方 Haru，MOC header revision1 | 真实 Core/WebGL **12项通过** | `review/live2d-browser-check.json` |
| 官方 Hiyori，revision3，独立holdout | 同一渲染器首次 **12项通过**；未据其调修 | `review/live2d-hiyori-holdout.json` |
| 原创适配器安全/作用域/版本前检 | Node **6项通过**，不是SDK播放替身 | `tests/test_live2d_adapter_ui.mjs` |

两份模型的预览/舞台截图均实际查看，背景透出无白矩形；对应私有视频为 `/workspace/.live2d/evaluation/haru/acceptance.webm`、`hiyori-holdout/acceptance.webm`，各约11秒。FFprobe确认视频有效，另抽帧实际查看。完整流程包含上传、预览不启用、确认、真实GPU像素/透明、合成测试音驱动口型、停止、隐藏释放/恢复、context loss/retry、身份切换和重载。JS异常0；夹具语音/LLM不代表真人听感或自然度。弃用提示和故意context loss的警告单独保留，不写成“浏览器所有日志均无警告”。

## 未解决和边界

- MOC6/新Core和新渲染特性、任意导出器兼容性、Windows/RTX4060性能、目标美术质量仍未验收；两模型通过不等于所有格式或全部项目完成。
- 样例只是兼容夹具；没有设为默认角色或承诺达到用户参考图品质。初始两ZIP的原始/visual派生manifest差异保留在私人 provenance，不冒充未经处理的完整SDK目录。
- SDK内部异步加载不可保证即时抢占；旧序列完成后会销毁迟到模型，不挂载到新角色。
- 本机评估许可与发布许可独立，后者尚待确认；这次证据和厂商文件不进入公开Git或默认包。

一手来源，访问日期2026-11-12：

- https://github.com/Live2D/CubismWebSamples/tree/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd
- https://github.com/Jannchie/pixi-live2d-display
- https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html
- https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html
- https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html
- https://www.live2d.com/eula/live2d-sample-model-terms_en.html
- https://www.live2d.com/en/sdk/license/expandable/
