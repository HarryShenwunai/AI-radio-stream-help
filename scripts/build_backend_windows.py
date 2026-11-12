"""Build the Windows x64 onedir backend; assets/user data are never bundled.

Run in a Windows Python environment with app/requirements-core.txt,
app/requirements.txt and PyInstaller installed. Models are copied explicitly
after a successful build, outside this script.
"""
from pathlib import Path
import argparse
import importlib.util
import os
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def command():
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
            '--name', 'companion-backend', '--distpath', str(ROOT/'.build/native'),
            '--workpath', str(ROOT/'.build/pyinstaller-windows'), '--specpath', str(ROOT/'.build'),
            '--paths', str(ROOT/'src'), '--add-data', str(ROOT/'app/static') + os.pathsep + 'static',
            '--hidden-import', 'PIL.PngImagePlugin']
    for package in ['llama_cpp', 'kokoro_onnx', 'espeakng_loader', 'pypinyin',
                    'pypinyin_dict', 'jieba', 'onnxruntime']:
        args += ['--collect-all', package]
    args += ['--collect-data', 'misaki']
    for package in ['pandas', 'scipy', 'IPython', 'jedi', 'matplotlib', 'tkinter']:
        args += ['--exclude-module', package]
    return args + [str(ROOT/'app/server.py')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-command', action='store_true', help='inspect without executing or requiring Windows')
    args = parser.parse_args()
    if args.print_command:
        print(subprocess.list2cmdline(command()))
        return
    if sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise SystemExit('Build on Windows x64 using a Windows Python interpreter; cross-compilation is unsupported.')
    required = ['PyInstaller', 'PIL', 'llama_cpp', 'kokoro_onnx', 'espeakng_loader',
                'pypinyin', 'pypinyin_dict', 'jieba', 'misaki', 'onnxruntime']
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit('Missing build dependencies: ' + ', '.join(missing))
    subprocess.run(command(), cwd=ROOT, check=True)
    binary = ROOT/'.build/native/companion-backend/companion-backend.exe'
    static = binary.parent/'_internal/static/index.html'
    if not binary.is_file() or not static.is_file():
        raise SystemExit('Build did not produce the backend executable and bundled static/index.html.')
    from collect_dependency_licenses import collect
    notices = collect(binary.parent/'licenses/distributions')
    print(f'Collected metadata for {notices["distributions_count"]} installed distributions; '
          f'{notices["with_issues"]} have inventory issues requiring review.')
    print(f'Built Windows backend: {binary}')


if __name__ == '__main__':
    main()
