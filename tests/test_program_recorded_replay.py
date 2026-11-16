"""Recorded-media integrity/CLI counterexamples; no Core, browser or inference."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from program_output_browser import load_recorded_replay, tone, validate_recorded_prompt, validate_recorded_replay_options


class ProgramRecordedReplayTests(unittest.TestCase):
    def options(self, **changes):
        return SimpleNamespace(**({'replay_result': Path('source.json'), 'replay_wav': Path('source.wav'),
                                  'real_model': None, 'real_tts': None, 'expect_expiry': False,
                                  'expect_budget_rejection': False, 'offline_preflight': False,
                                  'input': Path('original.txt'), 'completion': True, 'require_visible_mouth': True} | changes))

    def fixture(self, root):
        question='原来的观众问题';raw=question+'\n';reply='这是原来实际记录的回答。'
        current={'text':question,'source_text':raw,'source_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                 'delivered_text_sha256':hashlib.sha256(question.encode()).hexdigest()}
        messages=[{'role':'system','content':'原始公开规则'}, {'role':'user','content':question}]
        audio=tone(.1);wav=Path(root)/'source.wav';wav.write_bytes(audio)
        source={'real_model':True,'real_tts':True,'passed':False,'acceptance_kind':'positive_program','failure':'original expiry',
                'raw_input':copy.deepcopy(current),'model_inputs':[messages],
                'model_outputs':[{'text':reply,'finish_reason':'stop','warm_inference_seconds':26.5}],
                'tts_outputs':[{'text':reply,'sha256':hashlib.sha256(audio).hexdigest(),'seconds':9.5}]}
        result=Path(root)/'source.json';result.write_text(json.dumps(source,ensure_ascii=False))
        return result,wav,current,source

    def test_valid_pair_preserves_original_failure_reply_prompt_and_real_wav_duration(self):
        with tempfile.TemporaryDirectory() as root:
            result,wav,current,source=self.fixture(root);original=result.read_bytes()
            replay=load_recorded_replay(result,wav,current)
            self.assertEqual(replay['reply'],source['model_outputs'][0]['text'])
            self.assertNotEqual(replay['reply'],current['text'])
            self.assertEqual(replay['wav'],wav.read_bytes())
            self.assertAlmostEqual(replay['provenance']['wav_duration_seconds'],.1)
            self.assertFalse(replay['provenance']['source_original_passed'])
            self.assertEqual(replay['provenance']['original_model_output']['warm_inference_seconds'],26.5)
            self.assertEqual(replay['provenance']['original_tts_output']['seconds'],9.5)
            self.assertEqual(replay['provenance']['source_result_sha256'],hashlib.sha256(original).hexdigest())
            validate_recorded_prompt(replay,source['model_inputs'][0])
            self.assertEqual(result.read_bytes(),original)

    def test_wrong_wav_and_self_consistent_but_truncated_wav_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            result,wav,current,source=self.fixture(root)
            data=wav.read_bytes();wav.write_bytes(data[:-1]+bytes([data[-1]^1]))
            with self.assertRaisesRegex(ValueError,'SHA'):load_recorded_replay(result,wav,current)
            wav.write_bytes(data[:-2]);source['tts_outputs'][0]['sha256']=hashlib.sha256(wav.read_bytes()).hexdigest();result.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError,'complete'):load_recorded_replay(result,wav,current)

    def test_mismatched_text_and_incomplete_model_response_are_rejected(self):
        for field,value in [('text','另一条回答'),('finish_reason','length')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                result,wav,current,source=self.fixture(root);source['model_outputs'][0][field]=value;result.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError,'text pair'):load_recorded_replay(result,wav,current)

    def test_wrong_question_answer_as_question_and_changed_full_prompt_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            result,wav,current,source=self.fixture(root);replay=load_recorded_replay(result,wav,current)
            for text in ['另一条问题',replay['reply']]:
                changed={'text':text,'source_text':text+'\n','source_sha256':hashlib.sha256((text+'\n').encode()).hexdigest(),
                         'delivered_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
                with self.subTest(text=text), self.assertRaisesRegex(ValueError,'question/input'):load_recorded_replay(result,wav,changed)
            messages=copy.deepcopy(source['model_inputs'][0]);messages[0]['content']='不同的系统规则'
            with self.assertRaisesRegex(ValueError,'full prompt'):validate_recorded_prompt(replay,messages)

    def test_source_must_be_one_failed_real_provider_record(self):
        for field,value in [('passed',True),('real_model',False),('real_tts',False),('acceptance_kind','recorded_real_media_replay')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                result,wav,current,source=self.fixture(root);source[field]=value;result.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError,'failed single real-model'):load_recorded_replay(result,wav,current)

    def test_cli_flags_cannot_mix_providers_negative_modes_or_missing_pair(self):
        validate_recorded_replay_options(self.options())
        validate_recorded_replay_options(self.options(replay_result=None,replay_wav=None))
        for changes in [{'replay_wav':None},{'real_model':Path('model')},{'real_tts':Path('voice')},{'expect_expiry':True},
                        {'expect_budget_rejection':True},{'offline_preflight':True},{'input':None},{'completion':False},{'require_visible_mouth':False}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):validate_recorded_replay_options(self.options(**changes))
        with tempfile.TemporaryDirectory() as root:
            command=[sys.executable,str(Path(__file__).with_name('program_output_browser.py')),'--chrome','unused','--model','missing.zip',
                     '--runtime-dir','missing-runtime','--out',str(Path(root)/'out'),'--replay-result','missing.json','--replay-wav','missing.wav',
                     '--input','missing.txt','--real-model','missing-model','--completion','--require-visible-mouth']
            result=subprocess.run(command,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertIn('cannot combine real providers',result.stderr)
            self.assertNotIn('FileNotFoundError',result.stderr)


if __name__=='__main__':
    unittest.main()
