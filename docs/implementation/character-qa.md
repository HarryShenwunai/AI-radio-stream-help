# 自助 PNG 角色独立验收

2026-11-12 实际运行。审查者未修改被审应用实现，仅增加验收夹具、测试和本报告。对应源码 SHA256、运行环境、每项边界和缺陷保存在 `review/character-implementation-review.json`。

## 已完成

| 检查 | 实际通过 | 证据 |
| --- | ---: | --- |
| PNG 资产模块：真解码、文件系统、损坏与失败恢复 | 24 | `/workspace/research/character-assets-independent.log` |
| 角色目录：真 SQLite、WAL 迁移、隔离、删除失败恢复 | 24 | `/workspace/research/character-store-independent.log` |
| 本机 HTTP：角色/资产/鉴权/异步/旧库/模型凭证边界 | 22 | `/workspace/research/character-http-independent.log` |
| 角色前端：实际发布 JS、受控浏览器对象与竞态 | 18 | `/workspace/research/character-node-ui-independent.log` |
| 语音前端：实际发布 JS、受控 Audio/取消竞态 | 8 | `/workspace/research/character-node-voice-independent.log` |
| 真 Chrome：file upload、PNG 显示、HTMLAudio、响应布局 | 15 | `review/character-browser.json` |

上述是不同层级的检查，不等于原计划 28 项多格式导入验收全部通过。测试耗时只是运行记录，不是产品性能指标。

HTTP 测试使用独立临时数据库及真实路由、SQLite 和 Pillow。AI 生成/合成是夹具；凭证测试只用假密钥和两个临时 loopback HTTP 模型端点。过期连接快照返回409，两个端点均未收到请求；正确连接只向正确端点发送对应假密钥；模拟密钥写入中断返回503且无请求。

Chrome 使用真实文件输入上传两份不同色彩的自造 PNG，验证本机预览、服务器检查、显式启用、外观回退、取消不改当前形象、重载保留。另验证独立身份不串聊天/记忆、草稿按角色保留、恶意名称按文本显示。真实 HTMLAudio 播放生成的 4 秒440Hz WAV，验证说话图、停止回待机、两个页面只有一个播放者、切角色停声。启动允许 autoplay 以确定性检查生命周期；没有验证普通浏览器自动播放限制或听感。1440/390/360 CSS px 均无文档横向溢出，JS 异常0。截图已查看：`/workspace/dist/characters-desktop.png`、`characters-mobile.png`；其中恶意测试名称按字面显示是预期结果。

## 实际发现并修复

1. **CSP 阻止本机图片预览。** 原 `img-src` 不允许 `blob:`，真实 Chrome 的预览图无法解码。实现者仅给 `img-src` 增加 `blob:`；本测试新增策略断言并实际加载文件预览，已通过。原始失败报告在 `/workspace/research/character-browser-failure-1.json`。
2. **启用后旧修订永久不可点。** 列表在 busy 时生成 disabled 按钮，busy 结束后未重绘。前端已修 busy 变化时刷新外观按钮，当前修订仍禁用，旧修订可回退。Node 回归和真实点击均通过。原始失败报告在 `/workspace/research/character-browser-failure-2.json`。
3. **旧名称不满足新目录限制导致初始化失败。** 旧版本支持超过80字或控制字符名称；迁移后直接同步目录会失败。实现者只规范迁移副本中的名称并记录审计；81字和换行两种旧库均实际启动成功，原数据库 SHA256 不变。
4. **全局密钥与每角色提供方配置不匹配。** 主实现者发现并改为共享连接配置、凭证摘要一致性检查、换主机显式换/清密钥和发送前快照校验。独立验收用真实本机 HTTP 端点完成上述回归，未外发凭证。

## 重跑

在仓库根目录，Python 需 Pillow；Chrome 检查另需 Playwright 与 `/usr/bin/chromium`。本机 HTTP/Chrome 在本环境需要允许 loopback/socket 的执行权限。

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_assets.py -v
PYTHONPATH=src python -m unittest discover -s tests -p test_characters.py -v
PYTHONPATH=src python -m unittest discover -s tests -p test_character_http.py -v
node tests/test_character_ui.mjs
node tests/test_voice_ui.mjs
python tests/character_browser_check.py
```

使用直接 `node 文件` 可取得每条子测试结果；本环境 `node --test` 聚合输出只列两个文件，不应把文件数当作功能测试数。

## 未解决与未覆盖

- 当前是静态 PNG 状态映射，说话图不是音素级口型；没有加载或验收 Live2D/Core/VRM、第三方角色运行包、许可或真实画师样本。
- ICC/gAMA 元数据会移除，未做输入色域转换。当前应使用 sRGB8bit PNG；广色域色彩保真待单独支持与实测。
- 模块取消事件的回滚有测试；HTTP 上传时关闭浏览器是否及时取消解码未证明，可能留下一份已完成但未启用的修订，不改变当前外观。
- 本审查不证明原生桌面壳、安装包、系统窗口规则、Windows/macOS、多屏/游戏/目标显卡兼容；其他验收须单独报告。
- 没有目标硬件的 p95 延迟、内存/GPU/后台耗电验收，没有真实语音/模型质量或长期相处效果评估。
- 没有微信/哔哩哔哩/Zerolan 上游执行、云同步、公开分享、部署或生产环境操作；没有购买、连接账户、发消息、commit/push。

结论仅限已列版本的本机自助 PNG 子集：没有剩余阻断缺陷，允许继续整合；完整项目发布与多格式验收仍需各自证据。
