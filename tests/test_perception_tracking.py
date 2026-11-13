"""Synthetic boundary tests, separate from real MediaPipe evaluation evidence."""
import base64
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from companion_runtime.perception import PerceptionError,PerceptionScope
from companion_runtime.perception_tracking import (FaceModelStore,FaceTrackingManager,MediaPipeFaceEngine,
    project_face_result,read_face_model)


class SyntheticEngine:
    def __init__(self,action=None):self.action=action;self.initialized=False
    def status(self):return {'available':True,'configured':True,'processing':'local','provider':'explicit-synthetic-fixture'}
    def initialize(self):self.initialized=True
    def estimate(self,image,cancel):
        return self.action(cancel) if self.action else {'state':'no_face','face_center_direction':None,
            'head_pose_degrees':None,'expressions':{}}
    def close(self):self.initialized=False


def encoded():
    out=io.BytesIO();Image.new('RGB',(32,24),'white').save(out,format='PNG')
    return base64.b64encode(out.getvalue()).decode()


class TrackingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope=PerceptionScope('owner','role','appearance',1)
        self.current=self.scope
        self.engine=SyntheticEngine()
        self.manager=FaceTrackingManager('/unused',engine=self.engine,is_scope_current=lambda s:s==self.current)
    def start(self):return self.manager.start(self.scope,consent_confirmed=True)['session_id']
    def frame(self,sid,**kw):
        payload={'session_id':sid,'request_id':'frame1','image_base64':encoded(),'mime_type':'image/png',
                 'captured_at_ms':int(time.time()*1000)};payload.update(kw)
        return self.manager.frame(self.scope,**payload)
    def test_tracking_has_separate_status_and_camera_session(self):
        status=self.manager.status('owner')
        self.assertNotIn('vision',status);self.assertTrue(status['tracking']['available'])
        self.assertFalse(self.engine.initialized)
        sid=self.start();self.assertTrue(self.engine.initialized)
        self.assertEqual(self.manager.status('owner')['sessions'][0]['kind'],'camera')
        response=self.frame(sid)
        self.assertEqual(response['tracking']['state'],'no_face')
        self.assertNotIn('observation_id',response)
        self.assertFalse(response['retained'])
    def test_no_consent_never_initializes_engine(self):
        with self.assertRaises(PerceptionError) as caught:self.manager.start(self.scope,consent_confirmed=False)
        self.assertEqual(caught.exception.code,'consent_required');self.assertFalse(self.engine.initialized)
    def test_stale_scope_never_initializes_engine(self):
        self.current=PerceptionScope('owner','role','appearance',2)
        with self.assertRaises(PerceptionError) as caught:self.start()
        self.assertEqual(caught.exception.code,'scope_changed');self.assertFalse(self.engine.initialized)
    def test_face_frame_limits_are_small(self):
        status=self.manager.status('owner');limits=status['limits']
        self.assertEqual(limits['max_edge'],640);self.assertEqual(limits['max_pixels'],307200)
        self.assertEqual(limits['max_frame_bytes'],250000);self.assertEqual(limits['min_interval_seconds'],0.2)
    def test_stop_cancels_tracking_and_no_identity_is_retained(self):
        sid=self.start();self.manager.stop('owner',sid)
        with self.assertRaises(PerceptionError) as caught:self.frame(sid)
        self.assertEqual(caught.exception.code,'cancelled')
        self.assertEqual(self.manager.status('owner')['sessions'],[])
    def test_role_epoch_aba_invalidates(self):
        sid=self.start();self.current=PerceptionScope('owner','role','appearance',3)
        with self.assertRaises(PerceptionError) as caught:self.frame(sid)
        self.assertEqual(caught.exception.code,'scope_changed')
    def test_late_estimate_after_stop_is_discarded(self):
        entered,release=threading.Event(),threading.Event()
        def action(cancel):entered.set();release.wait(2);return {'state':'face','expressions':{}}
        self.engine.action=action;sid=self.start();results=[]
        def worker():
            try:self.frame(sid)
            except PerceptionError as error:results.append(error.code)
        thread=threading.Thread(target=worker);thread.start();self.assertTrue(entered.wait(2))
        self.manager.stop('owner',sid);release.set();thread.join(2)
        self.assertEqual(results,['cancelled']);self.assertFalse(thread.is_alive())
    def test_close_invalidates_existing_sessions(self):
        sid=self.start();self.manager.close()
        with self.assertRaises(PerceptionError):self.frame(sid)
        self.assertFalse(self.engine.initialized)


class ProjectionTests(unittest.TestCase):
    def result(self,faces=1,score=0.7):
        point=lambda x,y:SimpleNamespace(x=x,y=y)
        return SimpleNamespace(face_landmarks=[[point(.4,.3),point(.6,.3),point(.5,.7)]]*faces,
            face_blendshapes=[[SimpleNamespace(category_name='eyeBlinkLeft',score=score),
                SimpleNamespace(category_name='mouthSmileLeft',score=.8),
                SimpleNamespace(category_name='mouthSmileRight',score=.6)]],facial_transformation_matrixes=[])
    def test_no_face_and_multiple_faces_clear_direction(self):
        for n,state in [(0,'no_face'),(2,'multiple_faces')]:
            response=project_face_result(self.result(n))
            self.assertEqual(response['state'],state);self.assertIsNone(response['face_center_direction'])
            self.assertEqual(response['expressions'],{})
    def test_face_estimate_bounded_no_identity_or_confidence_invention(self):
        response=project_face_result(self.result())
        self.assertEqual(response['face_center_direction'],{'x':0.0,'y':0.0})
        self.assertEqual(response['expressions']['blink_left'],.7)
        self.assertEqual(response['expressions']['smile'],.7)
        self.assertFalse(response['identity_recognition']);self.assertNotIn('confidence',response)
        self.assertNotIn('face_landmarks',response)
    def test_known_camera_rotation_projects_yaw_without_identity(self):
        class Matrix:
            shape=(4,4)
            values=((0.866025403784,0,.5,0),(0,1,0,0),(-.5,0,0.866025403784,0),(0,0,0,1))
            def __getitem__(self,key):return self.values[key[0]][key[1]]
        result=self.result();result.facial_transformation_matrixes=[Matrix()]
        pose=project_face_result(result)['head_pose_degrees']
        self.assertAlmostEqual(pose['yaw'],30,places=2)
        self.assertAlmostEqual(pose['pitch'],0,places=2)
        self.assertAlmostEqual(pose['roll'],0,places=2)
    def test_bad_numbers_rejected_not_nan_json(self):
        for score in [float('nan'),float('inf'),True]:
            with self.assertRaises(PerceptionError):project_face_result(self.result(score=score))
    def test_scores_clamp_to_usable_range(self):
        response=project_face_result(self.result(score=2))
        self.assertEqual(response['expressions']['blink_left'],1.0)


class ModelFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_model_missing_invalid_size_and_wrong_sha(self):
        file=self.root/'model.task'
        with self.assertRaises(PerceptionError) as caught:read_face_model(file)
        self.assertEqual(caught.exception.code,'face_model_missing')
        file.write_bytes(b'not a model')
        with self.assertRaises(PerceptionError) as caught:read_face_model(file)
        self.assertEqual(caught.exception.code,'face_model_invalid')
        with patch('companion_runtime.perception_tracking.FACE_MODEL_BYTES',len(b'not a model')):
            with self.assertRaises(PerceptionError):read_face_model(file)
    def test_symlink_file_and_parent_rejected(self):
        original=self.root/'real';original.write_bytes(b'not model')
        linked=self.root/'linked';linked.symlink_to(original)
        with self.assertRaises(PerceptionError):read_face_model(linked)
        directory=self.root/'directory';directory.mkdir();linkdir=self.root/'linkdir';linkdir.symlink_to(directory,target_is_directory=True)
        with self.assertRaises(PerceptionError):read_face_model(linkdir/'x')
    def test_install_requires_true_and_never_network_on_store_creation(self):
        with patch('urllib.request.build_opener',side_effect=AssertionError('network not authorized')):
            store=FaceModelStore(self.root/'new')
            self.assertFalse(store.root_path.exists())
            for value in [False,1,None]:
                with self.assertRaises(PerceptionError):store.install_official(consent_confirmed=value)
    def test_bounded_installer_sha_and_atomic_write_with_explicit_stub(self):
        data=b'explicit synthetic model fixture'
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return data[:limit]
        store=FaceModelStore(self.root/'store')
        with patch('companion_runtime.perception_tracking.FACE_MODEL_BYTES',len(data)),patch(
                'companion_runtime.perception_tracking.FACE_MODEL_SHA256',hashlib.sha256(data).hexdigest()):
            with patch('urllib.request.OpenerDirector.open',return_value=Response()) as request:
                self.assertTrue(store.install_official(consent_confirmed=True)['installed'])
                self.assertEqual(store.model_path.read_bytes(),data)
                self.assertEqual(request.call_count,1)
                store.install_official(consent_confirmed=True)
                self.assertEqual(request.call_count,1)
    def test_download_checksum_failure_leaves_no_model_or_partial(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'bad'
        store=FaceModelStore(self.root/'store')
        with patch('urllib.request.OpenerDirector.open',return_value=Response()):
            with self.assertRaises(PerceptionError) as caught:store.install_official(consent_confirmed=True)
        self.assertEqual(caught.exception.code,'face_model_download_failed')
        self.assertFalse(store.model_path.exists());self.assertEqual(list(store.root_path.iterdir()),[])
    def test_status_does_not_import_or_initialize_optional_algorithm(self):
        engine=MediaPipeFaceEngine(self.root/'missing.task')
        with patch('importlib.import_module',side_effect=AssertionError('must not import')):
            status=engine.status()
        self.assertFalse(status['algorithm_loaded']);self.assertFalse(status['professional_eye_tracking'])
    def test_missing_dependency_cannot_claim_ready(self):
        engine=MediaPipeFaceEngine(self.root/'missing.task')
        import importlib.metadata
        with patch('importlib.metadata.version',side_effect=importlib.metadata.PackageNotFoundError):
            self.assertEqual(engine.status()['reason'],'face_dependency_missing')
            with self.assertRaises(PerceptionError) as caught:engine.initialize()
            self.assertEqual(caught.exception.code,'face_tracking_unavailable')
    def test_cancel_before_algorithm_import(self):
        engine=MediaPipeFaceEngine(self.root/'missing.task');cancel=threading.Event();cancel.set()
        with patch('importlib.import_module',side_effect=AssertionError('must not import')):
            with self.assertRaises(PerceptionError) as caught:engine.estimate(b'image',cancel)
        self.assertEqual(caught.exception.code,'cancelled')


if __name__=='__main__':unittest.main()
