"""Default asset seeding, choice preservation and actual selected-voice routing."""
from concurrent.futures import ThreadPoolExecutor
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
  f.app.LOCAL_VOICE=Engine();f.app.G2P=lambda text:(text,None);lookup=f.app.importlib.util.find_spec
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
 def test_room_endpoint_excludes_private_history_and_keys(self):
  self.f.post('memories',{'text':'ROOM_PRIVATE_CANARY','expected_character_id':self.f.initial_id});status,_,body=self.f.request('GET','/api/room');self.assertEqual(status,200);self.assertNotIn(b'ROOM_PRIVATE_CANARY',body);self.assertNotIn(b'api_key',body)
