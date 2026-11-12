# 来源与许可边界

本仓库没有复制并发布Zerolan、AIRI或SillyTavern的完整源码；设计分析通过链接、固定版本与文件标识引用上游。产品名称属于各自权利人，不构成本项目命名或合作声明。

2026-11-12静态核对：

- ZerolanLiveRobot、zerolan-core、zerolan-data：仓库声明/许可证为MIT。
- ZerolanPlayground：未在已读取的根目录找到独立许可证；Unity、Vuforia、Cubism、DOTween、TriLib与模型素材须分别核对，不从主仓库MIT推导覆盖。
- KonekoMinecraftBot：读取的LICENSE为Apache-2.0；master的package.json写MIT，dev写Apache License。复制或分发前按选定commit解决元数据差异。
- AIRI、Open-LLM-VTuber：主体MIT；角色模型与第三方依赖可能另有条款。
- SillyTavern：AGPL-3.0。研究功能不等于可以无条件把其源码合并进其他许可的产品。
- docs/history/prototype内的原创插图及原型派生截图沿用原型GPL-3.0，附原LICENSE。未复制他人的角色图、声音样本或商业界面截图。

公开仓库可阅读不等于所有素材可商用。新文档的发布不代替上游许可、平台账号授权或第三方模型条款；本次不为未知内容另行授予许可证。

## 启动批次源码

app/复用原GPL-3.0原型；新增src/、tests/、scripts/、desktop/与run.py也按app/LICENSE的GPL-3.0发布。研究索引、引用、模型卡及各外部资产保留各自来源/许可，不因本声明转授权。没有复制Zerolan完整源码或未知AR素材。

## 角色导入与桌面运行依赖

- Pillow 13.0.0 用于实际 PNG 解码、重编码与缩略图。发行元数据标识 MIT-CMU；完整原文见 app/licenses/PILLOW-LICENSE.txt。
- Electron 45.3.1 使用其官方发行运行时；便携包保留其 LICENSE、LICENSES.chromium.html 和原有第三方声明。源码及固定依赖见 desktop/package-lock.json。
- 本地模型、量化权重和声音文件的来源、固定版本及校验和见 app/model-sources.json、app/models-manifest.json 与 app/licenses/。权重不写入 Git，完整离线构建包可另附经过 SHA256 校验的相同文件。
- PNG 测试图由测试代码生成；默认 SVG 是原项目素材。用户自行导入的图片和声音须由用户持有相应使用权限。

上述为实际使用来源记录，不是完整的第三方法律审查或商业发行认证。
