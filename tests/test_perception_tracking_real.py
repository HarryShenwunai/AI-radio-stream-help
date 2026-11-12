"""Explicit real MediaPipe CPU evaluation; not part of dependency-free discovery.

Uses an official public portrait locally, never the user's camera or identity.
No sample image/frames/landmarks are copied into the public report.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import statistics
import threading
import time
from unittest.mock import patch
from PIL import Image
from companion_runtime.perception_tracking import MediaPipeFaceEngine,FACE_MODEL_SHA256


def encoded(image):
    output=io.BytesIO();image.convert('RGB').save(output,format='JPEG',quality=85);return output.getvalue()


def main():
    import resource
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-app-root',type=Path);parser.add_argument('--portaudio-library',type=Path)
    args=parser.parse_args();engine=MediaPipeFaceEngine(args.model)
    from companion_runtime.perception_optional import verify_tracking_addon
    if args.verify_app_root:assert verify_tracking_addon(args.verify_app_root).verified
    baseline=resource.getrusage(resource.RUSAGE_SELF)
    initialize_started=time.perf_counter()
    import cv2
    blocked_calls=[]
    def forbidden(*args,**kwargs):
        blocked_calls.append(True)
        raise RuntimeError('Forbidden OpenCV capture/codec API in face-only pipeline')
    for name in ('VideoCapture','VideoWriter','imread','imdecode'):
        setattr(cv2,name,forbidden)
    import ctypes.util
    import contextlib
    finder=ctypes.util.find_library
    override=patch('ctypes.util.find_library',side_effect=lambda name:str(args.portaudio_library) if name=='portaudio' else finder(name)) if args.portaudio_library else contextlib.nullcontext()
    with override:
        import sounddevice as sd
    blocked_audio_calls=[]
    def forbidden_audio(*args,**kwargs):
        blocked_audio_calls.append(True)
        raise RuntimeError('Forbidden Python audio stream in face-only pipeline')
    for name in ('InputStream','OutputStream','Stream','RawInputStream','RawOutputStream','RawStream','rec','play','playrec'):
        setattr(sd,name,forbidden_audio)
    engine.initialize()
    initialization_seconds=time.perf_counter()-initialize_started
    # An injected forbidden video path must be caught; no device is ever opened.
    with patch.object(engine._task,'detect',side_effect=lambda frame:cv2.VideoCapture('negative-control.invalid')):
        try:
            sample=Image.new('RGB',(2,2),'white');engine.estimate(encoded(sample),threading.Event())
            raise AssertionError('Negative control did not detect video API use')
        except Exception as error:
            assert getattr(error,'code',None)=='face_tracking_failed'
    assert len(blocked_calls)==1
    try:
        sd.InputStream()
        raise AssertionError('Audio negative control failed')
    except RuntimeError:pass
    assert len(blocked_audio_calls)==1
    blocked_audio_calls.clear()
    blocked_calls.clear()
    portrait=Image.open(args.image).convert('RGB');portrait.thumbnail((320,480))
    blank=Image.new('RGB',(640,480),'#606060')
    shifted=blank.copy();shifted.paste(portrait,(300,0))
    small=portrait.copy();small.thumbnail((300,360))
    pair=Image.new('RGB',(640,480),'#606060');pair.paste(small,(0,0));pair.paste(small,(340,0))
    cases=[('portrait',portrait,'face'),('blank_after_face',blank,'no_face'),
           ('portrait_after_blank',portrait,'face'),('shifted_right',shifted,'face'),('two_faces',pair,'multiple_faces')]
    checks=[];durations=[];cpu_start=time.process_time()
    try:
        for label,image,expected in cases:
            started=time.perf_counter();result=engine.estimate(encoded(image),threading.Event())
            elapsed=time.perf_counter()-started;durations.append(elapsed)
            assert result['state']==expected,(label,result)
            if expected!='face':assert result['face_center_direction'] is None and result['expressions']=={}
            checks.append({'case':label,'expected':expected,'passed':True,'elapsed_seconds':round(elapsed,5),'result':result})
        assert checks[3]['result']['face_center_direction']['x']>checks[0]['result']['face_center_direction']['x']+.25
        # Warm timing is direct algorithm timing, not the public 5Hz manager schedule.
        warm=[];data=encoded(portrait)
        for _ in range(20):
            started=time.perf_counter();engine.estimate(data,threading.Event());warm.append(time.perf_counter()-started)
        assert blocked_calls==[], 'A real face frame reached an OpenCV capture/codec API'
        assert blocked_audio_calls==[], 'A real face frame opened a Python audio stream'
        if args.verify_app_root:assert verify_tracking_addon(args.verify_app_root).verified
        report={'passed':True,'scope':'Real MediaPipe 1.2.3 CPU inference on one official portrait, blank and composed two-face images; not live camera or Windows',
                'model_sha256':FACE_MODEL_SHA256,'source_image_sha256':hashlib.sha256(args.image.read_bytes()).hexdigest(),
                'image_not_in_report':True,'addon_verified_after_real_initialization':bool(args.verify_app_root),'sounddevice_imported_but_no_stream_opened':True,'explicit_local_portaudio_library':bool(args.portaudio_library),'forbidden_python_audio_stream_calls':len(blocked_audio_calls),
                'injected_audio_stream_negative_control_detected':True,'forbidden_opencv_capture_codec_calls':len(blocked_calls),
                'injected_opencv_capture_negative_control_detected':True,'checks':checks,'warm_direct_inference_samples':len(warm),
                'warm_seconds_p50':round(statistics.median(warm),5),'warm_seconds_p95':round(sorted(warm)[18],5),
                'cpu_seconds':round(time.process_time()-cpu_start,4),'initialization_seconds':round(initialization_seconds,5),
                'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'baseline_peak_rss_kib':baseline.ru_maxrss,'hardware_camera_verified':False,'windows_execution_verified':False,
                'professional_eye_tracking_verified':False,'source_sha256':hashlib.sha256(Path('src/companion_runtime/perception_tracking.py').read_bytes()).hexdigest()}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
    finally:engine.close()


if __name__=='__main__':main()
