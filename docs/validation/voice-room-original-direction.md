# 声音、默认原角色与本地场景样稿

观察日期：2026-11-15。仅Windows PC产品方向，本轮执行环境为Linux PC Chrome。先调查、提出方案，用户同意后实施；不进行平台接入或部署。

## 原始依据

- 用户标准图IMG_1381.jpeg（原有Library身份保留，不重新公开）。实际查看原图，低分辨率色彩量化主色约#8b8577/#47524c/#636559/#cecac1，保留右上逆光、短黑发、浅卫衣、近景持杯。此色样提取不是整体色彩还原证明。
- Virtual Cottage 2：https://store.steampowered.com/app/2943180/Virtual_Cottage_2/ 。官方页面注明2026-03-27发布；实际取得并查看两张官方1920×1080商店截图。借鉴空间主体、边缘工具的主次，未复制房间、字体、角色或二进制素材；未运行该商业产品。
- LifeAt：https://lifeat.io/feature/virtual-spaces 。查看官方宣传图，说明空间、声音和独立工具组合；属于产品宣传，不算实际可用性测量。
- OBS：https://obsproject.com/kb/browser-source 。浏览器画面源可组合透明内容/音频；本轮未运行OBS。
- VTube Studio：https://github.com/DenchiSoft/VTubeStudio/wiki/Lipsync 。区分振幅口型与元音形状；本模型只制作了现有嘴部参数，不声称已具备五元音口型。
- Kokoro：https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md 。作者对当前中文音色自评为D，不等于所有场景质量的独立结论。不能仅切音色或提速就判定青春感通过。
- Qwen3-TTS：https://github.com/QwenLM/Qwen3-TTS 。确认有VoiceDesign风格控制能力；当前机器无torch/该引擎，不把官方能力当作本地效果。本轮未下载或验收该引擎。

## 最小修改及理由

1. 原Kokoro硬编码小贝，改成受限音色选项；偏好保存在角色SQLite内，避免新增全局runtime.json字段造成旧版回退失败，并保证切角色不串音色。未在无人试听时擅自更换最终默认声音。
2. 启动时可从应用目录default-live2d.zip或显式COMPANION_DEFAULT_LIVE2D加载项目原角色。一次性标记，保留用户已有外观及恢复为空的选择，错误包不污染标记。模型包单独私下交付，Core/Framework不入GitHub或分发默认包；已安装/自备合法运行时仍单独检查。
3. 本地room.html为声画样稿。原图灰绿与米白形成非对称角色/内容构图，专注/提问/休息使用同一个空间。字段均为用户主动填写；未加入虚构在线人数、平台事件或学习掌握记录。不是已自动接收直播上下文的公开输出窗口。接口只返回角色外观，不给私人聊天和密钥。
4. 复用StudySession计时；样稿使用现有30fps折叠渲染预算；未增加模型、语音或后台平台进程。有限场景测试不证明目标机性能。

## 已执行验证与失败反例

- 实际Core绘制检查：默认角色无需导入点击即可显示；MOC一致性检查及Core evaluations为真；刷新保留同一外观。角色包SHA256 ad977f491ef67e7421c718b23634a546348b5e4d933d556f65597d854fb2446d。
- 原角色+实际Kokoro中文语音经浏览器Audio/Analyser驱动嘴部，停止后口型复位。保存参数时间序列和完整录像；不以mouth字段替代完整自然度审查。
- 本地场景检查：计时实际递减、暂停不计时、切场景暂停专注、休息开始/暂停明确、输入不能执行HTML。
- 源码首启检查：并发初始化只创建一个默认外观；已有外观不覆盖；用户清空后重启不重新强加；损坏包可修复后重试。
- 真实音频九段：三种音色各读招呼、解释和恢复三句，原始生成均无削波。统一响度副本使用-20LUFS/-2dBTP作为试听比较条件，不是风格或上线验收阈值。原样音及测量均保留。
- 首次浏览器脚本等待不存在的getStats.format而失败；改等实际Core诊断和绘制。
- 新场景最初把时钟传入event.now而非reduce第三参数，导致未启动；同条件浏览器复现后修复。保留失败结果，不能把这些失败删除再称一次通过。
- 新角色音色隔离测试初次误用不存在的characters/activate路由，改用仓库原有characters/select，不是产品接口修复。

## 复跑

```sh
PYTHONPATH=src:tests python3 -m unittest -v test_default_live2d_voice test_app_update test_app_update_commit
COMPANION_VOICES=/path/to/voices PYTHONPATH=src:tests python3 tests/voice_room_browser.py --model /path/to/R3-Study-Companion.zip --runtime-dir /path/to/owner-local --voices /path/to/voices --chrome /path/to/chrome --out evidence/voice-room
python3 scripts/quality_gate.py --bootstrap --full --report evidence/quality.json
```

真实浏览器需要已合法取得的Core与本地Framework bundle，路径结构与脚本参数一致；语音需要已记录版本Kokoro/misaki依赖。以上不自动下载SDK、模型或连接平台。

## 验收边界

默认角色/口型机械检查、本地场景交互、实际音频已执行；用户对青春感的选择、角色审美及独立盲评尚未取得。Windows/RTX4060、真实服务、OBS/观众端均待验证。当前模型仍有此前记录的视觉局限，未补画、重绑或宣称视觉最终合格。当前场景在打开时固定角色，未做跨窗口实时角色同步。

P7三问：既有音频与角色API兼容，新增参数落在角色设置而非旧全局schema；边界由实际数据库/HTTP/浏览器测试支持；本次解决硬编码音色、缺默认加载入口和缺组合样稿，不把样稿当作最终直播室成品。
