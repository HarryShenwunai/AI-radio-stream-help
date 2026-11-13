"""Transactional UI-only update for the published Windows candidate.

The host guard deliberately does not interpret this journal. Only this trusted
updater can complete/restore its fixed set of UI and metadata paths. Models,
native libraries, accounts, user data and SDKs are outside its write set.
"""
from __future__ import annotations
from contextlib import contextmanager
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
from typing import Callable
from urllib.parse import urlsplit

FORMAT = 'companion-ui-update-v1'
UI_FILES = frozenset({'index.html','style.css','app.js','desktop.css','desktop.js'})
PROFILES = {'cpu':'resources/backend','cuda':'resources/backend-profiles/cuda'}
HOST = 'resources/app/main.cjs'
METADATA = frozenset({'BUILD-INFO.json','ASSEMBLY-INFO.json','SOURCE-COMMIT.txt','SHA256SUMS.txt',
                      'UI-UPDATE-INFO.json','VALIDATION/ui-update-checks.json',
                      *[base+'/runtime-profile-manifest.json' for base in PROFILES.values()]})
JOURNAL = 'resources/ui-update-journal.json'
SESSION = 'resources/runtime-session.json'

class UpdateError(Exception): pass

def digest(file: Path) -> str:
    with file.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def file_hash(file: Path) -> str | None:
    return digest(file) if file.is_file() else None

def relative(value: str) -> Path:
    if not isinstance(value,str) or '\\' in value or ':' in value:
        raise UpdateError('更新清单路径无效。')
    path=Path(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:raise UpdateError('更新清单路径越界。')
    return path

def safe(root: Path, value: str) -> Path:
    path=root/relative(value)
    current=root
    for part in path.relative_to(root).parts:
        current=current/part
        if current.is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(current)):
            raise UpdateError('更新路径包含链接或目录重解析点，已停止。')
    return path

def read_json(file: Path, limit: int=1024*1024) -> dict:
    if file.stat().st_size>limit:raise UpdateError('更新清单过大。')
    value=json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(value,dict):raise UpdateError('更新清单格式无效。')
    return value

def atomic_write(file: Path, data: bytes) -> None:
    file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_name(file.name+'.ui-tmp-'+str(os.getpid()))
    with temporary.open('wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,file)

def process_alive(pid: int) -> bool:
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except ProcessLookupError:return False
        except PermissionError:return True
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return ctypes.get_last_error()==5
    try:
        code=ctypes.c_ulong();return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:kernel.CloseHandle(handle)

def backend_reachable(value: object) -> bool:
    if not isinstance(value,str):return False
    parsed=urlsplit(value)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'} or not parsed.port:
        raise UpdateError('旧运行锁中的本机地址无效。')
    if parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:
        raise UpdateError('旧运行锁中的本机地址无效。')
    try:
        with socket.create_connection((parsed.hostname,parsed.port),timeout=.4):return True
    except OSError:return False

@contextmanager
def lease(root: Path):
    file=safe(root,SESSION)
    if file.exists():
        state=read_json(file,4096);pid=state.get('pid')
        if isinstance(pid,int) and 0<pid<2**32 and process_alive(pid):
            raise UpdateError('请先从托盘退出软件；更新尚未修改任何程序文件。')
        if backend_reachable(state.get('backend_origin')):
            raise UpdateError('本机服务仍在运行，请先退出软件；不会强制结束其它进程。')
        file.unlink()
    try:
        with file.open('x',encoding='utf-8') as stream:
            json.dump({'pid':os.getpid(),'kind':'ui-update'},stream);stream.flush();os.fsync(stream.fileno())
    except FileExistsError:raise UpdateError('另一个程序正在使用此运行目录。')
    try:yield
    finally:
        try:
            if read_json(file,4096).get('pid')==os.getpid():file.unlink()
        except OSError:pass

def load_update(folder: Path) -> dict:
    manifest=read_json(folder/'ui-update-manifest.json')
    if manifest.get('format')!=FORMAT or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',manifest.get('update_id','')):
        raise UpdateError('不是受支持的界面更新包。')
    if set(manifest['profiles'])!={'cpu','cuda'}:raise UpdateError('更新必须同时包含两个已发布配置。')
    operations=manifest['files']
    if not isinstance(operations,list) or not 1<=len(operations)<=32:raise UpdateError('更新文件数量无效。')
    seen=set()
    for operation in operations:
        target=operation['target']
        ui=next((target==base+'/app/static/'+name for base in PROFILES.values() for name in UI_FILES if target==base+'/app/static/'+name),False)
        if target not in METADATA and target!=HOST and not ui:raise UpdateError('更新包含非界面路径。')
        if target in seen:raise UpdateError('更新路径重复。')
        seen.add(target);relative(target)
        if not re.fullmatch('[a-f0-9]{64}',operation['new_sha256']):raise UpdateError('新文件SHA无效。')
        old=operation['old_sha256']
        if old is not None and not re.fullmatch('[a-f0-9]{64}',old):raise UpdateError('旧文件SHA无效。')
        payload=operation['payload']
        if not payload.startswith('payload/'):raise UpdateError('更新负载路径无效。')
        file=safe(folder,payload)
        if file_hash(file)!=operation['new_sha256']:raise UpdateError('更新包SHA校验失败；没有覆盖程序文件。')
    if HOST not in seen or not {base+'/runtime-profile-manifest.json' for base in PROFILES.values()}<=seen:
        raise UpdateError('缺少启动保护或配置清单。')
    for name,base in PROFILES.items():
        old=manifest['profiles'][name]['old'];new=manifest['profiles'][name]['new']
        if old['critical_files']!=new['critical_files']:raise UpdateError('界面更新不得更改原生组件或服务端关键SHA。')
        if old['source_id']!=manifest['base_source_id'] or new['source_id']!=manifest['new_source_id']:
            raise UpdateError('CPU/CUDA界面来源不一致。')
        for record in (old,new):
            calculated=hashlib.sha256(json.dumps(record['source_files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if record['source_id']!=calculated:raise UpdateError('配置来源SHA不一致。')
            for path in record['source_files']:
                if not path.startswith(('app/','src/')) or path.startswith(('app/data/','app/models/','app/voices/')):
                    raise UpdateError('来源清单含非程序路径。')
                relative(base+'/'+path)
    return manifest

def paths(root: Path, manifest: dict) -> tuple[Path,Path]:
    identity=manifest['update_id']
    return safe(root,'resources/.ui-stage-'+identity),safe(root,'resources/ui-update-backups/'+identity)

def static_map(profile: dict) -> dict[str,str]:
    return {Path(path).name:value for path,value in profile['source_files'].items() if path.startswith('app/static/')}

def check_static(directory: Path, expected: dict[str,str]) -> bool:
    if not directory.is_dir():return False
    if {p.name for p in directory.iterdir()}!=set(expected):return False
    return all(not (directory/name).is_symlink() and (directory/name).is_file() and digest(directory/name)==value for name,value in expected.items())

def verify_state(root: Path, manifest: dict, which: str, bootstrap_ok: bool=False) -> None:
    _,backup=paths(root,manifest)
    for operation in manifest['files']:
        wanted=operation['old_sha256' if which=='old' else 'new_sha256'];actual=file_hash(safe(root,operation['target']))
        if bootstrap_ok and operation['target']==HOST and actual==operation['new_sha256'] and file_hash(backup/'files'/HOST)==operation['old_sha256']:continue
        if actual!=wanted:raise UpdateError('现有文件SHA不匹配，拒绝覆盖：'+operation['target'])
    for name,base in PROFILES.items():
        profile=manifest['profiles'][name][which]
        if not check_static(safe(root,base+'/app/static'),static_map(profile)):
            raise UpdateError('现有界面目录有改动或多余文件，拒绝覆盖。')
        for relative_name,wanted in profile['source_files'].items():
            if file_hash(safe(root,base+'/'+relative_name))!=wanted:raise UpdateError('程序来源不匹配，拒绝更新。')

def write_journal(root: Path, manifest: dict, phase: str) -> None:
    # No destination/backup paths from this file are ever executed/interpreted.
    atomic_write(safe(root,JOURNAL),(json.dumps({'format':FORMAT,'update_id':manifest['update_id'],'phase':phase})+'\n').encode())

def restore(root: Path, manifest: dict) -> None:
    stage,backup=paths(root,manifest)
    for name,base in PROFILES.items():
        target=safe(root,base+'/app/static');saved=backup/'static'/name
        old=static_map(manifest['profiles'][name]['old']);new=static_map(manifest['profiles'][name]['new'])
        if check_static(target,old):continue
        if not check_static(saved,old):raise UpdateError('旧界面备份缺失或损坏，保留事务以便修复。')
        if target.exists():
            if not check_static(target,new):raise UpdateError('更新后文件另有修改，保留事务，未强制覆盖。')
            temporary=stage/('discard-'+name);temporary.parent.mkdir(parents=True,exist_ok=True)
            if temporary.exists():shutil.rmtree(temporary)
            os.replace(target,temporary)
        target.parent.mkdir(parents=True,exist_ok=True);os.replace(saved,target)
    # Restore the host last, after both UIs and all metadata are coherent again.
    for operation in sorted(manifest['files'],key=lambda item:item['target']==HOST):
        target=safe(root,operation['target']);old=operation['old_sha256'];current=file_hash(target)
        if current==old:continue
        if current not in {None,operation['new_sha256']}:raise UpdateError('程序文件另有修改，未强制覆盖。')
        saved=backup/'files'/relative(operation['target'])
        if old is None:
            if target.exists():target.unlink()
        else:
            if file_hash(saved)!=old:raise UpdateError('旧文件备份校验失败。')
            atomic_write(target,saved.read_bytes())
    verify_state(root,manifest,'old')
    journal=safe(root,JOURNAL)
    if journal.exists():journal.unlink()
    if stage.exists():shutil.rmtree(stage)

def execute(root: Path, folder: Path, rollback: bool=False,
            fault: Callable[[str],None] | None=None) -> dict:
    root=root.resolve();folder=folder.resolve();manifest=load_update(folder)
    if not (root/'companion-desktop.exe').is_file() or not (root/'resources/backend/python/python.exe').is_file():
        raise UpdateError('请选择已完整解压的旧Windows候选包目录。')
    stage,backup=paths(root,manifest);notify=fault or (lambda phase:None)
    with lease(root):
        journal=safe(root,JOURNAL)
        if journal.exists():
            state=read_json(journal,4096)
            if state.get('format')!=FORMAT or state.get('update_id')!=manifest['update_id']:
                raise UpdateError('请先使用对应版本的可信更新器恢复上一次事务。')
            restore(root,manifest)
        if rollback:
            try:verify_state(root,manifest,'old')
            except UpdateError:
                write_journal(root,manifest,'rollback');restore(root,manifest)
            return {'status':'rolled_back','update_id':manifest['update_id'],'windows_application_verified':False}
        try:verify_state(root,manifest,'new')
        except UpdateError:pass
        else:return {'status':'already_applied','update_id':manifest['update_id'],'windows_application_verified':False}
        verify_state(root,manifest,'old',bootstrap_ok=True)
        if stage.exists():shutil.rmtree(stage)
        stage.mkdir(parents=True)
        for name,base in PROFILES.items():
            shutil.copytree(safe(root,base+'/app/static'),stage/('static-'+name))
        for operation in manifest['files']:
            destination=safe(root,operation['target']);old=operation['old_sha256'];saved=backup/'files'/relative(operation['target'])
            if old is not None:
                if saved.exists():
                    if file_hash(saved)!=old:raise UpdateError('既有备份SHA不匹配，停止更新。')
                else:atomic_write(saved,destination.read_bytes())
            for name,base in PROFILES.items():
                prefix=base+'/app/static/'
                if operation['target'].startswith(prefix):atomic_write(stage/('static-'+name)/Path(operation['target']).name,safe(folder,operation['payload']).read_bytes())
        bootstrap=next(item for item in manifest['files'] if item['target']==HOST)
        atomic_write(safe(root,HOST),safe(folder,bootstrap['payload']).read_bytes());notify('after-bootstrap')
        write_journal(root,manifest,'prepared')
        try:
            notify('after-journal')
            for name,base in PROFILES.items():
                saved=backup/'static'/name;saved.parent.mkdir(parents=True,exist_ok=True)
                if saved.exists():
                    if not check_static(saved,static_map(manifest['profiles'][name]['old'])):raise UpdateError('旧界面备份损坏。')
                    shutil.rmtree(saved)
                os.replace(safe(root,base+'/app/static'),saved);notify('after-'+name+'-backup')
                os.replace(stage/('static-'+name),safe(root,base+'/app/static'));notify('after-'+name+'-static')
                write_journal(root,manifest,name+'-static')
            for index,operation in enumerate(manifest['files']):
                if operation['target']==HOST or '/app/static/' in operation['target']:continue
                atomic_write(safe(root,operation['target']),safe(folder,operation['payload']).read_bytes());notify('after-metadata-'+str(index))
                write_journal(root,manifest,'metadata-'+str(index))
            verify_state(root,manifest,'new');notify('before-commit')
            write_journal(root,manifest,'committed');journal.unlink()
            if stage.exists():shutil.rmtree(stage)
            return {'status':'applied','update_id':manifest['update_id'],'windows_application_verified':False}
        except Exception:
            restore(root,manifest)
            raise

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--update-root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
    if os.name!='nt':raise UpdateError('发布更新器请在Windows运行；跨平台文件测试不等于Windows验证。')
    target=args.target
    if target.name.lower()=='companion-desktop.exe':target=target.parent
    value=execute(target,args.update_root,args.rollback)
    print(json.dumps(value,ensure_ascii=False));print('界面操作已完成。角色、聊天、密钥、SDK和模型未被修改。备份保留在resources/ui-update-backups。')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (UpdateError,OSError,ValueError,KeyError) as error:
        print('更新已停止：'+str(error),file=sys.stderr)
        print('若提示未完成事务，请重跑同一可信更新器或rollback-ui-update.cmd；不要删除备份或运行锁。',file=sys.stderr)
        raise SystemExit(1)
