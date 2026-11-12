# 主人私聊桥接插件

这是接入已有 AstrBot weixin_oc 的插件源码，不是微信登录器。先由用户自行配置并验证 AstrBot；本轮没有登录、扫码、真实发信，也没有在真实AstrBot环境安装验证。

将本目录作为独立插件放入用户现有 AstrBot 插件目录，通过插件管理启用。配置完整的主人 `unified_msg_origin`（格式含 `:FriendMessage:`）、同机 `http://127.0.0.1:端口` 后端、单独配对token。不得使用模型API key或微信账户token充当bridge token，也不得提交配置到Git。未配置主人时不转发；其他来源/会话不处理。

入站只转发绑定主人的 weixin_oc 私聊文本，停止该会话的 AstrBot 默认AI流程，避免两个模型重复回复；后端故障时也不自动恢复为未经批准的回复。不会下载附件URL或把路径当工具参数。

`enable_send` 默认关闭。主人确认外发后可以打开；后端默认预览，只有主人手工批准，或明确启用固定主人origin自动回复，才可被领取。接收端只接受固定主人origin，模型不能指定收件人。发送失败/结果不明不自动重试，检查本机状态后再决定是否重新生成预览。

语音降级为 `Comp.File` 的 WAV 附件（名称“陪伴语音.wav”），不使用 `Comp.Record`，不能称微信原生语音条。`handed_to_adapter` 只表示调用适配器完成；缺少或失效context会导致发送失败，它不是对方已收到/听到的回执。

该插件只连接本机后端，不增加监听端口；URL拒绝非127.0.0.1、路径、用户信息和重定向。上游来源和日期在 src/companion_runtime/connectors/sources.json。核心接口见同目录README；端到端测试使用明确的AstrBot API替身，真实账户验收待用户配置。
