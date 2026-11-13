"""Explicit real CPU ASR on locally synthesized Chinese; never records a mic.

Run with the optional voice/TTS dependencies and existing licensed Kokoro assets.
Writes synthetic evidence outside application data, not a human quality verdict.
"""
from pathlib import Path
from dataclasses import asdict
import io
import json
import os
import resource
import time
import wave
import numpy as np
from kokoro_onnx import Kokoro
from misaki import zh
from companion_runtime.voice import LocalASR, VoiceError

root=Path(__file__).resolve().parents[1]
voices=Path(os.environ.get('COMPANION_VOICES','/workspace/companion/voices'))
model=Path(os.environ.get('COMPANION_ASR_MODELS','/workspace/asr-models/faster-whisper-tiny'))
source='你好，今天我们一起学习。'
voice=Kokoro(str(voices/'kokoro-v1.0.onnx'),str(voices/'voices-v1.0.bin'))
phonemes,_=zh.ZHG2P()(source)
samples,rate=voice.create(phonemes,voice='zf_xiaobei',speed=1.0,is_phonemes=True)
out=io.BytesIO()
with wave.open(out,'wb') as wav:
 wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
 wav.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
audio=out.getvalue()
Path('/workspace/research/asr-smoke.wav').write_bytes(audio)
asr=LocalASR(model)
started=time.monotonic();result=asr.transcribe_wav(audio);elapsed=time.monotonic()-started
silence=io.BytesIO()
with wave.open(silence,'wb') as wav:
 wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0'*32000)
try:
 asr.transcribe_wav(silence.getvalue());silence_result='unexpected transcript'
except VoiceError as error:silence_result=error.code
record={'date':'2026-11-12','scope':'real CPU faster-whisper tiny; input is local Kokoro synthetic speech, no microphone or cloud recognition',
        'source_text':source,'transcription':asdict(result),'wall_seconds_including_load':round(elapsed,3),
        'wav_bytes':len(audio),'silence_result':silence_result,'rss_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'model':json.loads((model/'source.json').read_text()),'human_audio_or_naturalness_accepted':False,
        'windows_or_rtx4060_tested':False,'passed':bool(result.text and silence_result=='no_speech')}
(root/'review/voice-real-smoke.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2))
assert record['passed']
