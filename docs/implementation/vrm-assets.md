# 自助 VRM 资产导入

实现：`src/companion_runtime/vrm_assets.py`，由现有 `AssetStore` 延迟调用；不依赖数据库、HTTP、网络、SDK 或固定角色。PNG 导入契约保留。

## 接口

```python
manifest = store.import_vrm(data: bytes, filename="用户角色.vrm", cancel_event=event)
store.get(manifest["id"])
store.resolve(manifest["id"], "model.vrm")
store.list_assets()
store.delete(manifest["id"])
```

每次导入生成新的 UUID 修订。导入只是预览，不选择角色或修改关系数据。所有校验、规范化、临时文件写入完成后才原子改名发布；失败或提交前取消清理临时目录，保留旧修订。删除的引用检查仍由角色层负责；库层沿用原子撤下与 `cleanup_pending`。

HTTP 约定（由 server 集成）：既有 `POST /api/characters/assets/import`，请求 `{character_id,format:"vrm",model:{filename,data_base64}}`。64 MiB 原始文件的 base64 约 85.34 MiB，路由必须独立设有界请求限制并预先检查解码长度。服务端为 `manifest.model.resource` 加受鉴权的 `model.url`，资源 MIME 为 `model/gltf-binary`，不使用上传文件名构造路径。

清单保留 `schema_version:1`，`format:"vrm"`、`vrm_version:"0"|"1"`、`states:{}`、`model:{resource:"model.vrm",bytes,sha256,mime}` 与通用 `thumbnail.png`。`metadata:{name,authors,license_url}` 只是有长度限制的文本；不能插入 HTML 或自动访问链接。显示名最多120字符，作者最多16个/各80字符，许可字段最多512字符。不会凭元数据自动认定素材授权。

`capabilities` 声明 `model_3d`、已识别的标准 `expressions`、口型/眨眼有无。它不承诺美术质量或绑定正确。`budgets` 记录纹理像素、RGBA 解码字节数、非纹理 BIN、展开 accessor 字节数、顶点、批次与图片数。

## 当前接受范围与工程限额

| 项目 | 限制 |
| --- | --- |
| 容器 | GLB v2，严格 JSON 后接单个 BIN，长度/对齐/填充正确；拒绝 ZIP、文本 glTF、附加块 |
| VRM | `VRM` 0.0 或 `VRMC_vrm` 1.0，二者只能一个；15个标准必需骨骼及引用检查 |
| 文件 / JSON | 输入与规范化模型各≤64 MiB；JSON≤4 MiB；嵌套≤48层 |
| bufferViews | ≤8192；重复/重叠引用展开合计≤60 MiB；单 BIN；所有资源 `uri`（包括 data URI）拒绝 |
| 几何 | 非纹理 bufferViews 合计≤48 MiB，展开 accessor≤96 MiB，≤200万顶点、512绘制批次；节点实例展开后也须符合顶点/批次限制 |
| 对象 | ≤4096节点、8192 accessors、512 meshes、256 materials、256 skins、1024 joints/skin |
| 纹理 | ≤32张；真实静态 PNG/JPEG；边长≤4096；全部图片合计≤3200万像素，即≤128,000,000 RGBA 字节 |
| 形变 | 每 primitive≤128个 morph；严格检查 accessor 范围、维度、引用与 sparse 索引 |
| 路径 | 只发布受控 `model.vrm`、`thumbnail.png`；无远程纹理、任意文件或用户路径 |

这些是应用初始工程限额，不是 VRM 标准或画师制作规范。32张图片上限来自官方样例实际包含19张图，不能把16张当通用规范。总像素限额包含模型缩略图及未被材质引用的内嵌图片。

明确支持的扩展列在代码 `SUPPORTED_EXTENSIONS`：VRM0、VRMC_vrm、SpringBone、NodeConstraint、MToon/HDR emissive 以及本地渲染器可读的 KHR 材质/纹理变换扩展。VRMC 版本仅接受明确的1.0或部分1.0-beta；VRMC_vrm本体只接受1.0。拒绝未知扩展、Draco、meshopt、KTX/Basis等需要额外解码器的压缩资源。此版本只接受三角网格、float POSITION、32bit矩阵、标准属性类型；未提供 bufferView 且没有 sparse 的零初始化 accessor 也暂不接受。动画≤100万采样关键帧，时间使用紧凑非sparse accessor且必须非负递增，输出维度与目标匹配。合法但超出此接受范围的文件会清晰失败，不称全 VRM 兼容。

浮点 accessor 内容必须有限，JSON 拒绝 NaN/Infinity、超 float32 数值及超浏览器精确范围整数。检查 buffer/accessor/sparse 字节跨度、真实网格索引、节点树环与重复父节点、骨骼、皮肤、场景、动画、表情、春骨和约束引用；约束依赖环拒绝。没有执行或加载上传脚本的入口。

## 规范化和性能

所有图片真实解码并从像素重新编码成 PNG，移除 EXIF/ICC/文本。PNG 的所有块先验 CRC，丢弃可选元数据后再交 Pillow，避免仅显示纹理却解压任意文本。拒绝16bit PNG和动画纹理。图片 bufferView 必须独立，不能被几何 accessor 复用。重新对齐、打包所有 bufferViews 并重写偏移和 BIN 长度，删除未引用 BIN 尾部和所有 glTF `extras`，保留 VRM 本体的许可等数据。因此交付模型的 hash/bytes 是规范化版本，可能与原文件不同；源图 JPEG 转 PNG 后可能变大并因64 MiB限制被拒绝。

同一个库串行导入；图像逐张解码，不同时持有所有纹理的 RGBA。128 MB纹理和96 MiB accessor是逻辑资源预算，**不等于进程 RSS 硬上限或 GPU 全部开销**。Python/JSON/原文件/HTTP base64/解码临时副本和渲染器还会占内存。候选导入附加内存预算为768 MiB，需在目标 Windows 与边界样本测量，当前没有 OS 级硬内存隔离；服务器须限制并发上传。取消在各阶段和批次循环间检查，不保证 Pillow 当前一张图解码即时中断。

2026-11-12 云端 Linux 单次官方样例导入：2.722秒，进程峰值118,208 KiB；19图、22,347,776像素、4,305,920几何字节、24,951顶点、13批次；规范化模型9,381,964字节。此为单次测试、非p95、非Windows/GPU验收，不代表边界峰值或图形质量达标。

另做自造接近总像素上限样本：两张纯色4096×4096与4096×3700 PNG，31,932,416像素，127,729,664逻辑RGBA字节；导入1.309秒，含夹具生成的进程峰值279,484 KiB。它验证像素这一维的边界，不包含最大64 MiB输入、最大JSON/几何和HTTP base64同时叠加的最坏情况。

## 已执行与待验证

- 自造两份不同 VRM0/1 GLB，PNG/JPEG真实解码/元数据去除、合法 sparse morph/索引/表情、统一 PNG/VRM 库和缩略图/资源枚举通过。
- 伪格式、截断、越界、外部/data URI、未知扩展、真实 NaN、坏 CRC、超纹理、节点/约束环、骨架/表情越界、磁盘失败、发布失败、取消回滚测试通过。
- 本模块测试19项与原 PNG24项共43项通过；独立 QA 另造两个有皮肤/表情的不同 VRM0/1 样本并完成导入，不等于最终美术质量。
- pixiv/three-vrm 官方 `VRM1_Constraint_Twist_Sample.vrm` 真实导入通过；其来源/授权由前端研究记录管理，不作为用户默认角色，不放入此测试源码。
- HTTP鉴权/角色绑定、真实 WebGL、播放口型/隐藏/恢复/资源释放、目标Windows峰值与帧率由集成层验收，不能用资产单元测试替代。
- 尚无完整 glTF Validator 认证、格式模糊测试覆盖或隔离解码进程；损坏素材仍涉及 Pillow/浏览器原生解码器的第三方实现边界。

官方参考（实际读取，2026-11-12）：[Khronos glTF 2.0 specification](https://github.com/KhronosGroup/glTF/blob/main/specification/2.0/Specification.adoc)、[VRM1 schema](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/schema/VRMC_vrm.schema.json)、[VRM0 schema](https://github.com/vrm-c/vrm-specification/blob/master/specification/0.0/schema/vrm.schema.json)。这里依据容器与资源规范实现受限接受范围，未声称完整验证上述所有 schema。
