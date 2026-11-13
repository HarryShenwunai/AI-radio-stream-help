"""Switch a packaged, same-source runtime only after the application exits."""
from __future__ import annotations
import argparse,ctypes,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path

def read_json(path: Path) -> dict:
    if path.stat().st_size>65536:raise ValueError('运行时元数据过大。')
    return json.loads(path.read_text(encoding='utf-8'))

def process_alive(pid: int) -> bool:
    if os.name!='nt':raise RuntimeError('请在Windows中运行。')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return ctypes.get_last_error()==5
    try:
        code=ctypes.c_ulong();kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:kernel.CloseHandle(handle)

def choose(resources: Path, profile: str) -> Path:
    if profile not in {'cpu','cuda'}:raise ValueError('只支持CPU或CUDA配置。')
    return resources/'backend' if profile=='cpu' else resources/'backend-profiles/cuda'

def verify(resources: Path, profile: str) -> dict:
    baseline=read_json(choose(resources,'cpu')/'runtime-profile-manifest.json')
    target=choose(resources,profile);manifest=read_json(target/'runtime-profile-manifest.json')
    if manifest['source_id']!=baseline['source_id'] or manifest['python_version']!=baseline['python_version']:
        raise ValueError('目标运行时与当前程序不同源；请使用同一版本完整包。')
    for name,expected in manifest['critical_files'].items():
        relative=Path(name)
        if relative.is_absolute() or relative.drive or '..' in relative.parts:raise ValueError('运行时清单路径无效。')
        file=target/relative
        with file.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=expected:raise ValueError('运行时校验失败，请重新完整解压。')
    return manifest

def select(resources: Path, profile: str, fallback: str | None=None) -> None:
    file=resources/'active-runtime-profile.json';old=read_json(file) if file.exists() else {'profile':'cpu'}
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=resources,prefix='.profile-',suffix='.tmp',delete=False) as stream:
        temporary=Path(stream.name);json.dump({'profile':profile,'previous_profile':old.get('profile','cpu'),'fallback':fallback},stream,ensure_ascii=False)
    os.replace(temporary,file)

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',choices=['cpu','cuda'],required=True);parser.add_argument('--launch',action='store_true');args=parser.parse_args()
    if os.name!='nt':raise RuntimeError('此入口必须在Windows运行，组装不能代替验收。')
    resources=Path(__file__).resolve().parent.parent;portable=resources.parent
    session=resources/'runtime-session.json'
    if session.exists():
        pid=read_json(session).get('pid')
        if isinstance(pid,int) and 0<pid<2**32 and process_alive(pid):raise RuntimeError('请先从托盘退出软件，再切换运行时；不会同时加载两套模型。')
    verify(resources,args.profile)
    target=choose(resources,args.profile)
    probe="import ctypes;from PIL import Image;import llama_cpp,onnxruntime,kokoro_onnx,espeakng_loader;ctypes.CDLL(espeakng_loader.get_library_path());print('Native imports passed')"
    if args.profile=='cuda':probe+=";llama_cpp.llama_backend_init();assert llama_cpp.llama_supports_gpu_offload(),'No usable GPU offload backend';llama_cpp.llama_backend_free()"
    env=dict(os.environ);env.pop('CUDA_PATH',None);env.pop('HIP_PATH',None)
    result=subprocess.run([str(target/'python/python.exe'),'-I','-X','utf8','-c',probe],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    if result.returncode:
        if args.profile=='cpu':raise RuntimeError('本机原生依赖未通过。请查看Microsoft官方VC++ x64运行库说明：https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist 。程序不会自动安装全局运行库。')
        verify(resources,'cpu');select(resources,'cpu','CUDA原生依赖预检失败，已恢复CPU配置。');print('CUDA依赖未通过，已退回CPU；未安装或更改任何系统驱动/运行库。')
    else:select(resources,args.profile);print('运行时配置已切换：'+args.profile+'。实际GPU卸载仍需在设置启用并验证。')
    if args.launch:subprocess.Popen([str(portable/'companion-desktop.exe')],cwd=portable)

if __name__=='__main__':
    try:main()
    except Exception as error:print(str(error),file=sys.stderr);raise SystemExit(1)
