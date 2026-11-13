# 本地面部方向估计与 Windows 离线组件

更新：2026-11-12。已实现、实际 CPU 算法与 Windows 包检查分开记录。没有用文字模型、鼠标或固定动画冒充摄像头推理。

## 当前可用范围

`perception_tracking.py` 运行固定官方 MediaPipe Face Landmarker 1.2.3，强制 CPU/XNNPACK。它从用户已经授权的摄像头画面估计面部中心、头部角度、眨眼、张嘴与微笑系数。没有人脸身份识别、个人生物模板或专业眼动校准。

PNG 角色可以使用有限状态和位置/倾斜响应。单张 PNG 没有拆件眼球，不能因此声称眼球能独立转动。Live2D 或其他已绑定头像需要另行映射参数并验收自然度。

摄像头默认关闭。用户声明“有摄像头”只决定入口是否可选，不等于检测到设备、授予权限或算法可用。用户设为无摄像头时，宿主停止所有 camera 会话。可选 5 英寸显示装置与 PC 主屏幕分享独立；关闭它不禁用 PC Vision。

## 稳定接入接口

```python
model_store = FaceModelStore(DATA / 'perception' / 'tracking')
# owner 明确点击安装才下载，固定 3.76MB 官方模型；不会自动运行 pip。
receipt = model_store.install_official(consent_confirmed=True)
tracking = FaceTrackingManager(model_path, is_scope_current=server_scope_checker)
tracking.status(owner_id)
tracking.start(scope, consent_confirmed=True)
tracking.frame(scope, session_id=..., request_id=..., image_base64=...,
               mime_type='image/jpeg', captured_at_ms=...)
tracking.stop(owner_id, session_id)
tracking.stop_all(owner_id)
tracking.close()
```

宿主路由为 owner-only `/api/perception/tracking/status`、`install`、`session/start`、`session/stop`、`frame`。owner Cookie、X-Companion、Host/Origin 与当前角色校验由宿主负责；插件 bearer 没有这些权限。停止旧角色 session 可以清理旧资源，不能终止另一个新 session。

status 不导入/启动 MediaPipe，不打开设备。它读取依赖元数据、模型大小/SHA及缓存状态。缺少包/模型或初始化失败分别明确 unavailable。首次明确 start 才导入并初始化算法；随后 `algorithm_loaded:true`，`inference_verified:false` 保留对真人/硬件精度的限制。

frame 返回：

```json
{
  "session_id":"opaque",
  "request_id":"opaque",
  "tracking":{
    "state":"face",
    "face_center_direction":{"x":0.2,"y":0.1},
    "head_pose_degrees":{"pitch":0,"yaw":0,"roll":0,"convention":"RzRyRx_camera_degrees_estimate"},
    "expressions":{"blink_left":0.1,"blink_right":0.1,"jaw_open":0.2,"smile":0.3},
    "measurement":"head_and_face_direction_estimate",
    "identity_recognition":false
  },
  "processing":"local",
  "retained":false
}
```

数值只是字段示意，不是本次推理记录。方向 x 向右为正、y 向上为正；前端镜像只影响预览，不能暗中混淆物理坐标。没有脸或有多张脸时返回 `no_face/multiple_faces`，方向与角度为 null、表情为空；头像应回到待机，不能跟随历史脸。eyeLook 系数是模型估计，不代表屏幕注视点。

限制：PNG/JPEG、250,000 bytes、最长边640、最多307,200像素、单在途、全局/会话最少间隔0.2秒。帧捕获≤3秒、结果≤5秒；角色/外观/epoch、停止和配置撤销都检查迟到结果。模型推理不配合立即取消时，仍丢弃无权交付的结果。原帧不落盘；短期去重结果不进入人物记忆。

## Windows CPython 3.12 无 pip 的实际交付

正式候选使用两个 CPython 3.12 x64 嵌入运行时，`python312._pth`，没有 pip。不能给用户 requirements 当成已安装功能。

新增共享固定目录：

```text
resources/optional/tracking/
  tracking-addon-manifest.json
  python312/site-packages/
  models/face_landmarker.task
  WHEEL-PROVENANCE.json
  NOTICE-TRACKING.txt
  LICENSE-MEDIAPIPE-MODEL.txt
```

15个官方 Windows 兼容 wheels 已按 PyPI SHA校验下载，总93,795,778 bytes。旧 CPU/CUDA 现有 numpy2.5.4、Pillow13.0.0、flatbuffers25.12.19、packaging26.3 原样复用，不覆盖旧 site-packages 或模型。完整版本、wheel 名、官方URL、大小、SHA与声明许可见 `review/tracking-windows-dependencies.json`。

最终 **v3** 包 `tracking-addon-cp312-win-x64-v3.zip` 不含不使用的 Windows FFmpeg 插件、ASIO SDK 或非 x64 备用二进制。每个省略文件的原始大小/SHA、来源与理由写入 manifest；所有上游许可证、NOTICE、README 保留。Matplotlib自己的公开sample_data也原样保留；“不含样本照片”特指本次本地MediaPipe评估portrait与用户采集帧，不是说上游wheel完全没有图片。v1/v2只作本机审计，不对外发布。

`activate_tracking_addon(ROOT)` 内部只识别已发布 CPU/CUDA 的固定资源结构，不接收角色/前端自定义路径。先核可信常量锚定的原始 manifest SHA，再核所有成员路径、大小、SHA和文件类型；拒绝链接/reparse、未列文件/目录、.pth、sitecustomize、陌生字节码及已排除的二进制。

通过后仅 `sys.path.append` 共享目录。`sys.dont_write_bytecode=True` 防止可执行缓存进入已锁目录；不使用 addsitedir 或执行安装钩子。失败只标不可用，不中断文本聊天。非 Windows x64 CPython3.12 不激活这些 DLL。`verify_tracking_addon(ROOT)` 可在 Linux 构建机验证文件，不能据此称 DLL 已运行。

最终ZIP 83,452,536bytes；SHA `4b3f763179bf771cd8466082114f9f9e4c87c0aab0d7caaacdab2fd705fccf21`。2043个锁payload加manifest共2044成员，解压231,680,607bytes。原始manifest SHA `de08abac2f341d0cacf2eba38fc89e53bef0252f98cc2f258736b95ed95bad12`；无LF canonical SHA `a72ef9399f156c76874ccda0357295b9123305e5b923ed7bf3d8673cf5484f8b`。

原始 manifest 含末尾 LF；安装器必须原样保留 ZIP 内字节。JSON重序列化去 LF 的 SHA另记为 semantic/canonical 值，不能混淆。

## 已处理的第三方组成

- 官方 OpenCV 精确源码40738fb16ceddb5fb3fea747585f7ce6abb0605b的 ffmpeg.cmake，指向第三方06dc20cad65dc7fcf784f70c95d46750520889a7。原插件 MD5与官方64位 pin一致。对应库版本 avcodec61.19.100、avformat61.7.100、avutil59.39.100、swscale8.3.100。
- 该插件是独立运行时可选 LGPL2.1 DLL。官方 readme 明确允许从分发剔除它；本方案按此处理，没有把整个 OpenCV wheel 概括为全 Apache。cv2.pyd 的 PE 导入表不依赖 FFmpeg 插件。
- sounddevice官方wheel附带多平台和ASIO备用库。保留默认x64非ASIO MIT PortAudio；省略3个ASIO、x86/ARM64备用与macOS库。原始选择逻辑和许可证不改。MediaPipe会导入其音频辅助模块，但面部路径不调用录音/播放流。
- MediaPipe NOTICE包含 GPL3+GCC Runtime Library Exception、Matplotlib有字体许可；这些原文保留，不能只用顶层包许可替代。

所有保留 PE/DLL/扩展均审计为x64。外部非系统依赖为 python3/python312 与VCRUNTIME140/VCRUNTIME140_1；旧CPU/CUDA运行时均包含它们。静态导入表不能替代 Windows 真机加载测试。

## 实际测试与剩余验收

已完成机器证据：

- 感知/跟随/可选加载器83项测试，含1,296条有界轨迹、5,184次真实管理器操作；strict mypy与关键Ruff。
- 真实 CPU 对官方portrait、空白、恢复人脸、位置移动与双人合成图推理。没有把样本图片/人脸点阵复制到公开包。
- 禁用OpenCV VideoCapture/VideoWriter/imread/imdecode与Python音频流的故障注入；注入必须被检出，正常脸部推理继续。记录与图像理解/真人摄像验收分开。
- 真实纯Python依赖import后全锁树再次通过、无pyc；关闭bytecode保护的独立负控制生成12个pyc，证明保护必要。这个Linux测试模拟了激活平台/基包位置检查，不冒称Windows执行。
- 同一资源模型在真实算法初始化/推理前后整树仍通过。Matplotlib缓存改为进程级私有临时字体缓存，不写addon、模型旁边或旧profile；不含帧或人脸模板。
- 最终ZIP逐成员CRC/SHA、解包树、所有许可证、仅预期省略和全部native架构另有真实检查报告。

数据来源：`review/tracking-real-check.json`、`tracking-addon-import-check.json`、`tracking-addon-v3-check.json`、`perception-module-check.json`。本次最终云Linux测试初始化1.653秒，20暖帧P50 10.41ms、P95 11.43ms，进程峰RSS189,600KiB；只代表这台构建机与样本。Linux缺libGLES/PortAudio时从官方Debian私有提取17KB/65KB运行库，音频负控显式指定该真实PortAudio库；不改系统或语音环境，不作为Windows/4060承诺。

Windows必须实际验证：嵌入无pip环境激活、所有DLL加载、用户授权/拒绝/撤销、无脸/多脸/眼镜/遮挡/背光、隐藏/角色切换不再发送帧、CPU/RAM与P95延迟、头像状态/参数映射与自然度。若P95接近采样间隔，应降频并只处理最新帧，不积压队列。5英寸实体展示、远场阵列与专业眼动没有通过软件测试自动实现。

## 官方来源

访问日期：2026-11-12。

- [MediaPipe v1.2.3 官方发布](https://github.com/google-ai-edge/mediapipe/releases/tag/v1.2.3)
- [官方PyPI包/文件元数据](https://pypi.org/pypi/mediapipe/1.2.3/json)
- [固定官方 Face Landmarker task](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)，3,758,596bytes；SHA64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff是本次观测并固定的校验值，非厂商公布SHA。
- [MediaPipe任务说明和模型卡入口](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)，三个模型卡分别标Apache2.0。
- [精确OpenCV FFmpeg pin](https://github.com/opencv/opencv/blob/40738fb16ceddb5fb3fea747585f7ce6abb0605b/3rdparty/ffmpeg/ffmpeg.cmake)
- [同一第三方提交的官方省略/分发说明](https://github.com/opencv/opencv_3rdparty/blob/06dc20cad65dc7fcf784f70c95d46750520889a7/readme.txt)
- [官方对应源码提交](https://github.com/opencv/opencv_3rdparty/tree/664c0098dcb47b361f20c1d6a518653c23f5f2b5)，v3不分发该FFmpeg二进制。
