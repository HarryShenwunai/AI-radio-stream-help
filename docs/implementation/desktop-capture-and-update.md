# 原生媒体、显示输出与离线小更新

验证日期：2026-11-12。以下把实际 Linux 主机验证与 Windows 待验分开。

## 原生媒体边界

`desktop/media-policy.cjs` 只对配对的本机后端主 frame 提供摄像头/麦克风的逐次原生确认。拒绝其它权限、外部 origin、子 frame 和无效媒体类型；异步确认后重新检查窗口及导航代际。隐藏、销毁或超时后的批准不生效。

主 UI 永远拒绝 `display-capture`。真实 Electron 45.3.1 负控发现，标准 `getDisplayMedia` 和旧 `getUserMedia({chromeMediaSource:'desktop'})` 共用这项前置许可；只在标准来源 handler 中选择窗口不足以阻止旧路径绕过。保留的调查夹具只有显式 `--investigate-display-preflight` 才临时允许前置许可，不能用于产品验收。

`desktop/screen-capture.cjs` 先显示原生来源菜单，再打开独立的打包本地预览窗口。该窗口没有 Node、预加载特权、外部请求、任意导航或通用 IPC，只运行固定脚本。用户在其中点击“开始预览”后才启动所选来源；只允许视频，不捕获系统音频。主进程重新枚举并核对来源，不自动选择第一块屏幕。这个安全捕获 renderer 不创建第二个角色舞台或音频播放器。

预览请求上限为 1600×900、10 fps，偏好 5 fps；返回 JPEG 最大 1600×900，主进程至少间隔 500ms、只准一个帧请求在途，前端实际每 2 秒本机预览一次。预览最长 15 分钟。关闭、隐藏或最小化捕获窗口/主窗口会结束捕获；主窗口导航、角色或外观切换同样通过各自所有者终止旧会话。取帧只在本机，只有前端再次明确分享后才交给后端视觉接口。

隔离预加载桥：

| 方法 | 返回及边界 |
| --- | --- |
| `startScreenPreview()` | 隔离世界检查真实用户激活；返回 `capture_id`、`awaiting_user` 和来源标签 |
| `getScreenPreviewFrame(id)` | `awaiting_user/active/stopped/failed`；active 含当前 JPEG 和时间，不写磁盘 |
| `stopScreenPreview(id)` | 只停止该 id；旧 id 不能结束新捕获 |
| `getDisplays()` | 实际 `screen.getAllDisplays()`，标识主屏和是否检测到其它屏幕 |
| `setDisplayOutput(number)` | 显式选择真实显示器，同一个主窗口填满其工作区 |
| `restoreDisplayOutput()` | 恢复原窗口尺寸、位置、展开及置顶状态；原显示器断开时落回主屏可见区域 |

显示器像素和编号不能证明物理 5 英寸或全息效果。设备声明“有”不等于已检测或已授权；声明没有额外显示器只退出输出模式，不禁用 PC 舞台或 PC Vision。输出可以从原生托盘返回，原显示器断开时自动恢复可见窗口。

## 实际证据

`desktop/test/media_native_probe.py` 启动真实应用 `desktop/main.cjs`，使用私有 Xvfb、原生菜单/确认框、明确启用的合成摄像头和真实测试桌面来源。它检查视频时间推进、停止、原生取消、专用窗口开始前不采集、JPEG、限帧、主 UI 旧捕获路径拒绝，以及单窗口输出/恢复。测试页面是专用夹具，不是整套产品 UI 验收。

复现：

```sh
/workspace/companion/.venv/bin/python desktop/test/media_native_probe.py --output /workspace/dist/native-media/reproduction
node desktop/test/media-policy.test.cjs
node desktop/test/screen-capture.test.cjs
node desktop/test/window-policy.test.cjs
```

视频没有音轨。真实 Windows 摄像头、远场麦克风、外接屏幕、4060 性能和物理全息效果仍需对应设备验收。Linux 单次合成帧率不是 Windows p95 指标。

## 程序小更新 v2

本次完整重建使用 `scripts/build_app_update.py`、`scripts/app_update.py`。早期 `build_ui_update.py` 是未发布的纯 UI v1 草案，不能包装这次后端与资源变化。

v2 固定锚定已发布 d01 基础包：CPU/CUDA 原配置清单、主机壳、原程序文件和原生解释器/DLL 都先核 SHA。写集是显式的 `PROGRAM_FILES`、8 个主机文件及元数据；包括三个固定场景 PNG、分层 2D renderer、所需 runtime 模块。角色包另行手动导入，更新器不能写用户角色、聊天、密钥、SDK、模型或原生库。

先暂存并校验负载，保存旧文件，再安装无新依赖的最小启动保护。事务标记存在时主机拒绝启动服务；所有新依赖写完后才替换完整新主机。正常写失败自动恢复；模拟断电留下可识别事务，重跑同一可信更新器恢复后继续。旧 SHA 不匹配、原生库改动、备份损坏、未知文件和链接均保守停止。多次文件替换可恢复，不称为一次全原子，也不保证恶意并发篡改安全。

构建只接受 `passed:true`、`sources_unchanged_during_checks:true` 的报告，并逐项匹配 `source_sha256`。须覆盖所有改变的程序及全部主机文件；场景 PNG 也必须在报告中。元数据的 commit、source ID、CPU/CUDA 来源及实际 profile payload 必须一致。程序更新负载上限 64MiB。

发布 CLI 在创建输出目录前调用本地 Git：确认完整提交对象实际存在，并逐字节核对该提交树与所有固定程序、主机和随包 installer 源码。调用工具本身及其 helper 也必须匹配；脏代码、旧提交、Gitless 目录或只长得像 40 位 SHA 的标签都拒绝。暂存完成后、封 ZIP 前再检查一次。请自动读取实际 `git rev-parse --verify HEAD`，不要手抄提交。纯 `build_folder` 保留测试夹具用途，不能替代发布 CLI 门禁。

```sh
python scripts/build_app_update.py \
  --base-package .build/desktop/character-windows312-x64 \
  --source-commit ACTUAL_40_CHARACTER_COMMIT \
  --update-id ACTUAL_UPDATE_ID \
  --validation-report review/ACTUAL_PASSING_REPORT.json \
  --output /workspace/dist/ACTUAL_UPDATE.zip
```

上面的大写参数是占位说明，不是已完成构建的声明。下载后核对可信 GitHub Release 提供的 SHA，完整解压并退出软件，运行 `apply-ui-update.cmd`。中断可重跑或 `rollback-ui-update.cmd`。沿用旧包模型，不要求重新下载整个基础包。代码尚未签名，不能把自带 SHA 清单称作密码学签名。

## 可选面捕离线扩展

`scripts/tracking_addon.py` 只接收锁定 SHA 的 `tracking-addon-cp312-win-x64-v3.zip`：83,452,536 bytes。压缩包、原始 manifest bytes 和无尾随 LF 的语义哈希分别核对；不能把这三种哈希混用。

该包含 2043 个锁文件和 manifest，解压 231,680,607 bytes。只新增 `resources/optional/tracking`；CPU/CUDA 共用，不覆盖原 profile 的 NumPy、Pillow、解释器、DLL 或模型。先核完整成员集合，再暂存校验并同卷改名；已有不同内容拒绝覆盖。禁用会将通过校验的目录移动成可恢复备份，不删用户资料。原生运行锁阻止软件运行中更换依赖。

明确剔除了面捕不需要的独立 FFmpeg Video I/O、ASIO 与跨架构组件；官方来源与理由由锁定 manifest、NOTICE 和 provenance 记录。旧 v1/v2 包保留作私有审计，不能作为新版附件外发。

把独立 v3 ZIP 放到小更新解压目录，退出软件后运行 `install-tracking-addon.cmd`。可用 `disable-tracking-addon.cmd` 可恢复禁用。此操作不自动打开摄像头、不证明 Windows DLL 或真人眼动跟踪已通过。真实全成员解包、重复安装、禁用及旧原生文件不变的报告在 `review/tracking-addon-v3-installer-check.json`。

事务测试覆盖每个程序写点的正常失败和模拟进程消失、SHA 篡改、路径越界、链接、活跃进程、损坏备份、来源/metadata 不一致、可恢复禁用。记录为 Linux 文件系统检查，不冒充 Windows 文件锁或 DLL 执行验证。
