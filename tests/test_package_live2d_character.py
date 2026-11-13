"""Synthetic format/source envelopes, never a playable MOC or Editor claim."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
import package_live2d_character as pack
from test_live2d_assets import files as runtime_fixture,png

class CharacterPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.output=self.root/'output';self.spec_file=self.root/'package-spec.json'
        items=runtime_fixture(True)
        for name,value in items.items():
            self.put('export/'+name,json.dumps(value).encode() if isinstance(value,dict) else value)
        self.moc=self.root/'export/actor.moc3'
        self.put('art/layers/face.png',png())
        self.put('art/layers.json',json.dumps({'format':'original-live2d-layers-v1','canvas':{'width':20,'height':30},
            'purpose':'Synthetic source envelope only; not modeling artwork or playable rig','layers':[{'name':'fixture-layer','file':'layers/face.png','sha256':pack.sha(self.root/'art/layers/face.png')}]}).encode())
        self.psd=b'8BPS'+struct.pack('>H',1)+b'\0'*6+struct.pack('>HIIHH',4,30,20,8,3)
        self.put('authoring/character.psd',self.psd);self.put('authoring/character.cmo3',b'CAFF synthetic source envelope; not a real Editor project')
        self.put('authoring/recipe.json',b'{"format":"original-live2d-recipe-v1","steps":[]}')
        self.put('NOTICE.txt',b'Synthetic test envelope only, no SDK or actual character.');self.project_members={'source/original.psd':self.psd,'workspace.json':b'{}'};self.write_project()
        self.spec={'format':'original-live2d-package-spec-v1','identity':'fixture-only','origin':'project-original-authoring',
            'runtime_model':self.pin('export/actor.model3.json'),'runtime_files':{name:pack.sha(self.root/'export'/name) for name in items if name not in {'actor.model3.json','LICENSE.txt'}},
            'source_manifest':self.pin('art/layers.json'),'psd':self.pin('authoring/character.psd'),'cmo3':self.pin('authoring/character.cmo3'),
            'project':self.pin('authoring/character.psd2live'),'rig_recipe':self.pin('authoring/recipe.json'),'notice':self.pin('NOTICE.txt')}
        self.save_spec()
    def put(self,name,data):
        file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data);return file
    def pin(self,name):return {'path':name,'sha256':pack.sha(self.root/name)}
    def save_spec(self):self.spec_file.write_text(json.dumps(self.spec,indent=2)+'\n')
    def write_project(self):
        manifest={'format':'PSD2Live','version':2,'files':{name:hashlib.sha256(data).hexdigest() for name,data in self.project_members.items()}}
        with zipfile.ZipFile(self.root/'authoring/character.psd2live','w',zipfile.ZIP_DEFLATED) as out:
            for name,data in self.project_members.items():out.writestr(name,data)
            out.writestr('manifest.json',json.dumps(manifest).encode())
    def package(self):return pack.package_character(self.root,self.spec_file,self.output)
    def assert_no_published(self):self.assertFalse(self.output.exists() and any(self.output.glob('*.zip')))

    def test_two_zip_receipts_and_real_assetstore_format_check_never_claim_playability(self):
        report=self.package();self.assertEqual(report['status'],'candidate');self.assertFalse(report['core_passed_by_packager']);self.assertFalse(report['full_character_claimed'])
        self.assertEqual(report['format_validation']['method'],'actual_AssetStore.import_live2d');self.assertTrue(report['format_validation']['passed'])
        self.assertFalse(report['format_validation']['playability_verified']);self.assertFalse(report['format_validation']['core_consistency_verified'])
        self.assertTrue(report['source_identity_checks']['project_embedded_psd_matches']);self.assertFalse(report['source_identity_checks']['editor_reopen_verified'])
        for kind,rows in [('runtime',report['runtime_members']),('source',report['source_members'])]:
            file=self.output/report[kind+'_zip']['name'];self.assertEqual(pack.sha(file),report[kind+'_zip']['sha256'])
            with zipfile.ZipFile(file) as archive:
                self.assertEqual(set(archive.namelist()),{row['path'] for row in rows})
                for row in rows:
                    data=archive.read(row['path']);self.assertEqual(len(data),row['bytes']);self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
        with zipfile.ZipFile(self.output/report['runtime_zip']['name']) as archive:
            self.assertNotIn('LICENSE.txt',archive.namelist());self.assertNotIn('character.cmo3',archive.namelist());self.assertIn('actor.physics3.json',archive.namelist())
        with zipfile.ZipFile(self.output/report['source_zip']['name']) as archive:
            self.assertEqual(archive.read('source/character.psd'),self.psd);self.assertIn('PACKAGE-INPUT.json',archive.namelist());self.assertIn('source/art/layers/face.png',archive.namelist())
    def test_moc_or_source_hash_drift_rejects_before_any_outputs(self):
        for name in ['export/actor.moc3','art/layers/face.png','authoring/character.cmo3']:
            with self.subTest(name=name):
                file=self.root/name;original=file.read_bytes();file.write_bytes(original+b'changed')
                with self.assertRaisesRegex(pack.PackageError,'sha_mismatch'):self.package()
                self.assert_no_published();file.write_bytes(original)
    def test_a_different_embedded_psd_is_not_accepted_as_the_same_source_project(self):
        self.project_members['source/original.psd']=self.psd+b'other source';self.write_project();self.spec['project']=self.pin('authoring/character.psd2live');self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'embedded_psd_identity'):self.package()
        self.assert_no_published()
    def test_runtime_reference_and_source_pin_sets_must_match_exactly(self):
        self.spec['runtime_files']['unreferenced.moc3']='a'*64;self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'pin_set_mismatch'):self.package()
        self.assert_no_published()
    def test_external_traversal_and_windows_alias_references_are_rejected(self):
        model=self.root/'export/actor.model3.json';original=json.loads(model.read_text())
        for value in ['https://evil.invalid/a.moc3','../outside.moc3','tex\\evil.moc3','CON.moc3','tex/face*.moc3','tex/face|eye.moc3','tex/face<eye.moc3']:
            with self.subTest(value=value):
                doc=json.loads(json.dumps(original));doc['FileReferences']['Moc']=value;model.write_text(json.dumps(doc));self.spec['runtime_model']=self.pin('export/actor.model3.json');self.spec['runtime_files'].pop('actor.moc3',None);self.spec['runtime_files'][value]=pack.sha(self.moc);self.save_spec()
                with self.assertRaises(pack.PackageError):self.package()
                self.assert_no_published();self.spec['runtime_files'].pop(value)
    def test_vendor_payload_cannot_be_hidden_inside_the_psd2live_project(self):
        self.project_members['vendor/live2dcubismcore.min.js']=b'forbidden';self.write_project();self.spec['project']=self.pin('authoring/character.psd2live');self.save_spec()
        with self.assertRaises(pack.PackageError):self.package()
        self.assert_no_published()
    def test_non_prio_binary_cannot_be_hidden_as_a_rig_object(self):
        self.project_members['rig/objects/'+('a'*64)+'.bin']=b'GGUF weight payload';self.write_project();self.spec['project']=self.pin('authoring/character.psd2live');self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'not_psd2live_rig_data'):self.package()
        self.assert_no_published()
    def test_forbidden_source_directory_and_symlink_are_rejected(self):
        old=self.spec['cmo3'];private=self.put('user-data/secret.cmo3',b'CAFF private source');self.spec['cmo3']=self.pin('user-data/secret.cmo3');self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'forbidden_source_directory'):self.package()
        self.assertEqual(private.read_bytes(),b'CAFF private source');self.spec['cmo3']=old;self.save_spec()
        original=self.moc.read_bytes();self.moc.unlink();outside=self.put('outside.moc3',original);self.moc.symlink_to(outside)
        with self.assertRaisesRegex(pack.PackageError,'link_rejected'):self.package()
        self.assert_no_published()
    def test_known_official_model_digest_is_rejected_even_after_renaming(self):
        with patch.object(pack,'DENIED_MOC_SHA256',frozenset({pack.sha(self.moc)})):
            with self.assertRaisesRegex(pack.PackageError,'official_sample'):self.package()
        self.assert_no_published()
    def test_source_png_cannot_just_be_an_executable_with_a_png_extension(self):
        file=self.root/'art/layers/face.png';file.write_bytes(b'MZ executable bytes');manifest=json.loads((self.root/'art/layers.json').read_text());manifest['layers'][0]['sha256']=pack.sha(file)
        (self.root/'art/layers.json').write_text(json.dumps(manifest));self.spec['source_manifest']=self.pin('art/layers.json');self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'original_png'):self.package()
        self.assert_no_published()
    def test_preexisting_outputs_are_never_replaced(self):
        self.output.mkdir();file=self.output/'fixture-only-candidate-runtime.zip';file.write_bytes(b'preserve')
        with self.assertRaisesRegex(pack.PackageError,'refusing_overwrite'):self.package()
        self.assertEqual(file.read_bytes(),b'preserve');self.assertEqual(len(list(self.output.iterdir())),1)
    def test_exclusive_publish_race_preserves_the_other_file_and_removes_only_our_link(self):
        original=pack.os.link;calls=0;file=self.output/'fixture-only-candidate-source.zip'
        def link(source,target):
            nonlocal calls
            calls+=1
            if calls==2:file.write_bytes(b'concurrent artifact')
            return original(source,target)
        with patch.object(pack.os,'link',side_effect=link),self.assertRaises(FileExistsError):self.package()
        self.assertEqual(file.read_bytes(),b'concurrent artifact');self.assertFalse((self.output/'fixture-only-candidate-runtime.zip').exists())
    def test_source_change_during_zip_write_cannot_create_a_success_receipt(self):
        original=pack.write_zip;changed=False
        def write(file,members,pins):
            nonlocal changed
            if not changed:
                changed=True;self.moc.write_bytes(self.moc.read_bytes()+b'changed during write')
            return original(file,members,pins)
        with patch.object(pack,'write_zip',side_effect=write),self.assertRaisesRegex(pack.PackageError,'changed_during_archive_write'):self.package()
        self.assert_no_published()
    def test_acceptance_binds_real_moc_and_evidence_without_deciding_that_it_passed(self):
        evidence=self.put('review/fixture-evidence.json',b'{"synthetic_format_fixture_only":true}')
        self.put('review/acceptance.json',json.dumps({'moc_sha256':pack.sha(self.moc),'claimed_decision':'full passed by outside author',
            'evidence':[{'path':'review/fixture-evidence.json','sha256':pack.sha(evidence)}]}).encode())
        self.spec['acceptance_index']=self.pin('review/acceptance.json');self.save_spec();report=self.package()
        self.assertTrue(report['acceptance_binding']['bound']);self.assertEqual(report['acceptance_binding']['decision_by_packager'],'not_performed');self.assertFalse(report['core_passed_by_packager']);self.assertFalse(report['full_character_claimed'])
        self.assertFalse(report['acceptance_binding']['evidence'][0]['copied_into_source_zip'])
    def test_acceptance_for_a_different_moc_or_changed_evidence_is_rejected(self):
        self.put('review/acceptance.json',json.dumps({'moc_sha256':'a'*64,'evidence':[]}).encode());self.spec['acceptance_index']=self.pin('review/acceptance.json');self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'moc_identity_mismatch'):self.package()
        self.assert_no_published()
        self.put('review/evidence.json',b'{"fixture":true}')
        index={'moc_sha256':pack.sha(self.moc),'evidence':[self.pin('review/evidence.json')]}
        self.put('review/acceptance.json',json.dumps(index).encode());self.spec['acceptance_index']=self.pin('review/acceptance.json');self.save_spec()
        self.put('review/evidence.json',b'{"changed":true}')
        with self.assertRaisesRegex(pack.PackageError,'sha_mismatch'):self.package()
        self.assert_no_published()
    def test_spec_and_output_directory_symlinks_are_rejected(self):
        saved=self.root/'actual-spec.json';self.spec_file.rename(saved);self.spec_file.symlink_to(saved)
        with self.assertRaisesRegex(pack.PackageError,'link_rejected'):self.package()
        self.spec_file.unlink();saved.rename(self.spec_file);other=self.root/'other-output';other.mkdir();self.output.symlink_to(other,target_is_directory=True)
        with self.assertRaisesRegex(pack.PackageError,'output_link'):self.package()
        self.assertEqual(list(other.iterdir()),[])
    def test_no_recursive_export_directory_collection_or_unlisted_source_extras(self):
        self.put('export/live2dcubismcore.min.js',b'do not collect this unused file');self.put('art/not-listed.png',png())
        report=self.package()
        with zipfile.ZipFile(self.output/report['runtime_zip']['name']) as archive:self.assertNotIn('live2dcubismcore.min.js',archive.namelist())
        with zipfile.ZipFile(self.output/report['source_zip']['name']) as archive:self.assertFalse(any('not-listed' in name for name in archive.namelist()))
    def test_explicit_original_png_and_submanifest_are_preserved_without_collecting_neighbors(self):
        original=self.put('art/head/original.png',png());submanifest=self.put('art/head/part-manifest.json',b'{"format":"original-live2d-layers-v1","layers":[]}')
        self.put('art/head/private-neighbor.json',b'{"do_not_collect":true}')
        self.spec['original_sources']=[{**self.pin('art/head/original.png'),'relative':'sources/head/original.png'}]
        self.spec['source_manifests']=[{**self.pin('art/head/part-manifest.json'),'relative':'sources/head/part-manifest.json'}];self.save_spec();report=self.package()
        with zipfile.ZipFile(self.output/report['source_zip']['name']) as archive:
            self.assertEqual(archive.read('source/art/sources/head/original.png'),original.read_bytes());self.assertEqual(archive.read('source/art/sources/head/part-manifest.json'),submanifest.read_bytes())
            self.assertFalse(any('private-neighbor' in name for name in archive.namelist()))
    def test_source_archive_aliases_cannot_overwrite_the_pinned_layer_manifest(self):
        self.put('art/another.json',b'{"format":"original-live2d-layers-v1","layers":[]}')
        self.spec['source_manifests']=[{**self.pin('art/another.json'),'relative':'layers.json'}];self.save_spec()
        with self.assertRaisesRegex(pack.PackageError,'source_archive_collision'):self.package()
        self.assert_no_published()
    def test_explicit_optional_can3_is_preserved_only_in_source_zip(self):
        animator=self.put('authoring/character.can3',b'CAFF synthetic animator envelope, not a real editable animation')
        self.spec['can3']=self.pin('authoring/character.can3');self.save_spec();report=self.package()
        with zipfile.ZipFile(self.output/report['source_zip']['name']) as archive:self.assertEqual(archive.read('source/character.can3'),animator.read_bytes())
        with zipfile.ZipFile(self.output/report['runtime_zip']['name']) as archive:self.assertFalse(any(name.endswith('.can3') for name in archive.namelist()))
        self.assertFalse(report['core_passed_by_packager']);self.assertFalse(report['source_identity_checks']['editor_reopen_verified'])
        row=next(item for item in report['source_members'] if item['path']=='source/character.can3');self.assertEqual(row['sha256'],pack.sha(animator));self.assertEqual(row['bytes'],animator.stat().st_size)
    def test_optional_can3_rejects_wrong_suffix_and_invalid_header(self):
        for path,value in [('authoring/fake.can3.bin',b'CAFF wrong extension'),('authoring/fake.can3',b'GGUF wrong source type')]:
            with self.subTest(path=path):
                self.put(path,value);self.spec['can3']=self.pin(path);self.save_spec()
                with self.assertRaises(pack.PackageError):self.package()
                self.assert_no_published()
    def test_optional_can3_sha_drift_is_rejected(self):
        file=self.put('authoring/character.can3',b'CAFF synthetic animator envelope');self.spec['can3']=self.pin('authoring/character.can3');self.save_spec();file.write_bytes(file.read_bytes()+b'changed')
        with self.assertRaisesRegex(pack.PackageError,'source_identity_sha_mismatch'):self.package()
        self.assert_no_published()

class ProjectJournalBudgetTests(unittest.TestCase):
    """Streaming compressed fixtures; never allocate a real 2GiB project."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.file=self.root/'source.psd2live';self.psd=b'8BPS synthetic identity bytes, not an editable PSD'
        self.psd_sha=hashlib.sha256(self.psd).hexdigest()
    def project(self,size,name=None,compression=zipfile.ZIP_DEFLATED):
        def chunks():
            yield b'{}'
            remaining=size-2;block=b' '*(1024*1024)
            while remaining:
                chunk=block[:min(remaining,len(block))];yield chunk;remaining-=len(chunk)
        checksum=hashlib.sha256()
        for chunk in chunks():checksum.update(chunk)
        actual=checksum.hexdigest();name=name or ('document/nodes/journal/'+actual+'.json')
        manifest={'format':'PSD2Live','files':{'source/original.psd':self.psd_sha,name:actual}}
        with zipfile.ZipFile(self.file,'w',compression) as archive:
            archive.writestr('source/original.psd',self.psd)
            with archive.open(name,'w') as output:
                for chunk in chunks():output.write(chunk)
            archive.writestr('manifest.json',json.dumps(manifest))
        return name
    def check(self):return pack.check_project(self.file,self.psd_sha)
    def test_content_addressed_journal_above_8m_and_at_exact_64m_passes(self):
        for size in [8*1024*1024+1,64*1024*1024]:
            with self.subTest(size=size):
                self.project(size);checks=self.check();self.assertEqual(checks['project_journal_members_verified'],1)
                self.assertEqual(checks['project_largest_journal_bytes'],size);self.assertTrue(checks['project_embedded_psd_matches'])
    def test_journal_one_byte_over_64m_fails(self):
        self.project(64*1024*1024+1)
        with self.assertRaisesRegex(pack.PackageError,'project_expansion_limit'):self.check()
    def test_nonjournal_json_above_8m_does_not_receive_the_exception(self):
        for name in ['workspace.json','rig/revisions/revision-'+('a'*64)+'.json','history/revisions/'+('a'*64)+'.json']:
            with self.subTest(name=name):
                self.project(8*1024*1024+1,name)
                with self.assertRaisesRegex(pack.PackageError,'project_expansion_limit'):self.check()
    def test_similar_prefix_and_malformed_hash_cannot_obtain_journal_budget(self):
        for name in ['document/nodes/journals/'+('a'*64)+'.json','document/nodes/journal/'+('a'*63)+'.json',
                     'document/nodes/journal/'+('A'*64)+'.json','document/nodes/journal-extra/'+('a'*64)+'.json']:
            with self.subTest(name=name):
                self.project(8*1024*1024+1,name)
                with self.assertRaises(pack.PackageError):self.check()
    def test_journal_filename_must_match_actual_content_even_when_manifest_hash_matches(self):
        self.project(256,'document/nodes/journal/'+('a'*64)+'.json')
        with self.assertRaisesRegex(pack.PackageError,'journal_content_address_mismatch'):self.check()
    def test_observed_history_revision_ids_do_not_assume_payload_content_addressing(self):
        name='history/revisions/'+('a'*64)+'.json';self.project(256,name)
        checks=self.check();self.assertEqual(checks['project_manifest_members_verified'],2)
        self.assertEqual(checks['project_journal_members_verified'],0)
    def test_history_revision_wrong_prefix_and_hash_shape_are_rejected(self):
        for name in ['history/revision/'+('a'*64)+'.json','history/revisions/'+('a'*63)+'.json',
                     'history/revisions/'+('A'*64)+'.json','history/revisions-extra/'+('a'*64)+'.json']:
            with self.subTest(name=name):
                self.project(256,name)
                with self.assertRaisesRegex(pack.PackageError,'project_member_not_allowlisted'):self.check()
    def test_content_address_does_not_replace_the_independent_manifest_hash(self):
        name=self.project(256)
        with zipfile.ZipFile(self.file) as archive:members={key:archive.read(key) for key in archive.namelist()}
        manifest=json.loads(members['manifest.json']);manifest['files'][name]='a'*64;members['manifest.json']=json.dumps(manifest).encode()
        with zipfile.ZipFile(self.file,'w',zipfile.ZIP_DEFLATED) as archive:
            for key,value in members.items():archive.writestr(key,value)
        with self.assertRaisesRegex(pack.PackageError,'project_member_sha_mismatch'):self.check()
    def test_member_crc_failure_is_still_detected(self):
        name=self.project(256,compression=zipfile.ZIP_STORED)
        with zipfile.ZipFile(self.file) as archive:info=archive.getinfo(name)
        raw=bytearray(self.file.read_bytes());offset=info.header_offset+30+len(name.encode())+len(info.extra);raw[offset]^=1;self.file.write_bytes(raw)
        with self.assertRaises(zipfile.BadZipFile):self.check()
    def test_aggregate_over_2g_fails_from_metadata_without_a_giant_file(self):
        self.project(256);infos=[]
        for index in range(8):
            info=zipfile.ZipInfo('rig/objects/'+format(index,'064x')+'.bin');info.file_size=256*1024*1024;infos.append(info)
        last=zipfile.ZipInfo('source/original.psd');last.file_size=1;infos.append(last)
        with patch.object(zipfile.ZipFile,'infolist',return_value=infos),self.assertRaisesRegex(pack.PackageError,'project_expansion_limit'):self.check()
    def test_external_json_and_selected_source_limits_remain_unchanged(self):
        self.assertEqual(pack.MAX_JSON,8*1024*1024);self.assertEqual(pack.MAX_SOURCE_BYTES,512*1024*1024);self.assertEqual(pack.MAX_SOURCE_FILE,256*1024*1024)
        self.assertEqual(pack._json(b'{}'+b' '*(8*1024*1024-2)),{})
        with self.assertRaisesRegex(pack.PackageError,'json_size_limit'):pack._json(b'{}'+b' '*(8*1024*1024-1))

class ProjectOuterFileBudgetTests(unittest.TestCase):
    """Sparse metadata fixtures: no large disk writes or bulk fixture hashing."""
    setUp=ProjectJournalBudgetTests.setUp
    project=ProjectJournalBudgetTests.project
    def sparse_project(self,size):
        self.project(256);raw=self.file.read_bytes()
        with self.file.open('wb') as output:output.seek(size-len(raw));output.write(raw)
        self.assertEqual(self.file.stat().st_size,size)
    def pin_project(self):
        # Hash-drift correctness is covered separately with real bytes. Here the
        # mock prevents reading sparse hundreds-of-MiB holes just to test limits.
        with patch.object(pack,'sha',return_value='a'*64):
            return pack.pinned(self.root,{'path':self.file.name,'sha256':'a'*64},('.psd2live',),{},source_limit=pack.MAX_PROJECT_FILE)
    def test_project_above_256m_reaches_actual_project_format_check(self):
        fixture=CharacterPackageTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        project=fixture.root/'authoring/character.psd2live';raw=project.read_bytes()
        with project.open('wb') as output:output.seek(256*1024*1024+1-len(raw));output.write(raw)
        fixture.spec['project']={'path':'authoring/character.psd2live','sha256':'a'*64};real_sha=pack.sha
        with patch.object(pack,'sha',side_effect=lambda file:'a'*64 if file==project else real_sha(file)):
            # Exercise the actual project-field call, not just a manually raised
            # limit, so forgetting to wire source_members would fail this test.
            members,checks=pack.source_members(fixture.root,fixture.spec,{},{})
            self.assertEqual(members['source/character.psd2live'],project);self.assertTrue(checks['project_embedded_psd_matches'])
            with self.assertRaisesRegex(pack.PackageError,'source_not_regular_or_over_budget'):
                pack.pinned(fixture.root,fixture.spec['project'],('.psd2live',),{})
    def test_exact_project_320m_passes_but_one_extra_byte_fails(self):
        self.sparse_project(320*1024*1024);self.assertEqual(self.pin_project(),self.file)
        with self.file.open('r+b') as output:output.truncate(320*1024*1024+1)
        with self.assertRaisesRegex(pack.PackageError,'source_not_regular_or_over_budget'):self.pin_project()
    def test_other_source_psd_png_still_reject_above_256m(self):
        for suffix in ['.psd','.png']:
            with self.subTest(suffix=suffix):
                file=self.root/('large'+suffix)
                with file.open('wb') as output:output.truncate(256*1024*1024+1)
                with patch.object(pack,'sha',return_value='a'*64),self.assertRaisesRegex(pack.PackageError,'source_not_regular_or_over_budget'):
                    pack.pinned(self.root,{'path':file.name,'sha256':'a'*64},(suffix,),{})

if __name__=='__main__':unittest.main()
