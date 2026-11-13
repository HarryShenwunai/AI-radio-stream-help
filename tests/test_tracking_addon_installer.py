from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tracking_addon as installer

class TrackingAddonInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.base=self.root/'application';self.base.mkdir();(self.base/'resources/backend/python').mkdir(parents=True)
        (self.base/'companion-desktop.exe').write_bytes(b'unchanged shell');(self.base/'resources/backend/python/python.exe').write_bytes(b'unchanged interpreter')
        (self.base/'resources/backend/python/native.dll').write_bytes(b'unchanged native DLL')
        (self.base/'user-data').mkdir();(self.base/'user-data/persona.json').write_bytes(b'private user sentinel')
        self.members={'models/face_landmarker.task':b'model sentinel','NOTICE-TRACKING.txt':b'fixture only',
                      'python312/site-packages/example/example.pyd':b'dummy non-executable native fixture',
                      'python312/site-packages/example/__init__.py':b''}
        self.archive=self.root/'addon.zip';self.build()
        self.original={str(p.relative_to(self.base)):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
    def build(self):
        self.manifest={'format':'companion-tracking-addon-v1','python':'cp312-win_amd64',
                       'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(self.members.items())]}
        data=(json.dumps(self.manifest,sort_keys=True)+'\n').encode()
        with zipfile.ZipFile(self.archive,'w',zipfile.ZIP_DEFLATED) as package:
            package.writestr(installer.MANIFEST,data)
            for name,body in self.members.items():package.writestr(name,body)
        for name,value in [('MANIFEST_SHA',installer.canonical_hash(self.manifest)),('MANIFEST_FILE_SHA',hashlib.sha256(data).hexdigest()),('ARCHIVE_SHA',installer.digest(self.archive)),('ARCHIVE_BYTES',self.archive.stat().st_size)]:
            patcher=patch.object(installer,name,value);patcher.start();self.addCleanup(patcher.stop)
    def assertUntouched(self):
        for name,data in self.original.items():self.assertEqual((self.base/name).read_bytes(),data)
    def test_install_repeat_and_reversible_disable_only_touch_new_optional_directory(self):
        self.assertEqual(installer.install(self.base,self.archive)['status'],'installed');self.assertUntouched()
        self.assertEqual(installer.install(self.base,self.archive)['status'],'already_installed')
        result=installer.install(self.base,self.archive,remove=True);self.assertEqual(result['status'],'disabled')
        self.assertFalse((self.base/installer.TARGET).exists());self.assertTrue((self.base/result['backup']).is_dir());self.assertUntouched()
    def test_corrupt_archive_stops_before_any_addon_target_is_created(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
        self.assertFalse((self.base/installer.TARGET).exists());self.assertUntouched()
    def test_unlocked_or_extra_installed_files_are_not_silently_overwritten(self):
        installer.install(self.base,self.archive);file=self.base/installer.TARGET/'python312/site-packages/extra.py';file.write_text('untrusted')
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive,remove=True)
        self.assertTrue(file.exists());self.assertUntouched()
    def test_malicious_manifest_paths_never_escape_the_fixed_optional_root(self):
        for name in ['../../private.py','python312/site-packages/../../python.exe','python312/site-packages/x.pth',
                     'python312/site-packages/sitecustomize.py','python312/site-packages/__pycache__/x.pyc',
                     'python312/site-packages/CON.py','python312/site-packages/evil.py.','python312/site-packages/x\\evil.py']:
            self.members={name:b'bad'};self.build()
            with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
            self.assertFalse((self.base/installer.TARGET).exists());self.assertUntouched()
    def test_existing_symlink_destination_or_unknown_staging_file_is_preserved(self):
        target=self.base/installer.TARGET;target.parent.mkdir(parents=True);outside=self.root/'outside';outside.mkdir();target.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
        self.assertEqual(list(outside.iterdir()),[]);target.unlink()
        stage=self.base/installer.STAGE;stage.mkdir();(stage/'unknown.py').write_bytes(b'unknown')
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
        self.assertEqual((stage/'unknown.py').read_bytes(),b'unknown');self.assertUntouched()
    def test_live_runtime_lease_prevents_dll_install_without_terminating_process(self):
        (self.base/'resources/runtime-session.json').write_text(json.dumps({'pid':os.getpid()}))
        with self.assertRaises(installer.UpdateError):installer.install(self.base,self.archive)
        self.assertFalse((self.base/installer.TARGET).exists());self.assertUntouched()
    def test_known_interrupted_stage_is_verified_then_rebuilt(self):
        stage=self.base/installer.STAGE;stage.mkdir(parents=True);(stage/'NOTICE-TRACKING.txt').write_bytes(b'partial write')
        self.assertEqual(installer.install(self.base,self.archive)['status'],'installed');self.assertFalse(stage.exists());self.assertUntouched()

if __name__=='__main__':unittest.main()
