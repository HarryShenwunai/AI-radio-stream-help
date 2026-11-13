"""Package explicitly pinned original Live2D runtime and editable sources.

Publishing tool only. It never downloads dependencies, runs Core, exports a rig,
or upgrades a candidate to an accepted/full character. The format check uses the
real application's AssetStore; a synthetic MOC envelope can pass that check.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES=512*1024*1024
MAX_SOURCE_FILE=256*1024*1024
MAX_PROJECT_FILE=320*1024*1024
MAX_JSON=8*1024*1024
MAX_PROJECT_JOURNAL=64*1024*1024
MAX_PROJECT_EXPANDED=2*1024*1024*1024
PROJECT_JOURNAL=re.compile(r'document/nodes/journal/([a-f0-9]{64})\.json')
DENIED_PARTS=frozenset({'vendor','node_modules','.live2d','.live2d-tools','sdk','data','profile-data','user-data',
                       'rejected-3d-reference','haru','hiyori','hiyori_pro','cubismwebsamples','cubismwebframework'})
DENIED_MOC_SHA256=frozenset({'aa59f7a3dc3b30b23b5f10afd9192ed755e4d01dc9a12442d99b972a418e2543',
                            '0323f5f377b9afef54318be09e9b4eea2a8cb266190ff9d2f843f95ecb77716c'})
REQUIRED=frozenset({'runtime_model','runtime_files','source_manifest','psd','cmo3','project','rig_recipe','notice'})

class PackageError(ValueError):pass

def sha(file: Path) -> str:
    with file.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise PackageError('duplicate_json_key')
        result[key]=value
    return result

def _json(data: bytes):
    if len(data)>MAX_JSON:raise PackageError('json_size_limit')
    def invalid(_value):raise PackageError('nonfinite_json')
    try:
        value=json.loads(data.decode('utf-8-sig'),object_pairs_hook=_pairs,parse_constant=invalid)
        if not isinstance(value,dict):raise PackageError('json_object_required')
        return value
    except (UnicodeError,json.JSONDecodeError) as error:raise PackageError('invalid_json') from error

def relative(value: str) -> str:
    if not isinstance(value,str) or not value or len(value)>240 or any(c in value for c in '\\:%?#<>"|*'):
        raise PackageError('unsafe_relative_path')
    path=PurePosixPath(value)
    if path.is_absolute() or any(part in {'','.','..'} for part in value.split('/')):raise PackageError('path_escape')
    for part in path.parts:
        lower=part.casefold()
        if lower in DENIED_PARTS or lower.startswith(('cubismsdk','rejected-3d')):raise PackageError('forbidden_source_directory')
        if part.endswith((' ','.')) or any(ord(c)<32 for c in part) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise PackageError('unsafe_windows_name')
    return path.as_posix()

def safe_file(root: Path,name: str,limit=MAX_SOURCE_FILE) -> Path:
    name=relative(name);file=root/name
    for part in (root,*root.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PackageError('source_link_rejected')
    current=root
    for part in PurePosixPath(name).parts:
        current=current/part
        if current.is_symlink() or getattr(current,'is_junction',lambda:False)():raise PackageError('source_link_rejected')
    if not file.is_file() or file.stat().st_size>limit:raise PackageError('source_not_regular_or_over_budget: '+name)
    return file

def pinned(root: Path,row: dict,suffixes: tuple[str,...],pins: dict | None=None, *, source_limit: int=MAX_SOURCE_FILE) -> Path:
    if not isinstance(row,dict) or not {'path','sha256'}<=set(row) or not isinstance(row['path'],str) or not re.fullmatch('[a-f0-9]{64}',str(row['sha256'])):
        raise PackageError('invalid_source_pin')
    if not row['path'].lower().endswith(suffixes):raise PackageError('source_type_not_allowlisted')
    file=safe_file(root,row['path'],min(source_limit,MAX_JSON) if row['path'].lower().endswith('.json') else source_limit)
    if sha(file)!=row['sha256']:raise PackageError('source_identity_sha_mismatch: '+row['path'])
    if pins is not None:
        if file in pins and pins[file]!=row['sha256']:raise PackageError('conflicting_source_pin')
        pins[file]=row['sha256']
    return file

def runtime_members(root: Path,model_row: dict,notice_row: dict,runtime_pins: dict,pins: dict) -> tuple[dict,dict]:
    model=pinned(root,model_row,('.model3.json',),pins);doc=_json(model.read_bytes());refs=doc.get('FileReferences')
    if not isinstance(refs,dict) or not {'Moc','Textures'}<=set(refs):raise PackageError('model_references_required')
    if set(refs)-{'Moc','Textures','Physics','DisplayInfo','Pose','Expressions','Motions'}:raise PackageError('unsupported_runtime_reference')
    members={model.name:model};paths=[(refs['Moc'],('.moc3',))]
    if not isinstance(refs['Textures'],list):raise PackageError('textures_must_be_list')
    paths.extend((name,('.png',)) for name in refs['Textures'])
    for field,suffix in [('Physics','.physics3.json'),('DisplayInfo','.cdi3.json'),('Pose','.pose3.json')]:
        if field in refs:paths.append((refs[field],(suffix,)))
    for row in refs.get('Expressions',[]):paths.append((row['File'],('.exp3.json',)))
    for rows in refs.get('Motions',{}).values():
        for row in rows:
            if 'Sound' in row:raise PackageError('model_audio_is_outside_runtime_package_scope')
            paths.append((row['File'],('.motion3.json',)))
    if not isinstance(runtime_pins,dict) or set(runtime_pins)!={name for name,_suffix in paths}:raise PackageError('runtime_reference_pin_set_mismatch')
    for name,suffix in paths:
        name=relative(name)
        if not name.lower().endswith(suffix):raise PackageError('runtime_reference_type_mismatch')
        file=pinned(model.parent,{'path':name,'sha256':runtime_pins[name]},suffix,pins)
        if file.stat().st_size>32*1024*1024:raise PackageError('runtime_resource_limit')
        if name.casefold() in {key.casefold() for key in members} and name not in members:raise PackageError('case_alias_runtime_member')
        members[name]=file
    moc=safe_file(model.parent,refs['Moc'])
    if sha(moc) in DENIED_MOC_SHA256:raise PackageError('known_official_sample_model_rejected')
    notice=pinned(root,notice_row,('.txt','.md'),pins)
    if notice.stat().st_size>64*1024:raise PackageError('notice_size_limit')
    notice.read_text(encoding='utf-8-sig');members['NOTICE.txt']=notice
    return members,{'model_sha256':sha(model),'moc_sha256':sha(moc),'moc_source':moc.relative_to(root).as_posix()}

def _project_member(name: str) -> bool:
    if name in {'README.txt','workspace.json','manifest.json','thumbnail.png','source/original.psd','auxiliary/tasks.json','history/HEAD.json'}:return True
    return bool(re.fullmatch(r'assets/[a-f0-9]{64}-[0-9]+x[0-9]+\.png|document/(?:clips|nodes/[a-z]+)/[a-f0-9]{64}\.json|history/(?:nodes|revisions)/[a-f0-9]{64}\.json|rig/objects/[a-f0-9]{64}\.bin|rig/revisions/revision-[a-f0-9]{64}\.json',name))

def check_project(project: Path,psd_sha256: str) -> dict:
    with zipfile.ZipFile(project) as archive:
        infos=archive.infolist()
        if not 1<=len(infos)<=8192:raise PackageError('project_entry_limit')
        names=set();total=0;journals=0;largest_journal=0
        for info in infos:
            relative(info.filename)
            mode=stat.S_IFMT(info.external_attr>>16)
            if not _project_member(info.filename) or info.is_dir() or mode not in {0,stat.S_IFREG} or info.flag_bits&1:
                raise PackageError('project_member_not_allowlisted')
            if info.filename.casefold() in names:raise PackageError('project_case_alias')
            names.add(info.filename.casefold());total+=info.file_size
            journal=PROJECT_JOURNAL.fullmatch(info.filename)
            member_limit=MAX_PROJECT_JOURNAL if journal else (MAX_JSON if info.filename.endswith('.json') else MAX_SOURCE_FILE)
            if info.file_size>member_limit or total>MAX_PROJECT_EXPANDED:raise PackageError('project_expansion_limit')
            if journal:journals+=1;largest_journal=max(largest_journal,info.file_size)
        if not {'manifest.json','source/original.psd'}<=set(archive.namelist()):raise PackageError('project_source_identity_missing')
        manifest=_json(archive.read('manifest.json'))
        if manifest.get('format')!='PSD2Live' or not isinstance(manifest.get('files'),dict):raise PackageError('not_a_psd2live_project')
        if set(manifest['files'])!=set(archive.namelist())-{'manifest.json'}:raise PackageError('project_manifest_member_mismatch')
        for name,wanted in manifest['files'].items():
            with archive.open(name) as source:
                first=source.read(4)
                if name.endswith('.bin') and first!=b'PRIO':raise PackageError('project_binary_is_not_psd2live_rig_data')
                checksum=hashlib.sha256(first)
                while chunk:=source.read(1024*1024):checksum.update(chunk)
                actual=checksum.hexdigest()
            journal=PROJECT_JOURNAL.fullmatch(name)
            if journal and actual!=journal.group(1):raise PackageError('project_journal_content_address_mismatch')
            if actual!=wanted:raise PackageError('project_member_sha_mismatch')
            if name=='source/original.psd' and actual!=psd_sha256:raise PackageError('project_embedded_psd_identity_mismatch')
    return {'project_manifest_members_verified':len(infos)-1,'project_embedded_psd_matches':True,
        'project_expanded_bytes':total,'project_journal_members_verified':journals,'project_largest_journal_bytes':largest_journal,
        'project_budget_scope':'maintainer_offline_source_packaging_only'}

def check_png(file: Path, *, layer=False) -> None:
    from PIL import Image
    with file.open('rb') as source:header=source.read(24)
    if len(header)!=24 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR' or not all(1<=side<=8192 for side in struct.unpack('>II',header[16:24])):
        raise PackageError('original_png_required')
    try:
        with Image.open(file) as image:
            if image.format!='PNG' or (layer and image.mode!='RGBA'):raise PackageError('original_png_required')
            image.verify()
    except OSError as error:raise PackageError('source_png_invalid') from error

def source_members(root: Path,spec: dict,runtime: dict,pins: dict) -> tuple[dict,dict]:
    manifest=pinned(root,spec['source_manifest'],('.json',),pins);doc=_json(manifest.read_bytes())
    if doc.get('format')!='original-live2d-layers-v1' or not isinstance(doc.get('layers'),list) or not 1<=len(doc['layers'])<=128:
        raise PackageError('original_layer_manifest_required')
    psd=pinned(root,spec['psd'],('.psd',),pins);cmo=pinned(root,spec['cmo3'],('.cmo3',),pins)
    project=pinned(root,spec['project'],('.psd2live',),pins,source_limit=MAX_PROJECT_FILE);recipe=pinned(root,spec['rig_recipe'],('.json',),pins)
    with psd.open('rb') as source:header=source.read(26)
    if len(header)!=26 or header[:6]!=b'8BPS\x00\x01' or struct.unpack_from('>II',header,14)!=(doc['canvas']['height'],doc['canvas']['width']):
        raise PackageError('psd_header_or_canvas_identity_mismatch')
    with cmo.open('rb') as source:
        if source.read(4)!=b'CAFF':raise PackageError('cmo3_header_required')
    if _json(recipe.read_bytes()).get('format')!='original-live2d-recipe-v1':raise PackageError('original_rig_recipe_required')
    members={'runtime/'+name:file for name,file in runtime.items()}
    members.update({'source/art/layers.json':manifest,'source/character.psd':psd,'source/character.cmo3':cmo,
                    'source/character.psd2live':project,'source/rig-recipe.json':recipe})
    if 'can3' in spec:
        animator=pinned(root,spec['can3'],('.can3',),pins)
        with animator.open('rb') as source:
            if source.read(4)!=b'CAFF':raise PackageError('can3_header_required')
        members['source/character.can3']=animator
    for layer in doc['layers']:
        name=relative(layer['file']);file=pinned(manifest.parent,{'path':name,'sha256':layer.get('sha256')},('.png',),pins);check_png(file,layer=True)
        members['source/art/'+name]=file
    for key,suffix in [('original_sources',('.png',)),('source_manifests',('.json',))]:
        rows=spec.get(key,[])
        if not isinstance(rows,list) or len(rows)>256:raise PackageError('additional_source_limit')
        for row in rows:
            file=pinned(root,row,suffix,pins);destination='source/art/'+relative(row['relative'])
            if not destination.lower().endswith(suffix):raise PackageError('source_archive_type_mismatch')
            if key=='source_manifests' and _json(file.read_bytes()).get('format')!='original-live2d-layers-v1':raise PackageError('original_submanifest_required')
            if key=='original_sources':check_png(file)
            if destination in members and members[destination]!=file:raise PackageError('source_archive_collision')
            members[destination]=file
    checks=check_project(project,sha(psd));checks.update({'source_layer_sha256_verified':len(doc['layers']),
        'authorship_independently_verified':False,'export_reproducibility_verified':False,'editor_reopen_verified':False})
    return members,checks

def bind_acceptance(root: Path,row: dict | None,moc_sha256: str,pins: dict) -> tuple[dict,Path | None]:
    if row is None:return {'bound':False,'decision_by_packager':'not_performed'},None
    file=pinned(root,row,('.json',),pins);index=_json(file.read_bytes())
    if index.get('moc_sha256')!=moc_sha256:raise PackageError('acceptance_index_moc_identity_mismatch')
    entries=index.get('evidence',[])
    if not isinstance(entries,list) or len(entries)>128:raise PackageError('evidence_limit')
    receipts=[]
    for evidence in entries:
        source=pinned(root,evidence,('.json','.png','.webm','.wav','.mp4','.txt'),pins)
        receipts.append({'path':evidence['path'],'sha256':sha(source),'bytes':source.stat().st_size,'copied_into_source_zip':False})
    return {'bound':True,'index_sha256':sha(file),'moc_sha256':moc_sha256,'evidence':receipts,'decision_by_packager':'not_performed'},file

def receipts(members: dict,pins: dict) -> list[dict]:
    aliases=set();rows=[]
    for name,file in sorted(members.items()):
        relative(name)
        if name.casefold() in aliases:raise PackageError('case_alias_archive_member')
        actual=sha(file)
        if file in pins and actual!=pins[file]:raise PackageError('input_changed_after_pin_check')
        aliases.add(name.casefold());rows.append({'path':name,'bytes':file.stat().st_size,'sha256':actual})
    return rows

def write_zip(file: Path,members: dict,pins: dict) -> None:
    with zipfile.ZipFile(file,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,source in sorted(members.items()):
            checksum=hashlib.sha256()
            with source.open('rb') as stream,archive.open(name,'w',force_zip64=True) as output:
                while chunk:=stream.read(1024*1024):checksum.update(chunk);output.write(chunk)
            if source in pins and checksum.hexdigest()!=pins[source]:raise PackageError('input_changed_during_archive_write')
    with zipfile.ZipFile(file) as archive:
        if archive.testzip() is not None:raise PackageError('zip_crc_failed')

def format_check(file: Path,moc_sha256: str) -> dict:
    sys.path.insert(0,str(ROOT/'src'))
    from companion_runtime.assets import AssetStore
    if file.stat().st_size>64*1024*1024:raise PackageError('runtime_zip_exceeds_import_budget')
    with tempfile.TemporaryDirectory(prefix='live2d-import-format-') as directory:
        manifest=AssetStore(Path(directory)/'assets').import_live2d(file.read_bytes(),file.name)
        mocs=[value for name,value in manifest['resources'].items() if name.endswith('.moc3')]
        if len(mocs)!=1 or mocs[0]['sha256']!=moc_sha256:raise PackageError('imported_moc_identity_changed')
        return {'passed':True,'method':'actual_AssetStore.import_live2d','scope':'format_and_normalization_only',
            'core_execution_performed':False,'core_consistency_verified':False,'playability_verified':False,
            'art_acceptance_verified':False,'capabilities_declared':manifest['capabilities']}

def package_character(root: Path,spec_file: Path,output: Path) -> dict:
    root=root.absolute()
    try:spec_relative=spec_file.absolute().relative_to(root).as_posix()
    except ValueError as error:raise PackageError('spec_must_be_under_explicit_root') from error
    spec_file=safe_file(root,spec_relative,MAX_JSON);spec_raw=spec_file.read_bytes();spec=_json(spec_raw)
    allowed=REQUIRED|{'format','identity','origin','original_sources','source_manifests','acceptance_index','can3'}
    if not isinstance(spec,dict) or set(spec)-allowed or not REQUIRED<=set(spec) or spec.get('format')!='original-live2d-package-spec-v1' or spec.get('origin')!='project-original-authoring':
        raise PackageError('explicit_original_source_spec_required')
    identity=spec.get('identity')
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',identity):raise PackageError('invalid_identity_label')
    output=output.absolute()
    for parent in (output,*output.parents):
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise PackageError('output_link_rejected')
    targets={kind:output/(identity+'-candidate-'+kind+suffix) for kind,suffix in [('runtime','.zip'),('source','.zip'),('report','.json')]}
    if any(file.exists() or file.is_symlink() for file in targets.values()):raise PackageError('output_exists_refusing_overwrite')
    pins={spec_file:hashlib.sha256(spec_raw).hexdigest()}
    runtime,binding=runtime_members(root,spec['runtime_model'],spec['notice'],spec['runtime_files'],pins);sources,checks=source_members(root,spec,runtime,pins)
    acceptance,index=bind_acceptance(root,spec.get('acceptance_index'),binding['moc_sha256'],pins)
    if index:sources['validation/acceptance-index.json']=index
    runtime_rows=receipts(runtime,pins);source_rows=receipts(sources,pins)
    if sum(row['bytes'] for row in runtime_rows)>96*1024*1024 or sum(row['bytes'] for row in source_rows)>MAX_SOURCE_BYTES:raise PackageError('package_total_size_limit')
    # Recheck all pinned bytes after project/archive inspection, before writing.
    before={name:sha(file) for name,file in sources.items()}
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.live2d-package-',dir=output) as directory:
        stage=Path(directory);runtime_zip=stage/'runtime.zip';write_zip(runtime_zip,runtime,pins)
        imported=format_check(runtime_zip,binding['moc_sha256'])
        input_file=stage/'PACKAGE-INPUT.json';input_file.write_bytes(spec_raw);sources['PACKAGE-INPUT.json']=input_file
        source_rows=receipts(sources,pins)
        if sum(row['bytes'] for row in source_rows)>MAX_SOURCE_BYTES:raise PackageError('package_total_size_limit')
        package_index={'format':'original-live2d-source-package-index-v1','status':'candidate','identity':identity,
            'binding':binding,'source_identity_checks':checks,'runtime_members':runtime_rows,'source_members_excluding_index':source_rows,
            'format_validation':imported,'acceptance_binding':acceptance,'core_passed_by_packager':False,'full_character_claimed':False}
        index_file=stage/'PACKAGE-INDEX.json';index_file.write_text(json.dumps(package_index,ensure_ascii=False,indent=2)+'\n')
        sources['PACKAGE-INDEX.json']=index_file
        source_zip=stage/'source.zip';write_zip(source_zip,sources,pins)
        if any(sha(file)!=wanted for file,wanted in pins.items()) or any(sha(sources[name])!=wanted for name,wanted in before.items()):raise PackageError('input_changed_during_packaging')
        report={**package_index,'source_members':receipts(sources,pins),'runtime_zip':{'name':targets['runtime'].name,'bytes':runtime_zip.stat().st_size,'sha256':sha(runtime_zip)},
            'source_zip':{'name':targets['source'].name,'bytes':source_zip.stat().st_size,'sha256':sha(source_zip)},'multi_output_commit_atomic':False}
        report_file=stage/'report.json';report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        staged={'runtime':runtime_zip,'source':source_zip,'report':report_file};published=[]
        try:
            for kind in ['runtime','source','report']:
                os.link(staged[kind],targets[kind]);published.append(kind)  # Atomic exclusive create; never replace an existing output.
        except Exception:
            for kind in published:
                if targets[kind].exists() and os.path.samefile(targets[kind],staged[kind]):targets[kind].unlink()
            raise
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    try:
        report=package_character(args.root,args.spec,args.output_dir)
        print(json.dumps({'status':'candidate','runtime_zip':report['runtime_zip'],'source_zip':report['source_zip'],'core_passed_by_packager':False,'format_validation':report['format_validation']},ensure_ascii=False));return 0
    except (PackageError,OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
        print(json.dumps({'error':str(error),'published_as_full':False},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
