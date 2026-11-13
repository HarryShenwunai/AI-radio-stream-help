# R3 上半身待机：放杯方案已取消

用户已取消放杯及五姿势动画方向。当前本地 R3 候选 runtime 仅保留上半身待机，手、杯子和袖子保持原姿势。此更新未部署、未经过 Windows 实机或用户视觉验收。

## 本次范围

- 删除当前候选包的 Review、GentleLower 动作入口及其 R3_review.motion3.json、R3_lower_eased.motion3.json 文件。
- 删除候选包的 revise_motion.py（放杯缓动生成）和 package_revision.py（旧放杯交付打包）。
- 从 preview.html 删除放杯采样表和播放器调用；record.py 删除放杯中点、终点采集分支。
- 新增 scripts/build_r3_upper_body_motion.py，可重复生成 Idle 动作；保留未知动作组和仍被引用的文件。它不改写 MOC3 或原画。
- Idle 为 12 秒循环，两次眨眼、极轻微侧倾。ParamAngleZ 范围约 ±2，对应此模型绑定约 ±0.14°，并非 ±2°。
- 旧二进制中的 ParamCupLower 与 ParamCupVisible 暂保留兼容，播放中固定为 0 与 1。没有宣称已从编译模型中移除放杯绑定。通用参数面板仍可能手动驱动旧参数；当前上半身预览不会开放这一操作。

## 保留与边界

未改动通用渲染器或其他角色的动作功能。未删除用户原图、分层源图、PSD2Live/CMO3 工程、历史录像与审查记录。候选包 authoring/source/editor 下的旧工程和脚本仅用于历史恢复，不是新方向的构建入口；旧 SHA256SUMS 对应历史交付，不代表本次修改后的 runtime。

该候选包在 .build/r3-motion-revision，未纳入 Git 的二进制交付。仓库新增的构建脚本、测试和本说明记录本次变更；已有未提交的原稿重建修改未覆盖。

## 验证

- 新增回归测试通过：只移除指定旧动作、保留其他动作及原素材、重复构建结果一致、杯子参数固定、循环首尾一致。
- 原有 Live2D 适配器 15 项测试通过。
- 云端真实 Live2D Core 播放约 12.5 秒，无 JavaScript 错误；实际眨眼与头部参数发生变化，杯子下降值全程为零。
- 比较中性、闭眼、小侧倾的实际 Core 网格：14 个手、杯子及袖子网格顶点不变；头部网格确实变化。
- MOC3 SHA256 与此前候选包一致。检查了闭眼及侧倾截图；这不是最终视觉验收。
- 结果摘要：review/r3-upper-body-cleanup.json；录像：.build/r3-motion-revision/r3-upper-body-preview.mp4。

## 后续安排

1. 先复核现有眨眼的覆盖边缘、头颈接缝和待机节奏。
2. 呼吸：为胸肩区域制作独立轻微形变，保护袖口与手杯接触，验证手杯网格不受影响。
3. 视线：当前没有独立眼球运动绑定，需要补画被眼睑遮住的眼部内容后再制作小幅视线变化。
4. 完成上述局部绑定后再输出预览。不要用整张画面缩放冒充呼吸，也不要用参数数值变化冒充实际可见效果。

## 后续实作：局部胸肩呼吸候选

已在原工程副本上为 Torso 网格新增 ParamBreath 的局部柔化位移（不是整图缩放）；导出新的 PSD2Live、CMO3、MOC3。原文件保留。重建规则见 scripts/r3_upper_body_breath_recipe.py；build_r3_upper_body_motion.py 的 --bound-breath 仅用于确认已有实际呼吸绑定的模型，旧模型默认不开启。

工作副本：.build/r3-upper-authoring/character-upper-breath.psd2live；运行包：同目录 runtime/model.model3.json。真实 Core 播放 12.6 秒，630 次参数采样，呼吸范围 0..约1，放杯参数全程为零；端点网格比较确认呼吸只改变 Torso，14 个手杯袖网格不变。记录见 review/r3-upper-body-breath.json。

进一步放大检查发现：半闭眼时闭眼贴图的睫毛线与原虹膜叠影，现有贴图透明度过渡不等于正确眼睑运动。完全闭眼及约 ±0.14° 头侧倾端点未见明显领口裂缝，但不能据此称全部视觉通过。需要单独眼白、虹膜和眼睑遮罩/补画才能可靠制作视线和无叠影眨眼；当前视线未实现，技术预览不得描述成完整自然待机成品。

现有已上传的旧预览 Library ID：libfile_6d31fcd5859c81918a8f6ad2a81854db（仅眨眼与微侧倾，不包含后新增的呼吸）。

## 眼部修复审查候选（未验收）

工作目录 .build/r3-eye-repair。沿用同一角色的原画、身体/手杯图层与小幅头部绑定，新增 EyeSclera、EyeIris、EyeLid、EyeUpperLash、EyeFrontDetail。旧 Eye_closed 淡入层不再进入候选。虹膜使用原像素提取，眼白和无杂线眼睑皮肤使用内置 image_gen 补画；提示词见该目录 imagegen-prompts.json。前景细发丝与眼周原像素独立保留，眼睑使用不透明几何遮挡眼球。虹膜带原生剪切遮罩，位移约为原图水平 ±1.1 像素、垂直 ±0.55 像素。当前动作使用更小的幅度。

已保存可编辑工程 character-eye-repaired.psd2live 及 runtime 下的 CMO3/MOC3。build_eye.py、bind_eye.py、extract_eye_layers.py、verify_record.py 保留在同目录，使用原有固定版 PSD2Live 工具。该候选重建了实际眼部网格，不是只改参数名。原稿与此前工程未被覆盖。

验证：真实 Core 24 组独立/组合姿态，原生虹膜蒙版数量为 1；纯视线只改变虹膜网格，纯呼吸只改变 Torso；14 个手、杯、袖网格不变。闭合及睁开共 21 帧逐帧检查，起止 PNG 像素完全一致；约 12.6 秒实际录像无 JavaScript 错误。Python 动作回归和原有 15 项 Node 适配器测试通过。Python 首次在只读环境中无法创建临时目录，切换到获准写入的执行环境后通过，非产品测试失败。

视觉限制：旧半闭眼叠影和补画中的拉伸杂线已移除；闭眼眼角线条仍偏硬，眼睑明暗偏平，需要继续审美复核。只处理可见眼睛，刘海遮住的一侧不作虚构补全。小侧倾与呼吸检查未见明显头颈裂缝，但不覆盖大角度转头。本次是审查候选，未部署、未获得用户认可或 Windows 实机验收。

交付：eye-repair-review.mp4 为全景；eye-detail-slow-review.mp4 为眼部放大两倍时长慢放（不增加原图细节）；blink-21-frames-final.png 为逐帧检查图。详细机器检查结果：review/r3-eye-repair.json。
