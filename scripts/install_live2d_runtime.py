"""Owner-only opt-in installer. Does not ship or execute any Live2D vendor code."""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from companion_runtime.live2d_runtime import (Live2DRuntime, Live2DRuntimeError, inspect_local_sdk,
    PROPRIETARY_LICENSE, OPEN_SOFTWARE_LICENSE, EXPANDABLE_LICENSE)

LICENSE_NOTICE = f'''Optional local Live2D setup, separate from role import.
Core: {PROPRIETARY_LICENSE}
Framework: {OPEN_SOFTWARE_LICENSE}
Official download notice: "Downloading or launching this software shall constitute consent to the Software License Agreement."
Both agreements also include acceptance "by downloading, installing or using the Software".
--accept-official-license is an explicit OWNER acknowledgement for these local runtime actions. Do not pass it on another person's behalf.
This does not establish redistribution, commercial, GPL compatibility or Expandable Application publication permission: {EXPANDABLE_LICENSE}
No script is executed by this installer. Browser rendering later executes the installed libraries locally.
'''

def main(argv=None):
    parser=argparse.ArgumentParser(description=LICENSE_NOTICE,formatter_class=argparse.RawDescriptionHelpFormatter)
    data=Path(os.environ.get('COMPANION_DATA',str(ROOT/'app/data')))
    parser.add_argument('--runtime-root',type=Path,default=Path(os.environ.get('COMPANION_LIVE2D_RUNTIME',str(data/'live2d-runtime'))))
    commands=parser.add_subparsers(dest='action',required=True)
    commands.add_parser('status',help='inspect local runtime status; no download/install')
    remove=commands.add_parser('remove',help='remove optional owner-installed runtime bytes, preserving PNG/VRM and role data')
    remove.add_argument('--artifact',choices=['core','bundle','all'],default='all')
    local=commands.add_parser('inspect-local',help='hash a user-provided SDK/Core without executing or installing')
    local.add_argument('source',type=Path)
    official=commands.add_parser('install-official',help='owner-authorized fixed official HTTPS Core retrieval; no vendor-published digest is claimed')
    official.add_argument('--accept-official-license',action='store_true')
    for name in ['install-local','install-bundle']:
        cmd=commands.add_parser(name,help='copy owner-trusted local bytes only after explicit acknowledgements')
        cmd.add_argument('source',type=Path)
        cmd.add_argument('--expected-sha256',required=True)
        cmd.add_argument('--accept-official-license',action='store_true')
        cmd.add_argument('--trust-local-sdk' if name=='install-local' else '--trust-local-bundle',action='store_true')
    args=parser.parse_args(argv)
    runtime=Live2DRuntime(args.runtime_root)
    try:
        if args.action=='status':result=runtime.status()
        elif args.action=='remove':result=runtime.remove(None if args.artifact=='all' else args.artifact)
        elif args.action=='inspect-local':
            _,result=inspect_local_sdk(args.source)
            result.update(installed=False,executed=False,official_published_digest=False)
        elif args.action=='install-official':result=runtime.install_official(accept_official_license=args.accept_official_license)
        elif args.action=='install-local':result=runtime.install_local(args.source,expected_sha256=args.expected_sha256,
                   trust_local_sdk=args.trust_local_sdk,accept_official_license=args.accept_official_license)
        else:result=runtime.install_bundle(args.source,expected_sha256=args.expected_sha256,
                   trust_local_bundle=args.trust_local_bundle,accept_official_license=args.accept_official_license)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (Live2DRuntimeError,OSError,ValueError) as error:
        code=str(error) if isinstance(error,Live2DRuntimeError) else 'local_runtime_operation_failed'
        print(json.dumps({'error':code,'license_notice':LICENSE_NOTICE},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
