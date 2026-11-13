"""Assemble a no-compiler Windows portable from existing verified runtime profiles.

Native Windows execution, microphone, CUDA offload and quality acceptance remain
separate. Models are shared once by the CPU and CUDA backend profiles.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from build_windows_embedded import copy_sources,configure_runtime,write_profile_manifest,write_runtime_sitecustomize,sha256
ROOT=Path(__file__).resolve().parents[1]

def immutable_copy(source: str, target: str) -> str:
    src=Path(source);dst=Path(target)
    if dst.exists():
        if os.path.samefile(src,dst):return str(dst)
        dst.unlink()
    if src.suffix.lower() in {'.gguf','.onnx','.bin','.dll','.pyd','.exe','.lib'}:
        try:os.link(src,dst);return str(dst)
        except OSError:pass
    return shutil.copy2(src,dst)

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-backend',type=Path,required=True);parser.add_argument('--cuda-backend',type=Path)
    parser.add_argument('--electron-dist',type=Path,required=True);parser.add_argument('--node',default='node')
    parser.add_argument('--models',type=Path);parser.add_argument('--voices',type=Path);parser.add_argument('--asr',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    configure_runtime('standalone312','cpu')
    records=[]
    for profile,path in [('cpu',args.cpu_backend),('cuda',args.cuda_backend)]:
        if not path:continue
        metadata=json.loads((path/'embedded-runtime-manifest.json').read_text())
        if metadata['compute_profile']!=profile or metadata['python']['version']!='3.12.16':raise ValueError('Unexpected runtime profile/version')
        # Only generated source folders are replaced. Interpreter/wheels/models
        # are never rewritten while refreshing a software source snapshot.
        for folder in ['app','src']:
            if (path/folder).exists():shutil.rmtree(path/folder)
        copy_sources(path);write_runtime_sitecustomize(path);write_profile_manifest(path,profile)
        records.append({'profile':profile,'packages':len(metadata['packages']),'python':metadata['python'],'source_id':json.loads((path/'runtime-profile-manifest.json').read_text())['source_id']})
    command=[args.node,str(ROOT/'desktop/build-windows.cjs'),'--embedded-backend='+str(args.cpu_backend.resolve()),'--electron-dist='+str(args.electron_dist.resolve()),'--output='+str(args.output.resolve()),'--link-immutable']
    if args.cuda_backend:command.append('--cuda-backend='+str(args.cuda_backend.resolve()))
    subprocess.run(command,check=True,cwd=ROOT)
    backend=args.output/'resources/backend';assets=[]
    expected=json.loads((ROOT/'app/models-manifest.json').read_text())
    for item in expected:
        relative=Path(item['path']);source_root=args.models if relative.parts[0]=='models' else args.voices
        if not source_root:continue
        source=source_root.joinpath(*relative.parts[1:]);target=backend/relative
        if sha256(source)!=item['sha256']:raise ValueError('Original model checksum mismatch')
        target.parent.mkdir(parents=True,exist_ok=True);immutable_copy(str(source),str(target))
    if args.asr:
        source=json.loads((args.asr/'source.json').read_text());target=backend/'models/asr/faster-whisper-tiny'
        if source['revision']!='d90ca5fe260221311c53c58e660288d3deb8d356':raise ValueError('Unexpected ASR snapshot')
        if {item['name'] for item in source['files']}!={'config.json','model.bin','tokenizer.json','vocabulary.txt'}:raise ValueError('Unexpected ASR files')
        for item in source['files']:
            if sha256(args.asr/item['name'])!=item['sha256']:raise ValueError('ASR model checksum mismatch')
        target.mkdir(parents=True,exist_ok=True)
        for name in [item['name'] for item in source['files']]+['source.json']:
            immutable_copy(str(args.asr/name),str(target/name))
    for item in expected:
        file=backend/item['path']
        if file.exists():
            if sha256(file)!=item['sha256']:raise ValueError('Packaged model checksum mismatch')
            assets.append({'path':item['path'],'sha256':item['sha256'],'bytes':file.stat().st_size})
    for name in ['windows_device_diagnostics.py','measure_windows_runtime.py']:
        source=ROOT/'scripts'/name
        if source.exists():shutil.copy2(source,args.output/'resources/app'/name)
    diagnostic='@echo off\r\ncd /d "%~dp0"\r\n"%~dp0resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0resources\\app\\windows_device_diagnostics.py" --output "%~dp0diagnostics\\hardware.json"\r\npause\r\n'
    (args.output/'诊断本机.cmd').write_text(diagnostic,encoding='ascii',newline='')
    measurement='@echo off\r\ncd /d "%~dp0"\r\n"%~dp0resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0resources\\app\\measure_windows_runtime.py" --session "%~dp0resources\\runtime-session.json" --output "%~dp0diagnostics\\resources.json"\r\npause\r\n'
    (args.output/'测量运行资源.cmd').write_text(measurement,encoding='ascii',newline='')
    report={'kind':'Windows x64 portable assembly','native_windows_execution_verified':False,'cuda_offload_confirmed':False,
            'compiler_required':False,'global_runtime_or_driver_installed':False,'profiles':records,'shared_assets':assets,
            'asr_snapshot':args.asr is not None,'model_copies_per_package':1,'models_shared_between_profiles':True}
    (args.output/'ASSEMBLY-INFO.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with (args.output/'README.txt').open('a',encoding='utf-8') as stream:
        stream.write('\n此包不需要Python、Node或Visual Studio编译。请完整解压后运行companion-desktop.exe。\n显式切换CPU/CUDA：先退出软件，再运行“使用CPU.cmd”或“使用CUDA.cmd”；设置中选择CPU/CUDA/自动。切换不复制模型，失败回退CPU。\n“诊断本机.cmd”只保存本机硬件信息；软件运行时可执行“测量运行资源.cmd”。报告留在本机，不自动发送。\n尚未在目标Windows真机完成运行、CUDA或最终画质验收。缺少微软VC++ x64运行库时会明确提示官方入口，不自动修改系统。\n')
        stream.write('CUDA配置内置对应cuBLAS/cudart；仍需本机NVIDIA驱动。语音识别默认CPU，本包未内置CUDA-ASR所需cuDNN，未承诺GPU-ASR。\n')
    print(json.dumps({'output':str(args.output),'profiles':[r['profile'] for r in records],'native_windows_execution_verified':False}))

if __name__=='__main__':main()
