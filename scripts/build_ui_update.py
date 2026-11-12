"""Build a small UI update for the published d01 Windows candidate only.

Reads the pristine unpacked base; does not change it, build native dependencies,
download anything, package user data/SDKs, or upload a Release.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from ui_update import FORMAT,HOST,METADATA,PROFILES,UI_FILES,digest,relative

ROOT=Path(__file__).resolve().parents[1]
BASE_COMMIT='d01ccc42bbe6795c216afae37dd0e53128ab58d9'
BASE_ARCHIVE_SHA='92d3e858cb93471b1fe4e633e2b5328aa43dc178f325a9bfa65ca62d1405b7e3'

def encoded(value: dict) -> bytes:
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def source_id(records: dict) -> str:
    return hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def build_folder(base: Path,ui: Path,host: Path,output: Path,commit: str,identity: str,validation: Path) -> dict:
    if not re.fullmatch('[a-f0-9]{40}',commit) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',identity):raise ValueError('Invalid source commit/update ID')
    info=json.loads((base/'BUILD-INFO.json').read_text())
    if info.get('source_commit')!=BASE_COMMIT or info.get('version')!='0.4.0-dev1':raise ValueError('Only the published0.4.0-dev1 d01 base is supported')
    checks=json.loads(validation.read_text())
    if checks.get('passed') is not True:raise ValueError('A passing UI validation report is required')
    if output.exists():raise ValueError('Use a new output folder')
    output.mkdir(parents=True)
    profiles={name:json.loads((base/folder/'runtime-profile-manifest.json').read_text()) for name,folder in PROFILES.items()}
    if profiles['cpu']['source_id']!=profiles['cuda']['source_id']:raise ValueError('Base CPU/CUDA sources differ')
    for name,folder in PROFILES.items():
        profile=profiles[name]
        if profile['source_id']!=source_id(profile['source_files']):raise ValueError('Invalid base source ID')
        for path,wanted in profile['source_files'].items():
            if digest(base/folder/relative(path))!=wanted:raise ValueError('Pristine base source mismatch')
    original=base/PROFILES['cpu']/'app/static';allowed=set(UI_FILES)
    for file in ui.iterdir():
        if file.is_file() and file.name not in allowed:
            old=original/file.name
            if not old.is_file() or digest(old)!=digest(file):raise ValueError('Non-allowlisted static change requires another update type: '+file.name)
    manifest={'format':FORMAT,'update_id':identity,'base_source_commit':BASE_COMMIT,'base_archive_sha256':BASE_ARCHIVE_SHA,
              'new_source_commit':commit,'base_source_id':profiles['cpu']['source_id'],'profiles':{},'files':[],
              'windows_update_executed':False,'windows_application_verified':False,'models_or_sdk_included':False}
    def add(target: str,data: bytes,payload: str) -> None:
        file=output/relative(payload);file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
        old=base/relative(target)
        manifest['files'].append({'target':target,'old_sha256':digest(old) if old.is_file() else None,
                                  'new_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'payload':payload})
    changes={}
    for name in sorted(UI_FILES):
        data=(ui/name).read_bytes();value=hashlib.sha256(data).hexdigest()
        if value!=digest(original/name):changes[name]=(data,value)
    if not changes:raise ValueError('No UI changes')
    for name,folder in PROFILES.items():
        old=profiles[name];new=deepcopy(old)
        for file,(data,value) in changes.items():
            new['source_files']['app/static/'+file]=value
            add(folder+'/app/static/'+file,data,'payload/static/'+file)
        new['source_id']=source_id(new['source_files'])
        assert old['critical_files']==new['critical_files']
        manifest['profiles'][name]={'old':old,'new':new}
        add(folder+'/runtime-profile-manifest.json',encoded(new),'payload/metadata/'+name+'-runtime-profile-manifest.json')
    new_id=manifest['profiles']['cpu']['new']['source_id']
    if new_id!=manifest['profiles']['cuda']['new']['source_id']:raise ValueError('New profile sources differ')
    manifest['new_source_id']=new_id
    new_host=host.read_bytes()
    if b'ui-update-journal.json' not in new_host or b'ensureNoPendingUIUpdate();' not in new_host:raise ValueError('The small fail-closed host guard is required')
    add(HOST,new_host,'payload/host/main.cjs')
    new_info=deepcopy(info);new_info['base_quality_gate']=new_info.pop('quality_gate',{})
    new_info.update(source_commit=commit,base_source_commit=BASE_COMMIT,ui_update_id=identity,
                    windows_native_execution_verified=False,cuda_offload_confirmed=False,
                    ui_validation={'report_sha256':digest(validation),'scope':'UI/engineering checks; not Windows native validation'})
    for name in PROFILES:new_info['profiles'][name]['source_id']=new_id
    add('BUILD-INFO.json',encoded(new_info),'payload/metadata/BUILD-INFO.json')
    assembly=json.loads((base/'ASSEMBLY-INFO.json').read_text())
    for entry in assembly['profiles']:entry['source_id']=new_id
    assembly['ui_update_id']=identity
    add('ASSEMBLY-INFO.json',encoded(assembly),'payload/metadata/ASSEMBLY-INFO.json')
    add('SOURCE-COMMIT.txt',(commit+'\n').encode(),'payload/metadata/SOURCE-COMMIT.txt')
    add('UI-UPDATE-INFO.json',encoded({'update_id':identity,'base_source_commit':BASE_COMMIT,'source_commit':commit,
                                     'source_id':new_id,'windows_application_verified':False,'user_data_touched':False}),
        'payload/metadata/UI-UPDATE-INFO.json')
    add('VALIDATION/ui-update-checks.json',validation.read_bytes(),'payload/metadata/ui-update-checks.json')
    rows={}
    for line in (base/'SHA256SUMS.txt').read_text().splitlines():
        if len(line)<67 or line[64:66]!='  ' or not re.fullmatch('[a-f0-9]{64}',line[:64]):raise ValueError('Invalid base checksum list')
        path=line[66:];relative(path)
        if path in rows:raise ValueError('Duplicate checksum row')
        rows[path]=line[:64]
    for operation in manifest['files']:rows[operation['target']]=operation['new_sha256']
    rows.pop('SHA256SUMS.txt',None)
    sums=''.join(value+'  '+name+'\n' for name,value in sorted(rows.items())).encode()
    add('SHA256SUMS.txt',sums,'payload/metadata/SHA256SUMS.txt')
    (output/'ui-update-manifest.json').write_bytes(encoded(manifest))
    shutil.copy2(ROOT/'scripts/ui_update.py',output/'ui_update.py')
    for file,argument in [('apply-ui-update.cmd',''),('rollback-ui-update.cmd',' --rollback')]:
        cmd='@echo off\r\nsetlocal DisableDelayedExpansion\r\nset "UI_TARGET=%~1"\r\nif not defined UI_TARGET set /p "UI_TARGET=Extracted old application folder: "\r\nif not defined UI_TARGET exit /b 1\r\nset "UI_TARGET=%UI_TARGET:"=%"\r\nfor %%I in ("%UI_TARGET%") do if /i "%%~nxI"=="companion-desktop.exe" set "UI_TARGET=%%~dpI"\r\nif not exist "%UI_TARGET%\\resources\\backend\\python\\python.exe" (echo Select the extracted old application folder.& pause& exit /b 1)\r\n"%UI_TARGET%\\resources\\backend\\python\\python.exe" -I -X utf8 "%~dp0ui_update.py" --target "%UI_TARGET%" --update-root "%~dp0"'+argument+'\r\nset "UI_RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %UI_RESULT%\r\n'
        (output/file).write_text(cmd,encoding='ascii',newline='')
    (output/'START-HERE.txt').write_text('\uFEFF界面小更新 · 仅适用于已发布0.4.0-dev1候选基础包\n\n1. 完整解压此小更新，先从托盘退出软件。\n2. 双击apply-ui-update.cmd，输入已解压的旧软件目录；也可把companion-desktop.exe拖到该CMD。\n3. 成功后正常打开软件。无需重新下载4.18GiB基础包，也不重新下载模型。\n\n遇到中断请重新运行同一可信更新器；恢复旧界面运行rollback-ui-update.cmd。不要删除resources/ui-update-backups或事务文件。\n更新只替换两配置的既有界面文件、来源清单及极小启动保护，不触及角色/聊天/密钥/SDK/模型。原哈希不符会停止，不强制覆盖手改程序。\n这是可恢复的多步文件事务，不把多目录rename称为一步全原子。不保证恶意并发修改安全。\nWindows运行和文件锁行为尚未在目标真机验收；跨平台模拟测试不等于Windows已通过。\n',encoding='utf-8')
    return manifest

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-package',type=Path,required=True);parser.add_argument('--ui',type=Path,default=ROOT/'app/static')
    parser.add_argument('--host',type=Path,default=ROOT/'desktop/main.cjs');parser.add_argument('--source-commit',required=True)
    parser.add_argument('--update-id',required=True);parser.add_argument('--validation-report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to replace an existing update ZIP')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ui-update-build-',dir=args.output.parent) as temp:
        folder=Path(temp);package=folder/'ui-update'
        manifest=build_folder(args.base_package,args.ui,args.host,package,args.source_commit,args.update_id,args.validation_report)
        temporary=args.output.with_suffix('.zip.part')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for file in sorted(package.rglob('*')):
                if file.is_file():archive.write(file,file.relative_to(package).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('Update ZIP CRC failed')
        temporary.replace(args.output)
        value=digest(args.output);args.output.with_suffix(args.output.suffix+'.sha256').write_text(value+'  '+args.output.name+'\n',encoding='ascii')
        summary={'artifact':str(args.output),'bytes':args.output.stat().st_size,'sha256':value,'update_id':args.update_id,
                 'base_source_commit':BASE_COMMIT,'new_source_commit':args.source_commit,'base_source_id':manifest['base_source_id'],
                 'new_source_id':manifest['new_source_id'],'operations':len(manifest['files']),'payload_copies':1,
                 'native_windows_verified':False,'models_sdk_or_user_data_included':False}
        args.output.with_name(args.output.stem+'-manifest.json').write_bytes(encoded(summary));print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
