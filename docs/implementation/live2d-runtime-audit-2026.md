# 真实 Cubism 运行时审计与纠正

日期：2026-11-12。对象是已安装、固定版本的真实运行库及本项目 adapter，不是四状态 PNG。读审计后，root 授权修复实际缺口；没有替换官模纹理、伪造 MOC 文件头或展示被拒三维图。

## 已核实事实与旧验证的纠正

`frontend/live2d-renderer.mjs` 旧0.1在模型加载后调用 `model.setLipSyncEnabled?.(true)`。已安装的 `@jannchie/pixi-live2d-display@1.4.0` 外层模型没有此 API；内部 `lipSyncEnabled` 默认 false。外层正确入口是 `startLipSync()/stopLipSync()`，`setLipSyncValue()` 单独赋值不会开启 Core 应用。

因此旧报告的 app `mouth` 数值变化只能证明音频幅度计算发生，不能证明真实 MOC 嘴部参数和网格变化。新验收不沿用该弱结论。实际浏览器负控让 Audio/Analyser 继续、只把开启方法临时设为 no-op，复现了“app mouth>0、Core嘴部参数0、网格不变”；恢复正确方法才产生实际变形。测试修改仅在隔离浏览器，不写生产或 SDK 源。

| 项目 | 审计前真实情况 | 当前纠正与边界 |
| --- | --- | --- |
| Head XYZ | wrapper 自带标准 Angle XYZ 的 focus/呼吸；只有鼠标入口 | 新增有界控制，读取模型实际范围；标准参数不存在则明确拒绝。实际 Core 参数与几何已测 |
| Body XYZ | focus/呼吸默认只推 Body X；Y/Z可能由作者motion驱动 | 对模型真实存在的 XYZ 提供控制；不会为缺失 rig 生成变形 |
| Gaze XY | 鼠标 focus；相机结果未接到Live2D | 接真实面部方向到现有 focus；只称面部方向估计，不称精确眼动。真实 Core 目光参数/网格变化已测 |
| Blink | wrapper 自动眨眼已启用，依赖作者参数 | 当前读取 Core 眼睑变化验收，手动启停；自定义非标准眼参数仍需作者映射，不能靠通用名称保证 |
| Breath | wrapper 默认呼吸同时含头/Body X 摆动 | 减小幅度并提供开关；真实 ParamBreath 变化已测，不据此称身体所有部位自然 |
| Mouth Open | 错误可选方法吞掉开启步骤 | 显式校验规范 API，用真实 RMS驱动 Core LipSync；停声归零并停用。系统语音仅真实boundary短动作，均不是音素级对齐 |
| Mouth Form | 仅可能由作者 motion/exp驱动，无独立入口 | 新增现有参数的有界手动检查；没有音素/语义嘴型模型，不伪称声母韵母口型 |
| Expression | 文件可导入，未给用户/Agent明确调用入口 | 只允许包内声明名称，Studio检查/adapter统一控制；真实表情参数变化已测 |
| Motion | 默认 Idle 组可能由wrapper惰性播放，其他动作无明确入口 | 只允许包内声明组和合法索引；可关闭自动待机并明确播放。模型自带声音仍被导入器剔除 |
| Physics | physics文件可加载且wrapper求解，旧测试没有证输出 | 明确开关、声明文件加载失败阻止ready；真实毛发参数关闭稳定、开启后变化已测。不存在的物理不伪造 |
| MOC 验证 | 后端只检查包结构/文件头，未调用Core一致性检查 | runtime加载开启 checkMocConsistency，真实Core成功后才ready；后端元数据不被篡改成“已授权/已验” |

固定 wrapper 的自然眨眼实现存在两个调用路径（无动作时与 natural movement 分支）；源码事实不等同已证视觉缺陷。没有为此擅自改 vendor。作者参数与运动质量仍须逐模型实看。

## 能否加载完整原创 MOC

可以加载符合当前 Core 的完整原创导出包。资源流是上传ZIP→安全解析→统一角色作用域URL→实际Core解析与一致性检查→纹理/可选物理姿态加载→首帧→预览确认启用，没有官方模型ID或固定mesh模板。`model3.json` 的 Moc、Textures、Expressions、Motions、Physics、Pose、DisplayInfo 均按导入资源映射；角色包不能带可执行脚本、外部URL或任意SDK。

这条加载能力不等于已经制作完成指定人物。真实原创 MOC 仍必须具备实际 ArtMesh/Deformer、参数键形、遮罩、纹理和动作；PNG层或 `.moc3` 后缀不能替代。CMO3编辑工程也不等于可运行导出物。当前私有已装 Core 实测为5.1.0、最高MOC header revision5；不能据当前官方网页宣称支持更新Core6/R5特性。

后端资源预算为ZIP64MiB、展开96MiB、资源96项、纹理32张/总3200万像素/边长4096、动作64项/32组、表情32项。参数控制读取真实 Core 的 id/min/max/default；无参数会拒绝，不伪造补齐。

## 实际资源验收

1. 作者工程和导出包来源可追溯，官方样例只能作为兼容性控制，不作为指定角色成品。
2. 原创MOC必须通过真实Core一致性、纹理/遮罩和首帧检查；不是只过ZIP/JSON或文件头。
3. 固定其他自动运动，逐轴测 Head/Body/Eye/Mouth 的实际Core值与真正drawable顶点/opacity变化；缺参数要列明。
4. Audio→Analyser→Core嘴部参数→口部几何/像素需同链验证；关闭lipSync但保留真实音频的负控必须不产生嘴部变形，不能仅检查app数值。
5. 表情/动作只播放资源中真实声明项，测试开始/结束/重置；默认已饱和的参数不能被误判为运行时失效。
6. Physics要看真实输出，不只看“已加载”标志；暂停、隐藏、切角色、GL丢失恢复不得留下Core/声音/旧帧。
7. 最后独立审查可见画面、层序和形变。顶点变化不代表眼嘴没有被错误前景遮住，也不等于美术/自然度达标。

## 当前实测与未解决事项

`review/live2d-controls-core-browser.json`记录真实Core控制验收通过（最终门数以报告为准），Haru技术评估：42参数、84drawables、2texture；实际Audio把MouthOpenY由0驱动到约0.34，3个真实口部drawable几何改变；stop后Core参数和全部drawable精确坐标数组/opacity回基线。Head/gaze、表达式、motion、physics输出、呼吸、眼睑和输入拒绝均测。强负控证明app幅度变化本身不够。

最初表情测试选F01失败：该资源只给MouthForm加0.27，而模型默认值已经是最大1，因此无法观察变化；换测资源中确实改变默认参数的F02，保留初次失败报告，不改作者文件、不放宽断言。

此报告中的Haru/Core/framework/视频仅在已授权的本机开发评估范围，私有 `.live2d/evaluation/controls-haru` 保存，不进默认角色/公开包。原创新MOC的可见画面、全部目标参数、美术与真人自然度仍需独立验收；不能以本报告15门替代。

主要源码依据：本项目adapter、`src/companion_runtime/live2d_assets.py`，以及已安装固定1.4.0的 cubism4.es.js 的 InternalModel、Cubism4InternalModel、SpeechController、MotionManager、ExpressionManager。访问日期2026-11-12；没有把其他fork/网页声明当作已装版本的实测。

后续增加了重复选择同一表情的幂等行为与显式动作重播，避免把已选择/正在播放误报为加载失败。首次原创fixture的固定150ms基线负控失败仍留红报告；补充实际Core评价计数，初帧执行Core，并在≥3次评价后建立基线，不把未捕获的首次变项写成已确定根因。

## 4K纹理寿命修复

独立真实 WebGL 反例证明：固定Jannchie1.4.0缓存原生GL句柄，并只更新旧的 `source.touched`；Pixi8.23的GC使用 `_gcLastUsed`，所以正常渲染没有刷新实际回收条件，最终会回收仍在显示的纹理，旧句柄继续绑定导致GL1282/白屏。不是增加参数或修改原画能解决的问题。

本项目在renderer的prerender生命周期（GC更新时钟之后）只对当前模型纹理调用Pixi正常 `getGlSource`，刷新实际使用时间。若资源已卸载后重新上传导致句柄变更，令wrapper重建缓存绑定。没有全局关闭GC、没有增长闲置阈值或保留所有历史模型。

`review/live2d-product-texture-lifecycle.json` 记录实际产品/4K原画调试模型的8门通过：活跃纹理老化后经真实帧更新恢复使用时间、eligible闲置纹理仍回收、强制unload后换新句柄恢复、默认GC实际66.276秒继续有画面且GL0、暂停销毁和恢复。独立复测在 `review/live2d-active-texture-gc-product-fix.json`。首个未用CanvasSource负控默认不参与自动GC，属于测试前置错误，原红报告留存；后续显式创建eligible资源而不更改产品策略。r3调试人物的眼嘴美术仍不因纹理稳定而通过。

## 手部、杯子与模型自定义控制

`applyControls({parameters:[{id,value}]})` 一次最多32个明确数据项；必须是Core真正存在的参数ID，数值有限且落在该参数真实min/max内。它按已有index写值，不调用会生成虚拟参数的缺失ID查找。重复ID/未知字段/不存在参数/越界均拒绝，reset恢复其真实默认值。杯子、手指或衣袖不会在软件中硬编码假参数，必须由真实MOC制作并连接形变/不透明度；同样通过包内motion/expression呈现用户动作。

真实Core测试基线还需等待参数、精确顶点数组和drawable opacity连续稳定，避免把作者Pose初始淡入混入口型负控。只关闭motion/breath/blink/physics不一定消除Pose的淡入；不能用一个固定150ms等待替代实际静态观察。

最终前端候选快照：`review/live2d-frontend-freeze.json`，2026-11-12T22:50:23Z。当前实际报告分别为官样例Core20项、自主MOCv2几何20项、4K纹理生命周期8项、Studio实际上传与控件6项；四份报告的源SHA均逐项等于该快照。全前端Node84项通过。上述结果不覆盖后续r4人物绘制、手指、杯子分离的可见质量；它们必须使用新的实际资产验收。
