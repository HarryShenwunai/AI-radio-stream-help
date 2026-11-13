# 本地语音与对话策略集成

更新：2026-11-12。实际实现位于`src/companion_runtime/voice.py`与`conversation.py`。本文件区分模块测试、真实本地模型与待验条件；不能把小样本观察当人类自然度通过。

## 已有接口

```python
from companion_runtime.voice import LocalASR, AudioLimits, VoiceError
asr = LocalASR(owner_model_dir, device='cpu', compute_type='int8')
status = asr.diagnostics()
result = asr.transcribe_wav(wav_bytes, cancel=threading_event)
```

`result`是可用`dataclasses.asdict`序列化的`Transcription`：text、segments、duration_seconds、language、elapsed_seconds、backend和device。`VoiceError.status/code`用于HTTP响应；取消为409/cancelled，缺依赖或模型为503，未识别出语音为422/no_speech。

默认只接完整单声道、PCM16、0.1–60秒、8–48kHz的WAV，字节上限6000000。验证RIFF总长、单fmt/data、PCM格式、字节率/帧对齐和实际帧数；不把改扩展名的WebM/MP3当WAV。允许的采样率见`AudioLimits`，不是所有音频格式。HTTP层须在读请求前限制base64/JSON体积并严格解码，约8MB编码体积不等于可随意增大所有接口上限。

ASR输出只用于原录音所属角色/会话；调用方仍要校验expected_character_id/媒体戳并在角色切换后丢弃迟到结果。模块不保存录音、不上传云识别、不调用浏览器SpeechRecognition，不在识别时下载权重。

## 依赖、模型与设备

选用[SYSTRAN faster-whisper](https://github.com/SYSTRAN/faster-whisper)：支持CPU int8及CUDA配置，使用PyAV解码，无须另装系统FFmpeg。当前固定依赖在`app/requirements-asr.txt`，`requirements-voice.txt`引用它。

真实验证发现：faster-whisper1.2.1的宽依赖安装到了PyAV19.0.2后，import成功但实际转写因已移除的`metadata_errors`参数失败。已固定PyAV16.1.0并复测；diagnostics对已知19+不兼容版本会给明确原因。不要以安装/import替代实际转写。

默认CPU可避免与二次元渲染争抢显存。RTX4060的CUDA选项仍需匹配驱动和运行库；当前官方README要求CUDA12/cuDNN9，未在用户Windows/GPU上验收。不自动降级后声称GPU正在工作。tiny用于小体积功能验证；base/small是可显式选择的多语种候选，中文人声质量须实际比较。

显式准备模型，仓库根目录示例：

```sh
python -m pip install -r app/requirements-voice.txt
PYTHONPATH=src python -m companion_runtime.voice download --model tiny --directory app/models/asr/faster-whisper-tiny
PYTHONPATH=src python -m companion_runtime.voice status --directory app/models/asr/faster-whisper-tiny
```

Windows由启动/构建程序设置模块路径或使用其对应命令，不能把`PYTHONPATH=...`直接当CMD语法。下载只允许tiny/base/small维护者模型名；tiny固定[Systran转换模型](https://huggingface.co/Systran/faster-whisper-tiny)的revision `d90ca5fe260221311c53c58e660288d3deb8d356`，四文件约78MB。显式下载记录commit与SHA256；相同source.json和文件哈希匹配时复用，不重复下载。base/small在显式下载时解析并记录版本，不是任意URL输入。

本机现有验证模型在`/workspace/asr-models/faster-whisper-tiny`，不是用户电脑路径。模型位于Git之外，打包或用户本地下载由主任务选择，不把运行缓存提交。

PyInstaller需收集faster_whisper/assets中的Silero VAD ONNX与本地依赖库；模型目录另配置。仅hiddenimport而未收集数据文件可能在真实语音路径失败。桌面打包由对应Agent负责。

## 选配外部TTS

```python
from companion_runtime.voice import ExternalTTSConfig, ExternalTTS
provider = ExternalTTS(ExternalTTSConfig(
    endpoint=owner_endpoint,
    ref_audio_path=owner_licensed_reference_path,
    prompt_text=owner_reference_transcript,
    prompt_lang='zh', text_lang='zh'))
audio = provider.synthesize(reply_text, cancel=threading_event)
```

配置来自已认证的本人设置，不从模型回答或角色包读取。HTTP只允许本机，远程要求HTTPS；禁止用户信息/查询/片段、已知元数据地址及重定向。可选Bearer凭证不写日志或repr。

此适配器实现[GPT-SoVITS上游api_v2](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/api_v2.py)的非流式`/tts`请求，含text/text_lang/ref_audio_path/prompt_text/prompt_lang，固定media_type=wav、streaming_mode=False。它不是Zerolan专用fork的协议。默认30秒、20MB上限；检查实际PCM16 WAV和响应完整性，失败不作为音频返回。

Kokoro继续作为默认本地合成。外部服务、参考声音和授权由用户自行配置；本轮没有克隆声线、下载第三方人物声音或启动GPT-SoVITS模型。实际HTTP层检查使用本机WAV服务替身，不能写成真实GPT-SoVITS质量通过。

取消检查在请求前、接收时和结果交付前执行。不能强行终止正在运行的原生ASR/TTS或尚未返回响应的外部计算；调用方必须先本机停声，并用generation与角色戳拒绝迟到结果。阻塞中的网络操作受socket timeout限制，非即时远端停算保证。

## 对话接口与实际漂移修复

```python
from companion_runtime import conversation
messages = conversation.build_messages(settings, recent_history, related_memories)
reply = conversation.generate_reply(settings, messages, actual_generate_once,
    on_delta=emit_delta, cancel=cancel_event, on_status=emit_status)
```

`actual_generate_once`仍是现有真实本地LLM或用户API，签名保留`(settings,messages,on_delta,cancel,max_tokens=240)`。模块没有预写聊天答案；最多一次真实生成式编辑，并发出replace状态让前端清理草稿。持久化、ground_memory_owner、角色/会话归属与审计仍由服务端控制。改写失败保留原消息，不能把半成品存为最终回答。

真实旧证据`review/character-native-check.json`中，保存“蓝纸风筝”后问疲累，模型仍围绕风筝回答。新策略在普通对话中把“记住：...”管理命令及确认从生成上下文剥离；显式召回时仍可引用近期原话。普通短期对话保留，长期记忆按相关性与用户开关读取。“别提问”“先别劝”“别总提旧事实”优先于召回关键词；工具和记忆不覆盖角色性格。

保留`用户明确保存的记忆（`标记供已有事实归属校正使用。角色名称/性格/偏好仍取自当前用户配置。运行回执与人物设定分开，不让模型声称创建了提醒。

规则只针对可观察的已知违例，不能证明所有语义正确。首轮新真实观察仍输出“我陪你去看电影”，已保留`review/conversation-before-presence-check.json`，再补unsupported_presence检查/测试及真实改写复测；没有用固定回答替换。

## 实际验证

- `tests/test_voice.py`：28项WAV、ASR替身、配置与取消检查通过。
- `tests/test_voice_http.py`：4项真实loopback HTTP传输检查通过，音频为WAV夹具，非GPT-SoVITS模型。
- `tests/test_conversation.py`：15项prompt/策略与真实回调接口夹具通过，不是自然度分数。
- `tests/manual_voice_smoke.py`：已运行真实CPU tiny识别本地Kokoro生成的2.683秒中文，文本“您好今天我们一起学习”，含加载1.206秒；静音no_speech。输入是合成语音，不是用户麦克风；Windows/RTX4060未测。记录在`review/voice-real-smoke.json`。
- `tests/manual_conversation_smoke.py`：真实Qwen3 4B四场景记录在`review/conversation-real-smoke.json`；旧口令未抢疲累话题，电影场景触发一次真实编辑。全部原始问题保留，不声明人类自然度通过。开发环境存在并行工作，耗时不能当可比较的p95或设备最低配置。

新测试文件曾与独立QA短时撞名：ExternalTTS测试固定为test_voice_http.py，QA已将应用级ASR集成恢复至test_asr_integration_http.py。两份均需纳入总回归，不以遗漏用例美化结果。

## 待验证

用户Windows实际录音/识别与GPU、复杂中文人声/噪声/口音、默认设备与权限、自然多轮质量、听到的音频进度与未听上下文截断、完整应用/原生包ASR、选定合法外部TTS质量与时延。主任务的端点、前端和打包集成需分别验证，模块夹具不替代这些检查。

固定 tiny 模型的官方模型卡和 OpenAI 原始 MIT 许可通知已于 2026-11-12 保存到 `app/licenses/FASTER-WHISPER-TINY_MODEL_CARD.md`、`OPENAI-WHISPER-MIT-LICENSE.txt`，原始版本与 SHA 见 `WHISPER-SOURCES.json`。这是随模型保留的来源通知，不代表所有第三方依赖的完整许可审查已完成。
