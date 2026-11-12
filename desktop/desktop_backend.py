"""Packaged CUDA startup guard: load native dependencies before HTTP readiness.

No model weights are loaded, no network/account is contacted, and no driver or
global runtime is installed. Development server and CPU startup are unchanged.
"""
import ctypes
from pathlib import Path
import runpy
import sys

def preflight() -> None:
    from PIL import Image
    import llama_cpp
    import onnxruntime
    import ctranslate2
    base=Path(__file__).resolve().parent.parent
    # A fixed package path, never a model-, user-, or renderer-selected DLL.
    ctypes.WinDLL(str(base/'python/Lib/site-packages/llama_cpp/lib/ggml-cuda.dll'))
    llama_cpp.llama_backend_init()
    if not llama_cpp.llama_supports_gpu_offload():
        raise RuntimeError('GPU offload backend is unavailable')
    # This capability probe does not allocate an LLM or prove actual offload.

if __name__=='__main__':
    try:preflight()
    except Exception:
        print('COMPANION_CUDA_PREFLIGHT_FAILED: native dependencies or GPU backend unavailable',file=sys.stderr,flush=True)
        raise SystemExit(72)
    runpy.run_path(str(Path(__file__).with_name('server.py')),run_name='__main__')
