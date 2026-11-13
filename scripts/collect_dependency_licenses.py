"""Copy installed Python distribution notices and metadata into a build output.

Only package metadata and explicitly identified license/notice files are read.
This does not inspect environment variables, credentials, user data or networks.
Missing upstream notice files are recorded; this inventory is not legal advice.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import re

MAX_NOTICE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def safe_name(value: str) -> str:
    # Prefixes used by callers avoid Windows reserved names such as CON/NUL.
    return re.sub(r'[^A-Za-z0-9._-]+', '_', value).strip('._-')[:100] or 'unnamed'


def notice_path(value: str) -> bool:
    parts = PurePosixPath(value.replace('\\', '/')).parts
    leaf = parts[-1].lower() if parts else ''
    return (any(part.lower() in {'license', 'licenses', 'licences'} for part in parts[:-1])
            or bool(re.match(r'^(licen[cs]e|copying|copyright|notice|authors)([._-]|$)', leaf)))


def package_source(distribution, relative: str) -> Path:
    """Accept only real package files below its installation root."""
    logical = PurePosixPath(relative.replace('\\', '/'))
    if logical.is_absolute() or '..' in logical.parts or ':' in relative:
        raise ValueError('notice path is absolute or traverses outside package root')
    base = Path(distribution.locate_file('')).resolve()
    source = Path(distribution.locate_file(relative))
    resolved = source.resolve()
    if source.is_symlink() or not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError('notice source is not a regular file below package root')
    return resolved


def collect(output: Path, distributions=None) -> dict:
    output = Path(output)
    if output.is_symlink() or (output.exists() and any(output.iterdir())):
        raise ValueError('license output must be a new or empty regular directory')
    output.mkdir(parents=True, exist_ok=True)
    inventory = {'generated_at': datetime.now(timezone.utc).isoformat(),
                 'scope': 'installed Python distribution metadata and package notice files; includes build/test dependencies if installed',
                 'distributions': [], 'total_copied_bytes': 0, 'external_requests': 0}
    installed = metadata.distributions() if distributions is None else distributions
    installed = sorted(installed, key=lambda item: (item.metadata.get('Name', '').lower(), item.version))
    used = set()
    for distribution in installed:
        name = distribution.metadata.get('Name', 'unknown')
        version = distribution.version
        text = distribution.read_text('METADATA') or distribution.read_text('PKG-INFO') or ''
        encoded = text.encode('utf-8')
        identity = f'{name}\0{version}\0{text}'.encode('utf-8')
        directory = 'pkg-' + safe_name(name + '-' + version) + '-' + hashlib.sha256(identity).hexdigest()[:10]
        if directory in used:
            continue
        used.add(directory)
        target = output/directory
        target.mkdir()
        (target/'METADATA.txt').write_bytes(encoded)
        record = {'name': name, 'version': version, 'directory': directory,
                  'metadata_sha256': hashlib.sha256(encoded).hexdigest(),
                  'license_expression': distribution.metadata.get('License-Expression'),
                  'notices': [], 'issues': []}
        candidates = {str(item) for item in distribution.files or [] if notice_path(str(item))}
        # PEP639 installs declared files below dist-info/licenses; older wheels
        # also place notices directly under dist-info. Prefer actual safe files.
        metadata_dirs = {str(PurePosixPath(str(item)).parent) for item in distribution.files or []
                         if str(item).replace('\\', '/').endswith('/METADATA')}
        for declared in distribution.metadata.get_all('License-File', []):
            for folder in metadata_dirs:
                alternatives = [str(PurePosixPath(folder)/'licenses'/declared),
                                str(PurePosixPath(folder)/declared)]
                accessible = []
                for relative in alternatives:
                    try:
                        package_source(distribution, relative)
                        accessible.append(relative)
                    except (OSError, ValueError):
                        pass
                candidates.update(accessible or alternatives[:1])
        for relative in sorted(candidates):
            try:
                source = package_source(distribution, relative)
                size = source.stat().st_size
                if size > MAX_NOTICE_BYTES:
                    raise ValueError('notice file exceeds 16MiB collection budget')
                if inventory['total_copied_bytes'] + size > MAX_TOTAL_BYTES:
                    raise ValueError('notice files exceed 64MiB collection budget')
                content = source.read_bytes()
                filename = f'notice-{len(record["notices"])+1:04d}-' + safe_name(source.name)
                (target/filename).write_bytes(content)
                record['notices'].append({'source': relative, 'file': filename, 'bytes': len(content),
                                          'sha256': hashlib.sha256(content).hexdigest()})
                inventory['total_copied_bytes'] += len(content)
            except (OSError, ValueError) as error:
                record['issues'].append({'source': relative, 'reason': str(error)})
        if not record['notices']:
            record['issues'].append({'reason': 'No accessible license/notice file advertised by this installed distribution; metadata retained.'})
        inventory['distributions'].append(record)
    inventory['distributions_count'] = len(inventory['distributions'])
    inventory['with_notice_files'] = sum(bool(item['notices']) for item in inventory['distributions'])
    inventory['with_issues'] = sum(bool(item['issues']) for item in inventory['distributions'])
    (output/'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--site-packages', type=Path, action='append',
                        help='read only these target package directories (repeatable; supports cross-platform wheel staging)')
    args = parser.parse_args()
    installed = None
    if args.site_packages:
        if any(not path.is_dir() or path.is_symlink() for path in args.site_packages):
            parser.error('--site-packages must identify existing regular package directories')
        installed = metadata.distributions(path=[str(path) for path in args.site_packages])
    result = collect(args.output, installed)
    print(json.dumps({key: result[key] for key in ['distributions_count', 'with_notice_files', 'with_issues', 'total_copied_bytes']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
