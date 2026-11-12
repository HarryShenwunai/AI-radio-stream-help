"""A synthetic loopback fixture verifies report scope and failure reporting."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util,json,threading,unittest
from unittest.mock import patch
FILE=Path(__file__).resolve().parents[2]/'scripts/measure_windows_runtime.py'
spec=importlib.util.spec_from_file_location('local_measurement',FILE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ResourceReport(unittest.TestCase):
    def test_only_plain_loopback_origins_are_accepted(self):
        for url in ['https://example.com','http://example.com:123','http://user@127.0.0.1:123','http://127.0.0.1:123/api/state','http://127.0.0.1:123/#fragment']:
            with self.subTest(url=url),self.assertRaises(ValueError):module.origin(url)
    def test_backend_failure_preserves_scoped_partial_report(self):
        paths=[];calls=0
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                nonlocal calls
                paths.append(self.path)
                if self.path=='/':body=b'<html>synthetic local page</html>'
                else:
                    calls+=1
                    if calls>1:self.send_response(503);self.end_headers();return
                    body=json.dumps({'backend_process':{'cpu_seconds':1,'private_mib':20,'working_set_mib':30},'secret':'must-not-enter-report'}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(module.time,'sleep'):report=module.measure('http://127.0.0.1:'+str(server.server_port),5)
            self.assertEqual(report['status'],'incomplete');self.assertEqual(len(report['samples']),1)
            self.assertEqual(set(paths),{'/','/api/runtime/diagnostics'});self.assertNotIn('must-not-enter-report',json.dumps(report));self.assertFalse(report['privacy']['external_upload'])
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
