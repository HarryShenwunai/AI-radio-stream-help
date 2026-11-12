# 自助 VRM 三维舞台

2026-11-12。现有 PNG 状态图、角色身份和声音拥有者继续使用；VRM 是新增的外观格式，未替代 Live2D 的独立许可和集成要求。

## 实现

- `frontend/renderer.mjs` 是渲染源，`frontend/package-lock.json` 固定依赖树。Three.js **0.180.0**、`@pixiv/three-vrm` **3.5.5**、esbuild **0.25.12**。运行 `npm ci --prefix frontend --ignore-scripts` 后 `npm --prefix frontend run build`，生成本机 `/vrm-renderer.js`。产品不访问 CDN、不加载角色脚本、不要求 `unsafe-eval`。
- 类型选择 VRM，上传 `.vrm`，后端检查/重编码并存为未启用修订。真实 WebGL 预览加载成功后才允许预览面板的确认按钮；确认启用沿原有角色资产接口。旧修订可再次使用；角色关系不随换皮复制或清除。
- 渲染器仅从同源 `/api/assets/…` 取已检查模型，纹理来自模型内 bufferView。使用 `TextureLoader` 让内嵌图片在既有 `img-src blob:` 下显示，避免隐含 `fetch(blob:)` 要求放宽 `connect-src`。模型许可 URL 作为纯文本资料，不加载网络内容。
- 透明 RGBA、抗锯齿、sRGB 输出与 ACES 色调映射，半身取景、舞台缩放、主/补/背光和半球环境光。VRM0 坐标转换；VRM0/1 交由固定版本的官方加载插件处理。用户提供的模型材质、拓扑与授权决定最终美术上限，官方兼容样例不代表参考图质量达成。
- 微幅呼吸/头部活动、视线跟随与自然间隔眨眼属于待机动作，不伪造角色心情。`aa` 表情在本机真实 Audio 播放期间由 WebAudio 时域 RMS 驱动；浏览器系统语音无法取得原始音频，仅在真实开始/结束事件期间作声音活动近似。两者都不是音素级口型，也不是面捕。
- 小窗默认30、展开60 fps上限，可选小窗20/30、展开30/60。帧率是调度上限，并非硬件实测保证。DPR最大2，最大边2048渲染像素；不启用实时阴影、后处理或追踪硬件。
- 停声归零口型并断开分析节点；隐藏/退出/换身份释放舞台几何、材质、纹理、WebGL上下文、声音分析与请求。预览退出角色页或隐藏时同样释放，重新进入重载。旧加载完成会被序列检查丢弃和释放。WebGL上下文丢失显示可恢复提示，重新加载先停声，防关闭分析上下文后复用同一音频元素。

## 已运行与边界

- 真实 Chrome 使用完整上传→服务器检查→WebGL预览→启用→舞台出图。实际查看 `/workspace/dist/vrm-initial-preview.png`、`vrm-initial-stage.png`：模型可见，预览棋盘透出，JS异常0。渲染统计18 draw calls、68,692 triangles。软件 SwiftShader帧率明显低于30/60；该记录不能证明Windows/RTX4060性能通过。
- 首轮两次等待失败来自测试：等待隐藏的 option 可见、无箭头字符串 `wait_for_function` 触发受限 CSP。测试改为DOM等待，产品没有放宽脚本策略。
- Node 角色回归由18扩为28，新增大模型/非法头部拒绝、先预览后确认、WebGL失败不激活、切角色清理迟到预览、原生隐藏清理迟到舞台，28通过；语音8通过。WebGL像素、语音RMS、恢复和平台性能须以独立真实浏览器/原生报告为准，不由受控对象测试代替。
- 不是 Live2D、VRMA 动作导入、用户脚本、全格式 GLTF、面捕或系统摄像头集成。VRM0/1 的任意导出器兼容性不能由单一官方样例保证。

## 一手来源和许可

访问/下载日期：2026-11-12。

- [Three.js官方仓库](https://github.com/mrdoob/three.js/tree/r180)，MIT：`app/licenses/renderer/three-LICENSE.txt`。
- [three-vrm官方v3.5.5](https://github.com/pixiv/three-vrm/tree/v3.5.5)，MIT：`app/licenses/renderer/three-vrm-LICENSE.txt`。
- [官方测试模型](https://github.com/pixiv/three-vrm/blob/v3.5.5/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm)，作者pixiv Inc.，模型内许可 `https://vrm.dev/licenses/1.0/`；元数据允许everyone使用、允许再分发。完整模型元数据、原文件SHA256和来源在 `research/vrm-fixtures/provenance.json`，许可页本地快照在相同目录。它是测试夹具，未设为默认角色。

PNG 四状态现已实际用于待机眨眼和说话眨眼：有对应图片时1.5–6秒间隔、120ms闭眼；无图片不伪造状态。`tests/png_blink_browser_check.py` 真实Chrome5项通过，`review/png-blink-browser.json` 留证，隐藏清理定时器。
