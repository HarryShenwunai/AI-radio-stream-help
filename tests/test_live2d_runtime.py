"""Synthetic script/data fixtures only. No Live2D SDK is fetched or executed."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

from companion_runtime.live2d_runtime import (Live2DRuntime, Live2DRuntimeError, NoRedirect,
    inspect_local_sdk, OFFICIAL_CORE_URL)

CORE=b'// SYNTHETIC TEST ONLY\r\nwindow.Live2DCubismCore = {};\r\n'
BUNDLE=b'// SYNTHETIC TEST ONLY\nwindow.CompanionLive2DRuntime = {};\n'

class Response:
    def __init__(self, data=CORE, url=OFFICIAL_CORE_URL, status=200, headers=None):
        self.stream=io.BytesIO(data);self.url=url;self.status=status;self.headers=headers or {}
    def geturl(self):return self.url
    def read(self,n):return self.stream.read(n)
    def __enter__(self):return self
    def __exit__(self,*_):pass

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=Live2DRuntime(self.root/'optional-runtime')
        self.core=self.root/'live2dcubismcore.min.js';self.core.write_bytes(CORE)
        self.bundle=self.root/'owner-built.js';self.bundle.write_bytes(BUNDLE)
        self.core_sha=hashlib.sha256(CORE).hexdigest();self.bundle_sha=hashlib.sha256(BUNDLE).hexdigest()
    def install_core(self):return self.runtime.install_local(self.core,expected_sha256=self.core_sha,trust_local_sdk=True,accept_official_license=True)
    def install_bundle(self):return self.runtime.install_bundle(self.bundle,expected_sha256=self.bundle_sha,trust_local_bundle=True,accept_official_license=True)
    def mock_official(self,response):
        class Opener:
            def open(_self,request,timeout):
                self.assertEqual(request.full_url,OFFICIAL_CORE_URL);self.assertEqual(timeout,15)
                return response
        return patch('companion_runtime.live2d_runtime.urllib.request.build_opener',return_value=Opener())

    def test_missing_runtime_status_creates_nothing_and_opens_no_network(self):
        with patch('urllib.request.build_opener',side_effect=AssertionError('network forbidden')):
            state=self.runtime.status()
        self.assertFalse(state['available']);self.assertFalse(state['renderer_available']);self.assertIsNone(state['core_url'])
        self.assertFalse(self.runtime.root.exists())

    def test_official_requires_explicit_true_before_any_network(self):
        with patch('urllib.request.build_opener',side_effect=AssertionError('network forbidden')):
            for consent in [False,None,'yes',1]:
                with self.assertRaisesRegex(Live2DRuntimeError,'owner_license_confirmation_required'):
                    self.runtime.install_official(accept_official_license=consent)

    def test_local_requires_consent_trust_and_expected_sha(self):
        for kw in [{},{'accept_official_license':True},{'accept_official_license':True,'trust_local_sdk':True}]:
            with self.assertRaises(Live2DRuntimeError):self.runtime.install_local(self.core,expected_sha256='',**kw)
        with self.assertRaisesRegex(Live2DRuntimeError,'sha256_mismatch'):
            self.runtime.install_local(self.core,expected_sha256='0'*64,trust_local_sdk=True,accept_official_license=True)
        self.assertFalse(self.runtime.root.exists())

    def test_local_preserves_bytes_pin_and_exact_origin_label(self):
        state=self.install_core();self.assertTrue(state['core_available']);self.assertFalse(state['available'])
        self.assertEqual(self.runtime.read_core(),CORE)
        self.assertEqual(state['artifacts']['core']['source_type'],'owner_local_sdk')
        self.assertFalse(state['official_published_digest']);self.assertFalse(state['publication_permission_verified'])
        self.assertIsNone(state['runtime_url'])

    def test_wrapper_requires_own_trust_and_license_flags(self):
        with self.assertRaises(Live2DRuntimeError):self.runtime.install_bundle(self.bundle,expected_sha256=self.bundle_sha)
        with self.assertRaises(Live2DRuntimeError):self.runtime.install_bundle(self.bundle,expected_sha256=self.bundle_sha,accept_official_license=True)
        self.install_core();state=self.install_bundle()
        self.assertTrue(state['available']);self.assertTrue(state['renderer_available'])
        self.assertEqual(state['runtime_url'],'/live2d-runtime.js');self.assertEqual(self.runtime.read_bundle(),BUNDLE)

    def test_official_mock_provenance_is_observed_not_published(self):
        with self.mock_official(Response(headers={'Content-Length':str(len(CORE))})):
            state=self.runtime.install_official(accept_official_license=True)
        self.assertEqual(state['artifacts']['core']['source_type'],'official_https')
        self.assertEqual(state['artifacts']['core']['pin_kind'],'observed_sha256')
        self.assertEqual(self.runtime.read_core(),CORE)

    def test_official_transport_context_requires_normal_tls_verification(self):
        with self.mock_official(Response()) as build:
            self.runtime.install_official(accept_official_license=True)
        handler=next(x for x in build.call_args.args if isinstance(x,urllib.request.HTTPSHandler))
        self.assertEqual(handler._context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(handler._context.check_hostname)

    def test_any_redirect_rejected_and_final_url_must_match(self):
        handler=NoRedirect()
        for url in ['https://evil.example/core.js',OFFICIAL_CORE_URL+'?version=other']:
            with self.assertRaisesRegex(Live2DRuntimeError,'official_redirect_rejected'):
                handler.redirect_request(None,None,302,'',{},url)
            with self.mock_official(Response(url=url)):
                with self.assertRaises(Live2DRuntimeError):self.runtime.install_official(accept_official_license=True)

    def test_oversize_unknown_length_and_declared_length_rejected(self):
        with patch('companion_runtime.live2d_runtime.MAX_SCRIPT_BYTES',128):
            for response in [Response(CORE+b'x'*200),Response(headers={'Content-Length':'999'}),Response(headers={'Content-Length':'-1'})]:
                with self.mock_official(response):
                    with self.assertRaisesRegex(Live2DRuntimeError,'download_limit'):
                        self.runtime.install_official(accept_official_license=True)

    def test_wrong_http_status_truncated_and_html_rejected(self):
        for response in [Response(status=403),Response(headers={'Content-Length':'999'}),Response(b'<html>Live2DCubismCore</html>')]:
            with self.mock_official(response):
                with self.assertRaises(Live2DRuntimeError):self.runtime.install_official(accept_official_license=True)

    def test_sdk_archive_only_extracts_selected_core_and_no_other_js(self):
        path=self.root/'sdk.zip'
        with zipfile.ZipFile(path,'w') as sdk:
            sdk.writestr('CubismSdkForWeb-test/Core/live2dcubismcore.min.js',CORE)
            sdk.writestr('CubismSdkForWeb-test/Core/live2dcubismcore.js',CORE+b'//not selected')
            sdk.writestr('CubismSdkForWeb-test/evil.js','throw new Error("never executed")')
        data,info=inspect_local_sdk(path);self.assertEqual(data,CORE);self.assertTrue(info['member'].endswith('.min.js'))
        self.runtime.install_local(path,expected_sha256=self.core_sha,accept_official_license=True,trust_local_sdk=True)
        self.assertFalse((self.runtime.root/'evil.js').exists())

    def test_unsafe_and_duplicate_sdk_entries_rejected(self):
        for extra in ['../evil.js','Core\\evil.js','/evil.js','C:/evil.js']:
            path=self.root/'bad.zip'
            with zipfile.ZipFile(path,'w') as sdk:
                sdk.writestr('Core/live2dcubismcore.min.js',CORE);sdk.writestr(extra,'bad')
            with self.assertRaises(Live2DRuntimeError):inspect_local_sdk(path)
        path=self.root/'ambiguous.zip'
        with zipfile.ZipFile(path,'w') as sdk:
            sdk.writestr('Core/live2dcubismcore.min.js',CORE);sdk.writestr('CubismSdkForWeb-other/Core/live2dcubismcore.min.js',CORE)
        with self.assertRaisesRegex(Live2DRuntimeError,'ambiguous_or_missing_core'):inspect_local_sdk(path)

    def test_symlink_sdk_core_member_rejected(self):
        path=self.root/'bad.zip'
        with zipfile.ZipFile(path,'w') as sdk:
            item=zipfile.ZipInfo('Core/live2dcubismcore.min.js');item.create_system=3;item.external_attr=(stat.S_IFLNK|0o777)<<16;sdk.writestr(item,CORE)
        with self.assertRaisesRegex(Live2DRuntimeError,'unsafe_sdk_core'):inspect_local_sdk(path)

    def test_sdk_central_directory_count_bounded_before_parsing(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as sdk:sdk.writestr('Core/live2dcubismcore.min.js',CORE)
        data=bytearray(raw.getvalue());index=data.rfind(b'PK\x05\x06');data[index+10:index+12]=(50000).to_bytes(2,'little')
        path=self.root/'large-directory.zip';path.write_bytes(data)
        with self.assertRaisesRegex(Live2DRuntimeError,'sdk_entry_limit'):inspect_local_sdk(path)

    def test_fixed_official_dispatch_with_real_loopback_http_body(self):
        # The test dispatcher deliberately remaps HTTPS to a loopback mock.
        # Production HTTPS verification is checked separately; no live TLS claim.
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Length',str(len(CORE)));self.end_headers()
                for index in range(0,len(CORE),5):self.wfile.write(CORE[index:index+5]);self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        real=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        test=self
        class Dispatcher:
            def open(_self,request,timeout):
                test.assertEqual(request.full_url,OFFICIAL_CORE_URL)
                response=real.open('http://127.0.0.1:'+str(server.server_port),timeout=timeout)
                response.geturl=lambda:OFFICIAL_CORE_URL
                return response
        try:
            with patch('companion_runtime.live2d_runtime.urllib.request.build_opener',return_value=Dispatcher()):
                self.runtime.install_official(accept_official_license=True)
            self.assertEqual(self.runtime.read_core(),CORE)
        finally:server.shutdown();server.server_close();thread.join(3)

    def test_installed_bytes_tampering_fails_closed(self):
        self.install_core();pointer=json.loads((self.runtime.root/'core.json').read_text())
        file=self.runtime.root/'revisions'/pointer['revision']/'script.js';file.write_bytes(CORE+b'// changed')
        self.assertFalse(self.runtime.status()['core_available'])
        with self.assertRaisesRegex(Live2DRuntimeError,'installed_runtime_changed'):self.runtime.read_core()

    def test_tampered_provenance_and_pointer_rejected(self):
        self.install_core();pointer=json.loads((self.runtime.root/'core.json').read_text())
        record=self.runtime.root/'revisions'/pointer['revision']/'record.json';data=json.loads(record.read_text());data['source']['owner_license_acknowledged']=False;record.write_text(json.dumps(data))
        self.assertFalse(self.runtime.status()['core_available'])
        (self.runtime.root/'core.json').write_text('{"revision":"../../secret"}')
        self.assertFalse(self.runtime.status()['core_available'])

    def test_failed_update_preserves_previous_active_runtime(self):
        self.install_core();old=(self.runtime.root/'core.json').read_bytes()
        changed=CORE+b'// owner update';self.core.write_bytes(changed)
        with patch('companion_runtime.live2d_runtime.os.replace',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):self.runtime.install_local(self.core,expected_sha256=hashlib.sha256(changed).hexdigest(),accept_official_license=True,trust_local_sdk=True)
        self.assertEqual((self.runtime.root/'core.json').read_bytes(),old);self.assertEqual(self.runtime.read_core(),CORE)

    def test_updates_keep_only_active_artifacts_and_remove_preserves_other_data(self):
        unrelated=self.root/'private-role.db';unrelated.write_bytes(b'unchanged')
        self.install_core();self.install_bundle();self.install_core()
        self.assertEqual(len(list((self.runtime.root/'revisions').iterdir())),2)
        self.runtime.remove('core');self.assertFalse(self.runtime.status()['core_available']);self.assertTrue(self.runtime.status()['renderer_available'])
        self.runtime.remove();self.assertEqual(len(list((self.runtime.root/'revisions').iterdir())),0)
        self.assertEqual(unrelated.read_bytes(),b'unchanged')

    @unittest.skipUnless(os.name=='posix','POSIX fixture; Windows ACL is separate')
    def test_directory_file_modes_and_symlink_refusal(self):
        self.install_core();self.assertEqual(stat.S_IMODE(self.runtime.root.stat().st_mode),0o700)
        pointer=json.loads((self.runtime.root/'core.json').read_text());script=self.runtime.root/'revisions'/pointer['revision']/'script.js'
        self.assertEqual(stat.S_IMODE(script.stat().st_mode),0o600)
        target=self.root/'other.js';target.write_bytes(CORE);script.unlink();script.symlink_to(target)
        self.assertFalse(self.runtime.status()['core_available'])
        alias=self.root/'alias';alias.symlink_to(self.runtime.root,target_is_directory=True)
        with self.assertRaises(Live2DRuntimeError):Live2DRuntime(alias).install_local(self.core,expected_sha256=self.core_sha,trust_local_sdk=True,accept_official_license=True)
