"""Availability declarations persist without manufacturing capture permission."""
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from companion_runtime.devices import DevicePreferences, DevicePreferencesError, DevicePreferencesStore


class DevicePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'devices'
        self.store = DevicePreferencesStore(self.root)

    def test_default_is_declared_not_detected_or_authorized(self):
        public = self.store.snapshot()
        self.assertEqual(set(public), {'display', 'camera', 'microphone'})
        for item in public.values():
            self.assertTrue(item['declared_available'])
            self.assertEqual(item['detection'], 'not_checked')
            self.assertEqual(item['permission'], 'not_requested')
            self.assertNotIn('active', item)
        self.assertEqual(public['display']['purpose'], 'optional_5inch_avatar_display')
        self.assertFalse(self.store.path.exists())

    def test_partial_change_survives_restart_and_other_devices_stay_available(self):
        value = self.store.save({'camera': False})
        self.assertEqual(value, DevicePreferences(camera=False))
        second = DevicePreferencesStore(self.root)
        self.assertEqual(second.load(), value)
        self.assertEqual(second.save({'microphone': False}), DevicePreferences(camera=False, microphone=False))
        self.assertEqual(second.save({'display': False}), DevicePreferences(False, False, False))
        self.assertEqual(second.save({'camera': True}), DevicePreferences(False, True, False))
        self.assertEqual(second.save({}), DevicePreferences(False, True, False))

    def test_public_copy_cannot_change_stored_preferences(self):
        public = self.store.save({'camera': False}).public()
        public['camera']['declared_available'] = True
        self.assertFalse(self.store.load().camera)

    def test_payload_is_boolean_only_and_no_unknown_fields(self):
        self.store.save({'camera': False})
        original = self.store.path.read_bytes()
        for payload in (None, [], 'camera', {'camera': 0}, {'camera': 1}, {'camera': 'false'},
                        {'camera': None}, {'display': {}}, {'microphone': []},
                        {'camera': True, 'permission': True}, {'screen': False}, {1: False}):
            with self.subTest(payload=payload), self.assertRaises(DevicePreferencesError):
                self.store.save(payload)
            self.assertEqual(self.store.path.read_bytes(), original)

    def test_corrupt_config_does_not_reenable_camera_or_overwrite_file(self):
        self.root.mkdir()
        for raw in (b'{', b'[]', b'null', b'{}', b'{"camera":false}',
                    b'{"camera":false,"display":true,"microphone":0}',
                    b'{"camera":false,"display":true,"microphone":true,"camera":true}',
                    b'x' * (self.store.MAX_BYTES + 1)):
            self.store.path.write_bytes(raw)
            with self.subTest(raw=raw[:80]):
                with self.assertRaises(DevicePreferencesError):
                    self.store.load()
                with self.assertRaises(DevicePreferencesError):
                    self.store.save({'camera': True})
                self.assertEqual(self.store.path.read_bytes(), raw)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_file_symlink_rejected_without_modifying_external_target(self):
        self.root.mkdir()
        target = Path(self.temporary.name) / 'external.json'
        target.write_text('{"display":true,"camera":false,"microphone":true}')
        before = target.read_bytes()
        self.store.path.symlink_to(target)
        with self.assertRaises(DevicePreferencesError):
            self.store.load()
        with self.assertRaises(DevicePreferencesError):
            self.store.save({'camera': True})
        self.assertEqual(target.read_bytes(), before)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_ancestor_symlink_and_nondirectory_rejected(self):
        target = Path(self.temporary.name) / 'target'
        target.mkdir()
        self.root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(DevicePreferencesError):
            DevicePreferencesStore(self.root / 'child').save({'camera': False})
        self.assertFalse((target / 'child').exists())
        self.root.unlink()
        self.root.write_text('not a directory')
        with self.assertRaises(DevicePreferencesError):
            self.store.load()

    def test_nonregular_target_rejected(self):
        self.root.mkdir()
        self.store.path.mkdir()
        with self.assertRaises(DevicePreferencesError):
            self.store.load()

    def test_reparse_flag_rejected(self):
        class Reparse:
            st_mode = stat.S_IFREG | 0o600
            st_file_attributes = 0x400
        self.assertTrue(self.store._unsafe(Reparse()))

    @unittest.skipUnless(os.name == 'posix', 'POSIX mode check')
    def test_private_file_and_directory_modes(self):
        self.store.save({'display': False})
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)

    def test_replace_failure_preserves_old_file_and_cleans_temporary(self):
        self.store.save({'camera': False})
        before = self.store.path.read_bytes()
        with patch('companion_runtime.devices.os.replace', side_effect=OSError('private-path')):
            with self.assertRaises(DevicePreferencesError) as error:
                self.store.save({'camera': True})
        self.assertEqual(error.exception.code, 'device_preferences_write_failed')
        self.assertNotIn('private-path', str(error.exception))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_same_instance_concurrent_partial_updates_preserve_all_switches(self):
        errors = []
        def update(name):
            try:
                self.store.save({name: False})
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=update, args=(name,)) for name in ('display', 'camera', 'microphone')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.store.load(), DevicePreferences(False, False, False))
        self.assertEqual(set(json.loads(self.store.path.read_text())), {'display', 'camera', 'microphone'})


if __name__ == '__main__':
    unittest.main()
