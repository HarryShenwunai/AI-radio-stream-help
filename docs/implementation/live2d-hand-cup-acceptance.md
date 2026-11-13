# 原创 Live2D 手杯验收

状态：2026-11-13，验收工具准备中；产品 adapter 0.2.2 保持 `live2d-frontend-control-fix-freeze.json` 的冻结状态。本文件不把中间导出物、单元测试或参数名称当成人物成品。下方 r1 记录是历史分检，不是最终候选的完成状态。

## 实际证据与未完成项

- `review/hand-cup-candidate-r1-probe.json`：真实 r4-r1 MOC 经当前 HTTP 导入、实际产品 adapter、独立原始 Core 与 WebGL 跑过五项分检。原图源/程序源 SHA 在该次运行中稳定。
- `CupVisible`：杯 opacity 从非零到 0，杯几何不变，全部非杯 drawable 的完整坐标与 opacity exact 相同。实际 GL 差异 6,273 像素。
- `CupX/CupY/Rotation`：三次测试实际只变杯子，旋转采用 -45°/+45°，不用等价的 -180°/+180°假作变化。
- 审定的 `(840,1570)`、`(800,1700)`、`(860,1500)`：实际 Core 三角形位置、UV 和规范化 atlas alpha 显示有纹理支持的归属均为 `ArtMeshTopwear`，未被 upperarm/forearm/cuff 纹理承载。不是根据 mesh 名称猜测，也不是仅看中性截图。
- r4-r1 缺实际 `CupHold`；整片刚性转指不是关节弯曲；完整动作和握持补偿尚待后续真实导出。完整验收状态仍为 **BLOCKED**。本机截图位于 `/workspace/dist/hand-cup-candidate-r1/`，并有真实浏览器录像，无系统音轨。
- 当前 instrument 单元共 37 项（acceptance 30、PRIO reader 4、multilinear 3），使用明示的合成几何/数据；它们不构成人物的 Core、画质或 Windows 通过证据。

## 测量方式

`tests/hand_cup_metamorphic_check.py` 使用两条独立的评价路径：

1. 同一个经过资产校验的真实 MOC，直接交给主人本机已安装的官方 Core，逐项设置真实已存在的参数索引，再调用 `raw.update()`。这里没有框架的眼睑、呼吸、physics 或 motion。
2. 当前产品的真实 adapter，通过 `applyControls()` 选择真实参数，关闭自动控制，再等待实际 Core 参数、完整顶点和 opacity 连续四次评价相同。使用 beforeModelUpdate 的最终参数，而非 framework 更新后恢复的参数。

测量不使用顶点 digest 作为 exact 证明，不用 `getStats().mouth` 证明变形，不调用会创建缺失参数的名字查找。GL 像素来自实际渲染；截图/录像保存当前真正的程序画面。模型、MOC、纹理/侧件、审定 source manifest/每个 layer、测量合同、工具与产品源、本机 Core/bundle 都记录 SHA；运行期间改变源会导致失败。

强制释放旧 motion/manual pin 后才评价包内动作，避免测试自己的持续 pin 把真实动作盖掉。动作计时使用模型实际 `elapsedTime`，不是在云端高负载下睡固定墙钟时长。

## 最终功能合同

最终制作者交两个独立 JSON：

- **实际测量合同** `actual-live2d-landmark-contract-v1`：由 `scripts/avatar_live2d_contract.py` 从真实默认姿态的 Core 三角形生成。每点包含真实 drawable ID、三个实际 vertex indices、barycentric weights、source canvas 坐标，另有真实参数范围与 CanvasInfo。不能使用旧 cavity 中心或越界后的最近网格回退。
- **功能合同** `live2d-hand-cup-metamorphic-v1` 或明确的 `v2`：由制作者明确填写下面字段，不能从参数名自动推断人体语义。仅 v2 支持下面规定的两个不可见技术杯辅助 mesh，不能把 v1 报告当成 v2 算法未变。

| 字段 | 必须提供的内容 |
| --- | --- |
| `model_binding` | 最终 `model3_sha256`、`moc3_sha256`、`landmarks_sha256`、`source_manifest_sha256` |
| `parameters` | 真实 `cup_hold/cup_visible/cup_x/cup_y/cup_rotation` ID；`held_sweep` 为 2–6 个真实标准 Body/Breath 参数 ID，`held_roles` 明确 body_x/y/z/lean/proportion 与 breath 角色，必须含 breath 和至少一个 body |
| `detached_pose/held_pose` | 参数值映射，实际 CupHold 分别为 0/1；CupHold 作者范围必须恰为 0..1 |
| `visibility_values` | 真实 `shown/hidden` 参数值 |
| `meshes` | 杯、torso、palms、upper/forearms 四组真实 Core drawable IDs；隐藏/变换杯子时全部非杯 mesh 都必须 exact 不变 |
| `cup_transforms` | X/Y/rotation 各两个不同且非旋转周期等价的作者值 |
| `fingers` | 十条，明确 viewer side，每条真实参数、mesh、两个 Curl 值，root/joint/tip/palm_root 四个实际 landmark 名称，预先声明 root 预算与依据、最小 tip 位移与 bend 变化 |
| `arm_hand_controls` | 两侧 arm/hand（可另 forearm），真实参数、目标 mesh 集合、两个测值。合法肩部 glue 可列入目标；不要求整件衣服所有顶点不动 |
| `grips` | 至少两对 cup/hand landmark，预先声明源像素容差与依据；若有 rest offset 必须明确且 ≤5 源 px，不可用大 offset 掩盖分离 |
| `semantic_probes` | `reviewed:true`、依据、审定 `source_points`、允许的 torso IDs（可显式包含合法背填）、禁止的全部 arm/forearm/cuff IDs。先证真实纹理归属，再要求 arm/hand 控制时保护点 barycentric 源坐标 exact 不变 |
| `actions` | 恰有 hold/detach/wave/empty_hands 四种角色；实际 motion group/index 或 expression 名称、明确 start_pose、sample_seconds、target_meshes、预期终态参数与 ≤0.01 作者单位容差 |

动作必须触发对应真实参数和目标网格，不能只把任意头部动作或仅小指 Curl 命名成“挥手”；wave必须真实改变至少一侧palm/arm。hold 要实际到 CupHold=1；detach 到 0；empty_hands 要杯完全隐藏且两个掌和十指仍可见。Studio 从包内元数据呈现真实动作，不增加固定角色按钮。

## 已预先固定的硬门

- CupHold=0：CupVisible 只能改变杯 opacity，不改变杯几何或任何非杯的几何/opacity。CupX/Y/Rotation 只能动杯。
- 每指：所有声明目标实际变化，非目标完整坐标与 opacity exact 不变；root 位移与 root 到 palm 同点误差均 ≤0.5 源 px；tip 位移 ≥1 源 px；root→joint 与 joint→tip 的夹角变化 ≥1°；真正 GL 像素有变化。刚性旋转可改变 tip，但不能通过 bend 门。
- 每侧 arm/hand（杯脱离时）：杯 exact 不动；审定衣身保护点 exact 不动；手指 root 到 palm 的误差仍 ≤0.5 源 px。允许已声明、合理的肩缘 glue，不能让手臂带整块腹部。
- CupHold=1：对明确的 Body/Breath 参数做 min/default/max 的实际笛卡尔积扫测，并加seed9426的离key组合样本，不只复验作者拟合表，最多 729 个状态（实际六轴含 Breath 默认=最小值时为 486）；同姿态实际评价 Hold0/1：Hold0杯必须保持ROOT且有至少一个Body和Breath分别真实移动手掌抓点，Hold1只改变杯几何且保持可见，双 grip 源像素误差均 ≤1 px；脱离态必须出现 >1px 的实际误差以证明模式耦合有效，依据在跑测前冻结。这是有限域测试，不能称无限连续域的形式化证明。
- 真实动作：实际 Core 终态、目标网格与 GL 像素三者都检查，并真实经过当前 Studio 导入→预览→动作选择→Escape 释放/focus 归位。

如果合法作者模型的参数/网格超过现有 bounded diagnostics 预算，测试应明确失败/指出预算，不能截断后冒称全部网格不变。审定点允许多个明确的 body-only 支持，包括位于 Topwear 后的 Topwear2 背填；不将旧 r1 的唯一 Topwear 观测写成通用门。禁止的 arm/cuff 即使只有 alpha1 仍拒绝，未声明的非 body 支持也拒绝。masked 语义支持尚未独立解出最终 clip alpha 时保守失败，不拿未裁剪 alpha 当可见性已证明。

## 有意义负控

完整跑测会保留同一个检测器对错误的真实状态的拒绝：

- 真 CupVisible 隐藏同时额外设置一个真实 finger curl，必须被“非杯 exact 不变”挡住。
- 真 held 状态额外设置 CupX 极值，使杯离开握持点，必须被抓点误差挡住。
- 给产品 API 不存在的实际参数，必须拒绝且 Core 参数数不变。
- 同样姿态重复真实评价必须 exact 相同，否则无法把变化归因于被测动作。

单位测试另证明：即使两次 mesh 完全没变，forearm 纹理错误承载 abdomen 仍被 alpha/所有权门挡住；只看“不相关 mesh 没动”抓不到这种分区错误。旧刚性 hinge revision 作为真实反例另外留存，不能被新 curl 的绿报告覆盖。

## 执行

```bash
python -m unittest discover -s tests -p test_hand_cup_acceptance.py -v
python tests/hand_cup_metamorphic_check.py \
  --model FINAL_EXPORT/character.model3.json \
  --contract FINAL_FUNCTIONAL_CONTRACT.json \
  --landmarks FINAL_ACTUAL_CORE_LANDMARKS.json \
  --source-manifest FINAL_SOURCE/layers.json \
  --runtime-dir /workspace/.live2d/owner-generated-runtime-check \
  --output review/hand-cup-FINAL.json \
  --evidence-dir /workspace/dist/hand-cup-FINAL
```

缺实际 CupHold/动作/审定点/最终源 SHA 时 CLI 写 `BLOCKED` 并 exit 2，不把检查 skip 掉。可先用 `tests/hand_cup_candidate_check.py` 对中间导出做分项；其状态永久带 `full_acceptance_blocked`，不能拿来宣称完整成品。

官方 Core/Framework 留在已授权的本机私有目录，不进默认包或 Git。证据截图中的自有原画并不表示人工艺术验收已过。Windows、4060、实体五寸屏与用户听感须分别执行，Linux SwiftShader 测试不替代这些门。

## 首个 CupHold 的真实否决与 identity 复验

- 新 owner-helper 构建 runtime（Core SHA `25ae938c…`、bundle `0f9bfd8a…`）实际运行 `export-hold` 时，原审定 cup 抓点已不在真实默认三角内。产品截图与独立 raw Core 都显示杯飞到头左；`review/hand-cup-r5-held-interpolation-probe.json` 保留初红，`review/hand-cup-r5-hold-default-diagnostics.json` 进一步固定全 Body/Breath=0 测 Hold0/1，两个模式 cup 完全同位错误，centroid 源坐标约 `(393.30,680.39)`，两掌约 `(755.12,1245.63)/(985.03,1248.28)`。源稳定、JS0，不是 SDK 初始化失败或更换抓点就能算通过。
- 制作人据源码追到 parent-of-deformer 使用 first/min Rotation cell 并丢失 CupRoot 27 格的作者工具行为，另存 `export-identity-probe` 修订恢复 parent UV 键，不覆盖飞杯红版。该 identity 修订已在同一新 owner runtime 实际产品+raw Core 五项通过：默认杯回掌、CupVisible/XY/±45°杯 only、3 source semantic 点有效；报告 `review/hand-cup-r5-identity-restored-product.json`。
- identity 版 Hold0/1 故意相同，不能称握持补偿已过。后续必须用真实新导出做 Body/Breath 角点和离key插值；再做完整4动作与最终真实 Audio/Core。失败视频已 ffprobe：初红6.84秒、双模式诊断10.32秒，无系统音轨，保存在对应 `/workspace/dist/hand-cup-r5-*` 目录。
- 独立审查补空满足门：不能拿 eye/finger 参数冒充 Body/Breath；至少一个实际 Body 及 Breath 分别真实移动掌抓点；Hold0杯 ROOT exact、Hold1只变杯且有实际耦合改善；finger-only Curl 不能冒充 wave；cup/torso/palms/arms/fingers 不可互相重叠，两个 grip 标签不能指向同一掌或同一源位置。新25项 instrument 单元仍不构成人物通过。

## 2026-11-13 当前结果与修正

production控制修复0.2.2已冻结，见 `review/live2d-frontend-control-fix-freeze.json`。实际SDK动作保存的参数现在可通过Studio reset恢复全部Core defaults和完整几何；清表情可再次选择同表情。延迟真实资源在load/reset后clean false取消，不给已换模型发送旧motion。Node88全过，33个手杯instrument单位测试另过。candidate7仅作为技术夹具，不能用这组runtime绿替代艺术接受。

810 directWarp机制在独立512上实际仍失败43例，max3.2233468源px（预算1px不动）；不是原61选格结果的延伸。新MOC相对实际810 q预测仅.002894px额外表示差，表明剩余源掌场非线性，正在复制实际body变形链的新结构验证。原512已经暴露并作为诊断/回归保留，最终结构还需新的独立seed。

Root目前要求先按原strict保留Hold0 exact红，再结合serialized identity表、实际浮点/ULP与GL证据明确制定语义；此时不得静默放宽。只有Body条件变化下恒等分支的微差可能属于数值问题；Cup控件改变任何非杯网格的exact0门与真实held≤1px门均保持。

## 2026-11-13 v2：不可见的原生杯连接辅助 mesh

原生 glue 的真实反事实先保留 v1 红：`review/hand-cup-native-glue-shared-root-product-probe.json`，8 个实际 Body/Hold 姿态通过，但 CupX 使两技术 helper 随杯变化，旧“所有非 active cup 几何不变”检查拒绝。这不是手掌/身体被杯控件带动，也不能删掉旧红后假称原检测器未改。

v2 保持 `meshes.cup` 仅为可见杯，新增 `meshes.cup_helpers` 恰好两个互异、真实存在的技术 ID；`cup_helper_bindings` 每项必须有 `mesh_id`、同 ID 的 `source_object_id`、实际 `source_parent_id`、`role:'invisible_cup_attachment'`、与 `model_binding.source_manifest_sha256` 相同的源绑定。它们不得与 cup/torso/palms/arms/fingers 重叠，不得成为 limb 或 action 的物理目标；仍须真实源/MOC SHA 与作者契约一致，不能只凭名称认定身份。

- CupX/Y/Rotation 只允许 active cup + 这两个技术 helper 的几何改变，物理角色其余完整坐标/opacity 必须 exact 不变；active cup 必须真的改变且产生 GL 像素差异，不能只让 helper 动来满足。
- helper 在实际默认、Body/Hold、杯 XYZ、肢体/十指、四动作每次采样都必须 opacity **严格 0**。任何正数包括 `1e-20`、缺 ID、额外第三 helper 或 body alias 都拒绝。JS 每次真实 Core snapshot/每个实际 motion 采样帧也检查，不仅终态检查。
- Hold0 可见杯 full vertices/opacity 跨 Body 仍严格 ROOT exact；同姿态 Hold0→Hold1 仍只允许 active cup 变形，两个 helper 几何也必须 exact 不变。握持 1 源 px、指根 .5 源 px 均未改变。
- helper 可随其真实 wrist 运动，这是技术连接的父链；该例外不允许物理角色任何额外 mesh 运动。肩部 glue 保护仍比较审定腹部 barycentric 点。

先前 810 flatten 方案在 512 新姿态中 43 处超 1 px，max3.22335；直接挂共同 BodyZ 的反事实 512 全失败、max41.33468。native-glue 最小结构同512 grip max.000031755；shared-root 旧512 max.005385861、事前封存的新 seed2718281828/1000 max.005953765，均真实 Core、source 稳定、ROOT/noncup exact/隐藏 helper opacity0。这只是结构机制证据，不代表最终衣服、美术、四动作或 Windows 已通过。1000 首次测量前封存记录为 `review/hand-cup-independent-seed1000-preregistration.json`；若之后据其调结构，它必须降为回归集，最终再用新 untouched seed。

## 硬杯形状独立门与可复现工具（2026-11-13）

正式 native-glue r1 的手指/接触技术 13 门通过，不代表杯子是硬的。新增实际检查发现：六 arm/forearm/hand 参数全 0，仅 Body/Breath 的新姿态也能把杯口拉弯；真实近景在 `dist/hand-cup-formal-affine-worst-visual/`，不是仅透明顶点误差。相同正式 MOC 的独立 1,000 姿态中，154 个 triangle-used 顶点最大 affine 残差 25.444747 源 px，similarity 残差 52.577668；81 个顶点有原纹理 alpha 支持，另 73 个在采样点低于 alpha32，没有 unused 顶点。不能用 grip1px 绿遮盖此红。

r2 导出前由 root 固定两条独立形状预算：相对同模型 rest，**全部 triangle-used 顶点**的最佳 2D affine 残差、最佳 orientation-preserving similarity 残差均 ≤0.5 源 px。1536×2048 在约 900 高舞台的 fit 比约 .439，.5 源 px 约 .22 屏幕 px；这是预先选择的亚像素预算，不是看新 MOC 后改门。仍单独保留 grip≤1 源 px、finger root≤.5 源 px。模型不得坍缩到 scale0 来获得零残差。

- `tests/live2d_cup_geometry.py`：纯标准库的中心化 affine/complex-similarity 拟合；8 项明示合成正负控涵盖剪切、单点弯曲、反射、坍缩、透明/unused 分组及退化/非法输入。单元通过不是角色通过。
- `tests/live2d_cup_rigidity_check.py`：实际 owner Core、source/model/runtime/输入 SHA 门；以实际 index buffer 识别 triangle-used 顶点，对 all/used/纹理 alpha 支持分别报告。纹理采样采用当前 shader UV 翻转及四 texel 保守支持；这不是最终 GPU mask 可见性证明。公开 declared limit，默认仅测量，不推断美术接受。
- 每次实际 `model.update()` 计时在 32 次实际 warmup 后采集，报告 p50/p95/max、样本数、计时量化、浏览器/CPU/引擎。只计 Core，排除参数写入、顶点提取、GPU/界面渲染；云端 asm.js 结果不能冒称 Windows/4060 FPS。新模型与同次 5,000 raw check 一并计时，避免重复工作。
- 字节同一的独立 5,000 输入已交付到 `tests/fixtures/live2d-cup-poses-seed2236067977-5000.json`，SHA `243ae53faad169f4b02ce73e1cd5912e9ec7710c3aa63221220e845faf83f057`。它在 20,655 网格选定后首次评价前封存；此前 1,000/2,000 已作为诊断，不能继续称未见 holdout。新 5,000 的**预测**最坏 .678606 源 px 不是导出 MOC 的通过，实际新 MOC 必须另跑。

```bash
PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright python tests/live2d_cup_rigidity_check.py \
  --model ACTUAL_EXPORT/character.model3.json \
  --poses tests/fixtures/live2d-cup-poses-seed2236067977-5000.json \
  --runtime-dir OWNER_INSTALLED_RUNTIME --cup-id ArtMeshLayer \
  --hold-parameter ParamCupHold --max-affine-residual-px 0.5 \
  --max-similarity-residual-px 0.5 --output review/ACTUAL-shape.json
```

`tests/fixtures/live2d-cup-root-combinations.json` 另列本原创模型真实 RootXY±500/rotation±45 的 27 组合；其它用户模型必须使用其自身实际 ID/范围。形状 checker 不导入假参数，不下载 SDK、不改 MOC；反复 default 评价必须 exact 稳定。

实际界面验证工具也已移入仓库：`live2d_mainstage_actions_check.py`、`live2d_mainstage_expression_check.py`、`live2d_mainstage_motion_recovery_check.py` 及 `live2d_action_midpoint_capture.py`。主舞台通过真正用户按钮选择包内动作/表情；复原能清表情并重选同名。SDK motion 503 的 cached-null 真实红、明确重新载入后恢复的真实绿分别保留。中段工具在观察到的实际模型 elapsedTime 暂停 renderer，只为同一 Core 帧截全景/近景，然后恢复；不能把这种诊断录制冒称无暂停的日常动画，另有正常主舞台视频。


## 硬杯形状独立门（2026-11-13）

抓点贴合不能证明杯子没有弯曲。正式 r1 曾在手臂控制全部为0的六轴 Body/Breath 正常姿态中通过抓点测试，但真实154个杯顶点的最佳 affine 拟合最大残差25.444747源像素、similarity残差52.577668，已否决该模型，旧证据保留。

新模型导出前固定：所有被真实三角形使用的杯顶点，最佳 affine 和 similarity 两项最大残差均不超过 **0.5源像素**；抓点1源像素和指根0.5源像素的原门不变。0.5源像素在2048高素材适配900高舞台时约0.22屏幕像素，目的是要求硬质外形保持在亚像素误差内。全部/三角形使用/纹理alpha支持的顶点分别报告，不能仅挑边缘少量点。

`tests/live2d_cup_rigidity_check.py` 是可复现CLI；`tests/live2d_cup_geometry.py` 用标准库实现中心化最小二乘，并有8项真正正负控。独立5000姿态夹具在拟合新模型前封存于 `tests/fixtures`；预测和真实新MOC结果必须分开。真实Core检查含32次预热，再逐次计时model.update，报告p50/p95/max和实际CPU/引擎。纯Core耗时不是绘制帧率，也不能作为Windows4060性能证明。运行参数以CLI `--help`为准；未明确传入门限时仅测量，不产生接受结论。

FollowWarp方案还需读取真正可编辑工程的全部控制点，验证四角交叉项、相似变换和非退化范围。多线性权重在作者域内非负时可保持该结构；这是有前提的数学证书，不能替代真实Core采样、动作中段截图及杯体近景。
