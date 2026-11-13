# Windows 本机一键构建

用户已确认可以使用自己的 Windows 电脑。当前云端 GitHub Actions 因账户计费锁定未分配 runner；本机脚本不修改或绕过账户设置。

## 操作

1. 将完整源码解压到可写的较短本机路径，例如 `C:\AI\companion-source`。不要只下载单个脚本。
2. 双击根目录 `build-windows.cmd`。首次会联网下载构建依赖和数 GB 模型；保留窗口，检查真实测试结果。
3. 成功时会打开 `.build/windows-local/releases/<时间>/`，其中包含完整 ZIP、SHA256 和解压后的程序文件夹。运行该文件夹里的 `companion-desktop.exe`，或完整解压 ZIP 后运行。不要单独移出 EXE。

依赖、缓存、测试临时数据、截图、日志和成品都放在项目 `.build`。失败时窗口保留错误，日志位于 `.build/windows-local/logs`；不会把未通过构建称为成功。脚本不会连接真实账号、上传私聊或部署。

模型会同时存在于下载缓存、解压后的便携目录和最终ZIP，构建依赖及中间目录还会额外占空间；不要只按模型下载大小预留磁盘。重复执行会保留旧发布目录，新的构建使用新的时间目录；确认不再需要后可手动删除旧的`.build/windows-local/releases/<时间>`，不要误删自己的用户数据目录。

## 真实前置条件

- Windows 10/11 **x64**、64位 PowerShell 5.1 或更高版本、可访问官方工具/PyPI/npm/模型源的网络，以及足够容纳依赖、模型、解压目录和 ZIP 的磁盘空间。模型测试需要数 GiB 内存；Windows占用和延迟以实际报告为准。
- 脚本优先使用已有 x64 Python 3.11/3.12；检测到3.10会自动准备项目内3.12，因为固定 Pillow13要求 `>=3.11`，Misaki要求 `<3.13`。缺少兼容 Python 时，使用校验过的 uv 下载 **Astral python-build-standalone CPython**，并非 python.org 安装器。
- 已有 x64 Node.js `>=22`可复用；否则下载官方 Node22便携 ZIP。工具URL、版本、官方SHA256及查询来源固定在 `scripts/windows-build-tools.json`。
- **Visual C++ x64运行库可能仍是前置条件。** 官方 llama.cpp、ONNX Runtime、eSpeak DLL依赖 `MSVCP140.dll`、`MSVCP140_1.dll`、`VCOMP140.dll` 等。脚本安装Python依赖后实际导入原生模块；缺DLL时会停止并给出[微软官方说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。不会静默安装系统运行库、请求管理员权限或修改系统配置。用户如需安装该前置，应自行按微软说明处理。

`build-windows.cmd`的ExecutionPolicy参数仅作用于本次PowerShell进程，不调用`Set-ExecutionPolicy`。uv显式使用`--no-registry --no-bin`，不登记Windows注册表、不修改系统或用户PATH；托管Python、缓存和bin目录均在`.build`。脚本不下载并直接执行未校验安装器，不使用`irm | iex`。

## 构建和验收流程

脚本先校验官方 llama-cpp-python0.3.36 `py3-none-win_amd64` CPU wheel的SHA256并安装，再安装固定项目依赖；禁止为llama-cpp-python退回源码编译，因而不强制安装Visual Studio编译工具。原生模块导入通过后，依次执行Python回归、前端/桌面策略测试、PyInstaller编译、编译后HTTP/PNG/隔离/重启检查、Electron便携组装和真实桌面程序检查。

默认继续执行仓库已有 `app/download_models.py` 的原样副本，校验既定三个模型资产SHA256；缓存放在`.build/windows-local/model-assets`。将模型加入成品后，真实执行本地LLM、Kokoro语音和取消检查；此时Electron已退出，避免两项高内存验证并发。依赖许可文本和实际版本清单附带在包中，缺失许可文件仍在inventory明确列出，不能由“采集完成”推导“许可已齐全”。

最后使用支持大于2GiB模型文件的Python ZIP64打包，并输出ZIP的SHA256、源文件哈希和构建报告。有Git工作副本时记录提交与是否有本地修改；源码ZIP没有Git元数据时提交值留空，以实际源文件哈希为依据。程序未做代码签名，不会修改Windows安全策略。

高级用户可运行 `build-windows.cmd -WithoutModels`，生成不含模型的运行包；该选项不会验收真实离线推理/语音。`-NoOpen`只关闭成功后自动打开输出文件夹的行为。

## 当前证据边界

本机云端Linux已使用官方校验的PowerShell7.5.4解析该脚本，并实际测试子进程成功、非零退出、无法启动时不会沿用旧成功退出码。这不是Windows执行结果，也不证明WindowsPowerShell5.1和用户电脑已经通过。脚本里的真实Windows、DLL、模型和语音检查必须在用户电脑执行后，以生成报告判断。

原有Linux/Chrome通过记录不会替代Windows10/11真机、显卡、多屏DPI、全屏游戏、性能或人声体验验收。
