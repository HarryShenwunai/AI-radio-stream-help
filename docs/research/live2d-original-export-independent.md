# 原创分层 Live2D 导出：独立源码调查与真 Core 验收

调查时间：2026-11-12 UTC。只读调查固定 psd2live `067ded459b6ed1b7e0d1566ce7b1fd04223bee06`；实际执行工具为单独下载校验的 v3.6.7，不能把 master 的能力直接写成该 release 已验证。本文是内部工程报告，尚未宣称用户角色美术完成。

## 结论和真实目标

Linux 上从真实分层 PSD 合成真正 MOC3 的路线已经实际跑通；不是必须依赖 Windows Cubism Editor 才能产出运行文件。当前障碍从“能否导出”变为“原画的正确分层、绘制顺序、可见变形与表现质量”。四张整图、换皮官模、可通过头部检测的假 MOC3 都不能代替原创模型。

独立测试已经把自有几何 PSD 的导出物送入本机官方 Cubism Core：一致性检查、真实参数驱动顶点、物理、全部四表情和四动作均有真实效果。但首版实际截图显示头部整块深色背发遮住眼嘴。隐藏几何在动并不足以通过可见绑定；该视觉反例已通知制作 Agent；v2 改正真实 PSD 存储层序后，已通过同一实际像素硬门。v1 原件和红证据均保留。

## 已核实事实

| 事实 | 一手或本机证据 | 边界 |
| --- | --- | --- |
| `Moc3Target.bundle` 将 RigIR 转为 Puppet，生成贴图、MOC3 和 sidecar | 固定源码 `targets/cubism/.../Moc3Target.kt` | 不是官方 Editor 编译器；不因此保证艺术质量 |
| `Moc3Export.toMocDocument` 真正降低网格、参数、变形器、关键形并处理版本降级 | 固定源码 `umamo/.../interop/moc3/export/Moc3Export.kt` | 导出会写出文件，损失通过 notice 报告；exit0 不能代替审查损失 |
| MOC 版本5对应 Cubism5.0，版本6对应5.3 | 固定源码 `umamo/.../format/moc3/moc/MocVersion.kt` | 本机官方 Core 最高 MOC5，应明确5.0目标 |
| 上游 `CubismCoreCheckTool` 调用真实 `csmHasMocConsistency` | 固定源码 `src/test/.../tools/CubismCoreCheckTool.kt` | 未配置 `PSD2LIVE_TEST_CUBISM_CORE` 时跳过，只测两个内置样本，不证明新模型 |
| 自有18层几何 PNG 经真实 PSD 和 v3.6.7 CLI 导出 | `.build/original-live2d-fixture/export-v1/authoring-export-report.json` | 纯工程测试角色，不能当用户角色成品 |
| v1 MOC3 为173056字节，格式版本5 | 同目录模型；初始 SHA `ea83df84ca6d7bbf2a87de9ef40dd8188b61be32acf942047158426d7faac2cc` | 后续版本须重新计算，不手抄替换 |
| 真 Core 接受 v1；20参数全部有顶点差异，20 drawables | `review/original-live2d-core-binary-only-v1.json` | 可见性门尚未包含在这份早期报告中 |
| 真框架 physics 使 HairFront/Back 等参数及实际顶点变化 | 同一独立报告 | 固定步长模拟，不是 Windows 实时帧率测试 |
| 四个 expression 和四个 motion 都改变声明参数与实际顶点 | `review/original-live2d-core-check.json` 的独立隔离采样 | 关物理、自动眨眼、呼吸和 idle；无操作60帧参数/顶点均零变化 |
| v1 的眼嘴被深色整椭圆遮住 | `/workspace/dist/evidence-original-live2d-core/bound-final/original-neutral.png` | 真实查看截图发现，不用二进制通过掩盖 |

本机 Core 与显示框架为用户已单独同意条款的本机评估安装；独立测试只引用其路径和 SHA，不把 SDK 代码打进产物，也不推断公开发布许可。

## v2 纠正后的实际结果

`review/original-live2d-core-v2.json` 七门通过，23个源文件 SHA 在测试前后不变。实际官方 Core 版本整数83951616，即5.1.0，最高 MOC5；本次 MOC5 可加载。

| 参数 | min/max 实际变化像素 | 判定 |
| --- | ---: | --- |
| ParamAngleX | 49987 | 可见转头变化 |
| ParamEyeLOpen | 2519 | 左眼可见开合 |
| ParamEyeROpen | 2516 | 右眼可见开合 |
| ParamMouthOpenY | 2538 | 嘴可见开合 |

同一个 harness 对 v1 得到左右眼/嘴各0像素，v2 得到上述非零结果。原因是 PSD writer 将层记录顺序反转；上游 reader 实际按底层优先读取。仅看 PSD 合并预览和图层数量不能发现此错。v2 同时把 UNKNOWN 的 body/teeth 改成工具识别的 topwear/upper teeth。这只证明自有几何样例的真实导出与可见绑定，不证明用户参考原画已制作完成。

实际截图与视频：`/workspace/dist/evidence-original-live2d-core/visible-v2/`。视频为浏览器实际执行记录，不是艺术演示；侧件以1/60秒固定步长求值，不作为实时帧率成绩。

## 可信但未独立全量验证的上游信息

- README 声称支持3.0–5.3、PSD自动网格/绑定/动作/物理、CMO3与MOC3输出；此次实际仅验证 v3.6.7 的5.0小几何模型。
- 当前 commit 声称完整测试1407项、1242通过、165条件跳过。我们没有运行该套件，也没有把这些数字当项目实测成绩。
- 上游 STATUS 明确记录 AI 拆发和遮挡补全3例“不可用”；拆嘴未验证。自动绑定可用不能推导自动拆画成熟。
- `.cmo3` 已真实写出，尚未用官方 Editor 重开和修改，不能称编辑器兼容完成。

## 推荐执行路径与替代路线

| 路线 | 适用条件 | 优势 | 主要限制 |
| --- | --- | --- | --- |
| 真实拆层 → PSD → psd2live/Umamo → 官方 Core 独立验收 | 能提供完整前后发、眼白、虹膜、眼睑、口腔、衣身、遮挡补全 | 本机自动导出实际可行，无需为首个 MOC 安装官方 Editor | 分层与参数模板仍需逐项校正；GPL 工具链与输出素材授权须分别确认 |
| 同一真实拆层 → 官方 Editor 人工绑定/复核 | 有合适 Windows/Editor 环境或建模师 | 可针对原画精修并直接验证可编辑工程 | 云端当前没有实测官方 Editor，成本与工时取决于实际层数和精度，待验证 |

先走已证明可执行的自动导出路径，把可见参数和原画质量作为否决门。自动结果不满足时保留同一原画拆层与模型工程，进入精修；不拿整图贴片改名代替。

实际执行的 CLI、输入和输出 SHA 已在 `authoring-export-report.json` 记录。运行时应固定私有 `user.home`、最大堆和明确输出目录，不写默认用户配置；不要调用会删除偏好的 `--clear-user-data`。为避免磁盘浪费，仅下载一个已校验107406792字节 Linux 包，不重复完整 clone/Gradle 构建。

## 必须通过的独立门

1. **真实分层来源**：独立透明部件、遮挡补全、层序和清晰命名。素材 SHA 与实际输入 PSD、导出 family 一起绑定。部分名称被工具识别为 UNKNOWN 时先纠正，不能只统计文件数量。
2. **真正文件兼容**：完整 `.model3.json`、纹理、MOC3 与 sidecars 全部可读；官方 Core 一致性、版本、真实 Model 构造通过。不得用自研求值器或 header 检查替代。
3. **参数有效性**：min/default/max 有限，索引与遮罩合法；嘴、左右眼、视线、转头的独立 sweep 必须有实际 Core 顶点或透明度差。
4. **实际可见性**：在真 WebGL 像素比较中，要求的眼口参数须有可见差异；隐藏网格运动、背发盖脸或全透明都不通过。保留相同模型的前后截图与录像。
5. **行为隔离**：停物理/自动运动，先跑不操作的参数和几何稳定负控，再验证每个 expression 的声明参数和每个 motion 的真实效果。文件存在、Promise true、自报 mouth 数字都不算完成。
6. **物理与实际音频**：受控冲击引出真实下游参数和顶点；产品侧还须真 Audio/RMS→Core嘴参数→可见嘴变化，静音/停止归零，负控禁 lip-sync 时不得仍声称成功。
7. **产品接入**：自助上传、预览不激活、明确激活、角色隔离、切走释放、失败恢复与隐藏停声。测试使用当前新 UI，不能为旧 harness 恢复隐藏表单。
8. **原画与环境**：对照用户参考图检查脸、发、衣、比例和遮挡；Windows10/11、4060、真实帧率、官方 Editor 工程重开是独立验收，Linux SwiftShader 和几何 fixture 不能替代。

## 已发现并修正的测试陷阱

Jannchie `Live2DModel.update(dt)` 只推进计时。真正内部求值发生在渲染前，求值末尾又恢复参数。因此连续同步调用90次 update 后直接读参数，会错误地认为表情无效。现独立 harness 每步真实 render，在 `beforeModelUpdate` 捕获送进 Core 的参数，render 后读真实顶点；初轮红报告与视频仍保留。

只看顶点也不充分：v1 的被挡眼嘴能变形，但不可见。这个反例推动实际 framebuffer 参数 sweep 硬门，不能因为第一轮 Core 检查全绿就宣布完整绑定。

## 未解决事项

- v1 几何样例的背发层序错误已在独立 v2 修正并重新验收；原 v1 红证据不删除，v2 仍不升级成用户艺术通过。
- 用户原画真实拆层、缺失区域补全、逐参数精修尚在制作。
- 当前产品 adapter 的真实 lip-sync API 修正由前端负责，独立原始 Core 测试没有替代该链路。
- CMO3 官方 Editor 实际重开、Windows4060和人工表现接受尚未通过。
- 工具源码 GPL、原始素材、官方 Core/框架的本机评估与公开发布边界分开；本次没有获得新的 SDK 公开发布许可。

## 真原画 r3 的后续独立否决与修复证据

已进一步将用户原画衍生的22层真实PSD送入官方 Core，不套用几何样例结果。实际中性、左右闭眼、张口、转头端点均已截图查看。`review/original-character-live2d-r3-pixel-probe.json` 证明眼嘴真实可见；完整长轮仍发现两个独立问题。

- **纹理寿命故障**：长轮实际出现已删除纹理的 WebGL1282，而 Core 顶点仍有限。真实GC负控证明第三方wrapper旧`touched`与Pixi8.23实际`_gcLastUsed`不兼容。实际产品adapter修正后，独立真实GC回归通过：活跃纹理保留、闲置可回收、unload重新上传；未关闭GC。证据`review/live2d-active-texture-gc-counterexample.json`、`review/live2d-active-texture-gc-product-fix.json`。默认时间耐久由前端另验，不能用加速负控替代。
- **嘴部艺术与坐标错误**：原CLI口部可见平直切线。MCP mouth-r1 修订在真实Core中把上下唇移到额头/领口，明确拒绝。新增此角色专属、预先审定的嘴部ROI，真实检测1099变化像素越区；没有把“有变化”当艺术完成。证据`review/original-character-live2d-r3-art-review.json`、`review/original-character-live2d-mouth-r1-roi-negative.json`。
- **单位校准**：真实Core读取PPU1536，`±0.01`目标parent-local高度只移动上唇约`±0.20`源像素，其他网格完全不变。原先把10当10像素的假设错误。严格中点对称门未过，最大偏差约0.0237源像素，原因未证。原始顶点和结构化测量保留在`review/original-character-live2d-lip-unit-measurements.json`，不能改写为exact对称通过。

原画尚未获得艺术接受。产品纹理修复与原画嘴修订分别处理，不靠修改原画绕开运行时故障，也不靠技术参数通过掩盖错位嘴唇。

## 已核实来源

以下均于2026-11-12访问，源码链接固定 commit：

- [psd2live README](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/README.md)
- [Moc3Target](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/targets/cubism/src/main/kotlin/io/github/psd2live/targets/cubism/Moc3Target.kt)
- [Moc3Export](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/umamo/src/main/kotlin/org/umamo/interop/moc3/export/Moc3Export.kt)
- [MocVersion](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/umamo/src/main/kotlin/org/umamo/format/moc3/moc/MocVersion.kt)
- [CubismCoreCheckTool](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/src/test/kotlin/io/github/psd2live/tools/CubismCoreCheckTool.kt)
- [ExportCli](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/src/main/kotlin/io/github/psd2live/ExportCli.kt)
- [工程与运行时边界](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/docs/zh/spec/RUNTIME_EXPORT_ARCHITECTURE_AND_GAPS.md)
- [PSD拆件规范](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/docs/zh/spec/PSD_LAYER_SPEC.md)
- [STATUS 的真实任务限制](https://github.com/tsunehimatoi/psd2live/blob/067ded459b6ed1b7e0d1566ce7b1fd04223bee06/docs/zh/STATUS.md)
