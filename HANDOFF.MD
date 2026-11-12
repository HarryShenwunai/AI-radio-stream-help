# 设计交接

更新：2026-11-12。执行新任务先阅读本文件及相应目录已有说明。

## 当前方向

项目未命名。目标是自然、有稳定性格、可文字/语音相处的虚拟角色；督学可选，长期记忆不是核心驱动。现有可运行原型与数据操作保留，新增能力通过适配层逐步验证。

本仓库用于设计与来源归档，不代表已经实现B站、弹幕姬、AR或MC集成。真实账号连接、开播、游戏动作、摄像头/屏幕采集、服务购买或部署需要对应明确授权。

当前参考：ZerolanLiveRobot、ZerolanPlayground、zerolan-core、zerolan-data、KonekoMinecraftBot。完整来源与读取版本在evidence/zerolan-source-refs.json。

## 实际踩坑与修正

- MC默认master没有同等Zerolan桥接；dev含src/web/zerolanPlugin.ts。应固定已验证commit，不能只克隆默认分支就宣称可联机。
- Core通用TTS入口是占位；实际文档要求特定GPT-SoVITS fork/zerolan分支/zerolan_api.py。不能将占位解释成整个体系无TTS，也不能把官方api_v2.py当兼容实现。
- Core的逐行JSON、当前原型SSE与WS控制不是同一种传输。网络chunk可能拆并消息，需增量UTF-8与帧缓冲。
- 模型Query/Prediction中Field(default=str(uuid4()))不是每次创建都生成新ID。适配时显式分配或改default_factory。
- 事件5秒超时日志不是取消执行；播放器停止、生成取消、未播放上下文截断和晚到结果丢弃须分别验证。
- Unity异步下载完成才入播放队列，需额外验证乱序与已取消generation的晚到音频。
- 字段类型和协议版本不等于身份与权限；公众事件不能进入私人history或工具执行路径。
- AR根目录未找到独立许可证；Unity、Vuforia、Cubism和素材各自核对。MC master的package许可元数据与LICENSE不同，dev又不同，不能取一个标签覆盖整个体系。
- 页面无横向溢出仍可能PDF架构图被裁切；使用紧凑竖图，并实际查看导出页。
- 搜索有多个仿官网；中文产品只采用已核对官网或发行方商店说明，不以聚合页、评分或宣传规模当需求证据。

## 状态与下一步

新集成测试Q01–Q10均NOT_RUN。已有36项后端/5项模拟模型协议等记录来自旧原型，不是本轮重测。主计划、工时和验收以docs/planning/revised-plan.md为准，历史计划另存history。

先做固定版本兼容样例，再决定适配或迁移。核心P0–P5含储备18–33人日；AR与MC均选则24–45人日，均是8小时/人日的工程估算，不是承诺。

仍未知：目标机器、预算、音色、具体弹幕姬/房间和官方账号条件、AR许可与真机、MC版本和服务器授权、真实集成时延与长期相处质量。

Git历史不放模型、安装包、私聊、数据库、密钥、Cookie或原始用户资料。不复制上游整套源码或未获许可素材；本仓库只提供分析与来源标识。

本轮设计文件/Schema结构检查18项通过；HTML由本地answer-me-with-html CLI生成，STE警告0。Chrome的1440/390宽度检查无页面横向溢出、无JavaScript异常；6页PDF中的架构图已查看。以上是文档交付检查，不是新增集成功能测试。

## 启动批次（用户已批准）

用户批准推荐路线并要求多Agent协作。主Agent集成；protocol负责协议、lifecycle负责取消状态、voice_ui负责前端/Chrome、live_ingress负责公开离线队列、independent_review独立审查。彼此采用文件独占避免写入冲突。当前代码在app/与src/，run.py可启动，计划执行状态以docs/planning/execution-board.md为准。

实际Python回归115项通过，Node竞态8项、Chrome检查12项通过。真实Qwen/Kokoro单次冒烟通过；首段10.790秒，完整17.248秒，语音3.124秒，取消0.091秒，RSS约5.27GiB，非p95/用户验收。完整Q01–Q10尚未验收；旧追踪文件是设计时快照，当前执行见phase1报告。没有真实直播、上游部署、OBS、AR、MC或微信连接。

新增踩坑：已成功rid换text曾静默返回旧cached回答，已预检拒绝409，且无效请求不使旧generation失效；直播字符串孤立surrogate与超大event_at曾抛异常，已统一invalid并加回归。HTTP abort只能阻止客户端接收，不能假称底层TTS停算；合成前后和浏览器serial均须检查。旧Audio回调必须绑定本对象，防误清新URL。

后续先测上游兼容和完整语音轮次；真实房间需明确弹幕姬/官方入口、设备与账号条件。AR/MC仍可选，不因多Agent自动扩大权限或压缩整体估算。
