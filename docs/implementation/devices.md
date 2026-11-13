# Hardware declarations

`DevicePreferencesStore(DATA / 'devices')` stores global user declarations in
`device-preferences.json`, independently of characters and relationship memory.

- `load()` returns immutable `DevicePreferences(display, camera, microphone)`.
- `save(payload)` accepts a partial object containing only boolean `display`,
  `camera`, `microphone`; an empty object preserves existing values.
- `snapshot()` or `load().public()` returns direct device keys with
  `declared_available`, `detection: "not_checked"`, `permission: "not_requested"`.
- All three are declared available on first launch, as requested by the user.
- `display` means an optional 5-inch avatar device. It never disables the primary
  PC scene, PC Vision or TTS. A microphone declaration never controls TTS output.

These values are declarations, never OS detection, current permissions or capture
activity. The backend/native integration must independently gate each input and
stop its existing capture when it becomes unavailable. A selected device still
needs an explicit session and actual operating-system/browser permission.

`DevicePreferencesError` has `code` and `status` (400 by default). Corrupt existing
storage produces an error rather than silently restoring defaults; that avoids
re-enabling a previously disabled input. Writes are atomic, files are bounded to
1024 bytes, and symlink/reparse/nonregular targets are refused. Modes are 0700 and
0600 on POSIX. Windows privacy depends on the user's AppData ACL. A trusted parent
directory and a single shared store instance are required; this does not claim
cross-process update locking or resistance to a malicious parent-directory owner.

Module checks: `PYTHONPATH=src python -m unittest discover -s tests -p test_devices.py`.
They validate storage and declarations, not physical hardware or Windows capture.
