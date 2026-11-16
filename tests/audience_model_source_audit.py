"""Read-only nested R3 provenance; extract selected original PNG bytes for inspection."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit(package, old_source, out):
    package_bytes = package.read_bytes()
    outer = zipfile.ZipFile(io.BytesIO(package_bytes))
    editable_bytes = outer.read('R3-Study-Editable.zip')
    editable = zipfile.ZipFile(io.BytesIO(editable_bytes))
    native_bytes = editable.read('character.psd2live')
    native = zipfile.ZipFile(io.BytesIO(native_bytes))
    manifest = json.loads(native.read('manifest.json'))
    checks = {name: sha(native.read(name)) == expected for name, expected in manifest['files'].items()}
    sources = [name for name in native.namelist() if name.startswith('document/nodes/source/')]
    assert len(sources) == 1, 'Multiple source nodes need explicit history resolution; never choose by filename'
    source_name = sources[0]
    source = json.loads(native.read(source_name))['value']
    out.mkdir(parents=True, exist_ok=True)
    layers = []
    for label in ['Mouth_open', 'Neck_face']:
        layer = next(layer for layer in source['layers'] if layer['name'] == label)
        matches = []
        for name in native.namelist():
            if name.startswith('assets/') and name.endswith(f"-{layer['rasterWidth']}x{layer['rasterHeight']}.png"):
                data = native.read(name)
                image = Image.open(io.BytesIO(data)).convert('RGBA')
                if sha(image.tobytes()) == layer['rgbaBlob']:
                    matches.append((name, data, image))
        assert len(matches) == 1, (label, len(matches))
        name, data, image = matches[0]
        target = out / (label+'.png')
        target.write_bytes(data)  # Exact archive bytes, no image editing.
        prior = Image.open(old_source / (label+'.png')).convert('RGBA')
        layers.append({'name': label, 'source_metadata': layer, 'asset': name,
                       'asset_sha256': sha(data), 'decoded_rgba_sha256': sha(image.tobytes()),
                       'alpha_extrema': image.getchannel('A').getextrema(),
                       'fully_opaque_pixels': image.getchannel('A').histogram()[255],
                       'fully_opaque_bbox': image.getchannel('A').point(lambda value: 255 if value == 255 else 0).getbbox(),
                       'matches_preexisting_source_rgba': image.size == prior.size and image.tobytes() == prior.tobytes(),
                       'extracted': str(target)})
    report = {'scope': 'Archive integrity and exact raster identity only; visual interpretation recorded separately',
              'package': str(package), 'package_sha256': sha(package_bytes),
              'editable_zip_sha256': sha(editable_bytes), 'native_sha256': sha(native_bytes),
              'original_psd_sha256': sha(native.read('source/original.psd')),
              'source_node': source_name, 'layer_count': len(source['layers']),
              'manifest_file_count': len(checks), 'manifest_all_match': all(checks.values()),
              'layers': layers, 'original_package_unchanged': package.read_bytes() == package_bytes}
    assert report['manifest_all_match'] and report['original_package_unchanged']
    (out/'source-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ['layer_count', 'manifest_file_count', 'manifest_all_match', 'original_package_unchanged']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--old-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    audit(args.package, args.old_source, args.out)
