"""真实 HTTP + 本机模拟模型服务，验证协议与失败恢复，不代替真实模型质量测试。"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util,tempfile,threading,json,urllib.request,http.cookiejar,time,unittest

root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('protocol_app',root/'server.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
requests=[]
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(data)
        if data['model']=='json':
            body=json.dumps({'choices':[{'message':{'content':'兼容普通 JSON 回答。'}}]},ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body);return
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        try:
            if data['model']=='malformed':self.wfile.write(b'data: invalid json\n\n');return
            for token in (['慢慢回复。']*100 if data['model']=='slow' else ['接住你刚说的，','随便聊聊也很好。']):
                part={'choices':[{'delta':{'content':token}}]}
                self.wfile.write(('data: '+json.dumps(part,ensure_ascii=False)+'\n\n').encode());self.wfile.flush();time.sleep(.03)
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):pass

class HTTPStreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        for server in [cls.provider,cls.http]:threading.Thread(target=server.serve_forever,daemon=True).start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):
        for server in [cls.http,cls.provider]:server.shutdown();server.server_close()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DATA=Path(self.tmp.name);app.init()
        app.set_settings({'engine':'api','api_base':f'http://127.0.0.1:{self.provider.server_port}/v1','api_model':'normal','voice':False})
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.client.open(self.base).close()
    def tearDown(self):self.tmp.cleanup()
    def post(self,path,data):
        return self.client.open(urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Companion':'local-app'}),timeout=8)
    def events(self,response):
        with response:
            return [json.loads(line[5:]) for line in response if line.startswith(b'data:')]
    def test_http_streams_actual_provider_chunks_and_metadata(self):
        events=self.events(self.post('chat/stream',{'text':'普通闲聊','request_id':'stream'}))
        self.assertEqual(events[0]['type'],'meta');self.assertEqual(events[-1]['type'],'done')
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),'接住你刚说的，随便聊聊也很好。')
        self.assertTrue(requests[-1]['stream']);self.assertEqual(len([m for m in app.state()['messages'] if m['role']=='user']),1)
    def test_cancel_during_remote_stream_releases_job_and_does_not_commit(self):
        app.set_settings({'api_model':'slow'});response=self.post('chat/stream',{'text':'写一段话','request_id':'stop'})
        while True:
            line=response.readline()
            if line.startswith(b'data:') and json.loads(line[5:])['type']=='delta':break
        with self.post('chat/stop',{'request_id':'stop'}) as r:self.assertTrue(json.load(r)['stopping'])
        rest=self.events(response);self.assertTrue(rest[-1]['cancelled']);self.assertFalse(app.MODEL_LOCK.locked())
        self.assertFalse(any(m['role']=='assistant' and m['kind']=='chat' for m in app.state()['messages']))
    def test_malformed_provider_data_is_error_and_same_message_can_retry(self):
        app.set_settings({'api_model':'malformed'})
        events=self.events(self.post('chat/stream',{'text':'能恢复吗','request_id':'failed'}));self.assertEqual(events[-1]['type'],'error')
        self.assertFalse(app.MODEL_LOCK.locked());app.set_settings({'api_model':'normal'})
        events=self.events(self.post('chat/stream',{'text':'能恢复吗','request_id':'failed'}))
        self.assertEqual(events[-1]['type'],'done');self.assertEqual(sum(m['role']=='user' for m in app.state()['messages']),1)
    def test_json_only_provider_works_with_streaming_application(self):
        app.set_settings({'api_model':'json'})
        events=self.events(self.post('chat/stream',{'text':'你好','request_id':'json'}))
        self.assertEqual(events[-1]['message']['text'],'兼容普通 JSON 回答。')
    def test_disabled_memory_is_not_transmitted_to_provider(self):
        app.add_memory('我喜欢独一无二的秘密饮料');app.set_settings({'memory_mode':'off'})
        self.events(self.post('chat/stream',{'text':'我喜欢什么饮料','request_id':'no-memory'}))
        self.assertNotIn('独一无二的秘密',json.dumps(requests[-1],ensure_ascii=False))

if __name__=='__main__':unittest.main(verbosity=2)
