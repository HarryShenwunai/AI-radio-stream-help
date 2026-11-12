# PNG状态素材库

实现：`src/companion_runtime/assets.py`。这是独立的本地素材层，不决定当前角色、不读取聊天数据库，也不发起网络请求。

## API

- `AssetStore(root).import_png_states(states, filenames=None, *, cancel_event=None)`：`states`为状态名到PNG字节的映射。返回新资产清单，不自动启用。
- `get(asset_id)`：读取并检查资产清单和资源存在性，返回新对象。
- `resolve(asset_id, resource)`：只返回该资产已登记的PNG/缩略图路径。清单本身不作为可公开资源。
- `list_assets()`：列出有效资产，跳过暂存、待清理和损坏目录。
- `delete(asset_id)`：调用方先确认资产没有被角色引用；返回`id/deleted/cleanup_pending`。
- `AssetError(message, status=400)`：提供可显示的中文错误和HTTP状态建议，不返回本机绝对路径。

`idle`必需；`talk`、`blink`、`talk_blink`可选。同一资产内状态画布必须一致。新导入总是生成新UUID修订，不覆盖已有资产；启用/回退属于角色层事务。

清单包含`id/schema_version/format/created_at/width/height/total_pixels/total_bytes`，`states`按状态记录`resource/width/height/bytes/sha256`；`thumbnail`使用同样描述；`capabilities`明确当前有哪些状态。原上传文件名不写入清单。

## 支持和初始预算

- 接受静态PNG，规范化为RGBA8；RGB、RGBA、调色板透明图片实际测试通过。
- APNG、16bit图片明确拒绝；不静默将16bit色值裁切。其他渲染器/Live2D不由此模块实现。
- 每张编码数据≤4MiB，上传合计≤8MiB；规范化后的状态和缩略图也合计≤8MiB。
- 每条边≤4096px，全部状态合计≤800万像素；缩略图最长边≤256px。
- 这些是应用初始限额，不是画师或PNG行业统一标准，目标设备验证后可调整。

先检查PNG签名、块边界和每个块CRC，再移除非绘制元数据，避免只为显示角色而解压大段文字/ICC/EXIF。Pillow实际verify及load检查像素内容；最终图和缩略图重新生成，不保留上传元数据。

根目录下暂存完整文件，最后原子重命名为UUID目录。失败/取消不会发布半成品，旧资产不改写。取消在预检、每次解码后与发布前检查；不能中断Pillow正在执行的一次解码。临时清理失败会明确报错；素材不可当已安装版本使用。

删除先原子移出可见资产命名空间，再清文件。文件被占用导致物理清理失败时，`cleanup_pending=true`并保留隐藏垃圾目录；该资产不再可resolve。当前未提供后台垃圾清理任务，也未承诺文件系统断电后的fsync级持久性。

路径只来自库生成的UUID与固定资源名。目录/资源符号链接、清单中伪造资源路径、未知资源名均拒绝。安全前提是素材根目录与应用进程由同一本机用户控制；没有试图防御拥有同一文件系统写权限的并发恶意进程。HTTP认证、角色归属、总库磁盘配额与生命周期由应用集成层负责。

## 实际验证

运行：

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_assets.py -v
```

本轮24项通过，约0.088秒，使用已安装Pillow13.0.0、临时文件系统和自造无人物PNG。涵盖两套不同画幅/名字、四状态、透明和调色板、元数据清除、CRC/截断/伪格式/坏压缩内容、像素/编码预算、原子失败清理、取消、遍历/符号链接、清单篡改、删除待清理、双实例共享锁。

这个耗时是小合成夹具的一次单元测试运行，不是实际角色导入p95、内存基准或UI验收。没有下载Pillow、第三方角色或SDK；没有修改服务器、UI、依赖清单、项目交接或执行Git提交。

本轮交接注意：上传HTTP被中止不代表服务端解码已停止；可用`cancel_event`做协作式取消，集成仍须丢弃迟到预览并避免自动启用。图片元数据先剥除再解码，16bit明确不支持；删除后文件锁清理失败用`cleanup_pending`报告。
