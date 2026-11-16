"""Bind the existing registered subtle-mouth patch in a distinct R3 candidate.

This changes opacity keyforms only, not artwork, geometry, yaw or phonemes.
The upstream build-only local_client.session must be supplied explicitly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--runtime-baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--client-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    baseline = args.runtime_baseline.resolve()
    out = args.out.resolve()
    if out.exists():
        raise SystemExit('Use a new candidate output directory; do not overwrite prior evidence')
    source_bytes, runtime_bytes = source.read_bytes(), baseline.read_bytes()
    out.mkdir(parents=True)
    sys.path.insert(0, str(args.client_dir.resolve()))
    from local_client import session
    with session() as client:
        client.edit('project_open', path=str(source), discard_unsaved=True)
        objects = client.call('workspace_inspect', {'scope': 'objects', 'limit': 64})[0]['items']
        mouth = next(row for row in objects if row.get('name') == 'Mouth_open' and row['target'].startswith('mesh:'))
        target = mouth['target']
        client.edit('rig_edit_structure', edits=[{'action': 'static', 'kind': 'mesh', 'id': target.split(':')[1], 'opacity': 1}])
        client.edit('keyform_apply', changes=[{'op': 'seed', 'target': target, 'key': {'ParamMouthOpenY': value}} for value in [0, 1]])
        client.edit('keyform_apply', changes=[{'op': 'set', 'target': target, 'key': {'ParamMouthOpenY': value}, 'channels': {'opacity': value}} for value in [0, 1]])
        client.edit('project_save_as', path=str(out/'R3-subtle-mouth-r1.psd2live'))
        client.edit('project_export_model', output_directory=str(out/'editable-export'))
    exported = out/'editable-export'
    moc = (exported/'original.moc3').read_bytes()
    with zipfile.ZipFile(baseline) as original:
        unchanged = {name: original.read(name) == (exported/name).read_bytes() for name in ['original.4096/texture_00.png', 'original.cdi3.json']}
        assert all(unchanged.values()), unchanged
        package = out/'R3-subtle-mouth-r1.zip'
        with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as candidate:
            for name in original.namelist():
                candidate.writestr(name, moc if name == 'original.moc3' else original.read(name))
    assert source.read_bytes() == source_bytes and baseline.read_bytes() == runtime_bytes
    report = {'scope': 'Candidate subtle closed/open patch blending; not jaw/phoneme rig or accepted artwork',
              'source_sha256': sha(source_bytes), 'baseline_sha256': sha(runtime_bytes),
              'candidate_zip_sha256': sha(package.read_bytes()), 'candidate_moc_sha256': sha(moc),
              'source_unmodified': True, 'baseline_unmodified': True,
              'artwork_and_display_info_byte_identical': unchanged,
              'changes': {'target': target, 'static_opacity': 1, 'ParamMouthOpenY_opacity_keys': [[0, 0], [1, 1]]},
              'geometry_changes_requested': False, 'acceptance': 'Pending actual Core continuity/neutral/ROI review'}
    (out/'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
