"""Explicit complete-file audit of the frozen Windows addon; no DLL execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import zipfile
from companion_runtime.perception_optional import MANIFEST_SHA256,verify_tracking_addon


def digest(file):
    with file.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--app-root',type=Path,required=True);parser.add_argument('--private-v1-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();start=time.perf_counter()
    state=verify_tracking_addon(args.app_root);assert state.verified
    root=state.site_packages_path.parents[1]
    with zipfile.ZipFile(args.archive) as archive:
        raw=archive.read('tracking-addon-manifest.json');assert hashlib.sha256(raw).hexdigest()==MANIFEST_SHA256
        manifest=json.loads(raw);expected={x['path'] for x in manifest['files']}|{'tracking-addon-manifest.json'}
        assert set(archive.namelist())==expected
        for row in manifest['files']:
            value=archive.read(row['path'])  # ZipFile also verifies each CRC on complete read.
            assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
        assert not any('opencv_videoio_ffmpeg' in name.casefold() for name in archive.namelist())
    old=json.loads((args.private_v1_root/'tracking-addon-manifest.json').read_bytes())
    old_rows={row['path']:row for row in old['files']};new_rows={row['path']:row for row in manifest['files']}
    removed=set(old_rows)-set(new_rows);changed={name for name in set(old_rows)&set(new_rows) if old_rows[name]!=new_rows[name]}
    expected_removed={'python312/site-packages/cv2/opencv_videoio_ffmpeg500_64.dll'}|{
        'python312/site-packages/_sounddevice_data/portaudio-binaries/'+name for name in (
        'libportaudio.dylib','libportaudio32bit-asio.dll','libportaudio32bit.dll',
        'libportaudioarm64-asio.dll','libportaudioarm64.dll','libportaudio64bit-asio.dll')}
    assert removed==expected_removed
    assert manifest['addon_revision']==3
    assert changed=={'NOTICE-TRACKING.txt','WHEEL-PROVENANCE.json'}
    assert not set(new_rows)-set(old_rows)
    licenses=[name for name in old_rows if any(word in name.casefold() for word in ('license','notice')) and name!='NOTICE-TRACKING.txt']
    assert all(old_rows[name]==new_rows[name] for name in licenses)
    machines=[]
    for name in new_rows:
        if name.lower().endswith(('.dll','.pyd')):
            with (root/name).open('rb') as source:
                header=source.read(64);offset=struct.unpack('<I',header[60:64])[0];source.seek(offset);pe=source.read(6)
            assert pe[:4]==b'PE\x00\x00' and struct.unpack('<H',pe[4:])[0]==0x8664
            machines.append(name)
    assert len(machines)==20 and set(machines)==set(manifest['native_x64_components'])
    pyd=state.site_packages_path/'cv2/cv2.pyd'
    pe=subprocess.run(['objdump','-p',str(pyd)],capture_output=True,text=True,check=True).stdout
    imports=[line.split('DLL Name:',1)[1].strip() for line in pe.splitlines() if 'DLL Name:' in line]
    assert not any('ffmpeg' in name.casefold() or 'avcodec' in name.casefold() for name in imports)
    report={'passed':True,'scope':'Complete locked ZIP/tree/CRC/SHA and PE audit, not Windows DLL execution',
        'archive_bytes':args.archive.stat().st_size,'archive_sha256':digest(args.archive),
        'manifest_raw_sha256':MANIFEST_SHA256,
        'manifest_no_lf_canonical_sha256':hashlib.sha256(json.dumps(manifest,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'locked_files':len(manifest['files']),'expanded_bytes':sum(r['bytes'] for r in manifest['files'])+len(raw),
        'unchanged_v1_payload_files':len(set(old_rows)&set(new_rows))-len(changed),
        'only_changed_metadata':sorted(changed),'omitted_plugins':manifest['omitted_runtime_plugins'],
        'upstream_license_notice_files_preserved':len(licenses),'x64_pe_members':len(machines),'cv2_pyd_imports':imports,
        'local_eval_portrait_or_user_frames_included':False,'windows_execution_verified':False,'elapsed_seconds':round(time.perf_counter()-start,4)}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
