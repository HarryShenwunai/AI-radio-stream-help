"""Optional owner-installed Live2D runtime. No vendor JS is bundled or executed.

Role import never calls this module's installation methods. The fixed official
URL is fetched only after an explicit owner license acknowledgement. Local SDK
and renderer bundle installation additionally requires an owner-expected SHA256.
Recorded digests are observed/owner pins, NOT Live2D-published checksums.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import stat
import threading
import time
import urllib.request
from uuid import UUID, uuid4
import zipfile

OFFICIAL_CORE_URL = 'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js'
PROPRIETARY_LICENSE = 'https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html'
OPEN_SOFTWARE_LICENSE = 'https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html'
EXPANDABLE_LICENSE = 'https://www.live2d.com/en/sdk/license/expandable/'
MAX_SCRIPT_BYTES = 8*1024*1024
MAX_SDK_BYTES = 256*1024*1024
MAX_ENTRIES = 10000
KINDS = {'core': 'live2d-core.js', 'bundle': 'live2d-runtime.js'}

class Live2DRuntimeError(ValueError):
    """Fixed codes; no local paths, script contents or hidden network details."""

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Live2DRuntimeError('official_redirect_rejected')


def _digest(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise Live2DRuntimeError('expected_sha256_required')
    return value


def _safe_directory(path):
    for entry in (path,*path.parents):
        if entry.is_symlink() or getattr(entry,'is_junction',lambda:False)():
            raise Live2DRuntimeError('unsafe_runtime_directory')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise Live2DRuntimeError('unsafe_runtime_directory')
    if os.name=='posix':os.chmod(path,0o700)


def _read_file(path, limit):
    path=Path(path)
    if path.is_symlink():raise Live2DRuntimeError('symlink_rejected')
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
    try:
        with os.fdopen(os.open(path,flags),'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
                raise Live2DRuntimeError('file_limit')
            value=stream.read(limit+1)
    except OSError:
        raise Live2DRuntimeError('local_file_unavailable') from None
    if len(value)>limit:raise Live2DRuntimeError('file_limit')
    return value


def _write_file(path, data):
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
    with os.fdopen(os.open(path,flags,0o600),'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def _validate_script(data, kind):
    if not isinstance(data,bytes) or not 1<=len(data)<=MAX_SCRIPT_BYTES:
        raise Live2DRuntimeError('script_limit')
    try:text=data.decode('utf-8-sig')
    except UnicodeError:raise Live2DRuntimeError('script_not_utf8') from None
    marker='Live2DCubismCore' if kind=='core' else 'CompanionLive2DRuntime'
    if marker not in text or text.lstrip().lower().startswith(('<html','<!doctype')):
        raise Live2DRuntimeError('unexpected_script')


def inspect_local_sdk(source):
    """Read local data without execution/installation; no license is accepted."""
    path=Path(source)
    raw=_read_file(path,MAX_SDK_BYTES if path.suffix.lower()=='.zip' else MAX_SCRIPT_BYTES)
    if path.suffix.lower()!='.zip':
        if path.name not in {'live2dcubismcore.min.js','live2dcubismcore.js'}:
            raise Live2DRuntimeError('expected_sdk_core_filename')
        _validate_script(raw,'core')
        return raw, {'source_kind':'local_core_file','core_sha256':hashlib.sha256(raw).hexdigest()}
    import io
    # Bound central-directory allocation BEFORE ZipFile parses every member.
    tail=raw[-65557:];end=tail.rfind(b'PK\x05\x06')
    if end<0 or len(tail)-end<22:raise Live2DRuntimeError('invalid_sdk_archive')
    eocd=tail[end:end+22]
    if int.from_bytes(eocd[4:6],'little') or int.from_bytes(eocd[6:8],'little'):
        raise Live2DRuntimeError('multipart_sdk_rejected')
    if int.from_bytes(eocd[10:12],'little')>MAX_ENTRIES:
        raise Live2DRuntimeError('sdk_entry_limit')
    # The advertised count can lie: scan central headers without building Python
    # ZipInfo objects, then require the advertised and actual counts to agree.
    cd_start=int.from_bytes(eocd[16:20],'little');cd_size=int.from_bytes(eocd[12:16],'little')
    if cd_start+cd_size>len(raw):raise Live2DRuntimeError('invalid_sdk_archive')
    cursor=cd_start;count=0
    while cursor<cd_start+cd_size:
        if raw[cursor:cursor+4]!=b'PK\x01\x02' or cursor+46>cd_start+cd_size:
            raise Live2DRuntimeError('invalid_sdk_archive')
        name_size=int.from_bytes(raw[cursor+28:cursor+30],'little')
        extra_size=int.from_bytes(raw[cursor+30:cursor+32],'little')
        comment_size=int.from_bytes(raw[cursor+32:cursor+34],'little')
        count+=1
        if count>MAX_ENTRIES or name_size>2048:raise Live2DRuntimeError('sdk_entry_limit')
        cursor+=46+name_size+extra_size+comment_size
    if cursor!=cd_start+cd_size or count!=int.from_bytes(eocd[10:12],'little'):
        raise Live2DRuntimeError('invalid_sdk_archive')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members=archive.infolist()
            if len(members)>MAX_ENTRIES:raise Live2DRuntimeError('sdk_entry_limit')
            candidates=[]
            for item in members:
                name=item.filename
                parts=PurePosixPath(name).parts
                if len(name)>512 or '\\' in name or '\0' in name or ':' in name or name.startswith('/') or '..' in parts:
                    raise Live2DRuntimeError('unsafe_sdk_path')
                if re.fullmatch(r'(?:CubismSdkForWeb-[A-Za-z0-9._-]+/)?Core/live2dcubismcore(?:\.min)?\.js',name):
                    mode=item.external_attr>>16
                    if item.flag_bits&1 or stat.S_ISLNK(mode) or item.file_size>MAX_SCRIPT_BYTES:
                        raise Live2DRuntimeError('unsafe_sdk_core')
                    candidates.append(item)
            # A real SDK may contain both minified and non-minified Core. Prefer
            # exactly one minified entry, otherwise exactly one unminified entry.
            mini=[x for x in candidates if x.filename.endswith('.min.js')]
            chosen=mini or candidates
            if len(chosen)!=1:raise Live2DRuntimeError('ambiguous_or_missing_core')
            with archive.open(chosen[0]) as stream:data=stream.read(MAX_SCRIPT_BYTES+1)
            _validate_script(data,'core')
            return data, {'source_kind':'local_sdk_zip','core_sha256':hashlib.sha256(data).hexdigest(),
                          'sdk_sha256':hashlib.sha256(raw).hexdigest(),'member':chosen[0].filename}
    except (zipfile.BadZipFile,RuntimeError,OSError):
        raise Live2DRuntimeError('invalid_sdk_archive') from None


class Live2DRuntime:
    def __init__(self, root: Path):
        self.root=Path(root)
        self._lock=threading.RLock()
        self._cleanup_pending=False

    def _require_owner(self, accepted):
        if accepted is not True:
            raise Live2DRuntimeError('owner_license_confirmation_required')

    def _official_bytes(self):
        context=ssl.create_default_context()  # No insecure flag or custom URL.
        opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),NoRedirect())
        request=urllib.request.Request(OFFICIAL_CORE_URL,headers={'User-Agent':'Companion-Owner-Runtime-Installer/1'})
        try:
            with opener.open(request,timeout=15) as response:
                if response.geturl()!=OFFICIAL_CORE_URL or response.status!=200:
                    raise Live2DRuntimeError('unexpected_official_response')
                declared=response.headers.get('Content-Length')
                if declared is not None and (not declared.isdecimal() or int(declared)>MAX_SCRIPT_BYTES):
                    raise Live2DRuntimeError('download_limit')
                start=time.monotonic();chunks=[];length=0
                while True:
                    chunk=response.read(min(65536,MAX_SCRIPT_BYTES+1-length))
                    if not chunk:break
                    length+=len(chunk)
                    if length>MAX_SCRIPT_BYTES or time.monotonic()-start>30:
                        raise Live2DRuntimeError('download_limit')
                    chunks.append(chunk)
                data=b''.join(chunks)
                if declared is not None and int(declared)!=len(data):
                    raise Live2DRuntimeError('truncated_download')
                _validate_script(data,'core')
                return data
        except Live2DRuntimeError:raise
        except Exception:raise Live2DRuntimeError('official_download_failed') from None

    def install_official(self, *, accept_official_license=False):
        self._require_owner(accept_official_license)
        # Confirmation is checked BEFORE constructing any network client.
        data=self._official_bytes()
        return self._install('core',data,{'type':'official_https','url':OFFICIAL_CORE_URL,
                              'pin_kind':'observed_sha256','owner_license_acknowledged':True})

    def install_local(self, source, *, expected_sha256, trust_local_sdk=False, accept_official_license=False):
        self._require_owner(accept_official_license)
        if trust_local_sdk is not True:raise Live2DRuntimeError('owner_local_sdk_trust_required')
        expected=_digest(expected_sha256)
        data,info=inspect_local_sdk(source)
        if info['core_sha256']!=expected:raise Live2DRuntimeError('sha256_mismatch')
        return self._install('core',data,{'type':'owner_local_sdk','pin_kind':'owner_expected_sha256',
                              'owner_license_acknowledged':True,'owner_origin_attested':True,
                              'sdk_sha256':info.get('sdk_sha256'),'member':info.get('member')})

    def install_bundle(self, source, *, expected_sha256, accept_official_license=False,
                       trust_local_bundle=False):
        self._require_owner(accept_official_license)
        if trust_local_bundle is not True:raise Live2DRuntimeError('owner_local_bundle_trust_required')
        expected=_digest(expected_sha256)
        data=_read_file(Path(source),MAX_SCRIPT_BYTES);_validate_script(data,'bundle')
        if hashlib.sha256(data).hexdigest()!=expected:raise Live2DRuntimeError('sha256_mismatch')
        return self._install('bundle',data,{'type':'owner_local_bundle','pin_kind':'owner_expected_sha256',
                              'owner_license_acknowledged':True,'owner_origin_attested':True,
                              'versions':{'pixi':'8.23.0','wrapper':'1.4.0'},
                              'versions_verified':False})

    def _install(self, kind, data, source):
        _validate_script(data,kind)
        digest=hashlib.sha256(data).hexdigest()
        with self._lock:
            _safe_directory(self.root);revisions=self.root/'revisions';_safe_directory(revisions)
            revision=str(uuid4());folder=revisions/revision
            pointer=self.root/(kind+'.json');temporary=self.root/('.active-'+str(uuid4())+'.tmp')
            if pointer.is_symlink():raise Live2DRuntimeError('symlink_rejected')
            folder.mkdir(mode=0o700)
            record={'kind':kind,'sha256':digest,'bytes':len(data),'installed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'source':source,'official_published_digest':False,'runtime_execution_verified':False,
                    'publication_permission_verified':False,'license_links':[PROPRIETARY_LICENSE,OPEN_SOFTWARE_LICENSE,EXPANDABLE_LICENSE]}
            try:
                _write_file(folder/'script.js',data)
                _write_file(folder/'record.json',json.dumps(record,ensure_ascii=False,sort_keys=True).encode())
                _write_file(temporary,json.dumps({'revision':revision}).encode())
                os.replace(temporary,pointer)  # Previous active runtime survives any pre-commit failure.
            except Exception:
                shutil.rmtree(folder,ignore_errors=True)
                raise
            finally:temporary.unlink(missing_ok=True)
            try:
                self._prune();self._cleanup_pending=False
            except OSError:
                self._cleanup_pending=True
            result=self.status();result['restart_application_required']=True
            return result

    def _record_and_bytes(self, kind):
        # Reading status must not create runtime directories or fetch dependencies.
        for path in (self.root,*self.root.parents):
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise Live2DRuntimeError('unsafe_runtime_directory')
        raw=_read_file(self.root/(kind+'.json'),4096)
        try:
            pointer=json.loads(raw);revision=pointer['revision']
            if not isinstance(revision,str) or str(UUID(revision))!=revision:raise ValueError()
            folder=self.root/'revisions'/revision
            if any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (self.root/'revisions',folder)):raise ValueError()
            record=json.loads(_read_file(folder/'record.json',16384))
            source=record['source']
            if record['kind']!=kind or source['owner_license_acknowledged'] is not True:raise ValueError()
            if source['type']=='official_https':
                if kind!='core' or source['url']!=OFFICIAL_CORE_URL:raise ValueError()
            elif source['type'] not in ({'owner_local_sdk'} if kind=='core' else {'owner_local_bundle'}):raise ValueError()
            elif source.get('owner_origin_attested') is not True:raise ValueError()
            if source.get('pin_kind') != ('observed_sha256' if source['type']=='official_https' else 'owner_expected_sha256'):raise ValueError()
            if type(record.get('bytes')) is not int or not 1<=record['bytes']<=MAX_SCRIPT_BYTES:raise ValueError()
            if not isinstance(record.get('installed_at'),str) or len(record['installed_at'])>100:raise ValueError()
            expected=_digest(record['sha256'])
        except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
            raise Live2DRuntimeError('invalid_runtime_record') from None
        data=_read_file(folder/'script.js',MAX_SCRIPT_BYTES);_validate_script(data,kind)
        if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=expected:
            raise Live2DRuntimeError('installed_runtime_changed')
        return record,data

    def read_core(self):
        with self._lock:return self._record_and_bytes('core')[1]

    def read_bundle(self):
        with self._lock:return self._record_and_bytes('bundle')[1]

    def status(self):
        with self._lock:
            artifacts={}
            for kind in KINDS:
                try:
                    record,_=self._record_and_bytes(kind)
                    artifacts[kind]={'available':True,'sha256':record['sha256'],'source_type':record['source']['type'],
                                     'pin_kind':record['source']['pin_kind'],'installed_at':record['installed_at']}
                except (Live2DRuntimeError,OSError,ValueError):
                    artifacts[kind]={'available':False,'reason':'not_installed_or_unverified'}
            ready=all(x['available'] for x in artifacts.values())
            return {'available':ready,'core_available':artifacts['core']['available'],'bundle_available':artifacts['bundle']['available'],'renderer_available':artifacts['bundle']['available'],
                    'core_url':'/live2d-core.js' if artifacts['core']['available'] else None,
                    'runtime_url':'/live2d-runtime.js' if artifacts['bundle']['available'] else None,
                    'core_version':None,'cleanup_pending':self._cleanup_pending,'artifacts':artifacts,'official_published_digest':False,
                    'runtime_execution_verified':False,'publication_permission_verified':False,
                    'reason':None if ready else 'owner_runtime_setup_required',
                    'license_links':[PROPRIETARY_LICENSE,OPEN_SOFTWARE_LICENSE,EXPANDABLE_LICENSE]}

    def remove(self, kind=None):
        if kind is not None and kind not in KINDS:raise Live2DRuntimeError('invalid_artifact')
        with self._lock:
            if not self.root.exists():return self.status()
            _safe_directory(self.root)
            for selected in (KINDS if kind is None else [kind]):
                path=self.root/(selected+'.json')
                if path.is_symlink():raise Live2DRuntimeError('symlink_rejected')
                path.unlink(missing_ok=True)
            if (self.root/'revisions').exists():self._prune()
            return self.status()

    def _prune(self):
        # Only remove our own unreferenced UUID revision directories; retain the
        # active Core+bundle, at most two scripts, with no automatic update job.
        retained=set()
        for kind in KINDS:
            path=self.root/(kind+'.json')
            if path.exists() and not path.is_symlink():
                try:retained.add(json.loads(_read_file(path,4096))['revision'])
                except (ValueError,KeyError,Live2DRuntimeError,RecursionError):pass
        for path in (self.root/'revisions').iterdir():
            try:valid=str(UUID(path.name))==path.name
            except ValueError:valid=False
            if valid and path.name not in retained and path.is_dir() and not path.is_symlink() and not getattr(path,'is_junction',lambda:False)():
                shutil.rmtree(path)
