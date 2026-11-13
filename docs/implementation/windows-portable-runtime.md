# Windows portable runtime

Current target is Windows 10/11 x64. RTX4060 /32GB are user-reported; GPU VRAM,
driver, CPU and actual performance still require the local diagnostics. Assembly
on Linux is not Windows execution or hardware acceptance.

## Ready-to-run layout

`companion-desktop.exe` contains the official Electron host. CPU is the default:

```
resources/backend/                         CPU Python and application
resources/backend/models/                  One shared Qwen model + ASR/tiny
resources/backend/voices/                  One shared Kokoro model/voice set
resources/backend-profiles/cuda/           Optional CUDA Python/application
resources/active-runtime-profile.json      Only cpu or cuda
resources/runtime-session.json             Owned PID and loopback origin
```

No Python, Node.js or Visual Studio compiler is required to run a completely
assembled directory. Native Microsoft VC++ x64 runtime and an appropriate NVIDIA
driver remain prerequisites where required. Neither is installed silently.
The full package contains the existing checksum-verified Qwen/Kokoro assets,
the fixed tiny ASR snapshot, and faster-whisper's packaged VAD ONNX asset.
No assets are fetched when recording audio.

Exit the application before running `使用CPU.cmd` or `使用CUDA.cmd`. The fixed
helper checks both profiles' source ID/interpreter and critical-file SHA256,
refuses while the owned host PID is alive, atomically writes the selection, and
launches the same host. A separate runtime/LLM is not started alongside it.
CUDA startup loads controlled native dependencies before emitting HTTP readiness;
failure exits72 and the host stops it before returning to CPU. This proves a
guarded failure path, not actual GPU model allocation. UI compute settings remain
explicit and shared by identities: cpu/cuda/auto, GPU layers0..64 and context4096
default (2048 optional). CUDA capability is distinct from confirmed offload.

CUDA runtime/cuBLAS are bundled only inside the CUDA profile. Isolated Python's
`sitecustomize.py` adds only fixed bundled DLL directories in that child process;
stale global CUDA/HIP paths cannot redirect it. No registry, global PATH, toolkit
or driver is modified. ASR defaults to CPU; optional CUDA ASR needs cuDNN9, which
this package does not include or claim to validate.

## Reproducible preparation

```sh
python scripts/build_windows_embedded.py --profile cpu --output .build/windows312-full-cpu-backend
python scripts/build_windows_embedded.py --profile cuda --output .build/windows312-cuda-ready-backend
node desktop/fetch-windows-electron.cjs --output .build/windows-electron
python scripts/assemble_windows_release.py --cpu-backend .build/windows312-full-cpu-backend --cuda-backend .build/windows312-cuda-ready-backend --electron-dist .build/windows-electron --models /existing/models --voices /existing/voices --asr /existing/faster-whisper-tiny --output /new/empty/package
```

The package assembler refreshes both source snapshots before comparing their
source ID. Original distribution/wheel URL/SHA and PE architecture are recorded.
Large immutable DLL/weight files can use local hardlinks during assembly; source,
configuration and metadata are independent copies. ZIP packaging materializes
normal files. Weights appear once under the shared backend, never in each profile.
Only model-manifest allowlisted weights and the four verified tiny files are
copied; arbitrary contents of a model directory are excluded.

On Windows, `build-windows.cmd` prepares project-local tools and follows the
prebuilt assembly route, performs native imports and the actual packaged GUI
smoke, and opens the result. `-CpuOnly` avoids the optional CUDA download;
`-WithoutModels` prepares the explicitly reduced package; `-NoOpen` prepares
without launching. `-NativeCompile` retains the earlier PyInstaller route.
PowerShell7 parser checks were actually run; Windows PowerShell5.1 execution is
still a separate target-machine check. No VS/C++ source build is the default.

## Local reports and acceptance

`诊断本机.cmd` records CPU model/logical cores, physical RAM, NVIDIA GPU name,
total/free VRAM and driver. No serials, UUIDs, window contents, conversation,
credentials or process list are read; it sends nothing externally. Driver551.61
is a conservative CUDA12.4 GA profile floor. NVIDIA's separate CUDA12.x minor
compatibility policy permits some older drivers under its documented limitations.
The renderer's2048MiB reserve is a planning allowance, not a measured requirement.

While the application is running, `测量运行资源.cmd` reads its loopback diagnostics
for30s. Proxying and redirects are disabled. It reports backend CPU time/private
memory and physical GPU snapshots locally; GPU/hardware samples can be cached
up to30s. It excludes Electron processes and cannot establish total app RAM,
renderer FPS, game impact, p95 latency or voice/visual quality. Those limits are
embedded in the JSON. The JSON is never automatically uploaded.

Target acceptance must record:

- Native imports, actual packaged PNG/VRM/voice paths, stop/hide/recover/exit and
  CPU/CUDA switch/failure recovery on the actual Windows device.
- Idle, text generation, playback, recognition and visible/hidden renderer
  measurements separately; confirm one model owner and retained renderer VRAM.
- Actual driver/GPU-offload evidence before labeling acceleration confirmed;
  compare CPU/CUDA latency using the same model, prompt/context and repeated runs.
- Real display/DPI/fullscreen behavior and reference-artwork quality; Linux/Xvfb
  shell tests and synthetic model fixtures do not prove these.

## Evidence and sources

Access date2026-11-12. The pinned values are in `scripts/windows-build-tools.json`
and each `embedded-runtime-manifest.json`:

- [Astral python-build-standalone20261110](https://github.com/astral-sh/python-build-standalone/releases/tag/20261110): CPython3.12.16 Windows x64. This is Astral's maintained distribution, not a python.org installer.
- [Official llama CPU0.3.36](https://github.com/abetlen/llama-cpp-python/releases/tag/v0.3.36) and [CUDA12.4 variant](https://github.com/abetlen/llama-cpp-python/releases/tag/v0.3.36-cu124).
- NVIDIA's [runtime12.4.127](https://pypi.org/project/nvidia-cuda-runtime-cu12/12.4.127/), [cuBLAS12.4.5.8](https://pypi.org/project/nvidia-cublas-cu12/12.4.5.8/) and [original driver compatibility tables](https://docs.nvidia.com/cuda/archive/12.4.0/cuda-toolkit-release-notes/index.html).
- [Microsoft VC++ prerequisite](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

Actually completed: hash/architecture assembly, synthetic policy/profile/startup
guard tests, Linux Electron window/IPC regression and PowerShell syntax parse.
Windows hardware, native CUDA execution, ASR CUDA, signed distribution and final
visual-quality acceptance remain unverified. License inventories/texts are
included; this is not a complete third-party redistribution/legal audit.
