# 原创 Live2D 当前交付与证据

更新：2026-11-13 UTC。当前为最终硬杯r2半身模型，之前的实验修订不是本次交付。用户否决的3D模型不再显示或分发。

当前42层原画对应42个实际网格、41参数；头眼嘴、衣身、上/前臂、手掌、十根独立手指和完整杯子均有实际几何。只有一个杯子，没有不可见技术杯助手网格或运行时拼图替代。杯子可独立移动、旋转、隐藏，拿杯时按Body/Breath域跟随双掌。自由摆臂与空手动作由对应motion切换，任意矛盾双臂姿态不作为持杯物理约束范围。

模型MOC SHA为6e34e112be84db93e0b9556fe0873ba713ba486f44987bfc96817395be5934bd；完整编辑工程SHA为1dd382af309e1ee15292cc628361e93d52bf9d83cf077fec1c5ab96379202d70。外部PSD与工程内原PSD逐SHA一致，42PNG及独立部件来源保持不变。

## 已实际通过

- [完整13门](../../review/hand-cup-rigid-r2-v1-full.json)：raw Core/真实产品/GL/Studio，十指最小真弯曲15.05°、根漂移0，其他部件与语义衣身保护、杯可见/XY/旋转、四动作、预览销毁/Esc。547是486所选角点+61离key，不是全表穷举。
- [独立5000握持](../../review/hand-cup-rigid-r2-actual5000-grip-asm.json)：max0.678588源px，预算1。杯形154个实际三角形使用顶点，[affine/similarity](../../review/hand-cup-rigid-r2-shape5000.json)最大0.0000857/0.0001063源px，均远小于0.5。
- 源中41310格/全部H0逐位恒等/全部H1对齐计划、Root27与父链通过独立reader；实际MOC保留7轴全表。静态export profile的3轴loss提示不代表执行裁轴，真实Core逐轴与5000行为已补验证。
- [主舞台9门](../../review/live2d-rigid-r2-mainstage-actions-ui.json)与[表情3门](../../review/live2d-rigid-r2-mainstage-expression-controls.json)：窗边/森林/傍晚背景、拿杯/移杯/空手/招手、复位/键盘/角色隔离有当前模型真实截图录像。
- [独立Core/GL](../../review/original-character-live2d-rigid-r2-core-gl.json)：13参数、四表情/八动作/物理、2378次Core；34衣袖姿态0翻转，最大edge1.222722，中性眼嘴与侧件已实看。
- [真正声音整链](../../review/real-live2d-rigid-r2-companion.json)：最终ZIP实际导入，Qwen/Kokoro/HTMLAudio/Analyser/Core口型与停止、SQLite回执和下一prompt通过。第一次环境中断的部分证据另存，第二次是完整恢复验证。

[前端证据汇总](../../review/live2d-rigid-r2-frontend-acceptance-summary.json)和[本次交付状态](completion-release.md)给出范围、性能及下载。真人画风/听感接受和Windows/4060实机不由这些Linux结果替代。

## 可编辑源与重导出

运行ZIP约11MB，完整源ZIP约346MB，另附可复现源证书与历史真实负控。源含42PNG、PSD、PSD2Live工程、CMO3、CAN3和配方；不含Core/Framework、第三方官方样例或权重。

完整工程已由官方PSD2Live3.6.7 CLI以6GiB heap真实重开并分别导出MOC与CMO/CAN，峰值RSS约6.2GiB；正常陪伴软件不需要Java。4GiB MCP重开曾失败，上游错误union遮蔽资源错误，原红保留；交付配方明确推荐已成功的CLI。官方Cubism Editor/Animator GUI重开仍待验证，不以文件头替代。

## 历史否决与修正

此前flattened-follow因内部Breath键遗漏及非线性误差被否决；旧NativeGlue虽然抓点绿，但正常Body-only杯形残差25.4447源px，不能当硬杯完成。它们的报告不覆盖本次r2。

当前改用NativeRoot外置和结构相似FollowWarp；自动插中键导致的H0一ULP漂移已通过固定原生恒等格全表copy修正，实际红IR另存可重放。四个真实动作的可见中段也有当前杯形检查；普通主舞台连续录像与诊断暂停帧分开。源与PSD、贴图不再混用旧祖先文件。
