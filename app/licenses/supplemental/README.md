# Supplemental upstream notices

Retrieved 2026-11-12. `source-records.json` records original URLs, release tags or
immutable commits, retrieved bytes and SHA256. Original files are preserved.

The Windows wheel inventory still accurately reports 23/27 packages with notice
files and four without standalone notice files. This supplement supplies actual
upstream texts for those four; it does not alter or conceal that inventory:

- jieba 0.42.1: MIT notice from exact tag `v0.42.1`, commit
  `1e20c89b66f56c9301b0feed211733ffaa1bd72a`. The published source archive also
  lacks a standalone license file; its PyPI SHA256 was verified separately.
- ordered-set 4.1.0: `MIT-LICENSE` from exact tag `release/4.1.0`, commit
  `d921651b2737f5cfe711868fab558a8ef79e26ca`. The published source archive also
  contains `MIT-LICENSE`; its bytes match the repository copy, and both the
  archive hash and extracted notice hash were verified.
- FlatBuffers 25.12.19: Apache-2.0 text from tag `v25.12.19`, resolved commit
  `7e163021e59cca4f8e1e35a7c828b5c6b7915953`.
- espeakng-loader 0.2.4: MIT notice from fixed upstream commit
  `0ddc87adf77e5850d7eeb542ac8a87d421b64daa`; included `pyproject.toml` declares
  that exact version. This MIT loader notice does not replace the native
  eSpeak NG license.

The loader contains native eSpeak NG. Its source/build workflow pins eSpeak NG
1.52.0 and its submodule resolves to that tag's commit
`4870adfa25b1a32b4361592f1be8a40337c58d6c`. Its original GPL text is included.
Source is available from the [fixed upstream source tree](https://github.com/espeak-ng/espeak-ng/tree/4870adfa25b1a32b4361592f1be8a40337c58d6c)
and [source archive](https://github.com/espeak-ng/espeak-ng/archive/4870adfa25b1a32b4361592f1be8a40337c58d6c.tar.gz).
The loader's original native-build and wheel-build workflows are included as
evidence. The wheel workflow downloads the latest native release asset, so the
distributed DLL's complete correspondence to a reproducible source/build has
not been independently established. Providing these texts and references does
not constitute a complete redistribution/legal review or settle every GPL
corresponding-source obligation. Retain this open item before wider release.
