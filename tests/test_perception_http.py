"""Run explicitly: a real loopback HTTP protocol check, never semantic VLM proof.

Uses sockets and an explicit synthetic server; ordinary unittest discovery does
not launch network listeners. The caller may save the redacted JSON evidence.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import hashlib
import sys
import threading
import time

from PIL import Image
from companion_runtime.perception import OpenAICompatibleVisionProvider, PerceptionError


def main():
    observations=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            url=data['messages'][1]['content'][1]['image_url']['url']
            with Image.open(io.BytesIO(base64.b64decode(url.split(',',1)[1]))) as image:
                size=image.size
            observations.append({'path':self.path,'has_authorization':self.headers.get('Authorization')=='Bearer fixture-only',
                                 'image_size':list(size),'model':data['model'],'message_count':len(data['messages'])})
            if self.path.startswith('/redirect/'):
                self.send_response(307);self.send_header('Location','/must-not-follow');self.end_headers();return
            if self.path.startswith('/oversize/'):
                raw=b'x'*524289
            elif self.path.startswith('/failure/'):
                raw=b'private provider error content';self.send_response(500);self.end_headers();self.wfile.write(raw);return
            else:
                raw=json.dumps({'choices':[{'message':{'content':'Synthetic fixture response; not image understanding.'}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    output=io.BytesIO();Image.new('RGB',(64,32),'#fedcba').save(output,format='JPEG')
    checks=[]
    started=time.monotonic()
    try:
        base='http://127.0.0.1:'+str(server.server_port)
        for path,expected in (('/v1',None),('/redirect','provider_failed'),('/oversize','provider_failed'),('/failure','provider_failed')):
            provider=OpenAICompatibleVisionProvider(base+path,'synthetic-protocol-fixture','fixture-only')
            try:
                text=provider.describe(output.getvalue(),'image/jpeg','Fixture protocol test',threading.Event())
                actual=None
                assert text=='Synthetic fixture response; not image understanding.'
            except PerceptionError as error:
                actual=error.code
                assert 'private' not in str(error) and 'fixture-only' not in str(error)
            assert actual==expected,(path,actual,expected)
            checks.append({'path':path,'expected_error':expected,'passed':True})
        assert len(observations)==4, 'Redirect was followed'
        assert all(x['has_authorization'] and x['image_size']==[64,32] and x['message_count']==2 for x in observations)
        source=Path(__file__).parents[1]/'src/companion_runtime/perception.py'
        report={'scope':'real loopback HTTP adapter protocol only; synthetic responses; no real VLM inference',
                'passed':True,'checks':checks,'redirect_followed':False,'requests':observations,
                'elapsed_seconds':round(time.monotonic()-started,4),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__':main()
