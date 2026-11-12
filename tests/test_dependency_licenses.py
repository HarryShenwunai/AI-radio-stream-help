"""Real distribution metadata/notice copying, including hostile RECORD paths."""
from email.message import Message
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/collect_dependency_licenses.py'
spec = importlib.util.spec_from_file_location('license_collector', SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class FakeDistribution:
    def __init__(self, root, files):
        self.root, self.files, self.version = root, files, '1.2'
        self.metadata = Message()
        self.metadata['Name'] = 'CON / malicious:package'
        self.metadata['License-Expression'] = 'MIT'

    def locate_file(self, name):
        return self.root/name

    def read_text(self, name):
        return 'Name: CON / malicious:package\nVersion: 1.2\nLicense-Expression: MIT\n' if name == 'METADATA' else None


class DependencyLicenseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='license-collector-')
        self.root = Path(self.tmp.name)
        self.packages = self.root/'packages'
        self.packages.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_notice_bytes_preserved_with_safe_names_and_metadata(self):
        folder = self.packages/'demo.dist-info/licenses'
        folder.mkdir(parents=True)
        data = b'Copyright fixture\r\nPermission fixture\r\n'
        (folder/'LICENSE.txt').write_bytes(data)
        (self.packages/'unrelated-user-data.txt').write_text('DO_NOT_COLLECT')
        distribution = FakeDistribution(self.packages, ['demo.dist-info/licenses/LICENSE.txt', 'unrelated-user-data.txt'])
        result = collector.collect(self.root/'out', [distribution])
        record = result['distributions'][0]
        copied = self.root/'out'/record['directory']/record['notices'][0]['file']
        self.assertEqual(copied.read_bytes(), data)
        self.assertEqual(record['notices'][0]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertTrue(record['directory'].startswith('pkg-'))
        self.assertEqual(len(record['notices']), 1)
        self.assertNotIn('DO_NOT_COLLECT', ''.join(path.read_text() for path in (self.root/'out').rglob('*') if path.is_file()))

    def test_parent_traversal_in_record_is_not_read(self):
        (self.root/'LICENSE-private').write_text('PRIVATE_CANARY')
        result = collector.collect(self.root/'out', [FakeDistribution(self.packages, ['../LICENSE-private'])])
        record = result['distributions'][0]
        self.assertEqual(record['notices'], [])
        self.assertTrue(any('traverses' in item['reason'] for item in record['issues']))
        self.assertNotIn('PRIVATE_CANARY', (self.root/'out/inventory.json').read_text())

    def test_metadata_license_file_declaration_resolves_in_distribution_metadata_directory(self):
        folder = self.packages/'demo.dist-info/legal'
        folder.mkdir(parents=True)
        (folder/'terms.txt').write_text('Actual declared permission')
        distribution = FakeDistribution(self.packages, ['demo.dist-info/METADATA'])
        distribution.metadata['License-File'] = 'legal/terms.txt'
        result = collector.collect(self.root/'out', [distribution])
        self.assertEqual(len(result['distributions'][0]['notices']), 1)

    def test_missing_upstream_notice_is_recorded_without_claiming_completeness(self):
        result = collector.collect(self.root/'out', [FakeDistribution(self.packages, [])])
        self.assertEqual(result['with_notice_files'], 0)
        self.assertEqual(result['with_issues'], 1)
        self.assertTrue((self.root/'out'/result['distributions'][0]['directory']/'METADATA.txt').is_file())

    def test_pep639_declared_notice_uses_licenses_subdirectory_without_false_missing_issue(self):
        folder = self.packages/'demo.dist-info/licenses'
        folder.mkdir(parents=True)
        (folder/'LICENSE').write_text('Actual PEP639 permission')
        distribution = FakeDistribution(self.packages, ['demo.dist-info/METADATA', 'demo.dist-info/licenses/LICENSE'])
        distribution.metadata['License-File'] = 'LICENSE'
        result = collector.collect(self.root/'out', [distribution])
        self.assertEqual(len(result['distributions'][0]['notices']), 1)
        self.assertEqual(result['with_issues'], 0)

    def test_nonempty_output_is_not_overwritten(self):
        output = self.root/'out'
        output.mkdir()
        (output/'keep.txt').write_text('KEEP')
        with self.assertRaises(ValueError):
            collector.collect(output, [])
        self.assertEqual((output/'keep.txt').read_text(), 'KEEP')


if __name__ == '__main__':
    unittest.main()
