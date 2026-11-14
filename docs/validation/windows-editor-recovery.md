# Windows PC深度修订：首个可复现闭环

日期2026-11-14。仅PC；没有手机开发或验收。

## 基线与缺口

GitHub基线d0e472115c35e315c5b0a60948cfe89bb5afcc9c，本地9f52fe7a8246aef5aa6786df91f0b1d8bae0b25a，树1a6d330ccf68edff2f73cfdce2cb57c03815f579相同。desktop/package.json声明0.5.0-dev3/Electron45.3.1，不代表目标设备已安装。当前安装包、GPU驱动、模型运行配置、OBS、原始弹幕、观众录制和独立评审均未取得。历史Windows构建受阻记录不作为当前状态证明。

## P7方案与竞争解释

目标：状态刷新不能打断正在编辑的公开教材。竞争解释A是服务端覆盖材料；B是前端使用旧草稿；C是DOM重建丢失编辑上下文。保持服务端材料不变，仅延迟status响应，等待期间编辑为另一段文本并选中5–12字符，再释放响应。

实际观察：文本和服务端材料均不变，推翻A/B；旧版教材details关闭、焦点丢失、选区变为29–29，支持C。修改仅捕获并恢复展开状态和当前教材框的焦点、选区；保留ID/API与现有作用域、请求序号校验。用户已移走焦点时不得抢回。回退该提交即可，不涉及数据迁移。

## 修改前固定判据

- 刷新前后草稿逐字相同、details展开状态相同；仍在编辑时焦点和选区相同。
- 只一次状态GET，零教材提交/模型请求，服务端教材不变。
- 用户聚焦关闭按钮后，刷新不抢回焦点。
- 原有关闭面板/切角色/乱序响应回归继续通过。

最终同一浏览器脚本在旧源码上仅编辑上下文断言失败，新版全部通过。早期错误焦点实验也保留，不能计作产品故障。无新增依赖、轮询和后台监听；网络记录支持请求数量不增，未做目标设备CPU/GPU/性能收益测量。

## 复跑

需要项目测试依赖、Playwright、Chrome与录像支持。两次使用不同空目录；第二条预期非零退出。

```sh
PYTHONPATH=src:tests python3 tests/live_material_focus_browser.py --chrome /path/to/chrome --out evidence/new
git show d0e472115c35e315c5b0a60948cfe89bb5afcc9c:app/static/connectors-ui.js > old-connectors.js
PYTHONPATH=src:tests python3 tests/live_material_focus_browser.py --chrome /path/to/chrome --out evidence/old --ui-source old-connectors.js
node --test tests/test_connector_settings_ui.mjs
```

Windows可在PowerShell先设置 $env:PYTHONPATH="src;tests"，使用python执行同一脚本，并指定实际Chrome路径；命令尚未在Windows真机执行。Chrome Trace与视频来自隔离合成会话，视频无音轨。该缺陷是编辑行为，未产生或检验音频。开发样例不得冒充未见验收样例。

## 三问及独立验收

接口：未改API、ID或持久化结构。边界：关闭/切角色已有回归，焦点已移开用真实浏览器检查；输入法组合过程和屏幕阅读器仍待专项验证。根因：补齐重建DOM时遗漏的编辑状态，不以延迟或重复轮询掩盖问题；目前仍重绘整张面板，其他表单焦点不在本轮修复范围。

外部工程师可复跑新旧源码；目标主播应使用未见教材测试刷新中编辑、撤销选区和继续输入。实际操作耗时改善、Windows系统DPI/多屏/睡眠、真实直播接收、独立学习收益及用户认可均待验证。初始学习材料保留路径另作未修改对照，不由本次编辑修复推导其全链路正确。

达到本地可复现闭环后停止扩大；下一步需要目标Windows安装包/环境与授权直播证据，不能靠增加PR数代替。
