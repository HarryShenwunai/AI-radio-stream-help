# 原创 Live2D 制作工具链调查与实测

查阅与实测：2026-11-12。完整原创模型与四张 PNG 状态图是不同交付物。

## 已核实的结论

Linux 上可以通过开源 PSD2Live 生成真实 `.cmo3`、`.moc3`、`.model3.json`、
纹理、物理、表情与动作文件。官方 Cubism Editor 不是该生成链的必经工具。
这条结论已有原创几何分层素材和真实 Cubism Core 验证，不再仅依据 README。

工具链成立不代表用户角色的美术已经完成。用户要求的手指、独立杯子、空手
遮挡补画及自然动作，需要真实独立原画和相应关键形。四张整图不能替代它们。

| 分类 | 判断 | 依据 |
|---|---|---|
| 已核实事实 | 当前本机有 OpenJDK 21.0.13，未找到官方 Editor、Wine、现成目标 PSD/CMO3 | 本机命令与文件清单；未声称搜索了不可访问文件 |
| 已核实事实 | 官方 Editor 下载与系统要求列 Windows、macOS，没有 Linux 发行项 | 官方下载页与系统要求页，见文末 |
| 已核实事实 | PSD2Live 3.6.7 的无窗口 CLI 与 MCP 可在本机运行 | 真实 `--help`、PSD 导出、项目保存和 API schema 查询 |
| 已核实事实 | 原创几何 v2 导出的 MOC3 被真实 Core 接受，眼嘴有可见像素变化 | 独立 QA 报告 `review/original-live2d-core-v2.json` |
| 可信但须逐项验证 | Umamo 支持 CMO3/MOC3 与无窗口转换 | 固定源码与作者文档；本轮未运行 Umamo 二进制 |
| 推断 | 同一生成器可复用到高质量原画层 | 须逐角色检查画面、遮挡、运动和实际运行成本 |
| 未知 | 输出 CMO3 在指定版本官方 Editor 中完整往返编辑的效果 | 本轮未安装官方 Editor，不能以自身读回代替官方实测 |

## 官方工具与许可边界

官方系统要求当前列出 Windows 10/11 64 位桌面模式、macOS 13/14/15/26。
网页列出的 Windows 要求包含约 1 GB 可用空间、OpenGL 3.3，推荐 4.5。
这不是 Linux Java/Wine 兼容性声明。Java 已安装也不能证明官方 Editor 可运行。
本轮没有安装 Wine、下载官方 Editor 或尝试移植其组件。

官方 Editor EULA 原文规定：

> By checking the box ... clicking “accept” or by downloading, installing or using
> the Software ... you ... accept all of its terms.

因此，本轮只读取网页，没有用“先下载看看”代替用户的 Editor 许可决定。
此前对 Core/Framework 的本机评估授权不能自动扩展为新的 Editor 条款授权。
Editor EULA 还单列修改、逆向、规避授权和组件拆分限制；它们不能作为寻找
未授权绕过方式的理由。本轮执行的是开源程序自己的写出路径，不依赖破解 Editor。

SDK/Core 的运行与发布许可、原画素材权利是另外的边界。本轮原始 Core 检查
沿用用户已授权的本机项目评估；不据此声明公开发行或商业许可已完成。
PSD2Live 工具整体使用 GPL-3.0，部分模块 MIT。开发工具的许可不能直接被
写成“生成的全部原画自动为 GPL”或“全部输出均可无限商用”的法律结论。

## 两条可执行路线

| 路线 | 已检查能力 | 优势 | 局限与成本 |
|---|---|---|---|
| 官方 Editor，Windows/macOS | 官方 PSD→建模→MOC3/动作导出文档 | 官方编辑和校验路径 | 需用户对应设备与许可；本轮不安装、不报价、不假称 Linux 已支持 |
| PSD2Live 3.6.7，Linux Java 21 | 真 CLI 导出、MCP 编辑、项目归档、Core 验收 | 当前环境可运行；已有原画层可编程绑定和保存历史 | 自动生成不是美术验收；必须检查版本差、坐标单位、遮挡与最终目标 Core |
| Umamo 0.5.0，Linux | 源码中的 CMO3/MOC3 编解码与 CLI 转换、Oracle 测试 | 可独立编辑与格式互通 | 作者标明 alpha；README 明确动画编辑尚未实现；本轮未运行 |

PSD2Live 是本轮实际跑通的开发工具。没有购买服务或把工具二进制加入应用。

## 版本、资源与真实产物

选定 `tsunehimatoi/psd2live` 的 `v3.6.7`，发布于 2026-10-24。
对应源码 tree 为 `bfadd8343774d5b6208146060c4fa175d84a0f4f`。
Linux x64 归档 107,406,792 字节，SHA256：

`ac788290387ca5b373d445f9f879185de3b4102373487b389e3adab0e433b686`

只解出 `lib/app` 的 120 个普通文件，共 93,330,537 字节，使用现有系统 Java。
没有系统安装，没有执行捆绑 JRE。可重新下载的 107 MB 压缩包在校验并记录
各已安装文件 SHA 后删除，以节省当前磁盘；收据在私有 `.build` 调查目录。
不能把解压路径称为新的官方 Editor 安装。

18 个原创几何 PNG 层经本项目 PSD 容器写出器生成 RGB/8-bit、真独立层 PSD。
PSD2Live 实际输出 `.cmo3`、`.can3`、MOC3 v5、`model3.json`、1024 纹理、
`physics3.json`、4 个 motion3、4 个 exp3 与显示信息。未换皮官方模型。

独立 v2 检查包含：Core 一致性、20 个参数真实顶点、可见眼嘴像素、物理、
表情、动作和无操作负控。其 20 个参数包含头 XYZ、身体 XYZ/Lean、比例、
双眼开合、眼珠 XY/Form、双眉 Y、嘴 Open/Form、呼吸和前后发摆动。
这套几何图仅是工具验证材料，不是用户角色，不进入默认角色或发布包。

## 制作与保存接口

`scripts/avatar_live2d_source.py pack` 接受真实独立 PNG 图层清单：

```json
{
  "format": "original-live2d-layers-v1",
  "canvas": {"width": 1536, "height": 2048},
  "layers": [
    {"name": "back hair", "file": "layers/back-hair.png", "x": 0, "y": 0},
    {"name": "topwear", "file": "layers/body.png", "x": 0, "y": 0},
    {"name": "face", "file": "layers/face.png", "x": 0, "y": 0}
  ]
}
```

数组按底到顶排列。原 PNG 不被修改；PSD 层位置保留原像素，透明边缘可以
通过图层坐标裁边。输入不能是把四幅完整状态图冒充独立拆件的清单。

```bash
python scripts/avatar_live2d_source.py pack --layers layers.json --output source/character.psd
python scripts/avatar_live2d_source.py export --input source/character.psd --output export-r1 --atlas 4096 --mesh-spacing 40
```

CLI 导出的 `*.psd2live.json` 是诊断记录，修改它不会修改模型。
MCP 可以真实导入 PSD、修改源角色、关键形、剪切蒙版和层级，再通过
`project_save_as` 保存包含原始素材与历史的 `.psd2live` 归档。
随后用 `project_export_model` 重新生成 CMO3/MOC3 文件族。

本轮已实际查询 `layer_classify`、`rig_generate`、`parameter_create/update`、
`keyform_apply`、`rig_deform`、`author_axis`、`rig_edit_structure`、`canvas_warp`、
`canvas_rotation`、`physics_put`、`motion_put`、`expression_put` 的完整 schema。
`scripts/avatar_live2d_recipe.py` 只编排这类声明式操作，不接收绘画、脚本或 shell 步骤。
外部 GPL MCP 客户端作为显式开发依赖传入，未并入应用运行代码。

## 实际反例与必须保留的校验门

1. PSD v1 写出器最初把编辑图层倒序。合并预览正确、MOC 顶点在动，但后发
   挡住眼口。独立像素门抓到眼嘴变化为零；修为 PSD 底层先存后，v2 才通过。
   合并预览、参数数量和隐藏顶点运动均不能证明有效角色。
2. 当前源码 master 已支持上/下唇别名，3.6.7 release 未支持这些专名。生产
   命名与分类须按实际运行版本，不能把 master 文档套在旧二进制上。
   `topwear`、`upper teeth` 可识别；`body`、`teeth` 在该 release 未识别。
3. `layer_classify` 的待生成分类须经 `rig_generate` 才落实到绑定树。
4. `rig_deform.translate` 的 delta 是当前目标局部包围盒宽/高的比例，
   不是画布像素。selectors 也使用归一化 rest domain。错误输入 10 会移动
   十个目标高度。r3-mouth-r1 因此被真实截图否决，不能作为可用源修订。
5. 修正关键形前须读取静止顶点，做 ±0.01 小量、真实 Core 顶点与坐标标定，
   再验证嘴 ROI、眼 ROI、头部端点和无操作负控。仅“大于零像素”不充分。
6. PSD2Live 的显示信息使用 `Drawables`。本应用已严格支持该有界 Id/Name
   元数据字段，保留其他未知字段拒绝；原始导出物没有为迁就导入器而改写。

### 已实测的位移标定与口部反例

独立 Core 量测记录在
`review/original-character-live2d-lip-unit-measurements.json`：画布 1536×2048、
PPU 1536，单独对上唇 `ArtMeshLayer3` 输入 ±0.01 局部高度，实际画布 Y
移动约 -0.20195 / +0.20742 像素；其他网格变化严格为零。Core Y 正向与画布
向下的 Y 相反。中点对称误差最大约 0.02369 源像素，未通过严格 1e-6 Core
单位对称门，因此没有宣称精确对称。

`author_axis` 会从默认姿态/已有关键形建立非默认形；不能假设先修改默认形、
再输入逆平移就一定恢复源图位置。r3-mouth-r2 的实际 Core 测量显示，上唇
native Y 最小约 694.53，neutral 约 704.28，而 Open=1 约 684.84，已经越过
native 反向移动。完整对照在
`review/original-character-live2d-original-mouth-registration.json`。
口部 ROI 技术门通过仍不代表轮廓自然贴合。r2 的 Open=1/Form=0 真实网格
边缘间隙上/下唇为 3.59 / 2.39 源像素；先前 6–9 像素是轮廓中心距目测，
已撤回，不能据此大幅过调。该边缘量测也不包含纹理 alpha，仍须看实际渲染。

后续注册修订另存工程、保留 r1/r2 红证据。声明式 recipe 已真实执行
`project_open → rig_deform → project_save_as → project_export_model`，不覆盖
先前原画、冻结导出目录或坏例证据；尚未艺术接受的导出不标为角色成品。

独立手杯绑定中，`canvas_rotation` 的 pivot 是画布像素、angle 为角度制；
`preservePose` 的同版源码负责把子图层变换到新父空间。多图层创建旋转要求
当前父级一致。`object_edit_appearance` 的 mesh `bind` 使用 `space=canvas`
保留默认位置，`space=local` 会改变继承外观。二者不能混用。

用户角色 r3 仍只用于脸部调试，合并的手杯身体不能满足独立手、手指和杯子。
后续源原画与绑定修订仍须独立验收，不因几何 fixture 通过而宣称完工。

## 一手来源（访问日均为 2026-11-12）

- 官方下载：https://www.live2d.com/en/cubism/download/editor/
- 官方系统要求：https://www.live2d.com/en/cubism/download/spec/
- 官方 Editor EULA：https://www.live2d.com/eula/live2D-editor-software-license-agreement_en.html
- 官方导出说明：https://docs.live2d.com/en/cubism-editor-manual/export-moc3-motion3-files/
- PSD2Live 固定 release：https://github.com/tsunehimatoi/psd2live/releases/tag/v3.6.7
- 同版开发/CLI：https://github.com/tsunehimatoi/psd2live/blob/v3.6.7/docs/zh/guide/DEVELOPMENT.md
- 同版 MCP：https://github.com/tsunehimatoi/psd2live/blob/v3.6.7/docs/zh/agent/MCP_AUTHORING.md
- 同版坐标变形实现：https://github.com/tsunehimatoi/psd2live/blob/v3.6.7/src/main/kotlin/io/github/psd2live/core/RigGeometryTools.kt
- 同版 PSD 层顺序实现：https://github.com/tsunehimatoi/psd2live/blob/v3.6.7/umamo/src/main/kotlin/org/umamo/format/psd/PsdReader.kt
- Umamo 固定源码：https://github.com/umamoorg/umamo/tree/ca16e9445cc04bf736d505c72aaa8a75f7b1172a
