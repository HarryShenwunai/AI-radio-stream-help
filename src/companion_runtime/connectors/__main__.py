"""Opt-in OpenLive local preview CLI. Default invocation opens no network."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from . import BiliOpenLive, OpenLiveCredentials

async def preview(config):
    if set(config) != {'access_key_id','access_key_secret','app_id','anchor_code','room_id'}:
        raise ValueError('config must contain exactly the five documented owner settings')
    client=BiliOpenLive(OpenLiveCredentials(config['access_key_id'],config['access_key_secret'],config['app_id'],config['anchor_code']),config['room_id'])
    stop=asyncio.Event();task=asyncio.create_task(client.run(stop))
    try:
        while not task.done():
            event=client.ingress.pop()
            if event is not None:
                print(json.dumps({'kind':'public_local_preview','event':asdict(event)},ensure_ascii=False),flush=True)
            await asyncio.sleep(.1)
    finally:
        stop.set()
        try:
            await asyncio.wait_for(task,12)
        except asyncio.TimeoutError:
            task.cancel()
        print(json.dumps(client.status(),ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser(description='Read-only OpenLive local preview; no outgoing platform messages')
    parser.add_argument('--connect',action='store_true',help='explicitly connect using owner credentials')
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    if not args.connect:
        print(json.dumps({'mode':'dryrun','network_opened':False,'account_verified':False,'outbound_supported':False}))
        return
    if args.config is None or args.config.stat().st_size > 8192:
        parser.error('--connect requires an owner-created config file of at most 8192 bytes')
    try:
        asyncio.run(preview(json.loads(args.config.read_text(encoding='utf-8'))))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit('Connector could not start; check owner config and optional aiohttp dependency. Credentials omitted.') from None

if __name__=='__main__':main()
