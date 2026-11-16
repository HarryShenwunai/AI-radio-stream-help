"""Default asset seeding, choice preservation and actual selected-voice routing."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import builtins
import io
import os
import types
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import wave
import test_character_http
from test_live2d_assets import archive, files
from companion_runtime.characters import CharacterStore
from companion_runtime.assets import AssetStore

class DefaultCharacterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.package=self.root/'default.zip';self.package.write_bytes(archive(files(True)));self.store=CharacterStore(self.root/'data');self.store.bootstrap()
 def test_default_is_enabled_once_and_survives_reopen(self):
  a=self.store.seed_default_live2d(self.package);self.assertIsNotNone(a['avatar_revision']);reopened=CharacterStore(self.root/'data');self.assertEqual(reopened.seed_default_live2d(self.package)['avatar_revision'],a['avatar_revision'])
  self.assertEqual(len(AssetStore(self.store.db_path(a['id']).parent/'assets').list_assets()),1)
 def test_existing_appearance_is_preserved(self):
  active=self.store.active();custom=str(uuid4());self.store.set_appearance(active['id'],custom);self.assertEqual(self.store.seed_default_live2d(self.package)['avatar_revision'],custom)
 def test_user_restore_to_empty_is_not_undone_on_restart(self):
  a=self.store.seed_default_live2d(self.package);self.store.set_appearance(a['id'],None);self.assertIsNone(CharacterStore(self.root/'data').seed_default_live2d(self.package)['avatar_revision'])
 def test_bad_archive_does_not_poison_retry(self):
  good=self.package.read_bytes();self.package.write_bytes(b'bad');
  with self.assertRaises(ValueError):self.store.seed_default_live2d(self.package)
  self.assertIsNone(self.store.active()['avatar_revision']);self.package.write_bytes(good);self.assertIsNotNone(self.store.seed_default_live2d(self.package)['avatar_revision'])
 def test_parallel_first_runs_create_one_default_asset(self):
  def run(_):return CharacterStore(self.root/'data').seed_default_live2d(self.package)['avatar_revision']
  with ThreadPoolExecutor(max_workers=3) as pool:ids=list(pool.map(run,range(3)))
  self.assertEqual(len(set(ids)),1)

class VoiceSelectionTests(unittest.TestCase):
 def setUp(self):
  self.f=test_character_http.CharacterHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown)
 def test_selection_persists_and_invalid_voice_cannot_replace_it(self):
  self.f.post('settings',{'local_voice':'zf_xiaoyi','voice_rate':1.06,'expected_character_id':self.f.initial_id});self.assertEqual(self.f.state()['settings']['local_voice'],'zf_xiaoyi')
  self.f.post('settings',{'local_voice':'invented_voice','expected_character_id':self.f.initial_id},expected=400);self.assertEqual(self.f.state()['settings']['local_voice'],'zf_xiaoyi')
 def test_voice_is_per_character_and_does_not_change_runtime_schema(self):
  f=self.f;f.post('settings',{'local_voice':'zf_xiaoyi','expected_character_id':f.initial_id});self.assertFalse((Path(f.tmp.name)/'runtime.json').exists())
  new=f.create('第二位角色');self.assertEqual(f.state()['settings']['local_voice'],'zf_xiaobei')
  f.select(f.initial_id);self.assertEqual(f.state()['settings']['local_voice'],'zf_xiaoyi')
 def test_synthesis_receives_selected_voice_and_returns_pcm(self):
  import numpy as np
  f=self.f;f.post('settings',{'local_voice':'zf_xiaoxiao','voice_rate':1.03,'expected_character_id':f.initial_id});folder=Path(f.tmp.name)/'voices';folder.mkdir();(folder/'kokoro-v1.0.onnx').touch();(folder/'voices-v1.0.bin').touch();f.app.VOICE_DIR=folder
  calls=[]
  class Engine:
   def create(self,*args,**kw):calls.append(kw);return np.zeros(2400),24000
  f.app.LOCAL_VOICE=Engine();f.app.G2P=lambda text:(text,None);f.app.LOCAL_VOICE_IDENTITY=f.app._local_voice_identity(folder/'kokoro-v1.0.onnx',folder/'voices-v1.0.bin');lookup=f.app.importlib.util.find_spec
  with patch.object(f.app.importlib.util,'find_spec',side_effect=lambda name:object() if name=='kokoro_onnx' else lookup(name)):
   pcm=f.real_synthesize('欢迎回来。')
  self.assertEqual(calls[0]['voice'],'zf_xiaoxiao');self.assertEqual(calls[0]['speed'],1.03)
  with wave.open(io.BytesIO(pcm)) as wav:self.assertEqual(wav.getnframes(),2400);self.assertEqual(wav.getsampwidth(),2)
 def test_kokoro_opt_out_precedes_native_import_even_when_environment_is_zero(self):
  import numpy as np
  f=self.f;folder=Path(f.tmp.name)/'voices';folder.mkdir();(folder/'kokoro-v1.0.onnx').touch();(folder/'voices-v1.0.bin').touch();f.app.VOICE_DIR=folder
  events=[];original_import=builtins.__import__;lookup=f.app.importlib.util.find_spec
  class Engine:
   def __init__(self,*args):events.append(('kokoro',os.environ.get('ORT_DISABLE_TELEMETRY')))
   def create(self,*args,**kw):return np.zeros(2400),24000
  def guarded_import(name,*args,**kwargs):
   if name=='onnxruntime':
    events.append(('import',os.environ.get('ORT_DISABLE_TELEMETRY')))
    return types.SimpleNamespace(disable_telemetry_events=lambda:events.append(('disable',os.environ.get('ORT_DISABLE_TELEMETRY'))))
   if name=='kokoro_onnx':return types.SimpleNamespace(Kokoro=Engine)
   if name=='misaki':return types.SimpleNamespace(zh=types.SimpleNamespace(ZHG2P=lambda:lambda text:(text,None)))
   return original_import(name,*args,**kwargs)
  for value in ('0',None):
   with self.subTest(initial=value),patch.dict(os.environ,{},clear=False):
    if value is None:os.environ.pop('ORT_DISABLE_TELEMETRY',None)
    else:os.environ['ORT_DISABLE_TELEMETRY']=value
    events.clear();f.app.LOCAL_VOICE=None;f.app.G2P=None
    with patch.object(f.app.importlib.util,'find_spec',side_effect=lambda name:object() if name=='kokoro_onnx' else lookup(name)),patch('builtins.__import__',side_effect=guarded_import):
     pcm=f.real_synthesize('欢迎回来。')
    self.assertEqual(events,[('import','1'),('disable','1'),('kokoro','1')]);self.assertTrue(pcm.startswith(b'RIFF'))
 @contextmanager
 def fake_initializer(self,fail_g2p=None,mutate_during_init=None):
  f=self.f;folder=Path(f.tmp.name)/'initializer-voices';folder.mkdir(exist_ok=True);(folder/'kokoro-v1.0.onnx').write_bytes(b'fake onnx');(folder/'voices-v1.0.bin').write_bytes(b'fake voices');f.app.VOICE_DIR=folder;events=[];original=builtins.__import__;lookup=f.app.importlib.util.find_spec
  class Session:
   def run(self,*args,**kwargs):
    events.append(('run',));import numpy as np
    return np.zeros(2400)
  class Engine:
   def __init__(self,*args):events.append(('construct',f.app.TTS_LOCK.locked()));self.sess=Session()
   def create(self,*args,**kwargs):events.append(('create',kwargs));return self.sess.run(),24000
  class G2P:
   def __init__(self):
    events.append(('g2p_construct',f.app.TTS_LOCK.locked()))
    if fail_g2p and fail_g2p.pop(0):raise RuntimeError('injected G2P construction failure')
    if mutate_during_init and mutate_during_init.pop(0):(folder/'voices-v1.0.bin').write_bytes(b'changed during constructor')
   def __call__(self,text):events.append(('text',text));return text,None
  def importing(name,*args,**kwargs):
   if name=='onnxruntime':events.append(('ort_import',os.environ.get('ORT_DISABLE_TELEMETRY')));return types.SimpleNamespace(disable_telemetry_events=lambda:events.append(('disable',)))
   if name=='kokoro_onnx':return types.SimpleNamespace(Kokoro=Engine)
   if name=='misaki':return types.SimpleNamespace(zh=types.SimpleNamespace(ZHG2P=G2P))
   return original(name,*args,**kwargs)
  with patch.object(f.app.importlib.util,'find_spec',side_effect=lambda name:object() if name=='kokoro_onnx' else lookup(name)),patch('builtins.__import__',side_effect=importing):yield events
 def test_explicit_initialization_constructs_once_without_text_audio_or_inference_and_lazy_synthesis_reuses(self):
  f=self.f;self.assertIsNone(f.app.LOCAL_VOICE);self.assertIsNone(f.app.G2P)
  with self.fake_initializer() as events,patch.dict(os.environ,{'ORT_DISABLE_TELEMETRY':'0'}):
   first=f.app.initialize_local_voice();second=f.app.initialize_local_voice()
   self.assertEqual(first,{'initialized':True,'reused':False});self.assertEqual(second,{'initialized':True,'reused':True});self.assertEqual(events.count(('construct',True)),1);self.assertEqual(events.count(('g2p_construct',True)),1);self.assertIn(('ort_import','1'),events);self.assertFalse(any(x[0] in ('run','create','text') for x in events));self.assertFalse(f.app.TTS_LOCK.locked())
   pcm=f.real_synthesize('欢迎回来。');self.assertTrue(pcm.startswith(b'RIFF'));self.assertEqual(events.count(('construct',True)),1);self.assertEqual(sum(x[0]=='create' for x in events),1);self.assertEqual(sum(x[0]=='run' for x in events),1)
 def test_initialization_partial_failure_is_not_published_and_retry_recovers(self):
  f=self.f
  with self.fake_initializer(fail_g2p=[True,False]) as events:
   with self.assertRaises(f.app.AppError):f.app.initialize_local_voice()
   self.assertIsNone(f.app.LOCAL_VOICE);self.assertIsNone(f.app.G2P);self.assertFalse(f.app.TTS_LOCK.locked())
   self.assertEqual(f.app.initialize_local_voice(),{'initialized':True,'reused':False});self.assertEqual(events.count(('construct',True)),2);self.assertFalse(f.app.TTS_LOCK.locked());self.assertFalse(any(x[0] in ('run','create','text') for x in events))
 def test_same_path_replacement_rebuilds_and_midinit_change_does_not_publish_new_identity(self):
  f=self.f
  with self.fake_initializer(mutate_during_init=[False,True,False]) as events:
   f.app.initialize_local_voice();old_voice=f.app.LOCAL_VOICE;old_identity=f.app.LOCAL_VOICE_IDENTITY
   (f.app.VOICE_DIR/'voices-v1.0.bin').write_bytes(b'replacement at same file path')
   with self.assertRaises(f.app.AppError):f.app.initialize_local_voice()
   self.assertIs(f.app.LOCAL_VOICE,old_voice);self.assertEqual(f.app.LOCAL_VOICE_IDENTITY,old_identity);self.assertNotEqual(f.app._local_voice_identity(f.app.VOICE_DIR/'kokoro-v1.0.onnx',f.app.VOICE_DIR/'voices-v1.0.bin'),old_identity);self.assertFalse(f.app.TTS_LOCK.locked())
   self.assertEqual(f.app.initialize_local_voice(),{'initialized':True,'reused':False});self.assertIsNot(f.app.LOCAL_VOICE,old_voice);self.assertNotEqual(f.app.LOCAL_VOICE_IDENTITY,old_identity);self.assertEqual(events.count(('construct',True)),3);self.assertFalse(any(x[0] in ('run','create','text') for x in events));self.assertEqual(f.app.initialize_local_voice(),{'initialized':True,'reused':True})
 def test_explicit_init_rejects_other_backends_missing_weights_and_busy_lock_without_external_request(self):
  f=self.f;settings=f.app.settings()
  for backend in ('external','system'):
   with self.subTest(backend=backend),patch.object(f.app,'settings',return_value={**settings,'voice_backend':backend}),patch.object(f.app,'ExternalTTS',side_effect=AssertionError('No external API during initialization')):
    with self.assertRaises(f.app.AppError):f.app.initialize_local_voice()
  with self.fake_initializer() as events:
   f.app.TTS_LOCK.acquire()
   try:
    with self.assertRaises(f.app.AppError):f.app.initialize_local_voice()
    self.assertTrue(f.app.TTS_LOCK.locked());self.assertEqual(events,[])
   finally:f.app.TTS_LOCK.release()
   f.app.initialize_local_voice();(f.app.VOICE_DIR/'voices-v1.0.bin').unlink()
   with self.assertRaises(f.app.AppError):f.app.initialize_local_voice()
   self.assertFalse(f.app.TTS_LOCK.locked());self.assertEqual(events.count(('construct',True)),1)
 def test_locked_snapshot_keeps_prepared_provider_refs_when_cache_is_replaced_later(self):
  f=self.f
  with self.fake_initializer():
   first=f.app.initialize_local_voice(with_resources=True)
   self.assertIs(first.voice,f.app.LOCAL_VOICE);self.assertIs(first.g2p,f.app.G2P);self.assertEqual(first.identity,f.app.LOCAL_VOICE_IDENTITY)
   (f.app.VOICE_DIR/'voices-v1.0.bin').write_bytes(b'replaced for next initialization')
   second=f.app.initialize_local_voice(with_resources=True)
   self.assertIsNot(first.voice,second.voice);self.assertIsNot(first.g2p,second.g2p);self.assertNotEqual(first.identity,second.identity)
   self.assertIs(second.voice,f.app.LOCAL_VOICE);self.assertFalse(f.app.TTS_LOCK.locked())
 def test_room_endpoint_excludes_private_history_and_keys(self):
  self.f.post('memories',{'text':'ROOM_PRIVATE_CANARY','expected_character_id':self.f.initial_id});status,_,body=self.f.request('GET','/api/room');self.assertEqual(status,200);self.assertNotIn(b'ROOM_PRIVATE_CANARY',body);self.assertNotIn(b'api_key',body)
