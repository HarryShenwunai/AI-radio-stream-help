"""Explicit synthetic adapters test ownership/protocol, not image understanding."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from companion_runtime.perception import (PerceptionError, PerceptionLimits, PerceptionManager,
    PerceptionScope, VisionConfigStore, OpenAICompatibleVisionProvider, validate_vision_base)


class SyntheticProvider:
    def __init__(self, processing='local', action=None):
        self.processing, self.action, self.calls = processing, action, []
    def status(self):
        return {'configured': True, 'processing': self.processing, 'inference_verified': False}
    def describe(self, image, mime, prompt, cancel):
        self.calls.append((image, mime, prompt))
        return self.action(cancel) if self.action else 'Synthetic protocol response; no semantic inference.'


def image_data(size=(24, 16), fmt='PNG', metadata=False):
    out = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text('PRIVATE', 'secret-location')
    Image.new('RGB', size, '#fedcba').save(out, format=fmt, pnginfo=info if fmt == 'PNG' else None)
    return base64.b64encode(out.getvalue()).decode()


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.wall = [200.0]
        self.scope = PerceptionScope('owner', 'role-a', 'appearance-a', 1)
        self.current = [self.scope]
        self.provider = SyntheticProvider()
        self.manager = PerceptionManager(self.provider, clock=lambda: self.now[0], wall_clock=lambda: self.wall[0],
                                          is_scope_current=lambda s: s == self.current[0])
    def start(self, kind='screen', **kw):
        return self.manager.start(self.scope, kind, consent_confirmed=True, **kw)['session_id']
    def frame(self, sid, request='frame1', **kw):
        data = dict(session_id=sid, request_id=request, image_base64=image_data(), mime_type='image/png',
                    captured_at_ms=int(self.wall[0]*1000))
        data.update(kw)
        return self.manager.frame(self.scope, **data)
    def code(self, code, fn):
        with self.assertRaises(PerceptionError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        return caught.exception
    def test_unconfigured_is_unavailable(self):
        manager = PerceptionManager()
        self.assertFalse(manager.status('owner')['vision']['configured'])
        self.code('vision_not_configured', lambda: manager.start(self.scope, 'screen', consent_confirmed=True))
    def test_consent_must_be_true_not_truthy(self):
        self.code('consent_required', lambda: self.manager.start(self.scope, 'screen', consent_confirmed=1))
    def test_remote_requires_separate_consent(self):
        self.manager.configure(SyntheticProvider('remote'))
        self.code('consent_required', lambda: self.start())
        self.assertTrue(self.start(remote_processing_confirmed=True))
    def test_invalid_start_cannot_cancel_existing(self):
        old = self.start()
        self.code('consent_required', lambda: self.manager.start(self.scope, 'screen', consent_confirmed=False))
        self.assertTrue(self.frame(old))
    def test_local_success_is_volatile_and_strips_metadata(self):
        result = self.frame(self.start(), image_base64=image_data(metadata=True))
        self.assertFalse(result['retained'])
        image, mime, _ = self.provider.calls[0]
        self.assertEqual(mime, 'image/jpeg')
        self.assertNotIn(b'secret-location', image)
        with Image.open(io.BytesIO(image)) as decoded:
            self.assertEqual(decoded.size, (24, 16))
            self.assertFalse(decoded.getexif())
    def test_exact_duplicate_does_not_infer_twice(self):
        sid = self.start()
        self.assertEqual(self.frame(sid), self.frame(sid))
        self.assertEqual(len(self.provider.calls), 1)
    def test_conflicting_duplicate_rejected(self):
        sid = self.start(); self.frame(sid)
        self.code('request_conflict', lambda: self.frame(sid, prompt='different'))
    def test_rate_limit_and_recovery(self):
        sid = self.start(); self.frame(sid)
        self.code('rate_limited', lambda: self.frame(sid, request='frame2'))
        self.now[0] += 2
        self.assertTrue(self.frame(sid, request='frame2'))
    def test_restart_cannot_bypass_global_rate_limit(self):
        self.frame(self.start())
        replacement=self.start()
        self.code('rate_limited',lambda:self.frame(replacement))
        self.now[0]+=2
        self.assertTrue(self.frame(replacement))
    def test_wrong_owner_cannot_read_or_stop(self):
        sid = self.start()
        self.assertEqual(self.manager.status('other')['sessions'], [])
        self.manager.stop('other', sid)
        other = PerceptionScope('other', 'role-a', 'appearance-a', 1)
        self.code('session_unavailable', lambda: self.manager.frame(other, session_id=sid, request_id='x',
            image_base64=image_data(), mime_type='image/png', captured_at_ms=200000))
        self.assertTrue(self.frame(sid))
    def test_stop_old_does_not_stop_new(self):
        old = self.start(); new = self.start()
        self.manager.stop('owner', old)
        self.assertTrue(self.frame(new))
        self.code('session_unavailable', lambda: self.frame(old))
    def test_scope_change_and_aba_do_not_reuse_session(self):
        sid = self.start()
        self.current[0] = PerceptionScope('owner', 'role-a', 'appearance-a', 3)
        self.code('scope_changed', lambda: self.frame(sid))
        self.current[0] = self.scope
        self.code('cancelled', lambda: self.frame(sid))
    def test_stale_scope_request_cannot_cancel_new_session(self):
        sid = self.start()
        stale = PerceptionScope('owner', 'old', 'old', 0)
        self.code('scope_changed', lambda: self.manager.frame(stale, session_id=sid, request_id='x',
            image_base64=image_data(), mime_type='image/png', captured_at_ms=200000))
        self.assertTrue(self.frame(sid))
    def test_expiration(self):
        sid = self.start(); self.now[0] += 900
        self.code('session_expired', lambda: self.frame(sid))
        self.assertEqual(self.manager.status('owner')['sessions'], [])
    def test_timestamp_validation(self):
        sid = self.start()
        for value in (True, '200000', -1):
            self.code('invalid_frame', lambda: self.frame(sid, captured_at_ms=value))
        for value in (180000, 203000):
            self.code('frame_expired', lambda: self.frame(sid, captured_at_ms=value))
    def test_bad_image_and_mime_do_not_consume_rate_slot(self):
        sid = self.start()
        for kwargs in ({'image_base64':'!'}, {'mime_type':'image/svg+xml'},
                       {'image_base64':base64.b64encode(b'not an image').decode()}, {'mime_type':'image/jpeg'}):
            self.code('invalid_frame', lambda: self.frame(sid, **kwargs))
        self.assertTrue(self.frame(sid))
    def test_pixel_and_byte_limits(self):
        sid = self.start()
        self.code('frame_too_large', lambda: self.frame(sid, image_base64=image_data(size=(1921,1))))
        self.code('frame_too_large', lambda: self.frame(sid, image_base64='A'*2_000_004))
    def test_animation_rejected(self):
        out = io.BytesIO()
        Image.new('RGB',(4,4),'red').save(out, format='PNG', save_all=True,
             append_images=[Image.new('RGB',(4,4),'blue')], duration=100)
        self.code('invalid_frame', lambda: self.frame(self.start(), image_base64=base64.b64encode(out.getvalue()).decode()))
    def test_invalid_prompt_and_identifiers(self):
        sid = self.start()
        self.code('invalid_request', lambda: self.frame(sid, request='../../x'))
        self.code('invalid_request', lambda: self.frame(sid, prompt='x'*501))
    def test_configuration_change_cancels_old_session(self):
        sid = self.start(); self.manager.configure(None)
        self.code('session_unavailable', lambda: self.frame(sid))
    def test_global_capacity_is_bounded(self):
        manager = PerceptionManager(self.provider, limits=PerceptionLimits(max_sessions=1))
        manager.start(self.scope,'screen',consent_confirmed=True)
        other=PerceptionScope('other','a','b',1)
        self.code('session_capacity', lambda: manager.start(other,'screen',consent_confirmed=True))
    def test_requests_cache_is_bounded(self):
        self.manager.limits=PerceptionLimits(max_requests_per_session=2)
        sid=self.start()
        for n in range(6):
            self.now[0]+=2; self.frame(sid, request='f'+str(n))
        self.assertEqual(len(self.manager._sessions[sid].requests),2)
    def test_stop_during_uncooperative_provider_discards_result(self):
        entered, release = threading.Event(), threading.Event()
        def action(cancel):
            entered.set(); release.wait(2); return 'must be discarded'
        self.manager.configure(SyntheticProvider(action=action))
        sid=self.start(); outcome=[]
        def worker():
            try: self.frame(sid)
            except PerceptionError as error: outcome.append(error.code)
        thread=threading.Thread(target=worker); thread.start()
        self.assertTrue(entered.wait(2))
        self.code('inflight', lambda: self.frame(sid, request='f2'))
        self.manager.stop('owner',sid); release.set(); thread.join(2)
        self.assertFalse(thread.is_alive()); self.assertEqual(outcome,['cancelled'])
        self.assertFalse(self.manager._busy)
    def test_epoch_change_during_provider_discards_result(self):
        self.manager.configure(SyntheticProvider(action=lambda cancel: self.current.__setitem__(0,
            PerceptionScope('owner','role-a','appearance-a',2)) or 'must be discarded'))
        self.code('scope_changed',lambda:self.frame(self.start()))
    def test_result_deadline(self):
        self.manager.configure(SyntheticProvider(action=lambda cancel: self.now.__setitem__(0,131) or 'too late'))
        self.code('frame_expired',lambda:self.frame(self.start()))
    def test_observation_is_server_created_and_bound_to_live_scope(self):
        sid=self.start();result=self.frame(sid)
        observation=self.manager.observation(self.scope,result['observation_id'])
        self.assertEqual(observation.scope,self.scope)
        self.assertEqual(observation.kind,'screen')
        self.assertEqual(len(observation.source_sha256),64)
        self.assertTrue(observation.evidence()['untrusted_context'])
        self.assertFalse(observation.evidence()['inference_verified'])
        self.assertNotIn('Synthetic',repr(observation))
        wrong=PerceptionScope('owner','role-a','appearance-a',2)
        self.code('observation_unavailable',lambda:self.manager.observation(wrong,result['observation_id']))
        self.assertIs(self.manager.observation(self.scope,result['observation_id']),observation)
        self.manager.stop('owner',sid)
        self.code('observation_unavailable',lambda:self.manager.observation(self.scope,result['observation_id']))
    def test_observation_expires_by_capture_age_and_is_bounded(self):
        self.manager.limits=PerceptionLimits(max_requests_per_session=2)
        sid=self.start();results=[]
        for n in range(3):
            self.now[0]+=2;results.append(self.frame(sid,request='f'+str(n)))
        self.code('observation_unavailable',lambda:self.manager.observation(self.scope,results[0]['observation_id']))
        self.wall[0]+=31
        self.code('observation_expired',lambda:self.manager.observation(self.scope,results[-1]['observation_id']))
    def test_observation_cannot_cross_owner_or_config_change(self):
        result=self.frame(self.start())
        other=PerceptionScope('other','role-a','appearance-a',1)
        self.code('observation_unavailable',lambda:self.manager.observation(other,result['observation_id']))
        self.manager.configure(None)
        self.code('observation_unavailable',lambda:self.manager.observation(self.scope,result['observation_id']))
    def test_provider_errors_redacted_and_slot_released(self):
        def fail(cancel): raise RuntimeError('SECRETKEY and PRIVATEIMAGE')
        self.manager.configure(SyntheticProvider(action=fail))
        error=self.code('provider_failed',lambda:self.frame(self.start()))
        self.assertNotIn('SECRET',str(error)); self.assertFalse(self.manager._busy)
    def test_limits_and_scope_types(self):
        for kwargs in ({'max_frame_bytes':True},{'max_sessions':1.5},{'min_interval_seconds':float('nan')},
                       {'max_inflight':2}):
            with self.assertRaises(ValueError): PerceptionLimits(**kwargs)
        with self.assertRaises(ValueError): PerceptionScope('owner','a','b',True)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store=VisionConfigStore(Path(self.temp.name)/'private')
    def test_disabled_default(self):
        self.assertIsNone(self.store.load().provider())
    def test_save_reload_key_omit_and_clear(self):
        config=self.store.save({'enabled':True,'base_url':'http://127.0.0.1:8080/v1','model':'image-model','api_key':'SECRET'})
        self.assertTrue(config.public()['has_api_key']); self.assertNotIn('SECRET',repr(config))
        self.assertNotIn('SECRET',json.dumps(config.public()))
        self.assertEqual(self.store.save({'model':'other'}).api_key,'SECRET')
        self.assertEqual(self.store.save({'api_key':''}).api_key,'')
        if os.name=='posix':
            self.assertEqual(self.store.path.stat().st_mode&0o777,0o600)
            self.assertEqual(self.store.root_path.stat().st_mode&0o777,0o700)
    def test_changed_endpoint_clears_old_key(self):
        self.store.save({'base_url':'https://first.example/v1','api_key':'SECRET'})
        changed=self.store.save({'base_url':'https://second.example/v1'})
        self.assertEqual(changed.api_key,'')
    def test_invalid_save_preserves_previous(self):
        self.store.save({'model':'original'})
        before=self.store.path.read_bytes()
        for payload in ({'enabled':'true'},{'enabled':True},{'api_key':'x\ny'},{'unknown':'x'}):
            with self.assertRaises(PerceptionError): self.store.save(payload)
            self.assertEqual(self.store.path.read_bytes(),before)
    def test_bad_saved_json_redacted(self):
        self.store.load(); self.store.path.write_text('SECRET-invalid')
        with self.assertRaises(PerceptionError) as caught:self.store.load()
        self.assertNotIn('SECRET',str(caught.exception))
    def test_oversize_and_nonregular_rejected(self):
        self.store.load(); self.store.path.write_bytes(b'x'*16385)
        with self.assertRaises(PerceptionError):self.store.load()
        self.store.path.unlink();self.store.path.mkdir()
        with self.assertRaises(PerceptionError):self.store.save({})
    @unittest.skipUnless(hasattr(os,'symlink'),'symlinks unavailable')
    def test_symlink_file_and_parent_rejected(self):
        target=Path(self.temp.name)/'target';target.write_text('private')
        self.store.load();self.store.path.symlink_to(target)
        with self.assertRaises(PerceptionError):self.store.load()
        with self.assertRaises(PerceptionError):self.store.save({})
        directory=Path(self.temp.name)/'linked';directory.symlink_to(self.store.root_path,target_is_directory=True)
        with self.assertRaises(PerceptionError):VisionConfigStore(directory/'nested').load()
        self.assertEqual(target.read_text(),'private')
    def test_atomic_replace_failure_preserves_previous_and_cleans_tmp(self):
        self.store.save({'model':'old'})
        with patch('companion_runtime.perception.os.replace',side_effect=OSError('secret path')):
            with self.assertRaises(PerceptionError) as caught:self.store.save({'model':'new'})
        self.assertNotIn('secret path',str(caught.exception))
        self.assertEqual(self.store.load().model,'old')
        self.assertEqual(list(self.store.root_path.glob('*.tmp')),[])


class ProviderTests(unittest.TestCase):
    def test_url_rules(self):
        for good,mode in [('http://localhost:8080/v1','local'),('http://[::1]:8080/v1','local'),
                          ('https://example.com/v1','remote')]:
            self.assertEqual(validate_vision_base(good)[1],mode)
        for bad in ('http://example.com','https://user:pass@example.com','https://x/?key=private',
                    'https://x/#private','http://169.254.169.254','https://metadata.google.internal',
                    'http://0.0.0.0:1','http://localhost:bad','https://[invalid','https://x/\nprivate'):
            with self.assertRaises(PerceptionError):validate_vision_base(bad)
    def test_credentials_never_in_repr_or_public_status(self):
        provider=OpenAICompatibleVisionProvider('https://example.com/v1','model','SECRET')
        self.assertNotIn('SECRET',repr(provider))
        self.assertNotIn('example.com',json.dumps(provider.status()))
        self.assertFalse(provider.status()['inference_verified'])
    def test_cancelled_before_network(self):
        cancel=threading.Event();cancel.set()
        provider=OpenAICompatibleVisionProvider('https://example.com/v1','model')
        with patch('urllib.request.build_opener',side_effect=AssertionError('must not call')):
            with self.assertRaises(PerceptionError) as caught:provider.describe(b'image','image/jpeg','',cancel)
        self.assertEqual(caught.exception.code,'cancelled')


if __name__=='__main__':unittest.main()
