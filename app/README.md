# 本地应用与自助角色

当前开发版本 **0.4.0-dev1**。已实现自助PNG角色、独立角色数据库、外观修订与回退，继续复用文字、语音、记忆和约定。目标是Windows 10/11；目前实际编译验证来自Linux，Windows CI与真机验收待完成。Live2D/VRM导入尚未实现。

## 启动

Windows 10/11 x64用户可在完整源码根目录双击 [`build-windows.cmd`](../build-windows.cmd)，默认准备依赖、编译并验证含模型的离线便携包。操作、Visual C++运行库前置、磁盘副本、日志和验收边界见[Windows本机一键构建](../docs/implementation/windows-local-build.md)。脚本已做语法与部分失败保护检查，尚未在用户Windows电脑实际执行，不能视为已验收安装包。

在仓库根目录、独立Python环境中运行：

```sh
python -m pip install -r app/requirements-core.txt
python run.py --no-browser --port 8765
```

推荐Python 3.12；本轮实际运行环境是Linux/Python 3.12。打开打印的`http://127.0.0.1:8765`。没有模型时仍能管理和导入角色，聊天生成会明确提示安装本地模型或配置模型API。

Windows源码启动可使用已安装的Python环境执行同样命令；该路径尚待Windows CI验证，不是已验收的安装包。

可选本地模型与音色：

```sh
python -m pip install -r app/requirements.txt
python app/download_models.py
```

这会安装可选依赖、联网下载并核验模型SHA256；权重不在源码中。也可通过`COMPANION_MODELS`、`COMPANION_VOICES`复用已有合法资产。设置中的模型API连接由所有角色共用；必要的当前聊天和相关记忆会发送给所选提供方。更换API服务域名时须填写对应新密钥，不能沿用旧服务的密钥。

## 导入自己的角色

1. 打开“角色”，输入名字并创建。新身份有自己的性格、聊天、记忆和约定；在“设置”中调整相处方式。
2. 选择静态形象PNG，可另选说话、眨眼、说话时眨眼图片，然后点击“预览形象”。预览不会立刻替换当前形象。
3. 预览各状态后点击“使用这个形象”。取消保留当前形象；外观列表可重新使用旧修订，达到用户可操作的回退。

单张PNG即可使用，推荐透明背景、sRGB、8bit素材。可选图片尺寸须一致；不支持16bit或动画PNG，也不接受改后缀伪装的文件。当前工程限额：单图4MiB、整组8MiB、单边4096像素、全部状态合计800万像素。这些是本版资源预算，不是画师行业标准。

图片状态由播放/停止等实际状态驱动。它是状态图切换，不是自动把原画绑定成Live2D。上传素材的元数据不会自动成为人格、配音或工具权限。当前只支持静态PNG状态；Cubism运行包、PSD工程、VRM和其他软件专用角色文件都不能当作已支持格式。

同一身份换形象保留关系数据。创建另一个角色不复制旧角色的私聊与记忆。切换、归档或删除会停止旧输出；待提醒约定在切走前会暂停。归档保留数据，可恢复；永久删除与保留至少一个可用角色的规则有明确提示。

当前最多50个角色、每个角色30个外观修订。数量是初始资源限制，角色名字没有固定白名单。当前外观需先换到其他修订后才能删除。浏览器请求断开时可能留下未启用修订，可从列表删除；不能把HTTP中止说成底层处理已停止。

## 桌面壳

桌面壳在`desktop/`，展开与收起复用同一页面。开发启动需安装Node依赖，并让`COMPANION_PYTHON`指向已安装应用依赖的Python解释器：

```sh
cd desktop
npm ci
npm start
```

默认解释器命令是`python3`；Windows环境可设置`COMPANION_PYTHON=python`或明确的解释器路径。桌面壳自行启动一个本机后端，也可用`npm start -- --backend-url=http://127.0.0.1:8765`连接自己已启动的后端。后端地址只允许本机HTTP。

恢复快捷键为`Ctrl+Shift+Space`（macOS映射Command）；鼠标穿透最长60秒会自动恢复。无法注册恢复快捷键时，隐藏入口会拒绝执行，避免角色失联。Linux透明、实际点击穿透与焦点有单独的X11/xfwm4验证；Windows 10/11、其他窗口管理器、混合DPI和全屏游戏仍待真机测试。

只在用户主动申请时询问麦克风授权；摄像头、屏幕采集和任意新窗口未开放。内嵌页面无Node集成，只能调用受限窗口操作。

## 数据与升级

源码默认数据在`app/data`；可用`COMPANION_DATA`指定独立目录。桌面壳默认使用系统用户数据目录中的`profile-data`。不要让两个版本同时写同一个目录。

- `characters.sqlite3`记录角色与外观指针；每个`profiles/<UUID>/companion.db`保存该身份的私有关系数据。
- PNG资产在该身份目录的`assets`下。共享模型连接在根`connection.json`，密钥独立保存在根`api-key`。
- 旧根`companion.db`首次通过SQLite备份迁入第一个角色，原文件保留不改。后续不会重复合并旧版产生的新记录，因此升级前先停止旧进程并保留备份。
- 页面导出/恢复针对当前角色的聊天、记忆、约定与设定，不包含API密钥或完整PNG资产文件。完整数据备份应在停止应用后复制整个数据目录。

删除清理若未完成会返回`cleanup_pending`，保留待清理记录并重试；不承诺磁盘安全擦除。恢复旧备份仍遵守遗忘记录，不能把已删除事实重新引入。

## 当前限制与验证

191项Python、26项Node竞态和15项Chrome检查通过；Linux Electron实际整包另有14项通过。具体范围见[交付记录](../docs/implementation/character-release.md)。真实Linux编译后端已跑本地Qwen/Kokoro，但模型自然度、长期关系效果与用户目标机器资源没有人工验收。

目前没有已核验的Windows安装包。Windows CI、干净Windows启动、声卡/权限、透明/穿透/焦点/多屏与游戏场景须另有结果。Live2D、VRM、云同步、公开角色市场、微信、B站SDK、OBS、AR和MC尚未完成。旧Linux包属于旧版本，不能作为本版Windows交付。

应用代码及原创占位SVG按[GPL-3.0](LICENSE)；依赖/模型另见[许可说明](ATTRIBUTIONS.md)。用户上传素材保留各自权利，不因导入就变成应用开源素材。
