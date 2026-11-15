# 单条批准节目：开发验证记录

2026-11-15。目标仅Windows PC；本文记录的是Linux Chrome开发验证，不是Windows、OBS、B站、观众接收、审美或学习收益验收。

## 根因与最小修改

| 问题 | 原始证据与区分实验 | 最小修改 | 已有验证 |
|---|---|---|---|
| room样稿与真正输出分离 | 原live-stage无人物；room固定关闭说话/字幕为手填 | live-stage复用CompanionScene；节目仅绑定当前助手已导入的外观，固定既有right/透明底和carbon文字色组 | 真实R3/Core、同job字幕/音频hash/口型；不是所有room草稿布置已接通 |
| 未开始媒体就报playing | 旧版注入audio.play拒绝，audit仍有playing→failed | WebAudio运行且audio.play实际成功后才发playing；媒体图失败明确返回false | play拒绝、resume拒绝、source失败均不报playing |
| 缺少批准人物/资源边界 | 旧job没有scene，private资源只能用cookie读取 | open冻结当前角色清单；批准绑定scene hash、approval_revision、audio_sha256；POST令牌接口只读固定清单并复核hash | question/未知私有金丝雀不进poll/receipt/scene，越界资源、错revision、篡改资源、切外观、撤权拒绝 |
| 加载/媒体晚响应能覆盖后来状态 | 针对pause与playing回包、completed与下一job/停止、暖scene和audio晚包分别故障注入 | epoch、播放世代、媒体启动与回执接受分别处理；加载不阻塞既有心跳 | 全部固定晚响应反例通过；不延长TTL或心跳预算 |
| 完成文字被空poll覆盖 | 第一轮completion的服务audit已经completed，但节目完成UI检查超时 | 完成终态保持到新job/明确重启，显式显示；空poll不改完成文字 | 同一冻结源码整段播放，节目与主播均completed，口型与字幕复位 |
| 字幕遮住杯/手 | browser-probe-fixed/03-stage-playing.png全宽条覆盖杯/手 | 只改既有right布局字幕宽度，角色/素材不移动、不裁切 | 1024/1280宽、720高：caption与character-space边界不交，无横向溢出；播放隐藏状态提示、撤权显示 |

节目资源transport默认不改变私有页面：原URL仍按当前角色和asset校验，再映射为已校验blob；不放token到URL、不用cookie、不加任意文件代理。只有节目页CSP允许固定安装运行库的nonce脚本，以及已校验blob的connect读取；其他页面仍保持原CSP。没有安装记录/许可的生产运行库路径仍拒绝。

节目无形象时明确显示“未设置节目人物”，保留音频/字幕降级；不将placeholder的ready当人物渲染成功。损坏或不支持的形象停止节目准备，不能冒充角色成功。本轮主线成功证据均使用真实R3/Core。

## 素材与证据来源

- 本次使用既有`R3-Study-Companion.zip`，SHA256 `ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d`。它是已存在的上半身候选，不是眼部最新母稿，也不是新的美术认可；没有修改原素材或恢复放杯入口。
- Core真实字节SHA256 `25ae938cb4fe282ce189b357bcc97e603d1e1f7ec78bf04150d401c23cdc792f`；既有owner bundle SHA256 `0f9bfd8af46da18bc3ef15d940d96d66a7aedf05e7edfa49911b2a65b0f7f81d`。
- 本环境缺少旧生产安装记录，浏览器测试用独立fixture读取上述已存在字节并校验；没有下载SDK、伪造许可记录或绕开生产许可门。真实Core执行不等于生产安装链验收。
- 主输入来自本对话原文；确定性生成是明确的机械复述，音频为PCM测试波形；不是AI回答质量、真实TTS、真实弹幕或新编作品。真实模型/TTS入口单独启用并记录冷加载、实际输入输出、finish_reason、阶段耗时和WAV。

本地开发证据目录（不随公开源码提交）包括：

- `.build/program-output/old-red-recovered/`：旧版playing错误与无人物反例。
- `.build/program-output/browser-diagnosis/`：nonce加载Core成功但blob MOC被旧CSP拒绝的控制台/响应。
- `.build/program-output/browser-probe-fixed/`：原全宽字幕遮杯图，保留作布局反例。
- `.build/program-output/browser-completion/`：服务已completed而节目终态检查失败的红记录。
- `.build/program-output/browser-final/`：1024/1280不遮挡与必要取消故障；该轮片段停止实测0.242秒，浏览器音频峰值0.15625，口型值0.4074；不是目标机中断保证。
- `.build/program-output/browser-closed-loop/`：最终同冻结字节整段播放和生命周期故障检查，完整双端视频、Trace、独立浏览器音轨、原始事件与audit；视频本身没有音轨。
- `.build/program-output/read-overhead.json`：0/1/100任务、audit500的局部读取开销；100任务owner投影中位约0.83ms、JSON约89.7KB。数据仅本机观察，没有虚构Windows预算；没有新增后台轮询或线程。

Trace包含真实角色/SDK响应及已失效本机临时令牌，不公开提交；模型、SDK、用户数据、音频和录像均不进入源码提交。

## 复跑

已有依赖与固定本地资产路径作为参数；不自动安装或下载。

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_live_interaction test_live_output test_platform_integration_http test_local_rehearsal test_program_output_http
node --test tests/test_character_ui.mjs tests/test_live2d_adapter_ui.mjs
PLAYWRIGHT_BROWSERS_PATH="$PWD/.build/p9-host/pw" PYTHONPATH=src:tests python3 tests/program_output_browser.py --chrome /path/to/chrome-headless-shell --model /path/to/R3-Study-Companion.zip --runtime-dir /path/to/existing/owner-local --out evidence/program --completion --faults
```

`PLAYWRIGHT_BROWSERS_PATH`指向已有录像工具目录，本环境的ffmpeg链接到系统`/usr/bin/ffmpeg`。`--runtime-dir`仅用于显式fixture，内含`live2dcubismcore.min.js`及`build/owner-live2d-runtime.js`。

真实模型与语音应在完整回归结束后顺序运行：使用已配置llama_cpp/kokoro环境，在上述命令追加`--real-model /path/to/qwen3-4b-instruct-2507-q4_k_m.gguf --real-tts /path/to/voices --completion`，去掉`--faults`。冷加载单列，事件仍30秒，length等不完整响应拒绝。实际未运行前不得声称真实推理/整段TTS已通过。

## 剩余边界

源码与确定性本地节目闭环有证据；当前可编辑艺术源链、最新眼部修订、美术/声线独立评审、Windows10/11/4060真机、同版安装包、真实音频设备/OBS、观众接收及学习收益仍须独立验收。浏览器音轨与播放状态不证明扬声器或观众收到。节目布局仅本轮固定right与透明输出；没有把独立预览草稿、其他人物、计时器或更多组件自动公开。
