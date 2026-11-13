# R3 透明舞台候选

沿用 R3 双眼绑定、原始脸和手杯姿势。此前矩形边界来自 `Background_and_hidden_body` 底层；直接隐藏又会暴露头发和蒸汽纹理中的原背景残留。

本次由 image_gen 提取透明头发和蒸汽；只把提取出的头发 alpha 与原有 alpha 相交，再注册回原尺寸。头发 RGB 逐像素保持原样，原脸颈镂空不可扩大不透明范围；其他原图层字节不变。脸部交界附近恢复原始头发 alpha，避免刘海缺口；保护蒙版固定为 8 位灰度，拒绝 16 位蒙版被错误截断成不透明区域。模型隐藏背景底层，蒸汽静态强度为 0.12。原工程与素材保留，输出在独立工作目录。提示词见 `review/r3-transparent-stage/imagegen-prompts.json`。

## 可重复流程

需要已有原始素材、前轮双眼素材、本轮两个 image_gen 输出、ImageMagick，以及现有获授权的本地建模工具/Core；不包含第三方二进制，也不自动接受任何许可。

```sh
python scripts/r3_both_eyes/prepare_transparent_stage.py --work-dir .build/r3-transparent-stage --source-dir .build/r3-motion-revision/source --eyes-dir .build/r3-both-eyes --hair-cutout .build/r3-transparent-stage/Hair_shell-extracted.png --steam-cutout .build/r3-transparent-stage/Steam-extracted.png
python scripts/r3_both_eyes/build_both.py --work-dir .build/r3-transparent-stage --source-dir .build/r3-transparent-stage/source --transparent-stage
python scripts/r3_both_eyes/bind_both.py --work-dir .build/r3-transparent-stage
```

导出后按已有 R3 包装流程创建 `model.model3.json`，调用 `scripts/build_r3_upper_body_motion.py`，开启 `--bound-breath --bound-gaze --bound-both-eyes`，保持 `ParamCupLower=0`。使用现有预览页与获授权运行时执行：

```sh
python scripts/r3_both_eyes/verify_record.py --work-dir .build/r3-transparent-stage --transparent-stage
```

Core 检查包括 46 个姿态、21 张眨眼帧、左右虹膜各自遮罩、手杯袖子固定、胸肩呼吸，以及背景/蒸汽实际透明度。实际应用导入与手机布局由 `tests/browser_audit.py` 验证；可添加 `--idle-video-seconds 12.5` 记录正常待机动作。浏览器报告现在记录源文件哈希、运行前工作树状态，并在检测期间源码变动时判失败，不能只用 HEAD 代替被测试内容。

## 验收范围

这是待视觉审查的候选，非用户最终认可。小幅头动和视线范围沿用 R3，不宣称大幅转头或完整隐藏眼眶透视。Windows 10/11、RTX 4060、官方 Cubism Editor 复开、Live2DViewerEX 实际导入以及真实账号联动仍未验收。GitHub Actions 的平台账号阻塞需由账号所有者处理；本地检查通过不代表远端 CI 已执行。
