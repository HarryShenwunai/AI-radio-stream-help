"""Serialize an explicitly selected PNG character; never edit pixels or activate.

The same runtime AssetStore validates every image and the clip metadata before
the self-service package is written. No account, user profile or app is changed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from companion_runtime.assets import AssetStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'assets/character-2d')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    files={'idle':'idle.png','talk':'talking.png','blink':'blink.png','talk_blink':'talking_blink.png'}
    states={name:(args.source/file).read_bytes() for name,file in files.items()}
    regions=json.loads((args.source/'recommended-animation-regions.json').read_text())['animation_regions']
    with tempfile.TemporaryDirectory(prefix='png-character-package-') as folder:
        asset=AssetStore(Path(folder)).import_png_states(states,files,animation_regions=regions)
        assert asset['animation_regions']==regions
    payload={'format':'companion-png-package','version':1,
             'states':{name:{'filename':files[name],'data_base64':base64.b64encode(value).decode('ascii')}
                       for name,value in states.items()},'animation_regions':regions}
    value=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(value)>12*1024*1024:raise ValueError('Package exceeds the frontend 12MiB input limit')
    if args.output.exists():raise FileExistsError('Choose a new output, preserving the previous artifact')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(value)
    checksum=hashlib.sha256(value).hexdigest()
    args.output.with_suffix(args.output.suffix+'.sha256').write_text(checksum+'  '+args.output.name+'\n')
    print(json.dumps({'path':str(args.output),'bytes':len(value),'sha256':checksum,
                      'source_images_edited':False,'activated':False},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
