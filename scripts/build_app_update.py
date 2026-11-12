"""Build the small, reversible v2 program-source update; never copy large models.

The base package is read-only and anchored to the published d01 manifests.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from app_update import (BASE_ARCHIVE_SHA, BASE_COMMIT, BASE_HOST_SHA, BASE_PROFILE_SHA, FORMAT,
                        HOST, HOST_FILES, PROGRAM_FILES, PROFILES, canonical_hash, load_update)
from ui_update import UpdateError, digest, relative, safe

ROOT=Path(__file__).resolve().parents[1]
PUBLISHER_FILES=frozenset({'scripts/build_app_update.py','scripts/app_update.py','scripts/ui_update.py','scripts/tracking_addon.py'})
COMMIT_FILES=frozenset({*PROGRAM_FILES,*['desktop/'+name for name in HOST_FILES],*PUBLISHER_FILES})

def validate_source_commit(source: Path, commit: str, *, publisher_source: Path | None=None) -> str:
    """Require a real Git commit whose selected release bytes match the checkout.

    This publishing guard intentionally is not part of the pure fixture builder.
    Installer helpers copied from the invoking tool's checkout are checked too.
    """
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Source commit must be a full 40-character Git commit ID')
    source=source.resolve()
    environment={**os.environ,'GIT_NO_REPLACE_OBJECTS':'1'}
    def git(*arguments: str) -> bytes:
        try:
            result=subprocess.run(['git','-C',str(source),*arguments],capture_output=True,timeout=15,env=environment)
        except (OSError,subprocess.TimeoutExpired) as error:raise ValueError('Publishing requires a readable local Git repository') from error
        if result.returncode:raise ValueError('Requested Git commit/repository is unavailable; refusing to publish a source label')
        return result.stdout
    if Path(os.fsdecode(git('rev-parse','--show-toplevel').strip())).resolve()!=source:
        raise ValueError('--source must be the Git repository root')
    resolved=git('rev-parse','--verify',commit+'^{commit}').decode('ascii').strip()
    if resolved!=commit:raise ValueError('Requested object is not the exact commit ID')
    entries={}
    for row in git('ls-tree','-r','-z','--full-tree',commit,'--',*sorted(COMMIT_FILES)).split(b'\0'):
        if not row:continue
        record,name=row.split(b'\t',1);mode,kind,oid=record.decode('ascii').split()
        entries[os.fsdecode(name)]=(mode,kind,oid)
    def matches(file: Path, wanted: str) -> bool:
        if not file.is_file():return False
        data=file.read_bytes()
        return hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()==wanted
    for name in sorted(COMMIT_FILES):
        entry=entries.get(name)
        if not entry or entry[0] not in {'100644','100755'} or entry[1]!='blob':
            raise ValueError('Required release source is absent or non-regular in the commit: '+name)
        try:file=safe(source,name)
        except UpdateError as error:raise ValueError('Unsafe release source path: '+name) from error
        if not matches(file,entry[2]):raise ValueError('Release source does not match the requested commit: '+name)
        if publisher_source is not None and name in PUBLISHER_FILES:
            try:publisher_file=safe(publisher_source.resolve(),name)
            except UpdateError as error:raise ValueError('Unsafe publisher/helper path: '+name) from error
            if not matches(publisher_file,entry[2]):raise ValueError('Invoking publisher/helper differs from the requested commit: '+name)
    return resolved

def encoded(value: dict) -> bytes:
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def bootstrap_host(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest()!=BASE_HOST_SHA:raise ValueError('Bootstrap requires the exact published host')
    source=original.decode()
    guard="""function ensureNoPendingUIUpdate() {
  if (app.isPackaged && process.platform === 'win32' && fs.existsSync(path.join(process.resourcesPath, 'ui-update-journal.json'))) {
    throw new Error('检测到未完成更新，请重跑同一可信apply-ui-update.cmd或rollback-ui-update.cmd；暂不启动服务。');
  }
}
"""
    needle='function setFocusable(value) {'
    start='      installIPC(); claimRuntimeSession(); await startBackend(); await createWindow();'
    if source.count(needle)!=1 or source.count(start)!=1:raise ValueError('Unexpected published host structure')
    return source.replace(needle,guard+needle).replace(start,start.replace('installIPC();','ensureNoPendingUIUpdate(); installIPC();')).encode()

def build_folder(base: Path, source: Path, output: Path, commit: str, identity: str, validation: Path) -> dict:
    import re
    if not re.fullmatch('[a-f0-9]{40}',commit) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',identity):raise ValueError('Invalid commit/update ID')
    checks=json.loads(validation.read_text())
    if checks.get('passed') is not True or checks.get('sources_unchanged_during_checks') is not True:raise ValueError('A current passing, source-stable engineering report is required')
    report_hashes=checks.get('source_sha256',{})
    info=json.loads((base/'BUILD-INFO.json').read_text())
    if info.get('source_commit')!=BASE_COMMIT or info.get('version')!='0.4.0-dev1':raise ValueError('Unsupported published base')
    if output.exists():raise ValueError('Use a new output folder')
    profiles={name:json.loads((base/folder/'runtime-profile-manifest.json').read_text()) for name,folder in PROFILES.items()}
    if profiles['cpu']['source_id']!=profiles['cuda']['source_id']:raise ValueError('Base CPU/CUDA source IDs differ')
    for name,folder in PROFILES.items():
        profile=profiles[name]
        if canonical_hash(profile)!=BASE_PROFILE_SHA[name]:raise ValueError('Unknown base profile')
        for file,wanted in {**profile['source_files'],**profile['critical_files']}.items():
            if digest(base/folder/relative(file))!=wanted:raise ValueError('Base source/native hash mismatch: '+file)
    output.mkdir(parents=True)
    manifest={'format':FORMAT,'update_id':identity,'base_source_commit':BASE_COMMIT,'base_archive_sha256':BASE_ARCHIVE_SHA,
        'new_source_commit':commit,'base_source_id':profiles['cpu']['source_id'],'profiles':{},'files':[],
        'windows_update_executed':False,'windows_application_verified':False,'models_or_sdk_included':False,
        'cryptographically_signed':False,'trust':'Verify artifact SHA against the trusted GitHub Release before running.'}
    def add(target: str,data: bytes,payload: str) -> None:
        destination=output/relative(payload);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
        old=base/relative(target)
        manifest['files'].append({'target':target,'old_sha256':digest(old) if old.is_file() else None,
            'new_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'payload':payload})
    changes={}
    for folder in ['app/static','src/companion_runtime']:
        for candidate in (source/folder).rglob('*'):
            if candidate.is_file() and '__pycache__' not in candidate.parts and candidate.suffix in {'.py','.js','.css','.html','.json','.svg','.png'}:
                file=candidate.relative_to(source).as_posix()
                if file=='src/companion_runtime/perception_addon_build.py':continue  # Build-only; never imported by runtime.
                if file not in profiles['cpu']['source_files'] and file not in PROGRAM_FILES:
                    raise ValueError('New source requires an explicit updater whitelist decision: '+file)
    for file in sorted(PROGRAM_FILES):
        current=source/relative(file)
        if not current.exists():continue
        data=current.read_bytes();wanted=hashlib.sha256(data).hexdigest();before=profiles['cpu']['source_files'].get(file)
        if before==wanted:continue
        if report_hashes.get(file)!=wanted:raise ValueError('Validation report does not bind current source: '+file)
        changes[file]=(data,wanted)
    if not changes:raise ValueError('No changed program source')
    # Source files outside the write set cannot silently differ from the source ID.
    for file,wanted in profiles['cpu']['source_files'].items():
        current=source/relative(file)
        if current.is_file() and file not in PROGRAM_FILES and digest(current)!=wanted:raise ValueError('Changed source is outside explicit updater whitelist: '+file)
    for name,folder in PROFILES.items():
        old=profiles[name];new=deepcopy(old)
        for file,(data,wanted) in changes.items():
            new['source_files'][file]=wanted;add(folder+'/'+file,data,'payload/program/'+file)
        new['source_id']=canonical_hash(new['source_files']);new['critical_files']['app/server.py']=new['source_files']['app/server.py']
        new['native_windows_verified']=False;new['gpu_offload_confirmed']=False
        manifest['profiles'][name]={'old':old,'new':new}
        add(folder+'/runtime-profile-manifest.json',encoded(new),'payload/metadata/'+name+'-runtime-profile-manifest.json')
    manifest['new_source_id']=manifest['profiles']['cpu']['new']['source_id']
    if manifest['new_source_id']!=manifest['profiles']['cuda']['new']['source_id']:raise ValueError('New CPU/CUDA program sources differ')
    for name in sorted(HOST_FILES):
        file=source/'desktop'/name;data=file.read_bytes();wanted=hashlib.sha256(data).hexdigest()
        if report_hashes.get('desktop/'+name)!=wanted:raise ValueError('Validation report does not bind desktop source: '+name)
        add('resources/app/'+name,data,'payload/host/'+name)
    original=(base/HOST).read_bytes();bootstrap=bootstrap_host(original)
    (output/'payload/host/bootstrap.cjs').write_bytes(bootstrap)
    manifest['bootstrap']={'old_sha256':BASE_HOST_SHA,'sha256':hashlib.sha256(bootstrap).hexdigest(),'payload':'payload/host/bootstrap.cjs'}
    new_info=deepcopy(info);new_info['base_quality_gate']=new_info.pop('quality_gate',{})
    new_info.update(source_commit=commit,base_source_commit=BASE_COMMIT,app_update_id=identity,
        windows_native_execution_verified=False,cuda_offload_confirmed=False,human_visual_quality_accepted=False,
        quality_gate={'report_sha256':digest(validation),'scope':'Current engineering/source checks; no Windows, physical hardware or human visual acceptance'})
    for name in PROFILES:new_info['profiles'][name]['source_id']=manifest['new_source_id']
    add('BUILD-INFO.json',encoded(new_info),'payload/metadata/BUILD-INFO.json')
    assembly=json.loads((base/'ASSEMBLY-INFO.json').read_text())
    for profile in assembly['profiles']:profile['source_id']=manifest['new_source_id']
    assembly['app_update_id']=identity
    add('ASSEMBLY-INFO.json',encoded(assembly),'payload/metadata/ASSEMBLY-INFO.json')
    add('SOURCE-COMMIT.txt',(commit+'\n').encode(),'payload/metadata/SOURCE-COMMIT.txt')
    add('APP-UPDATE-INFO.json',encoded({'update_id':identity,'source_commit':commit,'source_id':manifest['new_source_id'],
        'windows_application_verified':False,'user_data_touched':False,'signed':False}),'payload/metadata/APP-UPDATE-INFO.json')
    add('VALIDATION/app-update-checks.json',validation.read_bytes(),'payload/metadata/app-update-checks.json')
    sums={}
    for line in (base/'SHA256SUMS.txt').read_text().splitlines():
        if len(line)<67 or line[64:66]!='  ' or not re.fullmatch('[a-f0-9]{64}',line[:64]):raise ValueError('Invalid base checksum list')
        name=line[66:];relative(name)
        if name in sums:raise ValueError('Duplicate checksum path')
        sums[name]=line[:64]
    for operation in manifest['files']:sums[operation['target']]=operation['new_sha256']
    sums.pop('SHA256SUMS.txt',None)
    add('SHA256SUMS.txt',''.join(value+'  '+name+'\n' for name,value in sorted(sums.items())).encode(),'payload/metadata/SHA256SUMS.txt')
    (output/'app-update-manifest.json').write_bytes(encoded(manifest))
    for name in ['app_update.py','ui_update.py','tracking_addon.py']:shutil.copy2(ROOT/'scripts'/name,output/name)
    for name,argument in [('apply-ui-update.cmd',''),('rollback-ui-update.cmd',' --rollback')]:
        command='@echo off\r\nsetlocal DisableDelayedExpansion\r\nset "APP_TARGET=%~1"\r\nif not defined APP_TARGET set /p "APP_TARGET=Extracted old application folder: "\r\nif not defined APP_TARGET exit /b 1\r\nset "APP_TARGET=%APP_TARGET:"=%"\r\nfor %%I in ("%APP_TARGET%") do if /i "%%~nxI"=="companion-desktop.exe" set "APP_TARGET=%%~dpI"\r\nif not exist "%APP_TARGET%\\resources\\backend\\python\\python.exe" (echo Select the fully extracted old application folder.& pause& exit /b 1)\r\n"%APP_TARGET%\\resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0app_update.py" --target "%APP_TARGET%" --update-root "%~dp0"'+argument+'\r\nset "APP_RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %APP_RESULT%\r\n'
        (output/name).write_text(command,encoding='ascii',newline='')
    for name,argument in [('install-tracking-addon.cmd',''),('disable-tracking-addon.cmd',' --remove')]:
        command='@echo off\r\nsetlocal DisableDelayedExpansion\r\nset "APP_TARGET=%~1"\r\nif not defined APP_TARGET set /p "APP_TARGET=Extracted old application folder: "\r\nif not defined APP_TARGET exit /b 1\r\nset "APP_TARGET=%APP_TARGET:"=%"\r\nfor %%I in ("%APP_TARGET%") do if /i "%%~nxI"=="companion-desktop.exe" set "APP_TARGET=%%~dpI"\r\n"%APP_TARGET%\\resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0tracking_addon.py" --target "%APP_TARGET%" --archive "%~dp0tracking-addon-cp312-win-x64-v3.zip"'+argument+'\r\nset "APP_RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %APP_RESULT%\r\n'
        (output/name).write_text(command,encoding='ascii',newline='')
    (output/'START-HERE.txt').write_text('\uFEFF程序小更新（v2）· 仅用于已发布0.4.0-dev1基础候选包\n\n先核对可信GitHub Release提供的SHA256，再完整解压。先从托盘退出软件；双击apply-ui-update.cmd，输入旧软件解压目录。无需再次下载模型或4GB基础包。\n更新只替换固定白名单程序源文件、主机壳与来源清单。用户角色、聊天、密钥、SDK、模型、解释器、DLL和驱动不改。角色素材独立手动导入。\n中断后重跑同一可信更新器，或运行rollback-ui-update.cmd恢复。备份在resources/app-update-backups。不要删除事务、运行锁或备份。\n这是可恢复的多文件事务，不是一步全原子；不保证恶意并发篡改安全。Windows实际执行/文件锁/4060性能仍待真机验证；此包未进行代码签名。\n',encoding='utf-8')
    load_update(output)
    return manifest

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-package',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--source-commit',required=True);parser.add_argument('--update-id',required=True)
    parser.add_argument('--validation-report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite an existing release artifact')
    try:validate_source_commit(args.source,args.source_commit,publisher_source=ROOT)
    except ValueError as error:parser.error(str(error))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='source-update-build-',dir=args.output.parent) as temporary:
        folder=Path(temporary)/'app-update';manifest=build_folder(args.base_package,args.source,folder,args.source_commit,args.update_id,args.validation_report)
        try:validate_source_commit(args.source,args.source_commit,publisher_source=ROOT)
        except ValueError as error:parser.error(str(error))
        archive=args.output.with_suffix('.zip.part')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
            for file in sorted(folder.rglob('*')):
                if file.is_file():output.write(file,file.relative_to(folder).as_posix())
        with zipfile.ZipFile(archive) as output:
            if output.testzip() is not None:raise ValueError('Update ZIP CRC mismatch')
        archive.replace(args.output);value=digest(args.output)
        args.output.with_suffix(args.output.suffix+'.sha256').write_text(value+'  '+args.output.name+'\n')
        print(json.dumps({'artifact':str(args.output),'bytes':args.output.stat().st_size,'sha256':value,'operations':len(manifest['files']),
            'source_id':manifest['new_source_id'],'native_windows_verified':False,'models_or_user_data_included':False}))

if __name__=='__main__':main()
