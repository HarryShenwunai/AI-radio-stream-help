"""Pinned Qwen system-only prefill. The caller owns MODEL_LOCK, never a UI thread."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
from typing import Callable, Iterator, Mapping, Protocol, Sequence

from .public_preparation import PreparationNotReady

QWEN_TEMPLATE_SHA256 = '40c21f34cf67d8c760ef72f8ad3ae5afad514299d4b06e91dd9a8d705af7b541'
DEFAULT_MODEL_SHA256 = '2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e'


class PrefixUnsupported(ValueError):
    pass


class PrefixNotReady(PreparationNotReady):
    pass


class LocalModel(Protocol):
    metadata: Mapping[str, object]
    chat_format: str | None
    chat_handler: object | None
    n_tokens: int
    create_completion: Callable[..., object]
    create_chat_completion: Callable[..., object]
    sample: Callable[..., object]

    def tokenize(self, data: bytes, *, add_bos: bool, special: bool) -> list[int]: ...
    def reset(self) -> None: ...
    def eval(self, tokens: Sequence[int]) -> None: ...


class FormattedPrompt(Protocol):
    prompt: str
    added_special: bool


class ChatFormatter(Protocol):
    def __call__(self, *, messages: Sequence[Mapping[str, str]]) -> FormattedPrompt: ...


def _template_signature(model: LocalModel) -> str:
    fields = {key: model.metadata.get(key) for key in ('tokenizer.chat_template', 'tokenizer.ggml.add_bos_token',
                'tokenizer.ggml.bos_token_id', 'tokenizer.ggml.eos_token_id')}
    return hashlib.sha256(json.dumps({'metadata': fields, 'format': model.chat_format,
        'no_custom_handler': model.chat_handler is None}, sort_keys=True).encode()).hexdigest()


class PublicSystemPrefix:
    """Contains no question/history. Each new full prompt is checked independently."""
    def __init__(self, model: LocalModel, system: str, formatter_factory: Callable[..., ChatFormatter],
                 current: Callable[[], bool]) -> None:
        template = model.metadata.get('tokenizer.chat_template')
        if (not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != QWEN_TEMPLATE_SHA256
                or model.metadata.get('tokenizer.ggml.add_bos_token') not in (False, 'false')
                or str(model.metadata.get('tokenizer.ggml.bos_token_id')) != '151643'
                or str(model.metadata.get('tokenizer.ggml.eos_token_id')) != '151645'
                or model.chat_format != 'chat_template.default' or model.chat_handler is not None):
            raise PrefixUnsupported('local_prefix_template_unsupported')
        arguments = {'template': template, 'eos_token': '<|im_end|>', 'bos_token': '<|endoftext|>',
                     'stop_token_ids': [151645]}
        prepare_formatter = formatter_factory(**arguments, add_generation_prompt=False)
        rendered = prepare_formatter(messages=[{'role': 'system', 'content': system}])
        if not rendered.added_special or not rendered.prompt.endswith('<|im_end|>\n'):
            raise PrefixUnsupported('local_prefix_system_boundary_unsupported')
        prefix = rendered.prompt[:-1]  # End at a complete special token; no unknown user/BPE boundary.
        if prefix != '<|im_start|>system\n' + system + '<|im_end|>':
            raise PrefixUnsupported('local_prefix_system_rendering_unsupported')
        tokens = model.tokenize(prefix.encode(), add_bos=False, special=True)
        if not tokens or tokens[0] == 151643 or tokens[-1] != 151645:
            raise PrefixUnsupported('local_prefix_special_tokens_unsupported')
        if not current():
            raise PrefixNotReady('public_preparation_cancelled')
        self.model = model
        self.system = system
        self.tokens = tuple(tokens)
        self.formatter = formatter_factory(**arguments, add_generation_prompt=True)
        self.template_signature = _template_signature(model)
        self.current = current
        started = time.monotonic()
        changes: list[tuple[str, bool, object]] = []

        def forbidden(*args: object, **kwargs: object) -> object:
            raise PrefixNotReady('preparation_must_not_sample_or_generate')

        try:
            for name in ('sample', 'create_completion', 'create_chat_completion'):
                changes.append((name, name in vars(model), getattr(model, name)))
                setattr(model, name, forbidden)
            model.reset()
            model.eval(tokens)
            if model.n_tokens != len(tokens) or not current():
                raise PrefixNotReady('public_preparation_cancelled')
        except Exception:
            model.reset()
            raise
        finally:
            for name, owned, previous in reversed(changes):
                if owned:
                    setattr(model, name, previous)
                else:
                    delattr(model, name)
        self.prepare_seconds = time.monotonic() - started
        self.prefix_sha256 = hashlib.sha256(prefix.encode()).hexdigest()

    @contextmanager
    def generation(self, messages: Sequence[Mapping[str, str]]) -> Iterator[None]:
        if (not self.current() or _template_signature(self.model) != self.template_signature
                or self.model.n_tokens < len(self.tokens) or len(messages) != 2
                or messages[0].get('role') != 'system' or messages[0].get('content') != self.system
                or messages[1].get('role') != 'user'):
            raise PrefixNotReady('public_prefix_scope_or_cache_changed')
        formatted = self.formatter(messages=messages)
        if not formatted.added_special:
            raise PrefixNotReady('public_prefix_formatter_changed')
        full = self.model.tokenize(formatted.prompt.encode(), add_bos=False, special=True)
        if tuple(full[:len(self.tokens)]) != self.tokens:
            raise PrefixNotReady('public_prefix_full_tokens_mismatch')
        original = self.model.create_completion
        owned = 'create_completion' in vars(self.model)
        calls = 0

        def checked(*args: object, **kwargs: object) -> object:
            nonlocal calls
            if args or not self.current() or kwargs.get('prompt') != full:
                raise PrefixNotReady('actual_public_prompt_tokens_changed')
            calls += 1
            if calls != 1:
                raise PrefixNotReady('unexpected_multiple_public_completions')
            return original(*args, **kwargs)

        self.model.create_completion = checked
        try:
            yield
            if calls != 1 or not self.current():
                raise PrefixNotReady('public_preparation_cancelled_or_completion_missing')
        finally:
            if owned:
                self.model.create_completion = original
            else:
                delattr(self.model, 'create_completion')
