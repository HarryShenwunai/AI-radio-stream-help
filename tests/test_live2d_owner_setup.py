from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
import setup_live2d_owner as setup
from companion_runtime.live2d_runtime import Live2DRuntime

class FixtureRuntime(Live2DRuntime):
    def _official_bytes(self):return b'window.Live2DCubismCore={fixture:true};'

class PowerLoss(BaseException):pass

class Live2DOwnerSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.target=self.root/'profile-data'/'live2d-runtime';self.target.parent.mkdir()
        self.bundle=self.root/'fixture-bundle.js';self.bundle.write_bytes(b'window.CompanionLive2DRuntime={fixture:true};')
    def archive(self,name='package/index.js',*,kind=None,size=None):
        file=self.root/'fixture.tgz'
        with tarfile.open(file,'w:gz') as out:
            info=tarfile.TarInfo(name);data=b'fixture only';info.size=len(data) if size is None else size
            if kind is not None:info.type=kind;info.linkname='../../outside'
            out.addfile(info,io.BytesIO(data) if kind is None and size is None else None)
        return file
    def partial_original(self):
        FixtureRuntime(self.target).install_bundle(self.bundle,expected_sha256=setup.digest(self.bundle),accept_official_license=True,trust_local_bundle=True)
        return setup.runtime_fingerprint(self.target)
    def test_missing_owner_acknowledgement_stops_before_paths_download_or_execution(self):
        with patch.object(setup,'query_owner_paths') as paths,patch.object(setup,'fetch_archive') as fetch,patch.object(setup.subprocess,'run') as run:
            with self.assertRaises(SystemExit):setup.main(['install','--application-root',str(self.root)])
            paths.assert_not_called();fetch.assert_not_called();run.assert_not_called()
        with self.assertRaises(setup.SetupError):setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=False)
        self.assertFalse((self.target.parent/'.live2d-owner-setup').exists())
    def test_lock_file_and_cached_tarball_are_bound_to_sha(self):
        lock=setup.read_lock();self.assertEqual(len([row for row in lock['packages'] if row['role']=='runtime']),13)
        fake=self.root/'fake-lock.json';fake.write_bytes(b'{}')
        with self.assertRaisesRegex(setup.SetupError,'lock_sha'):setup.read_lock(fake)
        data=b'fixture tarball';row={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)};cache=self.root/'cache'
        file=setup.cached_archive(row,cache,lambda _row:data);self.assertEqual(file.read_bytes(),data)
        setup.cached_archive(row,cache,lambda _row:self.fail('verified cache must not download'))
        file.write_bytes(b'bad cache')
        with self.assertRaisesRegex(setup.SetupError,'cached_archive'):setup.cached_archive(row,cache,lambda _row:self.fail('bad cache must not silently replace'))
    def test_corrupt_download_is_rejected_before_cache_write(self):
        row={'sha256':'a'*64,'bytes':8};cache=self.root/'cache'
        with self.assertRaisesRegex(setup.SetupError,'download_sha'):setup.cached_archive(row,cache,lambda _row:b'bad')
        self.assertFalse(cache.exists())
    def test_nonregistry_download_is_rejected_before_opening_a_network_client(self):
        with patch.object(setup.urllib.request,'build_opener') as opener:
            with self.assertRaisesRegex(setup.SetupError,'invalid_locked_download'):setup.fetch_archive({'url':'https://evil.invalid/package.tgz','bytes':100})
            opener.assert_not_called()
    def test_oversized_registry_response_is_rejected(self):
        class Response(io.BytesIO):
            status=200
            def geturl(self):return 'https://registry.npmjs.org/fixture/-/fixture.tgz'
        class Opener:
            def open(self,*_args,**_kwargs):return Response(b'12345')
        with patch.object(setup.urllib.request,'build_opener',return_value=Opener()):
            with self.assertRaisesRegex(setup.SetupError,'download_limit'):setup.fetch_archive({'url':Response().geturl(),'bytes':4})
    def test_archive_traversal_links_windows_aliases_and_oversized_members_are_rejected(self):
        for index,name in enumerate(['package/../../outside','package/x\\outside','package/C:stream','package/CON.js','package/x.js.','package/./x.js']):
            with self.subTest(name=name),self.assertRaises(setup.SetupError):setup.unpack_package(self.archive(name),self.root/('dest'+str(index)),'package')
        with self.assertRaisesRegex(setup.SetupError,'link_or_special'):setup.unpack_package(self.archive(kind=tarfile.SYMTYPE),self.root/'link','package')
        with self.assertRaisesRegex(setup.SetupError,'member_limit'):setup.unpack_package(self.archive(size=33*1024*1024),self.root/'huge','package')
        self.assertFalse((self.root/'outside').exists())
    def test_safe_package_is_extracted_without_running_its_code(self):
        file=self.archive();size=setup.unpack_package(file,self.root/'module','package')
        self.assertEqual(size,len(b'fixture only'));self.assertEqual((self.root/'module/index.js').read_bytes(),b'fixture only')
    def test_existing_partial_runtime_is_preserved_and_restored_after_success(self):
        original=self.partial_original();self.assertEqual(setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True)['status'],'installed')
        self.assertTrue(FixtureRuntime(self.target).status()['available']);self.assertEqual(setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True)['status'],'already_configured')
        self.assertEqual(setup.restore_previous(self.target)['status'],'restored');self.assertEqual(setup.runtime_fingerprint(self.target),original)
    def test_first_install_can_be_reversibly_removed_without_touching_role_data(self):
        sentinel=self.target.parent/'private-role.sqlite';sentinel.write_bytes(b'private role sentinel')
        setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True);setup.restore_previous(self.target)
        self.assertFalse(self.target.exists());self.assertEqual(sentinel.read_bytes(),b'private role sentinel')
    def test_normal_failures_and_simulated_power_loss_restore_previous_runtime(self):
        original=self.partial_original()
        for failure in [OSError,PowerLoss]:
            for boundary in ['after-backup','after-install']:
                with self.subTest(failure=failure.__name__,boundary=boundary):
                    def fault(phase):
                        if phase==boundary:raise failure('fixture failure')
                    with self.assertRaises(failure):setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True,fault=fault)
                    setup.restore_previous(self.target,pending_only=True)
                    self.assertEqual(setup.runtime_fingerprint(self.target),original)
    def test_late_owner_modification_prevents_rollback_from_overwriting_it(self):
        self.partial_original();setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True)
        record=json.loads((self.target/'core.json').read_text());file=self.target/'revisions'/record['revision']/'script.js';file.write_bytes(b'owner changed this runtime')
        with self.assertRaisesRegex(setup.SetupError,'changed_since_setup'):setup.restore_previous(self.target)
        self.assertEqual(file.read_bytes(),b'owner changed this runtime')
    def test_corrupt_backup_does_not_discard_a_good_installed_pair(self):
        self.partial_original();setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True);current=setup.runtime_fingerprint(self.target)
        workspace=self.target.parent/'.live2d-owner-setup';record=json.loads((workspace/'transaction.json').read_text());backup=workspace/record['backup']
        pointer=json.loads((backup/'bundle.json').read_text());(backup/'revisions'/pointer['revision']/'script.js').write_bytes(b'corrupt backup')
        with self.assertRaisesRegex(setup.SetupError,'backup_changed'):setup.restore_previous(self.target)
        self.assertEqual(setup.runtime_fingerprint(self.target),current)
    def test_official_download_failure_keeps_existing_runtime_unchanged(self):
        class FailureRuntime(FixtureRuntime):
            def _official_bytes(self):raise ValueError('fixture official source unavailable')
        original=self.partial_original()
        with self.assertRaisesRegex(ValueError,'source unavailable'):setup.install_pair(self.target,self.bundle,FailureRuntime,accepted=True)
        self.assertEqual(setup.runtime_fingerprint(self.target),original)
    def test_setup_never_moves_a_role_directory_or_follows_a_runtime_symlink(self):
        self.target.mkdir();(self.target/'private.sqlite').write_bytes(b'private')
        with self.assertRaisesRegex(setup.SetupError,'nonruntime'):setup.install_pair(self.target,self.bundle,FixtureRuntime,accepted=True)
        self.assertEqual((self.target/'private.sqlite').read_bytes(),b'private')
        other=self.root/'another-runtime';other.symlink_to(self.target,target_is_directory=True)
        with self.assertRaisesRegex(setup.SetupError,'contains_link'):setup.install_pair(other,self.bundle,FixtureRuntime,accepted=True)
    def test_original_base_without_readonly_cli_is_not_launched_accidentally(self):
        app=self.root/'portable';(app/'resources/app').mkdir(parents=True);(app/'resources/app/main.cjs').write_bytes(b'old host')
        with patch.object(setup.subprocess,'run') as run:
            with self.assertRaisesRegex(setup.SetupError,'small_update_first'):setup.query_owner_paths(app)
            run.assert_not_called()

if __name__=='__main__':unittest.main()
