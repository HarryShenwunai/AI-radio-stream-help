"""Real local Git-object checks for the publishing CLI; no remote repository."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_app_update as builder

class AppUpdateCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.git('init','-q')
        for name in builder.COMMIT_FILES:
            file=self.source/name;file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes((ROOT/name).read_bytes() if name in builder.PUBLISHER_FILES else ('fixture: '+name+'\n').encode())
        self.commit=self.commit_all()
    def git(self,*arguments):
        return subprocess.run(['git','-C',str(self.source),*arguments],check=True,capture_output=True,
            env={**os.environ,'GIT_NO_REPLACE_OBJECTS':'1'}).stdout.decode().strip()
    def commit_all(self):
        self.git('add','--all');self.git('-c','user.name=CommitGuardFixture','-c','user.email=fixture@invalid.test','commit','-qm','publishing guard fixture')
        return self.git('rev-parse','HEAD')
    def cli(self,commit,source=None):
        output=self.root/'not-created'/'release.zip'
        result=subprocess.run([sys.executable,str(ROOT/'scripts/build_app_update.py'),'--source',str(source or self.source),
            '--source-commit',commit,'--base-package',str(self.root/'unused-base'),'--update-id','commit-guard-fixture',
            '--validation-report',str(self.root/'unused-report.json'),'--output',str(output)],capture_output=True,text=True)
        return result,output
    def test_actual_commit_and_exact_selected_source_are_accepted(self):
        self.assertEqual(builder.validate_source_commit(self.source,self.commit,publisher_source=ROOT),self.commit)
    def test_nonexistent_full_hex_is_not_treated_as_a_commit(self):
        with self.assertRaisesRegex(ValueError,'commit/repository'):builder.validate_source_commit(self.source,'f'*40)
    def test_existing_tree_object_is_not_a_commit(self):
        tree=self.git('rev-parse','HEAD^{tree}')
        with self.assertRaises(ValueError):builder.validate_source_commit(self.source,tree)
    def test_old_commit_is_rejected_after_a_selected_program_file_changes(self):
        (self.source/'app/server.py').write_bytes(b'fixture: changed server\n');new=self.commit_all()
        with self.assertRaisesRegex(ValueError,'app/server.py'):builder.validate_source_commit(self.source,self.commit)
        self.assertEqual(builder.validate_source_commit(self.source,new),new)
    def test_uncommitted_host_change_is_rejected(self):
        (self.source/'desktop/main.cjs').write_bytes(b'fixture: uncommitted host\n')
        with self.assertRaisesRegex(ValueError,'desktop/main.cjs'):builder.validate_source_commit(self.source,self.commit)
    def test_required_source_missing_in_git_or_replaced_by_link_is_rejected(self):
        self.git('rm','app/server.py');missing=self.commit_all()
        with self.assertRaisesRegex(ValueError,'absent'):builder.validate_source_commit(self.source,missing)
        self.git('reset','--hard',self.commit)
        file=self.source/'app/server.py';data=file.read_bytes();file.unlink();outside=self.root/'outside';outside.write_bytes(data);file.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'Unsafe release source'):builder.validate_source_commit(self.source,self.commit)
    def test_publisher_cannot_copy_uncommitted_helpers_from_another_checkout(self):
        other=self.root/'publisher';other.mkdir()
        with self.assertRaisesRegex(ValueError,'publisher/helper'):builder.validate_source_commit(self.source,self.commit,publisher_source=other)
    def test_cli_invalid_commit_fails_before_creating_any_artifact_or_output_directory(self):
        result,output=self.cli('f'*40)
        self.assertNotEqual(result.returncode,0);self.assertIn('commit/repository',result.stderr)
        self.assertFalse(output.exists());self.assertFalse(output.with_suffix('.zip.part').exists());self.assertFalse(output.parent.exists())
    def test_cli_stale_source_fails_without_building_a_package(self):
        (self.source/'app/server.py').write_bytes(b'fixture: dirty source\n')
        result,output=self.cli(self.commit)
        self.assertNotEqual(result.returncode,0);self.assertIn('app/server.py',result.stderr);self.assertFalse(output.parent.exists())
    def test_gitless_source_fails_instead_of_accepting_a_plausible_label(self):
        source=self.root/'gitless';source.mkdir();result,output=self.cli(self.commit,source)
        self.assertNotEqual(result.returncode,0);self.assertIn('repository',result.stderr);self.assertFalse(output.parent.exists())

if __name__=='__main__':unittest.main()
