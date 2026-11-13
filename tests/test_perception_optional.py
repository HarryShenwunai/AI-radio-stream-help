"""Closed-tree optional addon loader boundaries; no Windows DLL is executed."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_runtime.perception_optional import REUSED_BASE,activate_tracking_addon,verify_tracking_addon


class OptionalAddonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'resources/backend'
        self.app=self.base/'app';self.app.mkdir(parents=True)
        (self.base/'python/Lib/site-packages').mkdir(parents=True)
        self.root=Path(self.temp.name)/'resources/optional/tracking'
        self.root.mkdir(parents=True)
        file=self.root/'python312/site-packages/sentinel.py';file.parent.mkdir(parents=True)
        file.write_text('raise RuntimeError("MUST NOT EXECUTE")\n')
        model=self.root/'models/face_landmarker.task';model.parent.mkdir();model.write_bytes(b'synthetic fixture only')
        self.manifest={'format':'companion-tracking-addon-v1','addon_revision':3,'python':'cp312-win_amd64','mediapipe_version':'1.2.3',
             'reused_base_distributions':REUSED_BASE,'files':[]}
        for path in (file,model):self.add_row(path)
        self.patcher=None;self.pin()
        self.addCleanup(lambda:self.patcher.stop())
        self.addCleanup(lambda:sys.path.remove(str(file.parent)) if str(file.parent) in sys.path else None)
    def add_row(self,path):
        raw=path.read_bytes();self.manifest['files'].append({'path':path.relative_to(self.root).as_posix(),
            'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def pin(self):
        raw=json.dumps(self.manifest,sort_keys=True).encode();(self.root/'tracking-addon-manifest.json').write_bytes(raw)
        if self.patcher:self.patcher.stop()
        self.patcher=patch('companion_runtime.perception_optional.MANIFEST_SHA256',hashlib.sha256(raw).hexdigest())
        self.patcher.start()
    def test_valid_tree_verified_without_import_or_activation(self):
        with patch('importlib.import_module',side_effect=AssertionError('must not import')):
            state=verify_tracking_addon(self.app)
        self.assertTrue(state.verified);self.assertFalse(state.activated)
        self.assertEqual(state.model_path,self.root/'models/face_landmarker.task')
        self.assertNotIn(str(self.root/'python312/site-packages'),sys.path)
    def test_missing_addon_and_nonpackaged_layout_nonfatal(self):
        self.assertEqual(verify_tracking_addon(Path(self.temp.name)/'development/app').reason,'not_installed')
        import shutil
        shutil.rmtree(self.root)
        self.assertEqual(verify_tracking_addon(self.app).reason,'not_installed')
    def test_manifest_tampering_rejected_before_parse(self):
        (self.root/'tracking-addon-manifest.json').write_bytes(b'{PRIVATE invalid')
        state=verify_tracking_addon(self.app)
        self.assertFalse(state.verified);self.assertEqual(state.reason,'addon_manifest_mismatch')
        self.assertNotIn('PRIVATE',str(state))
    def test_oversize_manifest_rejected(self):
        (self.root/'tracking-addon-manifest.json').write_bytes(b'x'*4_000_001)
        self.assertEqual(verify_tracking_addon(self.app).reason,'invalid_addon_manifest')
    def test_member_changed_missing_or_unlisted_rejected(self):
        file=self.root/'python312/site-packages/sentinel.py'
        file.write_text('changed')
        self.assertFalse(verify_tracking_addon(self.app).verified)
        file.unlink()
        self.assertFalse(verify_tracking_addon(self.app).verified)
        file.write_text('raise RuntimeError("MUST NOT EXECUTE")\n')
        (file.parent/'extra.py').write_text('unlisted')
        self.assertEqual(verify_tracking_addon(self.app).reason,'unlisted_addon_file')
    def test_unlisted_empty_directory_rejected(self):
        (self.root/'unexpected').mkdir()
        self.assertEqual(verify_tracking_addon(self.app).reason,'unlisted_addon_directory')
    def test_symlink_file_directory_and_manifest_rejected(self):
        file=self.root/'python312/site-packages/sentinel.py';file.unlink()
        original=Path(self.temp.name)/'original';original.write_text('private')
        file.symlink_to(original)
        self.assertFalse(verify_tracking_addon(self.app).verified)
        file.unlink();file.write_text('raise RuntimeError("MUST NOT EXECUTE")\n')
        directory=self.root/'unexpected';directory.symlink_to(self.root/'models',target_is_directory=True)
        self.assertEqual(verify_tracking_addon(self.app).reason,'unsafe_addon_path')
        directory.unlink();manifest=self.root/'tracking-addon-manifest.json';manifest.unlink();manifest.symlink_to(original)
        self.assertEqual(verify_tracking_addon(self.app).reason,'invalid_addon_manifest')
    def test_startup_hooks_bytecode_reserved_and_unsafe_paths_rejected(self):
        original=self.manifest['files'][0]['path']
        for name in ('../outside.py','/absolute.py','python312/site-packages/start.pth',
                'python312/site-packages/__pycache__/evil.pyc','python312/site-packages/sitecustomize.py',
                'python312/site-packages/AUX.py','python312/site-packages/dot./file.py',
                'python312/site-packages//file.py','python312/site-packages/x:stream','python312/site-packages/cv2/opencv_videoio_ffmpeg500_64.dll'):
            self.manifest['files'][0]['path']=name;self.pin()
            self.assertFalse(verify_tracking_addon(self.app).verified,name)
        self.manifest['files'][0]['path']=original
    def test_case_insensitive_duplicate_manifest_rejected(self):
        duplicate=dict(self.manifest['files'][0]);duplicate['path']=duplicate['path'].upper()
        self.manifest['files'].append(duplicate);self.pin()
        self.assertEqual(verify_tracking_addon(self.app).reason,'invalid_addon_manifest')
    def test_foreign_root_and_base_replacement_rejected(self):
        for name in ('python312/site-packages/numpy/hijack.py','python312/site-packages/PIL/hijack.py',
                     'python312/site-packages/flatbuffers/hijack.py','python312/site-packages/packaging/hijack.py','other/evil.py'):
            self.manifest['files'][0]['path']=name;self.pin()
            self.assertFalse(verify_tracking_addon(self.app).verified)
    def test_manifest_shape_and_size_types_rejected(self):
        self.manifest['files'][0]['bytes']=True;self.pin()
        self.assertEqual(verify_tracking_addon(self.app).reason,'invalid_addon_manifest')
    def test_unsupported_runtime_never_appends_path(self):
        with patch('sys.platform','linux'):
            self.assertEqual(activate_tracking_addon(self.app).reason,'unsupported_runtime')
        self.assertNotIn(str(self.root/'python312/site-packages'),sys.path)
    def test_activation_appends_only_and_never_executes_sentinel(self):
        def distribution(name):
            return SimpleNamespace(version=REUSED_BASE[name],locate_file=lambda value:self.base/'python/Lib/site-packages')
        with patch('sys.platform','win32'),patch('importlib.metadata.distribution',side_effect=distribution),patch.object(sys,'dont_write_bytecode',False):
            before=list(sys.path);state=activate_tracking_addon(self.app)
            self.assertTrue(state.activated);self.assertTrue(sys.dont_write_bytecode)
            self.assertEqual(sys.path[:-1],before)
            self.assertEqual(sys.path[-1],str(self.root/'python312/site-packages'))
            self.assertNotIn('sentinel',sys.modules)
    def test_wrong_base_version_does_not_activate(self):
        with patch('sys.platform','win32'),patch('importlib.metadata.distribution',return_value=SimpleNamespace(version='wrong')):
            state=activate_tracking_addon(self.app)
        self.assertEqual(state.reason,'base_dependency_mismatch');self.assertFalse(state.activated)
    def test_cuda_locates_shared_addon(self):
        cuda=Path(self.temp.name)/'resources/backend-profiles/cuda/app';cuda.mkdir(parents=True)
        self.assertTrue(verify_tracking_addon(cuda).verified)


if __name__=='__main__':unittest.main()
