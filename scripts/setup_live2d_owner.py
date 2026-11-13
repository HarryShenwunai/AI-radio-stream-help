"""Owner-run, optional local Live2D evaluation setup. No vendor bytes are shipped.

Uses the portable application's Python and a SHA-locked native esbuild CLI;
never runs npm, Node package scripts, or role-provided code.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from uuid import UUID,uuid4

sys.path.insert(0,str(Path(__file__).resolve().parent))
from ui_update import UpdateError, atomic_write, digest, lease, safe

LOCK_SHA256='65e66fc7151e519afc938fcdfdbac46898f4bf47fb6f6ea54e68547b59666671'
CORE_LICENSE='https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html'
FRAMEWORK_LICENSE='https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html'
NOTICE=f'''Optional OWNER-LOCAL development evaluation only.
Read and accept BOTH agreements before downloading/installing/using:
Core: {CORE_LICENSE}
Framework: {FRAMEWORK_LICENSE}
This is not permission to redistribute vendor libraries, publish an Expandable
Application, or use commercially. No vendor code belongs in GitHub/default ZIP.
Only fixed npm archives and the existing official Core HTTPS endpoint are used.
No npm install/postinstall/prepare scripts run. A verified native esbuild binary
is executed locally to build the optional renderer. Browser execution is later.
'''
ENTRY="import*as PIXI from'pixi.js';import'pixi.js/unsafe-eval';import{Live2DModel}from'@jannchie/pixi-live2d-display/cubism4';window.CompanionLive2DRuntime={PIXI,Live2DModel,versions:{pixi:'8.23.0',wrapper:'1.4.0'}};"

class SetupError(ValueError):pass

def read_lock(file: Path | None=None) -> dict:
    file=file or Path(__file__).with_name('live2d-owner-packages.json')
    raw=file.read_bytes()
    if len(raw)>128*1024 or hashlib.sha256(raw).hexdigest()!=LOCK_SHA256:raise SetupError('package_lock_sha_mismatch')
    value=json.loads(raw)
    if value.get('format')!='companion-live2d-owner-npm-v1':raise SetupError('invalid_package_lock')
    return value

def selected_packages(lock: dict, platform: str) -> list[dict]:
    if platform not in {'win32-x64','linux-x64'}:raise SetupError('unsupported_builder_platform')
    role='builder-windows' if platform=='win32-x64' else 'builder-linux-test'
    return [row for row in lock['packages'] if row['role'] in {'runtime','build-license',role}]

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*_args,**_kwargs):raise SetupError('registry_redirect_rejected')

def fetch_archive(row: dict) -> bytes:
    if not row['url'].startswith('https://registry.npmjs.org/') or not 0<row['bytes']<=20*1024*1024:raise SetupError('invalid_locked_download')
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),_NoRedirect())
    request=urllib.request.Request(row['url'],headers={'User-Agent':'Companion-Owner-Local-Setup/1'})
    with opener.open(request,timeout=20) as response:
        if response.status!=200 or response.geturl()!=row['url']:raise SetupError('unexpected_registry_response')
        chunks=[];length=0;start=time.monotonic()
        while True:
            chunk=response.read(min(65536,row['bytes']+1-length))
            if not chunk:break
            chunks.append(chunk);length+=len(chunk)
            if length>row['bytes'] or time.monotonic()-start>90:raise SetupError('registry_download_limit')
    return b''.join(chunks)

def cached_archive(row: dict, cache: Path, fetcher=fetch_archive) -> Path:
    file=safe(cache,row['sha256']+'.tgz')
    if file.exists():
        if file.stat().st_size!=row['bytes'] or digest(file)!=row['sha256']:raise SetupError('cached_archive_changed')
        return file
    data=fetcher(row)
    if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise SetupError('download_sha_mismatch')
    atomic_write(file,data);return file

def _member_name(value: str, prefix: str) -> str:
    parts=value.split('/')
    if not parts or parts[0]!=prefix or '\\' in value or ':' in value or any(part in {'','..','.'} for part in parts):raise SetupError('unsafe_package_member')
    for part in parts:
        if part.endswith((' ','.')) or any(ord(char)<32 for char in part) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise SetupError('unsafe_package_member')
    name='/'.join(parts[1:])
    if not name or PurePosixPath(name).is_absolute():raise SetupError('unsafe_package_member')
    return name

def unpack_package(archive: Path, destination: Path, prefix: str) -> int:
    if destination.exists():raise SetupError('package_destination_exists')
    destination.mkdir(parents=True);total=0;count=0;seen=set()
    with tarfile.open(archive,'r|gz') as package:
        for member in package:
            name=member.name.rstrip('/') if member.isdir() else member.name
            if name==prefix and member.isdir():continue
            relative=_member_name(name,prefix);count+=1
            if count>12000 or member.size>32*1024*1024 or member.size<0:raise SetupError('package_member_limit')
            if relative.casefold() in seen:raise SetupError('duplicate_package_member')
            seen.add(relative.casefold());target=safe(destination,relative)
            if member.isdir():target.mkdir(parents=True,exist_ok=True);continue
            if not member.isfile():raise SetupError('package_link_or_special_file_rejected')
            total+=member.size
            if total>128*1024*1024:raise SetupError('package_expansion_limit')
            source=package.extractfile(member)
            if source is None:raise SetupError('package_file_unavailable')
            data=source.read(member.size+1)
            if len(data)!=member.size:raise SetupError('truncated_package_member')
            atomic_write(target,data)
    return total

def _verify_native(file: Path, platform: str) -> None:
    raw=file.read_bytes()
    if platform=='win32-x64':
        if raw[:2]!=b'MZ' or len(raw)<64:raise SetupError('expected_windows_esbuild')
        offset=struct.unpack_from('<I',raw,60)[0]
        if offset+6>len(raw) or raw[offset:offset+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,offset+4)[0]!=0x8664:raise SetupError('expected_x64_esbuild')
    elif raw[:5]!=b'\x7fELF\x02' or int.from_bytes(raw[18:20],'little')!=62:raise SetupError('expected_linux_x64_esbuild')

def build_bundle(lock: dict, cache: Path, work: Path, platform: str, *, fetcher=fetch_archive) -> dict:
    rows=selected_packages(lock,platform);folders={};total=0
    for row in rows:
        archive=cached_archive(row,cache,fetcher)
        folder=work/'node_modules'/row['name'];total+=unpack_package(archive,folder,row['archive_prefix'])
        if total>160*1024*1024:raise SetupError('total_expansion_limit')
        metadata=json.loads((folder/'package.json').read_bytes())
        if metadata['name']!=row['name'] or metadata['version']!=row['version']:raise SetupError('package_identity_mismatch')
        folders[row['name']]=folder
    names=set(folders)
    for row in rows:
        if row['role']=='runtime' and not set(row['dependencies'])<=names:raise SetupError('unlocked_dependency')
    binary=folders['@esbuild/'+platform]/('esbuild.exe' if platform=='win32-x64' else 'bin/esbuild')
    _verify_native(binary,platform);binary.chmod(0o700)
    environment={key:value for key,value in os.environ.items() if key not in {'NODE_PATH','NODE_OPTIONS','ESBUILD_BINARY_PATH'}}
    version=subprocess.run([str(binary),'--version'],capture_output=True,text=True,check=True,timeout=15,env=environment).stdout.strip()
    if version!='0.25.12':raise SetupError('unexpected_builder_version')
    notices=['Owner-local evaluation runtime; not part of default/public distribution.',
             'Live2D Cubism Framework: Copyright(c) Live2D Inc. All rights reserved.',FRAMEWORK_LICENSE,
             'Core is separately installed from the official source and is absent from this bundle.']
    for name,folder in sorted(folders.items()):
        for file in sorted(folder.rglob('*')):
            if file.is_file() and file.name.lower().startswith(('license','licence','copying')):
                if file.stat().st_size>128*1024:raise SetupError('license_file_limit')
                notices.append(name+'/'+file.relative_to(folder).as_posix()+'\n'+file.read_text(encoding='utf-8'))
    notice='\n\n'.join(notices)+'\n';entry=work/'entry.mjs';entry.write_text(ENTRY)
    output=work/'owner-live2d-runtime.js'
    subprocess.run([str(binary),str(entry),'--bundle','--platform=browser','--format=iife','--target=chrome120','--minify','--legal-comments=eof','--log-level=warning','--outfile='+str(output)],check=True,capture_output=True,timeout=90,env=environment)
    data=('/*!\n'+notice.replace('*/','* /')+'\n*/\n').encode()+output.read_bytes()
    if len(data)>8*1024*1024 or b'CompanionLive2DRuntime' not in data:raise SetupError('invalid_built_runtime')
    output.write_bytes(data);output.with_suffix('.NOTICE.txt').write_text(notice)
    return {'bundle':output,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'download_bytes':sum(row['bytes'] for row in rows),
        'unpacked_bytes':total,'native_builder_platform':platform,'native_builder_version':version,
        'npm_lifecycle_scripts_executed':False,'node_required':False,'windows_application_execution_verified':False}

def query_owner_paths(application: Path) -> dict:
    host=safe(application,'resources/app/main.cjs');module=safe(application,'resources/app/owner-runtime-path.cjs')
    if not host.is_file() or b'--owner-runtime-path' not in host.read_bytes() or not module.is_file():raise SetupError('apply_current_small_update_first')
    sums={}
    for row in safe(application,'SHA256SUMS.txt').read_text().splitlines():
        if len(row)>=67 and row[64:66]=='  ':sums[row[66:]]=row[:64]
    for relative in ['companion-desktop.exe','resources/app/main.cjs','resources/app/owner-runtime-path.cjs']:
        if sums.get(relative)!=digest(safe(application,relative)):raise SetupError('application_owner_path_source_changed')
    result=subprocess.run([str(safe(application,'companion-desktop.exe')),'--owner-runtime-path'],cwd=application,capture_output=True,text=True,encoding='utf-8',timeout=30)
    records=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    if result.returncode or len(records)!=1:raise SetupError('owner_path_query_failed')
    value=records[0]
    if value.get('schema_version')!=1 or value.get('backend_started') is not False or value.get('window_count')!=0 or not all(isinstance(value.get(key),str) and Path(value[key]).is_absolute() for key in ['data_root','live2d_runtime_root']):
        raise SetupError('invalid_owner_path_response')
    return value

def load_runtime(application: Path):
    base=safe(application,'resources/backend');manifest=json.loads(safe(base,'runtime-profile-manifest.json').read_bytes())
    for name in ['src/companion_runtime/__init__.py','src/companion_runtime/live2d_runtime.py']:
        if digest(safe(base,name))!=manifest['source_files'].get(name):raise SetupError('installed_runtime_source_changed')
    sys.path.insert(0,str(base/'src'))
    return importlib.import_module('companion_runtime.live2d_runtime').Live2DRuntime

def runtime_fingerprint(root: Path) -> dict:
    if not root.exists():return {}
    result={}
    for file in root.rglob('*'):
        relative=file.relative_to(root).as_posix();safe(root,relative)
        if file.is_dir():continue
        if not file.is_file() or not (relative in {'core.json','bundle.json'} or re.fullmatch(r'revisions/[a-f0-9-]{36}/(?:script.js|record.json)',relative)):
            raise SetupError('target_contains_nonruntime_files')
        if file.stat().st_size>8*1024*1024 or len(result)>12:raise SetupError('runtime_file_limit')
        result[relative]=digest(file)
    return result

def _workspace(target: Path) -> Path:
    for parent in (target,*target.parents):
        if parent.is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(parent)):raise SetupError('runtime_path_contains_link')
    root=safe(target.parent,'.live2d-owner-setup');root.mkdir(parents=True,exist_ok=True);root.chmod(0o700);return root

def restore_previous(target: Path, *, pending_only=False) -> dict:
    workspace=_workspace(target);file=safe(workspace,'transaction.json')
    if not file.exists():return {'status':'no_previous_setup'}
    record=json.loads(file.read_bytes())
    if record.get('format')!='companion-owner-live2d-setup-v1' or record.get('target')!=target.name:raise SetupError('invalid_setup_transaction')
    if pending_only and record['phase'] in {'installed','restored'}:return {'status':'not_pending'}
    for key in ['candidate','backup']:
        if record[key] is not None and str(UUID(record[key]))!=record[key]:raise SetupError('invalid_setup_transaction')
    current=runtime_fingerprint(target)
    if current and current!=record['new_fingerprint'] and current!=record['old_fingerprint']:raise SetupError('runtime_changed_since_setup')
    backup=safe(workspace,record['backup']) if record['backup'] else None
    if current==record['old_fingerprint'] and target.exists():pass
    else:
        if backup and runtime_fingerprint(backup)!=record['old_fingerprint']:raise SetupError('previous_runtime_backup_changed')
        if target.exists():os.replace(target,safe(workspace,'disabled-'+str(uuid4())))
        if backup and backup.exists():os.replace(backup,target)
    record['phase']='restored';atomic_write(file,(json.dumps(record,indent=2)+'\n').encode());return {'status':'restored','runtime_root':str(target)}

def install_pair(target: Path, bundle: Path, runtime_factory, *, accepted: bool, fault=None) -> dict:
    if accepted is not True:raise SetupError('owner_license_acknowledgement_required')
    workspace=_workspace(target);restore_previous(target,pending_only=True)
    if runtime_factory(target).status()['available']:return {'status':'already_configured','runtime_root':str(target)}
    old=runtime_fingerprint(target);candidate=str(uuid4());backup=str(uuid4()) if target.exists() else None
    staging=safe(workspace,candidate);runtime=runtime_factory(staging)
    try:
        runtime.install_bundle(bundle,expected_sha256=digest(bundle),accept_official_license=True,trust_local_bundle=True)
        runtime.install_official(accept_official_license=True)
        if not runtime.status()['available']:raise SetupError('staged_runtime_not_available')
        record={'format':'companion-owner-live2d-setup-v1','target':target.name,'candidate':candidate,'backup':backup,
            'old_fingerprint':old,'new_fingerprint':runtime_fingerprint(staging),'phase':'prepared'}
        atomic_write(safe(workspace,'transaction.json'),(json.dumps(record,indent=2)+'\n').encode())
        if backup:os.replace(target,safe(workspace,backup))
        if fault:fault('after-backup')
        os.replace(staging,target)
        if fault:fault('after-install')
        record['phase']='installed';atomic_write(safe(workspace,'transaction.json'),(json.dumps(record,indent=2)+'\n').encode())
        return {'status':'installed','runtime_root':str(target),'runtime':runtime_factory(target).status(),'publication_permission_verified':False}
    except Exception:
        restore_previous(target,pending_only=True)
        raise

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=NOTICE,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action',choices=['plan','install','restore']);parser.add_argument('--application-root',type=Path,required=True)
    parser.add_argument('--runtime-root',type=Path);parser.add_argument('--accept-official-license',action='store_true');parser.add_argument('--trust-locked-build',action='store_true');args=parser.parse_args(argv)
    if args.action=='install' and not (args.accept_official_license and args.trust_locked_build):parser.error('Explicit OWNER license acceptance and locked-build acknowledgement are required before any download.')
    if os.name!='nt':parser.error('Owner delivery CLI is Windows-only; Linux build smoke is a separate developer check.')
    application=args.application_root.resolve();paths=query_owner_paths(application);target=(args.runtime_root or Path(paths['live2d_runtime_root'])).absolute();lock=read_lock()
    if args.action=='plan':
        print(json.dumps({'runtime_root':str(target),'download_bytes':sum(row['bytes'] for row in selected_packages(lock,'win32-x64')),'core_download_bytes':'bounded by existing official installer; observed digest only','npm_scripts_executed':False,'node_required':False,'license_links':lock['license_links']},indent=2));return 0
    runtime_factory=load_runtime(application)
    with lease(application):
        if args.action=='restore':result=restore_previous(target)
        else:
            workspace=_workspace(target);restore_previous(target,pending_only=True)
            if runtime_factory(target).status()['available']:result={'status':'already_configured','runtime_root':str(target)}
            else:
                # Keep package paths short on Windows without changing machine
                # long-path policy; tempfile creates an owner-private directory.
                with tempfile.TemporaryDirectory(prefix='companion-l2d-') as temporary:
                    built=build_bundle(lock,workspace/'cache',Path(temporary),'win32-x64')
                    result=install_pair(target,built['bundle'],runtime_factory,accepted=True)
                    result['build']={key:value for key,value in built.items() if key!='bundle'}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (SetupError,UpdateError,OSError,ValueError,subprocess.SubprocessError,tarfile.TarError) as error:
        print(json.dumps({'error':str(error),'vendor_distributed':False,'windows_application_execution_verified':False},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)
