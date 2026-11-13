"""Read only this application's local diagnostics, never conversations or windows."""
from __future__ import annotations
import argparse,datetime as dt,http.cookiejar,json,statistics,time,urllib.parse,urllib.request
from pathlib import Path

def origin(value: str) -> str:
    parsed=urllib.parse.urlsplit(value)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'} or not parsed.port or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:
        raise ValueError('Only this application loopback origin is allowed')
    return f'http://{parsed.hostname}:{parsed.port}'

def measure(base: str, seconds: int) -> dict:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('Unexpected application redirect')
    base=origin(base);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    samples=[];started=time.monotonic();failure=None
    try:
        opener.open(base+'/',timeout=5).close()
        while True:
            with opener.open(base+'/api/runtime/diagnostics',timeout=6) as response:
                body=response.read(65537)
                if len(body)>65536:raise ValueError('Diagnostic response exceeds limit')
                value=json.loads(body)
            samples.append({'elapsed_seconds':round(time.monotonic()-started,3),'backend_process':value.get('backend_process',{}),'nvidia':value.get('nvidia',{}),'compute':value.get('compute',{}),'hardware_collected_at':value.get('collected_at')})
            if time.monotonic()-started>=seconds:break
            time.sleep(min(2,max(.1,seconds-(time.monotonic()-started))))
    except (OSError,ValueError):failure='local_backend_unavailable_or_invalid'
    elapsed=samples[-1]['elapsed_seconds']-samples[0]['elapsed_seconds'] if len(samples)>1 else 0
    first=samples[0]['backend_process'] if samples else {};last=samples[-1]['backend_process'] if samples else {}
    cpu=(last.get('cpu_seconds',0)-first.get('cpu_seconds',0))/elapsed*100 if elapsed else None
    private=[s['backend_process']['private_mib'] for s in samples if 'private_mib' in s['backend_process']]
    working=[s['backend_process']['working_set_mib'] for s in samples if 'working_set_mib' in s['backend_process']]
    return {'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'incomplete' if failure else 'complete','failure_reason':failure,'scope':'this Python backend only, excludes Electron/GPU-process allocations; physical GPU totals can include other applications',
            'duration_seconds':round(elapsed,3),'backend_average_cpu_percent_one_core':round(cpu,2) if cpu is not None else None,
            'backend_max_private_mib':max(private) if private else None,'backend_max_working_set_mib':max(working) if working else None,'samples':samples,
            'limitations':['GPU and hardware snapshots can be cached up to30s; inspect collected_at','No target p95 or UI/frame-rate/voice-quality inference from this passive sample'],
            'privacy':{'network':'loopback application only','read_conversations':False,'read_windows':False,'external_upload':False}}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--session',type=Path,required=True);parser.add_argument('--seconds',type=int,default=30);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not 5<=args.seconds<=300:raise SystemExit('Measurement must be5..300 seconds')
    if not args.session.is_file():raise SystemExit('请先启动桌面软件，再测量运行资源。')
    session=json.loads(args.session.read_text());value=measure(session['backend_origin'],args.seconds);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(value,ensure_ascii=False,indent=2))
