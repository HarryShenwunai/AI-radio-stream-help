# 本地应用：启动批次

保留v0.2原型，增加生成标识、私人入口检查、语音取消与晚到结果抑制。当前开发版本0.3.0-dev1，不是完整直播/AR/MC成品。旧称呼只是历史角色占位，不作为项目名称。

在仓库根目录运行：

```sh
python run.py --no-browser --port 8765
```

需要Python 3.10+。打开终端打印的本机地址。HTTP/SQLite与协议组件只依赖标准库；聊天生成仍需本地推理依赖及模型，或在设置中配置兼容API。缺依赖/模型时会明确报错，不会用固定聊天冒充模型。

可选本地模型安装，先在独立虚拟环境中执行：

```sh
python -m pip install -r app/requirements.txt
python app/download_models.py
```

下载按清单核验SHA256；会联网并占用磁盘，未随源码附带权重。复用已有合法资产可设置COMPANION_MODELS、COMPANION_VOICES指向对应目录。数据默认在app/data，可通过COMPANION_DATA指定**独立目录**；不要让旧版和新版同时写同一数据库。

默认只监听127.0.0.1。本地浏览器Cookie不是直播桥接凭证，不允许将其交给弹幕姬、AR或游戏执行器。私人HTTP入口拒绝live频道、其他来源或会话，以及自称owner的字段；目前没有公开HTTP入口。

自动语音携带generation_id与request_id，文字必须与该轮已保存回复匹配；历史朗读只传message_id并由服务端读消息。设置试音仍允许本人提交文字。取消先停止本机音频；无法中止的TTS计算可能继续，迟到结果会丢弃。

语音输入仍依赖浏览器识别，可能使用在线服务，需要用户同意。默认浏览器自动播放限制与目标机声卡未完成验收。微信、B站SDK、OBS、AR、MC尚未接入。

源码及原创SVG按[GPL-3.0](LICENSE)；可选模型/运行库另见[许可说明](ATTRIBUTIONS.md)。当前没有新增编译安装包，旧Linux包对应v0.2。
