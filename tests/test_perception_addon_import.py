"""Explicit real pure-Python import/closed-tree check on a cross-build host.

Platform/base-metadata checks are simulated only to exercise activation policy;
no Windows extension is imported or claimed to execute on Linux.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from companion_runtime.perception_optional import REUSED_BASE,activate_tracking_addon,verify_tracking_addon


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    before=verify_tracking_addon(args.app_root);assert before.verified
    base=args.app_root.parent
    def distribution(name):return SimpleNamespace(version=REUSED_BASE[name],locate_file=lambda item:base/'python/Lib/site-packages')
    (base/'python/Lib/site-packages').mkdir(parents=True,exist_ok=True)
    sys.dont_write_bytecode=False  # Negative starting condition; no -B masking.
    started=time.perf_counter()
    with patch('sys.platform','win32'),patch('importlib.metadata.distribution',side_effect=distribution):
        state=activate_tracking_addon(args.app_root)
    assert state.activated and sys.dont_write_bytecode is True
    module=importlib.import_module('absl.logging')
    assert Path(module.__file__).is_relative_to(state.site_packages_path)
    positive_elapsed=time.perf_counter()-started
    after=verify_tracking_addon(args.app_root);assert after.verified
    assert not list(state.site_packages_path.rglob('__pycache__'))
    # Independent real import without the guard must create cache on a clean copy.
    with tempfile.TemporaryDirectory(prefix='tracking-cache-negative-') as name:
        root=Path(name);shutil.copytree(state.site_packages_path/'absl',root/'absl')
        code='import sys;sys.path.insert(0,sys.argv[1]);sys.dont_write_bytecode=False;import absl.logging'
        child=subprocess.run([sys.executable,'-c',code,str(root)],capture_output=True,text=True)
        assert child.returncode==0,child.stderr
        caches=list(root.rglob('*.pyc'));assert caches
        negative_count=len(caches)
    report={'passed':True,'scope':'Real CPython3.12 pure-Python package import; platform/base-location activation checks simulated on Linux; no Windows DLL execution',
        'verified_before':True,'verified_after_real_import':True,'dont_write_bytecode_initial':False,
        'dont_write_bytecode_after_activate':True,'optional_pycache_files':0,
        'negative_without_guard_created_pyc_files':negative_count,'activation_and_import_seconds':round(positive_elapsed,5),
        'manifest_sha256':state.public()['manifest_sha256'],'windows_execution_verified':False,
        'source_sha256':hashlib.sha256(Path('src/companion_runtime/perception_optional.py').read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
