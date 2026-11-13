"""Recoverable, explicitly allowlisted source update for the published d01 base.

No model, DLL, SDK, account, user data or character directory may be written.
This is an unsigned package: obtain its SHA from the project's trusted Release.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Callable

# Windows delivery uses -I: explicitly load only the trusted sibling helper.
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ui_update import UpdateError, atomic_write, digest, file_hash, lease, read_json, relative, safe

FORMAT = 'companion-app-source-update-v2'
BASE_COMMIT = 'd01ccc42bbe6795c216afae37dd0e53128ab58d9'
BASE_ARCHIVE_SHA = '92d3e858cb93471b1fe4e633e2b5328aa43dc178f325a9bfa65ca62d1405b7e3'
BASE_PROFILE_SHA = {'cpu':'ddb6282ec5ce07d9eadbb68101bff94d7dc89d88ee90d7fc2612faafc3062dff',
                    'cuda':'257471b93a849124f506995350eaa9027c16e186902349ed19208559315b44f8'}
BASE_HOST_SHA = '7874d91e87f1c23610da8e80e4dbf655e11d37c27f73b4532879444eee97f6fc'
PROFILES = {'cpu':'resources/backend','cuda':'resources/backend-profiles/cuda'}
HOST = 'resources/app/main.cjs'
HOST_FILES = frozenset({'package.json','main.cjs','preload.cjs','window-policy.cjs','media-policy.cjs','screen-capture.cjs','screen-capture.html','screen-capture-view.js','screen-capture.css','owner-runtime-path.cjs'})
STATIC_FILES = frozenset({'index.html','style.css','app.js','desktop.css','desktop.js','avatar.svg',
    'connectors-ui.js','live2d-renderer.js','playback-receipts.js','voice-input.js','vrm-renderer.js',
    'ui-kit.js','companion-core.js','scene-controller.js','stage-actions.js','speech-controller.js','conversation-view.js',
    'studio.js','connection-flow.js','sound-flow.js','privacy-flow.js','assistance-view.js','layered-2d-renderer.js',
    'scene-morning.png','scene-forest.png','scene-evening.png'})
RUNTIME_FILES = frozenset({'__init__.py','assets.py','characters.py','conversation.py','device_diagnostics.py',
    'http_payload.py','integration_service.py','lifecycle.py','live.py','live2d_assets.py','live2d_runtime.py',
    'playback.py','runtime_settings.py','voice.py','vrm_assets.py','zerolan.py','assistance.py','perception.py','devices.py',
    'perception_tracking.py','perception_optional.py','layered_2d_assets.py','preference_learning.py'})
PROGRAM_FILES = frozenset({'app/server.py', *['app/static/'+name for name in STATIC_FILES],
                          *['src/companion_runtime/'+name for name in RUNTIME_FILES]})
METADATA = frozenset({'BUILD-INFO.json','ASSEMBLY-INFO.json','SOURCE-COMMIT.txt','SHA256SUMS.txt',
    'APP-UPDATE-INFO.json','VALIDATION/app-update-checks.json',
    *[base+'/runtime-profile-manifest.json' for base in PROFILES.values()]})
JOURNAL = 'resources/ui-update-journal.json'  # Also recognized by the small startup guard.
MAX_PAYLOAD = 64*1024*1024

def canonical_hash(record: dict) -> str:
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_desktop_metadata(package: bytes, server: bytes | None=None) -> dict:
    """Keep Electron's version aligned without changing its data identity/entry."""
    try:metadata=json.loads(package)
    except (ValueError,UnicodeError) as error:raise UpdateError('桌面package.json不是有效JSON。') from error
    if not isinstance(metadata,dict) or metadata.get('name')!='companion-desktop-runtime' or metadata.get('main')!='main.cjs':
        raise UpdateError('桌面应用名称与入口必须保持原值，防止改变用户数据路径。')
    version=metadata.get('version')
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',version):
        raise UpdateError('桌面应用版本无效。')
    if server is not None:
        try:
            tree=ast.parse(server)
            values=[node.value.value for node in tree.body if isinstance(node,ast.Assign)
                    and any(isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets)
                    and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)]
        except (SyntaxError,ValueError,UnicodeError) as error:raise UpdateError('无法静态读取服务端版本。') from error
        if values!=[version]:raise UpdateError('桌面与服务端版本必须一致。')
    return metadata

def allowed_target(target: str) -> bool:
    return target in METADATA or target in {'resources/app/'+name for name in HOST_FILES} or any(
        target == base+'/'+name for base in PROFILES.values() for name in PROGRAM_FILES)

def load_update(folder: Path) -> dict:
    manifest=read_json(safe(folder,'app-update-manifest.json'))
    if manifest.get('format')!=FORMAT or manifest.get('base_source_commit')!=BASE_COMMIT or manifest.get('base_archive_sha256')!=BASE_ARCHIVE_SHA:
        raise UpdateError('更新与已发布的基础候选包不匹配。')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',manifest.get('update_id','')) or not re.fullmatch('[a-f0-9]{40}',manifest.get('new_source_commit','')):
        raise UpdateError('更新标识无效。')
    if set(manifest.get('profiles',{}))!=set(PROFILES):raise UpdateError('更新必须包含CPU和CUDA两个配置。')
    operations=manifest.get('files')
    if not isinstance(operations,list) or not 1<=len(operations)<=128:raise UpdateError('更新文件数量无效。')
    seen={};total=0
    for operation in operations:
        target=operation['target'];relative(target)
        if not allowed_target(target) or target in seen:raise UpdateError('更新路径不在固定程序白名单中或重复。')
        seen[target]=operation
        for key in ['new_sha256','old_sha256']:
            value=operation[key]
            if key=='old_sha256' and value is None:continue
            if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise UpdateError('文件SHA无效。')
        payload=operation['payload']
        if not payload.startswith('payload/'):raise UpdateError('负载路径无效。')
        file=safe(folder,payload);size=file.stat().st_size;total+=size
        if size!=operation['bytes'] or size>20*1024*1024 or file_hash(file)!=operation['new_sha256']:raise UpdateError('更新负载大小或SHA不匹配。')
    if total>MAX_PAYLOAD:raise UpdateError('程序更新超过64MiB；模型或其它大文件不属于此更新。')
    if not {HOST,'resources/app/package.json',*METADATA}<=set(seen):raise UpdateError('更新缺少启动保护或元数据。')
    package=safe(folder,seen['resources/app/package.json']['payload']).read_bytes()
    validate_desktop_metadata(package)
    for name,base in PROFILES.items():
        old=manifest['profiles'][name]['old'];new=manifest['profiles'][name]['new']
        if canonical_hash(old)!=BASE_PROFILE_SHA[name]:raise UpdateError('基础配置不是已发布的固定版本。')
        for value in [old,new]:
            if value['source_id']!=canonical_hash(value['source_files']):raise UpdateError('程序来源SHA不匹配。')
        if old['source_id']!=manifest['base_source_id'] or new['source_id']!=manifest['new_source_id']:raise UpdateError('CPU/CUDA程序来源不一致。')
        if not set(old['source_files'])<=set(new['source_files']):raise UpdateError('此更新不支持删除原程序文件。')
        for source,wanted in new['source_files'].items():
            if not isinstance(source,str) or not isinstance(wanted,str) or not re.fullmatch('[a-f0-9]{64}',wanted):
                raise UpdateError('程序来源成员或SHA无效。')
            relative(source)
            if source not in old['source_files'] and source not in PROGRAM_FILES:raise UpdateError('新增来源不在固定程序白名单中。')
            before=old['source_files'].get(source)
            if before==wanted:continue
            operation=seen.get(base+'/'+source)
            if source not in PROGRAM_FILES or not operation or operation['old_sha256']!=before or operation['new_sha256']!=wanted:
                raise UpdateError('程序来源改动没有相应的固定白名单负载。')
        for target,operation in seen.items():
            if not target.startswith(base+'/'):continue
            source=target[len(base)+1:]
            if source=='runtime-profile-manifest.json':continue
            if old['source_files'].get(source)!=operation['old_sha256'] or new['source_files'].get(source)!=operation['new_sha256']:
                raise UpdateError('负载与程序来源清单不一致。')
        expected=dict(old['critical_files']);expected['app/server.py']=new['source_files']['app/server.py']
        if new['critical_files']!=expected:raise UpdateError('此更新不得替换原生解释器、DLL或推理运行库。')
        if new['python_version']!=old['python_version'] or new['profile']!=name or new['native_windows_verified'] is not False or new['gpu_offload_confirmed'] is not False:
            raise UpdateError('更新不得伪造本机/显卡验收状态。')
        profile_operation=seen[base+'/runtime-profile-manifest.json']
        if json.loads(safe(folder,profile_operation['payload']).read_bytes())!=new:raise UpdateError('配置负载与清单声明不一致。')
        server_operation=seen.get(base+'/app/server.py')
        if server_operation:validate_desktop_metadata(package,safe(folder,server_operation['payload']).read_bytes())
    build_info=json.loads(safe(folder,seen['BUILD-INFO.json']['payload']).read_bytes())
    if build_info.get('source_commit')!=manifest['new_source_commit'] or any(build_info['profiles'][name]['source_id']!=manifest['new_source_id'] for name in PROFILES):
        raise UpdateError('发布元数据与程序来源不一致。')
    if safe(folder,seen['SOURCE-COMMIT.txt']['payload']).read_text().strip()!=manifest['new_source_commit']:
        raise UpdateError('发布提交标识不一致。')
    bootstrap=manifest.get('bootstrap',{})
    file=safe(folder,bootstrap.get('payload','invalid'))
    if bootstrap.get('old_sha256')!=BASE_HOST_SHA or seen[HOST]['old_sha256']!=BASE_HOST_SHA or file_hash(file)!=bootstrap.get('sha256'):
        raise UpdateError('最小启动保护不匹配固定基础壳。')
    if file.stat().st_size>128*1024:raise UpdateError('最小启动保护过大。')
    host=safe(folder,seen[HOST]['payload']).read_bytes()
    if b'ui-update-journal.json' not in host or b'ensureNoPendingUIUpdate();' not in host:
        raise UpdateError('最终主机缺少未完成事务启动门禁。')
    return manifest

def paths(root: Path, manifest: dict) -> tuple[Path,Path]:
    identity=manifest['update_id']
    return safe(root,'resources/.app-stage-'+identity),safe(root,'resources/app-update-backups/'+identity)

def verify_state(root: Path, manifest: dict, which: str, bootstrap_ok: bool=False) -> None:
    for operation in manifest['files']:
        actual=file_hash(safe(root,operation['target']));wanted=operation['old_sha256' if which=='old' else 'new_sha256']
        if bootstrap_ok and operation['target']==HOST and actual==manifest['bootstrap']['sha256']:continue
        if actual!=wanted:raise UpdateError('现有程序文件SHA不匹配，拒绝覆盖：'+operation['target'])
    for name,base in PROFILES.items():
        profile=manifest['profiles'][name][which]
        for source,wanted in {**profile['source_files'],**profile['critical_files']}.items():
            if file_hash(safe(root,base+'/'+source))!=wanted:raise UpdateError('程序或原生运行库已被修改：'+base+'/'+source)
        # Unexpected executable source in these fixed program directories is not
        # silently carried into the updated source ID.
        for directory in ['app/static','src/companion_runtime']:
            folder=safe(root,base+'/'+directory)
            for file in folder.rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and file.suffix in {'.py','.js','.css','.html','.json','.svg'}:
                    source=file.relative_to(safe(root,base)).as_posix()
                    if source not in profile['source_files']:raise UpdateError('程序目录有来源不明的额外文件，拒绝更新。')

def journal(root: Path, manifest: dict, phase: str) -> None:
    atomic_write(safe(root,JOURNAL),(json.dumps({'format':FORMAT,'update_id':manifest['update_id'],'phase':phase})+'\n').encode())

def restore(root: Path, manifest: dict) -> None:
    stage,backup=paths(root,manifest)
    # Restore host last, so the fail-closed guard remains until old sources agree.
    for operation in sorted(manifest['files'],key=lambda item:item['target']==HOST):
        target=safe(root,operation['target']);old=operation['old_sha256'];actual=file_hash(target)
        if actual==old:continue
        valid={None,operation['new_sha256']}
        if operation['target']==HOST:valid.add(manifest['bootstrap']['sha256'])
        if actual not in valid:raise UpdateError('事务文件已另有修改；保留备份和启动保护，未强制覆盖。')
        if old is None:
            if target.exists():target.unlink()
        else:
            saved=safe(backup,'files/'+operation['target'])
            if file_hash(saved)!=old:raise UpdateError('原程序备份缺失或SHA不匹配，保留恢复事务。')
            atomic_write(target,saved.read_bytes())
    verify_state(root,manifest,'old')
    marker=safe(root,JOURNAL)
    if marker.exists():marker.unlink()
    if stage.exists():shutil.rmtree(stage)

def execute(root: Path, folder: Path, rollback: bool=False, fault: Callable[[str],None] | None=None) -> dict:
    root=root.resolve();folder=folder.resolve();manifest=load_update(folder);notify=fault or (lambda _phase:None)
    if not (root/'companion-desktop.exe').is_file() or not (root/'resources/backend/python/python.exe').is_file():
        raise UpdateError('请选择已完整解压的已发布Windows基础候选包目录。')
    stage,backup=paths(root,manifest)
    with lease(root):
        marker=safe(root,JOURNAL)
        if marker.exists():
            retained=read_json(marker,4096)
            if retained.get('format')!=FORMAT or retained.get('update_id')!=manifest['update_id']:
                raise UpdateError('请先使用上一次事务对应的可信更新器恢复。')
            restore(root,manifest)
        if rollback:
            try:verify_state(root,manifest,'old')
            except UpdateError:
                journal(root,manifest,'rollback');restore(root,manifest)
            return {'status':'rolled_back','update_id':manifest['update_id'],'windows_application_verified':False}
        try:verify_state(root,manifest,'new')
        except UpdateError:pass
        else:return {'status':'already_applied','update_id':manifest['update_id'],'windows_application_verified':False}
        verify_state(root,manifest,'old',bootstrap_ok=True)
        if stage.exists():shutil.rmtree(stage)
        stage.mkdir(parents=True)
        for operation in manifest['files']:
            destination=safe(root,operation['target']);old=operation['old_sha256'];saved=safe(backup,'files/'+operation['target'])
            if old is not None:
                if saved.exists():
                    if file_hash(saved)!=old:raise UpdateError('原程序备份SHA不匹配，拒绝更新。')
                else:
                    if file_hash(destination)!=old:raise UpdateError('原程序备份尚未建立，不能采用中间启动保护。')
                    atomic_write(saved,destination.read_bytes())
            data=safe(folder,operation['payload']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=operation['new_sha256']:raise UpdateError('暂存时负载发生变化。')
            atomic_write(safe(stage,operation['target']),data)
        bootstrap=safe(folder,manifest['bootstrap']['payload']).read_bytes()
        if hashlib.sha256(bootstrap).hexdigest()!=manifest['bootstrap']['sha256']:raise UpdateError('启动保护负载发生变化。')
        atomic_write(safe(root,HOST),bootstrap);notify('after-bootstrap')
        journal(root,manifest,'prepared')
        try:
            notify('after-journal')
            for index,operation in enumerate(sorted(manifest['files'],key=lambda item:item['target']==HOST)):
                atomic_write(safe(root,operation['target']),safe(stage,operation['target']).read_bytes())
                journal(root,manifest,'file-'+str(index));notify('after-file-'+str(index))
            verify_state(root,manifest,'new');notify('before-commit');journal(root,manifest,'committed');marker.unlink()
            if stage.exists():shutil.rmtree(stage)
            return {'status':'applied','update_id':manifest['update_id'],'windows_application_verified':False,'models_or_user_data_touched':False}
        except Exception:
            restore(root,manifest);raise

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--update-root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
    if os.name!='nt':raise UpdateError('此交付更新器须在Windows运行；文件夹夹具测试不等于Windows验证。')
    target=args.target.parent if args.target.name.lower()=='companion-desktop.exe' else args.target
    print(json.dumps(execute(target,args.update_root,args.rollback),ensure_ascii=False))
    print('程序源文件更新完成；用户角色、聊天、密钥、SDK、模型和驱动未修改。')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (UpdateError,OSError,ValueError,KeyError,TypeError) as error:
        print('更新已停止：'+str(error),file=sys.stderr)
        print('中断后请重跑同一可信更新器，或运行rollback-ui-update.cmd；不要删除备份或事务。',file=sys.stderr)
        raise SystemExit(1)
