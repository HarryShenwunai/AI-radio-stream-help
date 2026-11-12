#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Use an environment with the optional inference dependencies already installed.
# Assets and user data are deliberately excluded from this build step.
"${COMPANION_BUILD_PYTHON:-python}" -m PyInstaller --noconfirm --onedir --name companion-backend \
  --distpath .build/native --workpath .build/pyinstaller --specpath .build \
  --paths "$(pwd)/src" --add-data "$(pwd)/app/static:static" \
  --hidden-import PIL.PngImagePlugin \
  --collect-all llama_cpp --collect-all kokoro_onnx \
  --collect-all espeakng_loader --collect-all pypinyin \
  --collect-all pypinyin_dict --collect-all jieba \
  --collect-data misaki --collect-all onnxruntime \
  --exclude-module pandas --exclude-module scipy \
  --exclude-module IPython --exclude-module jedi \
  --exclude-module matplotlib --exclude-module tkinter "$(pwd)/app/server.py"
