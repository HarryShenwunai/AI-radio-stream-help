"""No actual model. System-only prep and independent unseen stream-token guards."""
import hashlib
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_runtime.public_prefix import PublicSystemPrefix, PrefixNotReady, PrefixUnsupported

TEMPLATE='mechanical Qwen-shaped formatter fixture, never real model qualification'


class Formatter:
    calls=[]
    def __init__(self,*,add_generation_prompt,**kwargs):self.add_generation_prompt=add_generation_prompt
    def __call__(self,*,messages):
        self.calls.append((self.add_generation_prompt,[dict(m) for m in messages]))
        result=''.join('<|im_start|>'+m['role']+'\n'+m['content']+'<|im_end|>\n' for m in messages)
        if self.add_generation_prompt:result+='<|im_start|>assistant\n'
        return SimpleNamespace(prompt=result,added_special=True)


class FakeModel:
    def __init__(self):
        self.metadata={'tokenizer.chat_template':TEMPLATE,'tokenizer.ggml.add_bos_token':'false','tokenizer.ggml.bos_token_id':'151643','tokenizer.ggml.eos_token_id':'151645'}
        self.chat_format='chat_template.default';self.chat_handler=None;self.n_tokens=0;self.evals=[];self.completions=[];self.try_sample=False
    def tokenize(self,data,*,add_bos,special):
        assert add_bos is False and special is True
        result=[]
        for part in re.split(r'(<\|im_start\|>|<\|im_end\|>)',data.decode()):result.extend([{'<|im_start|>':151644,'<|im_end|>':151645}[part]] if part in ('<|im_start|>','<|im_end|>') else list(part.encode()))
        return result
    def reset(self):self.n_tokens=0
    def eval(self,tokens):
        self.evals.append(list(tokens));self.n_tokens+=len(tokens)
        if self.try_sample:self.sample()
    def sample(self,*args,**kwargs):raise AssertionError('not used by mechanical generator')
    def create_chat_completion(self,*,messages,**kwargs):
        formatted=Formatter(add_generation_prompt=True)(messages=messages)
        return self.create_completion(prompt=self.tokenize(formatted.prompt.encode(),add_bos=False,special=True),**kwargs)
    def create_completion(self,**kwargs):
        self.completions.append(kwargs);self.n_tokens=len(kwargs['prompt'])+1
        def stream():
            yield {'choices':[{'delta':{'content':'mechanical-delta'},'finish_reason':None}]}
            yield {'choices':[{'delta':{},'finish_reason':'stop'}]}
        return stream()


class GenericPublicPrefixTests(unittest.TestCase):
    def setUp(self):
        self.model=FakeModel();self.current=True;Formatter.calls=[]
        self.patch=patch('companion_runtime.public_prefix.QWEN_TEMPLATE_SHA256',hashlib.sha256(TEMPLATE.encode()).hexdigest());self.patch.start();self.addCleanup(self.patch.stop)
    def prepare(self):return PublicSystemPrefix(self.model,'public system only',Formatter,lambda:self.current)
    def test_prepares_system_only_and_accepts_two_unseen_complete_stream_prompts(self):
        prefix=self.prepare();self.assertEqual(Formatter.calls,[(False,[{'role':'system','content':'public system only'}])]);self.assertEqual(len(self.model.evals),1);self.assertEqual(self.model.completions,[])
        for question in ('unseen-one','unseen-two'):
            messages=[{'role':'system','content':'public system only'},{'role':'user','content':question}]
            with prefix.generation(messages):
                result=self.model.create_chat_completion(messages=messages,stream=True,seed=42,max_tokens=160)
                chunks=list(result)
            self.assertEqual(chunks[-1]['choices'][0]['finish_reason'],'stop');self.assertEqual(self.model.completions[-1]['seed'],42);self.assertIs(self.model.completions[-1]['stream'],True)
        self.assertEqual(len(self.model.completions),2);self.assertNotEqual(self.model.completions[0]['prompt'],self.model.completions[1]['prompt']);self.assertNotIn('create_completion',vars(self.model))
    def test_private_scope_template_model_cache_and_actual_prompt_mismatch_refuse(self):
        prefix=self.prepare();messages=[{'role':'system','content':'public system only'},{'role':'user','content':'unseen'}]
        with self.assertRaises(PrefixNotReady):
            with prefix.generation(messages):self.model.create_completion(prompt=[1],stream=True)
        self.assertEqual(self.model.completions,[]);self.assertNotIn('create_completion',vars(self.model))
        self.current=False
        with self.assertRaises(PrefixNotReady):
            with prefix.generation(messages):self.fail('stale private epoch must not enter')
        self.current=True;self.model.metadata['tokenizer.chat_template']='changed'
        with self.assertRaises(PrefixNotReady):
            with prefix.generation(messages):self.fail('changed template must not enter')
        self.model.metadata['tokenizer.chat_template']=TEMPLATE;self.model.reset()
        with self.assertRaises(PrefixNotReady):
            with prefix.generation(messages):self.fail('lost cache must not enter')
    def test_unsupported_metadata_does_not_fake_prefix_ready_and_prep_cannot_sample(self):
        self.model.chat_handler=object()
        with self.assertRaises(PrefixUnsupported):self.prepare()
        self.assertEqual(self.model.evals,[])
        self.model.chat_handler=None;self.model.try_sample=True
        with self.assertRaises(PrefixNotReady):self.prepare()
        self.assertEqual(self.model.n_tokens,0);self.assertNotIn('sample',vars(self.model));self.assertNotIn('create_chat_completion',vars(self.model))


if __name__=='__main__':unittest.main()
