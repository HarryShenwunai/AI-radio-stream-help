# 自助 Live2D 运行包导入

已实现 `AssetStore.import_live2d(zip_bytes, filename=None, *, cancel_event=None)`，复用 UUID 修订、预览后启用、统一 `get/list_assets/resolve/delete`。不下载或捆绑 Cubism SDK/Core，不购买许可，不安装固定角色；未执行真实 Core 播放。

HTTP 使用既有导入路由，`{character_id,format:"live2d",model:{filename:"角色.zip",data_base64}}`。返回 `format:"live2d"`、`states:{}`、`model:{resource:"model.model3.json",model3json:"model.model3.json",mime,bytes,sha256}`、`resources:{受控资源名:{resource,mime,bytes,sha256}}`、通用缩略图、纹理预算与能力信息。服务端给 model/resources 加同角色鉴权 URL。model3.json 内引用重写为平面的 `r0001.moc3/r0002.png/...`，不保留用户路径。

**相对 URL 会丢失 `?character_id`。** 渲染器必须使用 `resources` 的完整同源 URL，或仅在运行时重写 FileReferences。不得开放跨角色资源访问来解决这个问题。

| 边界 | 当前工程限额 / 行为 |
| --- | --- |
| ZIP | ≤64 MiB、≤256条、仅 stored/deflate、无加密；声明展开总≤96 MiB、每项≤32 MiB、逐项压缩比≤200 |
| 路径 | 拒绝绝对路径、网址、反斜线、`..`、空段、Windows保留名、尾点/空格、Unicode规范化或大小写重名、符号链接/非普通文件、文件/目录冲突 |
| 根目录 | 只有一个 `.model3.json`（也支持通用名 `model3.json`）；引用须在它所在目录内且真实存在；从不解压到用户指定路径 |
| JSON | 每份≤2 MiB、包内合计≤8 MiB、嵌套≤32；拒重复键、NaN/Infinity、脚本/URI字段、未知结构 |
| 资源 | 最多96个；Moc、Textures、Motions、Expressions、Physics、DisplayInfo、Pose；模型UserData、动作Sound和动作事件自动剔除，不执行/不发布；MotionSync暂不支持 |
| 纹理 | 真正静态PNG/JPEG，≤32张、边长≤4096、累计≤3200万像素（128,000,000逻辑RGBA字节）；PNG先查CRC，全部从像素转PNG并移除文本/EXIF/ICC |
| 动作/表情 | ≤32动作组/64动作/32表情；曲线分段/计数、类型、数值范围校验；时间保持单调，导出Duration舍入容差≤10ms且≤1帧；无字符串脚本或事件消费者 |
| 物理 | ≤256设置、4096总顶点、每设置≤256输入/输出；检查顶点索引、计数、参数类型及归一化范围 |
| 附带声明 | 最多8份/总512 KiB UTF-8 LICENSE/LICENCE/NOTICE/COPYING作为 `rXXXX.notice.txt` 私有普通文本保留，不能按HTML解释；其存在不表示授权成立 |

ZIP每个普通条目都实际有界读取并检查CRC；只发布校验后的模型、实际支持的引用资源与明确许可文本。未引用的图片、说明或源路径不公开。脚本、HTML、DLL/EXE/WASM、嵌套ZIP和源工程文件拒绝。常见官方包附带的WAV/MP3/OGG/M4A/FLAC和userdata3.json可留在上传归档中，受同一ZIP预算/CRC/JSON检查，但不会解码、播放或存入发布目录；Sound/UserData引用仍先检查路径/类型，不能用将被剔除为由绕过网址、绝对路径或`..`检查。模型和动作JSON删除这些引用/事件及事件计数，manifest.warnings明确“动作音频/事件未导入，语音由应用提供”，不宣称原样保留全部功能。

显示文本允许合法Unicode Zs空格（如日文名称的U+3000），继续拒控制/格式字符、CRLF和孤立surrogate；避免把官方`左目　開閉`误判成坏名称。写入只发生在私有 staging，成功后原子发布；失败/提交前取消回滚且保留旧资产。删除仍须角色层先确认无引用。

MOC3 **只检查文件头包络**（`MOC3` magic、至少64字节、当前识别的1–6头修订码和字节序标志），不宣称解析了二进制内部数组、参数、顶点、版本兼容或安全性。标签为“header revision”，不能据此断言某 Cubism Editor/Core 版本可播放。所有清单固定保留 `core_verified:false`、`runtime.core_consistency_verified:false`、`license_verified:false`。合成测试MOC3只是包络，绝非可播放模型。

渲染必须保留三道门：用户合法提供匹配的Core；Core真实一致性/版本检查通过；用户有权使用模型与相应应用分发许可适用。Core不可用或模型不一致时清晰失败，不能用通用缩略图冒充动态预览成功。不应把用户上传Core JS当模型包内脚本执行。

文件与纹理预算不等于 RSS/GPU 硬上限：ZIP源、base64、JSON和解码副本、Core展开的MOC数据会额外占用内存。库内同根串行导入，逐张解码；真实Core的展开大小、空闲/运动帧率、销毁释放与目标Windows额外RSS必须单独验收，当前尚无这些结果。

已执行16项自造包测试，与原PNG24项、VRM19项共59项通过。涵盖两份不同结构包、重写引用、纹理真解码/metadata剥离、许可文本保留、路径/重名/链接、CRC/截断/压缩比、坏MOC头、未知字段/URL/脚本、动作计数、物理越界、超纹理、磁盘/发布失败/取消回滚/删除。复核官方文档后补测exp3/pose3可省略Version、motion可省略Loop以及cdi3的ArtMeshes/CombinedParameters；另测自动剔除Sound/UserData/events、Unicode Zs、严格有界的导出时间舍入容差。这批资产测试没有下载第三方模型、SDK或Core，也没有以包络测试宣称真实播放、授权确认或最终画质验收。前端单独获得许可进行的SDK/官方模型评估记录由其测试报告管理，不属于上述单元测试结论。

实际读取的官方格式资料（2026-11-12）：[CubismSpecs model3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/model3.json.md)、[motion3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/motion3.json.md)、[exp3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/exp3.json.md)、[physics3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/physics3.json.md)、[cdi3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/cdi3.json.md)、[pose3](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/pose3.json.md)。实现为上述格式的受限接受范围，不是完整兼容或官方认证。
