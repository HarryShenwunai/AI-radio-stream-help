"""Development-only deterministic Windows optional addon builder, never run at startup.

Input is an audited PyPI wheel lock. Does not install packages, modify the base
runtime or execute wheels. The result requires a trusted manifest SHA in the host.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import struct
import urllib.parse
import urllib.request
import zipfile

from .perception import _NoRedirect
from .perception_tracking import FACE_MODEL_SHA256,FACE_MODEL_BYTES,read_face_model


OMIT_PORTAUDIO = {'libportaudio.dylib': {'bytes': 236064, 'sha256': 'f48bedb7f4f79c0ca050776afe943458555db7341e0dae00511d109ccde907c0'}, 'libportaudio32bit-asio.dll': {'bytes': 280576, 'sha256': 'b96d817debe1747d8ca3a5e5b57d1021bf0207ebbd907242331357b97c65e6d7'}, 'libportaudio32bit.dll': {'bytes': 260608, 'sha256': '3d27383a00397dae64b266189791ac20f84a19820778724e05705c2f6012dfd9'}, 'libportaudio64bit-asio.dll': {'bytes': 343040, 'sha256': 'e38618a0cb83a0287bee3b8bd68a710ae0d34178217ef4fa21ed56f765111943'}, 'libportaudioarm64-asio.dll': {'bytes': 316416, 'sha256': '57b7826fd3883daabbb8951814655a4ec253acb822c0ff6ce4002da9463064f5'}, 'libportaudioarm64.dll': {'bytes': 293888, 'sha256': 'e39e95e95c0cb262c70ca4e676e440cf34be5643fe5a31cdfe23e8ab6f1422cb'}}


def canonical(value):
    return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()


def safe_relative(name):
    path=PurePosixPath(name)
    if (not name or len(name)>240 or name.startswith('/') or '\\' in name or ':' in name or
            any(part in ('','.','..') or part.endswith((' ','.')) or any(ord(c)<32 for c in part)
                for part in name.split('/'))):
        raise ValueError('Unsafe addon member')
    if any(part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],
                                        *[f'LPT{i}' for i in range(1,10)]} for part in path.parts):
        raise ValueError('Windows reserved addon member')
    if any(part.lower() in {'sitecustomize.py','usercustomize.py','__pycache__'} or
           part.lower().endswith(('.pth','.pyc','.pyo')) for part in path.parts):
        raise ValueError('Executable startup hook or bytecode is forbidden')
    return path


def fetch_wheel(package,cache):
    name=package['filename'];assert re.fullmatch(r'[A-Za-z0-9_.+%-]+',name)
    path=cache/name
    if path.is_file() and path.stat().st_size==package['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==package['sha256']:
        return path
    url=urllib.parse.urlsplit(package['url'])
    if url.scheme!='https' or url.hostname!='files.pythonhosted.org' or url.username or url.query or url.fragment:
        raise ValueError('Only locked official PyPI wheel URLs are accepted')
    temporary=path.with_suffix('.part')
    try:
        total=0;digest=hashlib.sha256()
        with urllib.request.build_opener(_NoRedirect()).open(package['url'],timeout=45) as response,temporary.open('xb') as output:
            while True:
                data=response.read(1024*1024)
                if not data:break
                total+=len(data)
                if total>package['bytes']:raise ValueError('Wheel exceeds locked size')
                digest.update(data);output.write(data)
        if total!=package['bytes'] or digest.hexdigest()!=package['sha256']:raise ValueError('Wheel SHA mismatch')
        temporary.replace(path)
        print('verified '+name,flush=True)
        return path
    finally:temporary.unlink(missing_ok=True)


def build(metadata_path,model_path,output_root,cache,archive_path):
    metadata=json.loads(metadata_path.read_bytes())
    packages=[p for p in metadata['packages'] if not p['reused_from_base']]
    assert len(packages)==15 and sum(p['bytes'] for p in packages)==93795778
    assert metadata['reused']=={'numpy':'2.5.4','pillow':'13.0.0','flatbuffers':'25.12.19','packaging':'26.3'}
    if output_root.exists():raise ValueError('Addon output must be a new directory')
    cache.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as pool:wheels=list(pool.map(lambda p:fetch_wheel(p,cache),packages))
    output_root.mkdir(parents=True,mode=0o700)
    seen=set();excluded=[];omitted=[];extracted=0
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            if len(archive.infolist())>15000:raise ValueError('Wheel member limit')
            for member in archive.infolist():
                if member.is_dir():continue
                path=safe_relative(member.filename)
                mode=member.external_attr>>16
                if stat.S_IFMT(mode) not in (0,stat.S_IFREG):raise ValueError('Nonregular wheel member')
                parts=path.parts
                if parts[0].endswith('.data'):
                    if len(parts)<3 or parts[1] not in ('purelib','platlib'):
                        excluded.append({'wheel':wheel.name,'member':member.filename,'reason':'non-import install scheme'});continue
                    parts=parts[2:]
                relative='python312/site-packages/'+'/'.join(parts)
                safe_relative(relative)
                if relative=='python312/site-packages/cv2/opencv_videoio_ffmpeg500_64.dll':
                    value=archive.read(member)
                    if len(value)!=30876160 or hashlib.sha256(value).hexdigest()!='7aabff029d1fa47cf56ede4dbbe05dc62da3208f07cd16471d4c966a33f9aa31':
                        raise ValueError('Unexpected optional FFmpeg plugin')
                    omitted.append({'path':relative,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest(),
                        'md5_matches_upstream_pin':'a821a1135251859655090c795af05789',
                        'reason':'Unused independently loaded Windows FFmpeg plugin omitted under upstream redistribution instructions; no camera/video codec capture is performed by this face pipeline.'})
                    continue
                if relative.startswith('python312/site-packages/_sounddevice_data/portaudio-binaries/') and parts[-1] in OMIT_PORTAUDIO:
                    value=archive.read(member);expected=OMIT_PORTAUDIO[parts[-1]]
                    if len(value)!=expected['bytes'] or hashlib.sha256(value).hexdigest()!=expected['sha256']:
                        raise ValueError('Unexpected optional PortAudio SDK/architecture binary')
                    omitted.append({'path':relative,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest(),
                        'reason':'Unused ASIO SDK or non-x64 platform standby omitted; retain default Windows x64 non-ASIO PortAudio selected by the unmodified upstream loader.'})
                    continue
                if relative.casefold() in seen:raise ValueError('Duplicate addon path')
                seen.add(relative.casefold())
                extracted+=member.file_size
                if extracted>450_000_000:raise ValueError('Uncompressed addon limit')
                target=output_root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(member) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
    if len(omitted)!=7:raise ValueError('Expected precisely seven omitted standalone/SDK/foreign-platform binaries')
    readme_url='https://raw.githubusercontent.com/opencv/opencv_3rdparty/06dc20cad65dc7fcf784f70c95d46750520889a7/readme.txt'
    with urllib.request.build_opener(_NoRedirect()).open(readme_url,timeout=20) as response:
        upstream_readme=response.read(20000)
    if b'simply exclude' not in upstream_readme or len(upstream_readme)>20000:raise ValueError('Official omission instructions unavailable')
    metadata['distribution_policy']={'revision':3,'omitted_runtime_plugins':omitted,'upstream_readme':readme_url,
        'upstream_readme_sha256':hashlib.sha256(upstream_readme).hexdigest(),
        'opencv_python_tag':'93','opencv_source_commit':'40738fb16ceddb5fb3fea747585f7ce6abb0605b',
        'upstream_ffmpeg_binary_commit':'06dc20cad65dc7fcf784f70c95d46750520889a7',
        'upstream_corresponding_source_commit':'664c0098dcb47b361f20c1d6a518653c23f5f2b5',
        'ffmpeg_libraries':{'avcodec':'61.19.100','avformat':'61.7.100','avutil':'59.39.100','swscale':'8.3.100'},
        'pe_fact':'cv2.pyd imports system/python DLLs, not FFmpeg plugin; official source documents runtime optional plugin loading.'}
    model=read_face_model(model_path)
    target=output_root/'models/face_landmarker.task';target.parent.mkdir();target.write_bytes(model)
    (output_root/'WHEEL-PROVENANCE.json').write_bytes(canonical(metadata))
    (output_root/'NOTICE-TRACKING.txt').write_text(
        'Optional local CPU face/head-direction estimation. Not professional eye tracking or identity recognition.\n'
        'Preserved upstream wheel licenses and third-party notices are under python312/site-packages.\n'
        'MediaPipe 1.2.3: https://github.com/google-ai-edge/mediapipe/releases/tag/v1.2.3 (Apache-2.0).\n'
        'Fixed official face_landmarker float16/1 task; SHA observed 2026-11-12, not a vendor-published SHA.\n'
        'Model source: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task\n'
        'Official BlazeFace / Face Mesh V2 / Blendshapes V2 model cards each state Apache License, Version 2.0.\n'
        'Model cards: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker\n'
        'No sample portrait, user image, biometric identity database, chat history or credentials are included.\n'
        'Windows CPython 3.12 x64 DLL execution has not been tested on this Linux build host.\n',encoding='utf-8')
    notice=output_root/'NOTICE-TRACKING.txt'
    with notice.open('a',encoding='utf-8') as stream:
        stream.write('\nRevision 3 deliberately omits the independent Windows FFmpeg LGPL plugin, original SHA256 '+omitted[0]['sha256']+'.\n')
        stream.write('Also omitted: '+', '.join(sorted(OMIT_PORTAUDIO))+'. The default libportaudio64bit.dll and all license/README files remain.\n')
        stream.write('Upstream sounddevice.py selects the x64 non-ASIO DLL unless SD_ENABLE_ASIO is explicitly set. MediaPipe imports sounddevice for its unused audio APIs, but this face-only pipeline opens no Python audio streams.\n')
        stream.write('All other wheel members and upstream licenses/notices remain unchanged. Browser capture -> Pillow RGB -> numpy -> MediaPipe Tasks does not call OpenCV VideoCapture/VideoWriter.\n')
        stream.write('Exact upstream source and omission instructions: '+readme_url+'\n\n')
        stream.write(upstream_readme.decode('utf-8'))
    with urllib.request.build_opener(_NoRedirect()).open('https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.2.3/LICENSE',timeout=20) as response:
        license_data=response.read(20000)
    if b'Apache License' not in license_data or len(license_data)>20000:raise ValueError('Official license unavailable')
    (output_root/'LICENSE-MEDIAPIPE-MODEL.txt').write_bytes(license_data)
    # Audit every executable magic, including unexpected extension names.
    native_components=[]
    for file in sorted(output_root.rglob('*')):
        if not file.is_file():continue
        with file.open('rb') as source:
            header=source.read(64)
            if header.startswith(b'MZ'):
                offset=struct.unpack('<I',header[60:64])[0];source.seek(offset);pe=source.read(6)
                if pe[:4]!=b'PE\x00\x00' or struct.unpack('<H',pe[4:])[0]!=0x8664 or file.suffix.lower() not in ('.dll','.pyd'):
                    raise ValueError('Only audited x64 DLL/CPython extension components are accepted')
                native_components.append(file.relative_to(output_root).as_posix())
            elif header[:4] in (b'\xca\xfe\xba\xbe',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\x7fELF'):
                raise ValueError('Unexpected non-Windows executable component')
    if len(native_components)!=20:raise ValueError('Unexpected native component inventory')
    files=[]
    for file in sorted(output_root.rglob('*')):
        if file.is_file():files.append({'path':file.relative_to(output_root).as_posix(),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    manifest={'format':'companion-tracking-addon-v1','addon_revision':3,'omitted_runtime_plugins':omitted,'python':'cp312-win_amd64','mediapipe_version':'1.2.3',
              'reused_base_distributions':metadata['reused'],'wheel_download_bytes':metadata['download_bytes'],
              'model_sha256':FACE_MODEL_SHA256,'model_bytes':FACE_MODEL_BYTES,'native_x64_components':native_components,'files':files,
              'excluded_nonimport_members':excluded,'windows_execution_verified':False}
    raw=canonical(manifest);(output_root/'tracking-addon-manifest.json').write_bytes(raw)
    archive_path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(output_root.rglob('*')):
            if file.is_file():
                info=zipfile.ZipInfo(file.relative_to(output_root).as_posix(),date_time=(2026,11,12,0,0,0))
                info.create_system=3;info.external_attr=(stat.S_IFREG|0o600)<<16;info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,file.read_bytes(),compresslevel=6)
    report={'manifest_sha256':hashlib.sha256(raw).hexdigest(),'manifest_bytes':len(raw),'locked_file_count':len(files),
            'expanded_bytes':sum(f['bytes'] for f in files)+len(raw),'wheel_download_bytes':metadata['download_bytes'],
            'archive_bytes':archive_path.stat().st_size,'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            'addon_directory':str(output_root),'archive_path':str(archive_path),'windows_execution_verified':False}
    print(json.dumps(report,indent=2));return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--metadata',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    report=build(args.metadata,args.model,args.output,args.cache,args.archive)
    args.report.write_bytes(canonical(report))


if __name__=='__main__':main()
