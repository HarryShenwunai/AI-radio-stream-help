"""Verify one fixed Windows tracking addon, then append its import directory.

Never accepts a renderer/role path, runs pip, uses addsitedir or executes .pth/
sitecustomize. The caller supplies the application's own __file__ parent only.
"""
from __future__ import annotations
from dataclasses import dataclass,field
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import struct
import sys
from typing import Any

MANIFEST_SHA256 = 'de08abac2f341d0cacf2eba38fc89e53bef0252f98cc2f258736b95ed95bad12'
REUSED_BASE = {'numpy':'2.5.4','pillow':'13.0.0','flatbuffers':'25.12.19','packaging':'26.3'}
MAX_MANIFEST_BYTES = 4_000_000
MAX_FILES = 15_000


@dataclass(frozen=True)
class TrackingAddonState:
    verified: bool = False
    activated: bool = False
    reason: str = 'not_installed'
    model_path: Path | None = field(default=None,repr=False)
    site_packages_path: Path | None = field(default=None,repr=False)

    def public(self) -> dict[str,object]:
        return {'verified':self.verified,'activated':self.activated,'reason':self.reason,
                'manifest_sha256':MANIFEST_SHA256,'windows_execution_verified':False}


class _InvalidAddon(ValueError):
    pass


def _unsafe(info:os.stat_result)->bool:
    return (stat.S_ISLNK(info.st_mode) or
            bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)))


def _parents(path:Path)->None:
    for parent in (path,*path.parents):
        info=parent.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):raise _InvalidAddon('unsafe_addon_path')


def _locate(app_root:Path)->tuple[Path,Path]|None:
    app_root=app_root.absolute()
    if app_root.name!='app':return None
    backend=app_root.parent
    if backend.name=='backend' and backend.parent.name=='resources':resources=backend.parent
    elif (backend.name=='cuda' and backend.parent.name=='backend-profiles' and
          backend.parent.parent.name=='resources'):resources=backend.parent.parent
    else:return None
    _parents(app_root)
    return backend,resources/'optional'/'tracking'


def _relative(value:object)->str:
    if not isinstance(value,str) or not value or len(value)>240 or ':' in value or '\\' in value:
        raise _InvalidAddon('invalid_addon_member')
    path=PurePosixPath(value)
    if path.is_absolute() or any(part in ('','.','..') or part.endswith((' ','.')) or
            any(ord(char)<32 for char in part) for part in value.split('/')):
        raise _InvalidAddon('invalid_addon_member')
    for part in path.parts:
        if part.lower().endswith(('-asio.dll','.dylib')) or part.lower() in ('libportaudio32bit.dll','libportaudioarm64.dll'):
            raise _InvalidAddon('unneeded_sdk_or_platform_binary_forbidden')
        if (part.lower().startswith('opencv_videoio_ffmpeg') and part.lower().endswith('.dll')):
            raise _InvalidAddon('unneeded_ffmpeg_plugin_forbidden')
        if (part.lower() in ('__pycache__','sitecustomize.py','usercustomize.py') or
            part.lower().endswith(('.pth','.pyc','.pyo')) or
            part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],
                                         *[f'LPT{i}' for i in range(1,10)]}):
            raise _InvalidAddon('invalid_addon_member')
    return value


def _file_hash(path:Path,expected_size:int)->str:
    _parents(path.parent)
    info=path.lstat()
    if _unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_size!=expected_size:
        raise _InvalidAddon('addon_file_mismatch')
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
    with os.fdopen(os.open(path,flags),'rb') as source:
        opened=os.fstat(source.fileno())
        if (_unsafe(opened) or not stat.S_ISREG(opened.st_mode) or opened.st_size!=expected_size or
            (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino)):
            raise _InvalidAddon('addon_file_mismatch')
        result=hashlib.sha256();total=0
        while True:
            block=source.read(1024*1024)
            if not block:break
            total+=len(block)
            if total>expected_size:raise _InvalidAddon('addon_file_mismatch')
            result.update(block)
        if total!=expected_size:raise _InvalidAddon('addon_file_mismatch')
    return result.hexdigest()


def _verify(backend:Path,addon:Path)->TrackingAddonState:
    if not addon.exists():return TrackingAddonState(reason='not_installed')
    _parents(addon)
    file=addon/'tracking-addon-manifest.json'
    info=file.lstat()
    if _unsafe(info) or not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=MAX_MANIFEST_BYTES:
        raise _InvalidAddon('invalid_addon_manifest')
    if not re.fullmatch('[a-f0-9]{64}',MANIFEST_SHA256) or _file_hash(file,info.st_size)!=MANIFEST_SHA256:
        raise _InvalidAddon('addon_manifest_mismatch')
    # Hash again after bounded read: JSON is never parsed from an unpinned replacement.
    with os.fdopen(os.open(file,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)),'rb') as stream:
        opened=os.fstat(stream.fileno())
        if _unsafe(opened) or not stat.S_ISREG(opened.st_mode) or opened.st_size>MAX_MANIFEST_BYTES:
            raise _InvalidAddon('invalid_addon_manifest')
        raw=stream.read(MAX_MANIFEST_BYTES+1)
    if len(raw)>MAX_MANIFEST_BYTES or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA256:
        raise _InvalidAddon('addon_manifest_mismatch')
    manifest:Any=json.loads(raw)
    if (not isinstance(manifest,dict) or manifest.get('format')!='companion-tracking-addon-v1' or
        manifest.get('addon_revision')!=3 or manifest.get('python')!='cp312-win_amd64' or manifest.get('mediapipe_version')!='1.2.3' or
        manifest.get('reused_base_distributions')!=REUSED_BASE):raise _InvalidAddon('invalid_addon_manifest')
    rows=manifest.get('files')
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_FILES:raise _InvalidAddon('invalid_addon_manifest')
    expected={'tracking-addon-manifest.json'};folded={'tracking-addon-manifest.json'};directories={''}
    total=0
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'path','bytes','sha256'}:raise _InvalidAddon('invalid_addon_manifest')
        name=_relative(row['path']);size=row['bytes'];digest=row['sha256']
        if (type(size) is not int or not 0<=size<=150_000_000 or not isinstance(digest,str) or
            not re.fullmatch('[a-f0-9]{64}',digest) or name.casefold() in folded):
            raise _InvalidAddon('invalid_addon_manifest')
        if not (name.startswith('python312/site-packages/') or name in ('models/face_landmarker.task',
                'WHEEL-PROVENANCE.json','NOTICE-TRACKING.txt','LICENSE-MEDIAPIPE-MODEL.txt')):
            raise _InvalidAddon('invalid_addon_member')
        top=PurePosixPath(name).parts
        if len(top)>2 and top[:2]==('python312','site-packages') and top[2].lower() in ('numpy','pil','flatbuffers','packaging'):
            raise _InvalidAddon('base_dependency_replacement_forbidden')
        total+=size
        if total>450_000_000:raise _InvalidAddon('addon_size_limit')
        if _file_hash(addon/name,size)!=digest:raise _InvalidAddon('addon_file_mismatch')
        expected.add(name);folded.add(name.casefold())
        for parent in PurePosixPath(name).parents:
            if str(parent)!='.':directories.add(str(parent))
    stack=[addon];seen=set();count=0
    while stack:
        directory=stack.pop()
        for item in directory.iterdir():
            count+=1
            if count>MAX_FILES*3:raise _InvalidAddon('addon_member_limit')
            name=item.relative_to(addon).as_posix();info=item.lstat()
            if _unsafe(info):raise _InvalidAddon('unsafe_addon_path')
            if stat.S_ISDIR(info.st_mode):
                if name not in directories:raise _InvalidAddon('unlisted_addon_directory')
                stack.append(item)
            elif stat.S_ISREG(info.st_mode):
                if name not in expected:raise _InvalidAddon('unlisted_addon_file')
                seen.add(name)
            else:raise _InvalidAddon('unsafe_addon_path')
    if seen!=expected:raise _InvalidAddon('addon_file_mismatch')
    return TrackingAddonState(True,False,'verified',addon/'models/face_landmarker.task',addon/'python312/site-packages')


def verify_tracking_addon(backend_app_root:Path)->TrackingAddonState:
    """Offline verification, no imports; useful on a Linux cross-build host too."""
    try:
        located=_locate(backend_app_root)
        if located is None:return TrackingAddonState(reason='not_installed')
        return _verify(*located)
    except _InvalidAddon as error:return TrackingAddonState(reason=str(error))
    except Exception:return TrackingAddonState(reason='invalid_addon')


def activate_tracking_addon(backend_app_root:Path)->TrackingAddonState:
    """Host-only fixed layout; failures leave the normal chat runtime untouched."""
    if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or struct.calcsize('P')!=8:
        return TrackingAddonState(reason='unsupported_runtime')
    state=verify_tracking_addon(backend_app_root)
    if not state.verified:return state
    try:
        located=_locate(backend_app_root)
        if located is None:return TrackingAddonState(reason='not_installed')
        backend,_=located
        base=(backend/'python/Lib/site-packages').absolute()
        _parents(base)
        for name,version in REUSED_BASE.items():
            distribution=importlib.metadata.distribution(name)
            if distribution.version!=version or Path(str(distribution.locate_file(''))).absolute()!=base:
                return TrackingAddonState(reason='base_dependency_mismatch')
        # No unlisted bytecode may later take precedence over verified source.
        sys.dont_write_bytecode=True
        directory=str(state.site_packages_path)
        if directory not in sys.path:sys.path.append(directory)
        importlib.invalidate_caches()
        return TrackingAddonState(True,True,'activated',state.model_path,state.site_packages_path)
    except Exception:return TrackingAddonState(reason='base_dependency_mismatch')
