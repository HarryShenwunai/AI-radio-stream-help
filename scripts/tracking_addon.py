"""Install a single SHA-locked optional Windows face-tracking add-on offline.

Only adds resources/optional/tracking. Existing profiles, DLLs, models and user
data are outside the write set. Close the application before running this tool.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from ui_update import UpdateError, atomic_write, digest, lease, relative, safe

MANIFEST_SHA='a72ef9399f156c76874ccda0357295b9123305e5b923ed7bf3d8673cf5484f8b'
MANIFEST_FILE_SHA='de08abac2f341d0cacf2eba38fc89e53bef0252f98cc2f258736b95ed95bad12'
ARCHIVE_SHA='4b3f763179bf771cd8466082114f9f9e4c87c0aab0d7caaacdab2fd705fccf21'
ARCHIVE_BYTES=83_452_536
TARGET='resources/optional/tracking'
STAGE='resources/optional/.tracking-stage-'+MANIFEST_SHA[:16]
BACKUP='resources/optional/tracking-disabled-'+MANIFEST_SHA[:16]
MANIFEST='tracking-addon-manifest.json'
FIXED_FILES=frozenset({MANIFEST,'models/face_landmarker.task','WHEEL-PROVENANCE.json','NOTICE-TRACKING.txt','LICENSE-MEDIAPIPE-MODEL.txt'})

def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def allowed(path: str) -> bool:
    relative(path)
    if path in FIXED_FILES:return True
    if not path.startswith('python312/site-packages/'):return False
    parts=path.split('/')
    return not any(part.endswith((' ','.')) or part.casefold() in {'__pycache__','sitecustomize.py','usercustomize.py'} or
                   part.split('.')[0].casefold() in {'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]} for part in parts) and not path.casefold().endswith(('.pth','.pyc'))

def manifest_from_bytes(data: bytes) -> dict:
    if len(data)>1024*1024:raise UpdateError('跟踪扩展清单过大。')
    value=json.loads(data)
    if hashlib.sha256(data).hexdigest()!=MANIFEST_FILE_SHA or not isinstance(value,dict) or canonical_hash(value)!=MANIFEST_SHA or value.get('format')!='companion-tracking-addon-v1' or value.get('python')!='cp312-win_amd64':
        raise UpdateError('不是固定SHA的官方依赖扩展包。')
    names=set();total=0
    for row in value['files']:
        name=row['path']
        if not allowed(name) or name.casefold() in names or not isinstance(row['bytes'],int) or row['bytes']<0:
            raise UpdateError('扩展清单路径或大小无效。')
        names.add(name.casefold());total+=row['bytes']
    if not 1<=len(names)<=3000 or total>400*1024*1024:raise UpdateError('扩展文件数量或总大小异常。')
    return value

def verify_directory(folder: Path, manifest: dict) -> None:
    wanted={row['path']:row for row in manifest['files']}
    actual=set()
    for file in folder.rglob('*'):
        if file.is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(file)):raise UpdateError('扩展目录包含链接。')
        if file.is_file():actual.add(file.relative_to(folder).as_posix())
    if actual!=set(wanted)|{MANIFEST}:raise UpdateError('扩展目录含缺失或额外文件；不会强制覆盖。')
    manifest_from_bytes(safe(folder,MANIFEST).read_bytes())
    for name,row in wanted.items():
        file=safe(folder,name)
        if file.stat().st_size!=row['bytes'] or digest(file)!=row['sha256']:raise UpdateError('扩展文件SHA不匹配：'+name)

def install(root: Path, archive: Path, remove: bool=False) -> dict:
    root=root.resolve()
    if not (root/'companion-desktop.exe').is_file() or not (root/'resources/backend/python/python.exe').is_file():
        raise UpdateError('请选择完整解压的Windows候选包目录。')
    with lease(root):
        target=safe(root,TARGET);stage=safe(root,STAGE);backup=safe(root,BACKUP)
        if remove:
            if not target.exists():return {'status':'already_absent','windows_execution_verified':False}
            manifest=manifest_from_bytes(safe(target,MANIFEST).read_bytes());verify_directory(target,manifest)
            if backup.exists():raise UpdateError('可恢复备份已存在，未覆盖。')
            os.replace(target,backup)
            return {'status':'disabled','backup':BACKUP,'windows_execution_verified':False}
        if archive.stat().st_size!=ARCHIVE_BYTES or digest(archive)!=ARCHIVE_SHA:raise UpdateError('扩展ZIP大小或SHA与已锁发布包不匹配。')
        with zipfile.ZipFile(archive) as package:
            manifest_bytes=package.read(MANIFEST);manifest=manifest_from_bytes(manifest_bytes)
            if target.exists():
                verify_directory(target,manifest)
                return {'status':'already_installed','windows_execution_verified':False}
            infos=package.infolist();wanted={row['path']:row for row in manifest['files']};names=set()
            for info in infos:
                name=info.filename
                if info.is_dir() or not allowed(name) or name.casefold() in names or stat.S_ISLNK(info.external_attr>>16):raise UpdateError('ZIP含非锁定成员、目录、链接或大小写重复路径。')
                names.add(name.casefold())
                expected=wanted.get(name)
                if name!=MANIFEST and (not expected or info.file_size!=expected['bytes']):raise UpdateError('ZIP成员与锁清单不符。')
            if {info.filename for info in infos}!=set(wanted)|{MANIFEST}:raise UpdateError('ZIP成员集合不匹配。')
            if stage.exists():
                # Only delete a known interrupted staging directory containing no
                # links or paths outside this exact locked manifest.
                expected_names=set(wanted)|{MANIFEST}
                for file in stage.rglob('*'):
                    if file.is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(file)) or (file.is_file() and file.relative_to(stage).as_posix() not in expected_names):
                        raise UpdateError('残留暂存目录有未知文件，未清除。')
                shutil.rmtree(stage)
            stage.mkdir(parents=True)
            try:
                for info in infos:
                    data=package.read(info)
                    if info.filename!=MANIFEST and hashlib.sha256(data).hexdigest()!=wanted[info.filename]['sha256']:raise UpdateError('解包成员SHA失败。')
                    atomic_write(safe(stage,info.filename),data)
                verify_directory(stage,manifest)
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():raise UpdateError('目标目录在安装期间出现，未覆盖。')
                os.replace(stage,target)
            except Exception:
                # Keep this bounded staging tree for a future verified retry.
                raise
        return {'status':'installed','path':TARGET,'windows_execution_verified':False,'old_profile_native_files_modified':False,'physical_gaze_verified':False}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--archive',type=Path,default=Path(__file__).resolve().parent/'tracking-addon-cp312-win-x64-v3.zip');parser.add_argument('--remove',action='store_true');args=parser.parse_args()
    if os.name!='nt':raise UpdateError('请在Windows运行交付安装器；跨平台解包不等于Windows DLL测试。')
    target=args.target.parent if args.target.name.lower()=='companion-desktop.exe' else args.target
    print(json.dumps(install(target,args.archive,args.remove),ensure_ascii=False));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (UpdateError,OSError,ValueError,KeyError,zipfile.BadZipFile) as error:
        print('跟踪扩展安装已停止：'+str(error),file=sys.stderr);raise SystemExit(1)
