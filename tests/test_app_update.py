from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import app_update as updater
import build_app_update as builder

class PowerLoss(BaseException):pass

class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.base=self.root/'base';self.source=self.root/'source';self.bundle=self.root/'bundle';self.report=self.root/'checks.json'
        self.base.mkdir();self.source.mkdir()
        def put(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.put=put
        host=b"function setFocusable(value) {}\nasync function start(){\n      installIPC(); claimRuntimeSession(); await startBackend(); await createWindow();\n}\n"
        put(self.base/updater.HOST,host)
        package={'name':'companion-desktop-runtime','version':'0.4.0-dev1','main':'main.cjs'}
        put(self.base/'resources/app/package.json',builder.encoded(package))
        source_files={'app/server.py':b'VERSION = "0.4.0-dev1"\nprint("old")\n','app/static/index.html':b'<p>old</p>',
                      'src/companion_runtime/__init__.py':b''}
        profiles={}
        for name,folder in updater.PROFILES.items():
            for file,data in source_files.items():put(self.base/folder/file,data)
            put(self.base/folder/'python/python.exe',b'fixed interpreter')
            put(self.base/folder/'python/lib.dll',b'fixed native DLL')
            records={name:hashlib.sha256(data).hexdigest() for name,data in source_files.items()}
            critical={'app/server.py':records['app/server.py'],'python/python.exe':updater.digest(self.base/folder/'python/python.exe'),
                      'python/lib.dll':updater.digest(self.base/folder/'python/lib.dll')}
            profile={'schema_version':1,'profile':name,'python_version':'3.12.16','source_files':records,'source_id':updater.canonical_hash(records),
                     'critical_files':critical,'native_windows_verified':False,'gpu_offload_confirmed':False}
            profiles[name]=profile;put(self.base/folder/'runtime-profile-manifest.json',builder.encoded(profile))
        put(self.base/'companion-desktop.exe',b'fixed shell binary')
        put(self.base/'models/llm.gguf',b'unchanged large model sentinel');put(self.base/'user-data/characters/private.json',b'private character sentinel')
        info={'source_commit':updater.BASE_COMMIT,'version':'0.4.0-dev1','profiles':{'cpu':{},'cuda':{}},'quality_gate':{'passed':True}}
        put(self.base/'BUILD-INFO.json',builder.encoded(info));put(self.base/'ASSEMBLY-INFO.json',builder.encoded({'profiles':[{'profile':'cpu'},{'profile':'cuda'}]}))
        put(self.base/'SOURCE-COMMIT.txt',(updater.BASE_COMMIT+'\n').encode())
        sums=''.join(updater.digest(file)+'  '+file.relative_to(self.base).as_posix()+'\n' for file in sorted(self.base.rglob('*')) if file.is_file())
        put(self.base/'SHA256SUMS.txt',sums.encode())
        for file,data in source_files.items():put(self.source/file,data)
        put(self.source/'app/server.py',b'VERSION = "0.5.0-dev3"\nprint("new")\n');put(self.source/'app/static/index.html',b'<p>new</p>')
        put(self.source/'app/static/ui-kit.js',b'export const a=1;');put(self.source/'src/companion_runtime/perception.py',b'VISION="unconfigured"\n')
        for name in updater.HOST_FILES:put(self.source/'desktop'/name,b'// new fixed host source '+name.encode()+
            (b'\n// ui-update-journal.json\nensureNoPendingUIUpdate();\n' if name=='main.cjs' else b''))
        package['version']='0.5.0-dev3';put(self.source/'desktop/package.json',builder.encoded(package))
        hashes={file.relative_to(self.source).as_posix():updater.digest(file) for file in self.source.rglob('*') if file.is_file()}
        self.report.write_bytes(builder.encoded({'passed':True,'sources_unchanged_during_checks':True,'source_sha256':hashes}))
        self.original={file.relative_to(self.base).as_posix():file.read_bytes() for file in self.base.rglob('*') if file.is_file()}
        profile_hashes={name:updater.canonical_hash(profile) for name,profile in profiles.items()};host_hash=hashlib.sha256(host).hexdigest()
        for module in [updater,builder]:
            for name,value in [('BASE_PROFILE_SHA',profile_hashes),('BASE_HOST_SHA',host_hash)]:
                patcher=patch.object(module,name,value);patcher.start();self.addCleanup(patcher.stop)
        self.manifest=builder.build_folder(self.base,self.source,self.bundle,'a'*40,'fixture-v2',self.report)

    def snapshot(self):
        return {file.relative_to(self.base).as_posix():file.read_bytes() for file in self.base.rglob('*')
                if file.is_file() and 'app-update-backups' not in file.parts and not any(part.startswith('.app-stage-') for part in file.parts)}
    def assertOriginal(self):self.assertEqual(self.original,self.snapshot())
    def write_manifest(self,value):
        (self.bundle/'app-update-manifest.json').write_bytes(builder.encoded(value))

    def test_real_folder_apply_repeat_and_rollback_preserves_models_data_and_native_files(self):
        self.assertEqual(updater.execute(self.base,self.bundle)['status'],'applied')
        updater.verify_state(self.base,self.manifest,'new')
        self.assertEqual(updater.execute(self.base,self.bundle)['status'],'already_applied')
        self.assertEqual((self.base/'models/llm.gguf').read_bytes(),b'unchanged large model sentinel')
        self.assertEqual((self.base/'user-data/characters/private.json').read_bytes(),b'private character sentinel')
        self.assertEqual(updater.execute(self.base,self.bundle,rollback=True)['status'],'rolled_back');self.assertOriginal()

    def test_desktop_version_is_applied_and_restored_without_changing_name_or_entry(self):
        self.assertIn('package.json',updater.HOST_FILES);self.assertIn('desktop/package.json',builder.COMMIT_FILES)
        operation=next(item for item in self.manifest['files'] if item['target']=='resources/app/package.json')
        self.assertEqual(operation['new_sha256'],updater.digest(self.source/'desktop/package.json'))
        updater.execute(self.base,self.bundle)
        metadata=json.loads((self.base/'resources/app/package.json').read_bytes())
        self.assertEqual(metadata,{'name':'companion-desktop-runtime','main':'main.cjs','version':'0.5.0-dev3'})
        for folder in updater.PROFILES.values():
            updater.validate_desktop_metadata((self.base/'resources/app/package.json').read_bytes(),(self.base/folder/'app/server.py').read_bytes())
        updater.execute(self.base,self.bundle,rollback=True)
        self.assertEqual(json.loads((self.base/'resources/app/package.json').read_bytes())['version'],'0.4.0-dev1');self.assertOriginal()

    def test_builder_rejects_desktop_identity_entry_and_server_version_mismatch(self):
        original=json.loads((self.source/'desktop/package.json').read_bytes())
        for index,changes in enumerate([{'name':'different-app'},{'main':'other.cjs'},{'version':'0.5.0-dev2'}]):
            with self.subTest(changes=changes):
                (self.source/'desktop/package.json').write_bytes(builder.encoded({**original,**changes}))
                destination=self.root/('invalid-metadata-'+str(index))
                with self.assertRaises(updater.UpdateError):builder.build_folder(self.base,self.source,destination,'a'*40,'invalid-metadata',self.report)
                self.assertFalse(destination.exists())

    def test_loader_rejects_rehashed_desktop_metadata_and_missing_package_payload(self):
        target='resources/app/package.json';operation=next(item for item in self.manifest['files'] if item['target']==target)
        file=self.bundle/operation['payload'];original=file.read_bytes()
        for changes in [{'name':'different-app'},{'main':'other.cjs'},{'version':'0.5.0-dev2'}]:
            with self.subTest(changes=changes):
                data=builder.encoded({**json.loads(original),**changes});file.write_bytes(data);value=deepcopy(self.manifest)
                changed=next(item for item in value['files'] if item['target']==target);changed['bytes']=len(data);changed['new_sha256']=hashlib.sha256(data).hexdigest();self.write_manifest(value)
                with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
                self.assertOriginal()
        file.write_bytes(original);value=deepcopy(self.manifest);value['files']=[item for item in value['files'] if item['target']!=target];self.write_manifest(value)
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertOriginal()

    def test_every_write_fault_rolls_back_without_leaving_an_incoherent_runnable_program(self):
        phases=['after-journal',*[f'after-file-{index}' for index in range(len(self.manifest['files']))],'before-commit']
        for phase in phases:
            with self.subTest(phase=phase):
                def fail(current):
                    if current==phase:raise OSError('simulated write/verification failure')
                with self.assertRaises(OSError):updater.execute(self.base,self.bundle,fault=fail)
                self.assertOriginal()

    def test_power_loss_at_each_phase_recovers_on_next_trusted_run(self):
        phases=['after-bootstrap','after-journal',*[f'after-file-{index}' for index in range(len(self.manifest['files']))],'before-commit']
        for phase in phases:
            with self.subTest(phase=phase):
                def fail(current):
                    if current==phase:raise PowerLoss()
                with self.assertRaises(PowerLoss):updater.execute(self.base,self.bundle,fault=fail)
                self.assertEqual(updater.execute(self.base,self.bundle)['status'],'applied')
                updater.execute(self.base,self.bundle,rollback=True);self.assertOriginal()

    def test_native_dll_modification_stops_before_any_program_write(self):
        target=self.base/'resources/backend/python/lib.dll';target.write_bytes(b'changed DLL')
        before=self.snapshot()
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertEqual(before,self.snapshot())

    def test_source_modification_and_extra_python_source_are_not_carried_into_new_source_id(self):
        for target in ['resources/backend/app/server.py','resources/backend/src/companion_runtime/unknown.py']:
            file=self.base/target;old=file.read_bytes() if file.exists() else None;file.write_bytes(b'modified')
            before=self.snapshot()
            with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
            self.assertEqual(before,self.snapshot())
            if old is None:file.unlink()
            else:file.write_bytes(old)

    def test_payload_corruption_is_rejected_before_writes(self):
        item=self.manifest['files'][0];(self.bundle/item['payload']).write_bytes(b'corrupt')
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertOriginal()

    def test_manifest_cannot_target_user_data_models_dlls_or_path_traversal(self):
        for target in ['user-data/characters/a.json','models/new.gguf','resources/backend/python/lib.dll','resources/backend/app/../../data/key']:
            value=deepcopy(self.manifest);value['files'][0]['target']=target;self.write_manifest(value)
            with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
            self.assertOriginal()

    def test_forged_original_profile_and_native_update_are_rejected(self):
        value=deepcopy(self.manifest);value['profiles']['cpu']['old']['python_version']='forged';self.write_manifest(value)
        with self.assertRaises(updater.UpdateError):updater.load_update(self.bundle)

    def test_source_manifest_cannot_introduce_null_hashes_or_nonprogram_members(self):
        value=deepcopy(self.manifest)
        for name in updater.PROFILES:
            new=value['profiles'][name]['new'];new['source_files']['data/keys.json']=None
            new['source_id']=updater.canonical_hash(new['source_files'])
        value['new_source_id']=value['profiles']['cpu']['new']['source_id'];self.write_manifest(value)
        with self.assertRaises(updater.UpdateError):updater.load_update(self.bundle)
        value=deepcopy(self.manifest);value['profiles']['cpu']['new']['critical_files']['python/lib.dll']='f'*64;self.write_manifest(value)
        with self.assertRaises(updater.UpdateError):updater.load_update(self.bundle)

    def test_profile_payload_and_release_source_metadata_must_match_declared_update(self):
        def replace_payload(manifest,target,data):
            operation=next(item for item in manifest['files'] if item['target']==target)
            (self.bundle/operation['payload']).write_bytes(data);operation['bytes']=len(data);operation['new_sha256']=hashlib.sha256(data).hexdigest()
        for target,data in [('resources/backend/runtime-profile-manifest.json',builder.encoded({'source_id':'forged'})),
                            ('SOURCE-COMMIT.txt',b'forged-commit\n'),('BUILD-INFO.json',builder.encoded({'source_commit':'forged'}))]:
            with self.subTest(target=target):
                operation=next(item for item in self.manifest['files'] if item['target']==target)
                file=self.bundle/operation['payload'];original=file.read_bytes()
                value=deepcopy(self.manifest);replace_payload(value,target,data);self.write_manifest(value)
                with self.assertRaises(updater.UpdateError):updater.load_update(self.bundle)
                file.write_bytes(original)

    def test_live_host_process_blocks_update_without_killing_it(self):
        marker=self.base/'resources/runtime-session.json';marker.write_text(json.dumps({'pid':os.getpid()}))
        before=self.snapshot()
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertEqual(before,self.snapshot());marker.unlink();self.assertOriginal()

    def test_symlink_payload_or_destination_is_never_followed(self):
        operation=self.manifest['files'][0];file=self.bundle/operation['payload'];content=file.read_bytes();file.unlink()
        external=self.root/'external';external.write_bytes(content);file.symlink_to(external)
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertOriginal();file.unlink();file.write_bytes(content)
        destination=self.base/operation['target'];old=destination.read_bytes();destination.unlink();destination.symlink_to(external)
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertEqual(external.read_bytes(),content);destination.unlink();destination.write_bytes(old)

    def test_bad_backup_preserves_journal_and_fails_closed(self):
        def fail(phase):
            if phase=='after-file-0':raise PowerLoss()
        with self.assertRaises(PowerLoss):updater.execute(self.base,self.bundle,fault=fail)
        _,backup=updater.paths(self.base,self.manifest)
        first=sorted(self.manifest['files'],key=lambda item:item['target']==updater.HOST)[0]
        (backup/'files'/first['target']).write_bytes(b'broken backup')
        with self.assertRaises(updater.UpdateError):updater.execute(self.base,self.bundle)
        self.assertTrue((self.base/updater.JOURNAL).exists())
        self.assertIn(b'ensureNoPendingUIUpdate',(self.base/updater.HOST).read_bytes())

    def test_builder_rejects_stale_validation_and_unallowlisted_new_source(self):
        (self.source/'app/server.py').write_bytes(b'VERSION = "0.5.0-dev3"\nprint("untested change")\n')
        with self.assertRaises(ValueError):builder.build_folder(self.base,self.source,self.root/'stale','b'*40,'stale',self.report)
        self.put(self.source/'src/companion_runtime/unreviewed.py',b'new module')
        with self.assertRaises(ValueError):builder.build_folder(self.base,self.source,self.root/'unknown','b'*40,'unknown',self.report)

if __name__=='__main__':unittest.main()
