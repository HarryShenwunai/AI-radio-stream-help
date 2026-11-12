# Windows 候选交付材料

**完整便携包的 Release 附件尚未上传成功，暂时不能从这里下载软件本体。** 当前 GitHub 授权可以推送仓库内容，但上传域名 `uploads.github.com` 返回 `401 Bad credentials`。发布草稿保留，未把空下载页标为发布完成。

- [源码版本 d01ccc4](https://github.com/HarryShenwunai/AI-radio-stream-help/tree/d01ccc42bbe6795c216afae37dd0e53128ab58d9)
- [下载真实运行证据 ZIP](https://github.com/HarryShenwunai/AI-radio-stream-help/raw/refs/heads/feat/phase1-runtime/deliveries/0.4.0-dev1-candidate/evidence-companion-real-20261112-163732.zip)
- [候选包清单](candidate-manifest.json)：完整包 4,491,413,065 bytes，SHA256已校验。
- [分卷及SHA清单](release-manifest.json)：因GitHub单个Release附件须小于2GiB，完整包准备为三卷。
- 下载/合并脚本已完成五项真实PowerShell/.NET小夹具检查；[报告](download-helper-check.json)注明Linux执行范围，不宣称Windows实测。

`download-and-assemble.cmd` 和 `.ps1` 是待附件上传完成后使用的工具。当前不要把脚本可下载当成完整软件已经可下载。

运行证据ZIP含真实模型整链录像、四张截图、实际Kokoro WAV及机读报告。录像没有系统音轨；WAV独立附带；自有几何VRM不是最终角色美术。不含Live2D SDK、第三方官方角色或其仅本机评估截图/录像。

当前源码/本机回归通过不代替Windows/4060、真实B站/ClawBot与人工自然度验收；详情见仓库验收台账。
