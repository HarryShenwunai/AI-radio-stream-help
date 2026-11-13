# Windows 主人自助安装 Live2D 运行库

调查与验证日期：2026-11-12。目标是让现有便携包加载真正的 MOC 模型，复用原有 Python、模型和用户资料。默认发行物继续不含 Core、Framework 或生成后的 vendor bundle。

## 已核实的现状与选择

已发布基础包包含 Windows x64 CPython 3.12，以及 Electron 45.3.1。`Live2DRuntime` 已支持官方固定 HTTPS Core 下载、主人信任的 bundle 安装、逐次读取 SHA 校验和独立移除。此前缺少无需 Node/npm 的本机 bundle 构建步骤。

| 可行路径 | 条件与成本 | 取舍 |
| --- | --- | --- |
| 固定原生 esbuild + 嵌入 Python | Windows 下载 28,859,896 bytes 的 15 个固定 npm tarball，再获取官方 Core | 本次实现；不需要 Node/npm，不执行 package 生命周期 |
| 主人已有 Node 环境 + 既有构建脚本 | 使用 `frontend/build-live2d-runtime.mjs`，自行取得同版本依赖并接受许可 | 已有开发环境可复用；新用户还需准备 Node，额外体积待验证 |

Electron 的 RunAsNode fuse 未作为依赖条件。没有假设打包程序一定能充当 Node CLI，也不将本机评估授权扩大成 SDK 再分发授权。

固定源码列表：`scripts/live2d-owner-packages.json`。包含 PIXI 8.23.0、Jannchie 1.4.0 的实际 13 包闭包、esbuild 0.25.12 许可证包和两个平台的原生构建器。Windows 只选择 Windows 构建器；Linux 构建器只用于开发验证。npm 原 SHA512 已与实际 tarball 核对，再固定本项目计算的 SHA256。它们不是 Live2D 官方发布的 Core 校验和。

## 用户在 Windows 上操作

1. 应用当前小更新，完整解压其中的 owner setup 工具。
2. 从托盘退出陪伴软件。
3. 双击 `setup-live2d-owner.cmd`，选择已解压的软件目录。
4. 阅读 Core 与 Framework 条款。
5. 输入 `LOCAL-EVALUATION`，明确接受条款并信任固定来源的本机构建。
6. 完成后重新打开软件，再预览并确认选择自己的 Live2D 角色。

未确认时不创建下载客户端、不构建或安装。安装不购买服务、不登录平台，不上传图片、角色、聊天或 SDK。当前确认限主人本机开发评估；公开/商业分发另行核实。

Core 条款：https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html

Framework 条款：https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html

恢复以前的运行库可使用同一工具目录中的命令：

```text
<软件目录>\resources\backend\python\python.exe -I -X utf8 setup_live2d_owner.py restore --application-root <软件目录>
```

路径含空格时加双引号。恢复需要退出软件；它只切回先前的可选运行库，保留当前版本的私有备份，不删除角色或聊天。若主人后来改过运行库或旧备份损坏，会拒绝覆盖并保留现场。

## 路径、权限与恢复

`companion-desktop.exe --owner-runtime-path` 是新增的只读入口：由真正的 Electron `app.getPath('userData')` 推导本次环境的 DATA/Live2D 位置，输出 JSON 后退出。它不启动窗口、后端、托盘或恢复已有窗口。相对环境覆盖按实际后端工作目录解析，不猜测 APPDATA。使用自定义启动环境时，应保持同样的环境；也可由主人显式传 `--runtime-root`。

helper 在执行此入口前核对现有程序、主机源及路径模块的发布 SHA；原始旧包没有该入口时直接提示先应用小更新，避免旧程序忽略参数后意外正常启动。加载安装器模块前，也核对 CPU profile 中的 `companion_runtime` 初始化与 `live2d_runtime.py` 源 SHA。

默认仍使用原便携包的 CPU Python，即使正常聊天选择 CUDA；不改变推理配置或系统 Python。现有运行租约阻止软件运行时或更新事务中安装。所有 npm URL 固定为 HTTPS Registry，拒绝重定向，大小和 SHA 均受限。安全解包拒绝链接、特殊文件、路径越界、Windows 保留别名、大小写重复及解压膨胀。不会调用 npm、`install.js`、`prepare` 或 `postinstall`。

构建在主人私有临时目录进行，缩短 Windows 路径；archive 缓存和恢复记录留在主人数据目录的 `.live2d-owner-setup`，不进入应用默认 resources 或 Git。bundle 的第三方许可完整写入 banner 和 NOTICE，避免把长许可正文放到 Windows 命令行。Core 继续走原 `install_official`，只记录实际观测 SHA，不编造官方 digest。

新 Core 与 bundle 先在独立目录通过原有 SHA gate，准备完整后再切换。原运行库保留备份；普通错误自动恢复，模拟进程中止可从事务记录恢复。角色目录、模型、密钥及聊天不在写集。安装成功只证明文件和来源门禁通过，实际执行、模型渲染及美术效果另验。

## 已完成的验证

- 真正的 Electron Linux 只读入口：默认 Unicode 用户目录、相对路径覆盖均正确，窗口数 0，后端未启动。报告 `review/owner-runtime-path-native-check.json`。
- 从空缓存实际 HTTPS 下载 15 个锁包，逐 SHA 核实后执行 Linux esbuild，构建 1,183,739-byte bundle；再真实下载官方 Core，完整安装与恢复通过。报告 `review/live2d-owner-setup-fresh-http-check.json`。
- 最终源再次验证缓存、构建、Core 安装与恢复。报告 `review/live2d-owner-setup-smoke.json`。没有把缓存复用称作再次下载。
- Windows 构建器只核固定 SHA 和 PE/AMD64，没有在 Linux 执行 Windows exe。
- 自动测试覆盖许可缺失零副作用、锁/下载损坏、HTTP/解压上限、恶意 tar、原运行库保留、每个切换边界错误/模拟断电恢复、修改后拒绝覆盖、损坏备份保守停止，以及旧 host 不被误启动。

Windows 原生构建、实际 Core 初始化、4060 性能与用户角色质量仍须目标设备验证。Linux 构建与文件安装不是 Windows 绿灯。默认发行没有下载副作用，也没有任何 vendor 二进制或 JS 进入 GitHub。
