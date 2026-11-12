"""按明确来源下载本地模型。不会读取或上传聊天数据。"""
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib
import json
import os
import sys

root=Path(__file__).resolve().parent
QWEN='https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/resolve/ae44f08e1392f39c0e474af10c3ff8355c8b6688/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
FILES=[
 ('models/qwen3-4b-instruct-2507-q4_k_m.gguf',QWEN,'2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e'),
 ('voices/kokoro-v1.0.onnx','https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx','beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a'),
 ('voices/voices-v1.0.bin','https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin','bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'),
]
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
for name,url,expected in FILES:
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if expected and digest(target)!=expected:raise SystemExit('已有模型校验失败，请先移走文件：'+str(target))
        print('已存在：',name);continue
    part=target.with_suffix(target.suffix+'.part');offset=part.stat().st_size if part.exists() else 0
    headers={'User-Agent':'XiaoLan-Local-Companion/0.2'}
    if offset:headers['Range']=f'bytes={offset}-'
    print('下载：',name,'（支持断点续传）',flush=True)
    try:
        with urlopen(Request(url,headers=headers),timeout=90) as response:
            append=offset>0 and response.status==206
            if not append:offset=0
            total=offset+int(response.headers.get('Content-Length',0));done=offset;last=-1
            with part.open('ab' if append else 'wb') as out:
                while block:=response.read(1024*1024):
                    out.write(block);done+=len(block)
                    progress=int(done*100/total) if total else 0
                    if progress//10!=last:print(f'  {progress}% · {done//1048576} MB',flush=True);last=progress//10
        if expected and digest(part)!=expected:raise RuntimeError('SHA256 校验失败，请重下此文件')
        part.replace(target)
    except Exception as e:raise SystemExit('下载未完成，保留断点。再次运行可继续。'+str(e))
print('模型已准备好，可运行启动脚本。')
