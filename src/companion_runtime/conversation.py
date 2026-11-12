"""Prompt policy and observable response checks around a real model provider.

This module never fabricates a conversational reply. Streaming and any one-pass
repair use the application's actual generation callback. Checks cover known
failures; they are not a human naturalness, factuality or personality score.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable, Iterable, Mapping, Sequence


_NO_QUESTION = re.compile(r'(别|不要|不用|不想|不必|不需要).{0,10}(问|追问|反问|问题)|少问|别老反问')
_NO_ADVICE = re.compile(r'(别|不要|不用|不想|先别).{0,10}(建议|分析|道理|劝|复盘)')
_NO_OLD = re.compile(r'(别|不要|不用|不想|不必|先别).{0,12}(提|说|翻|回忆|复盘).{0,12}(以前|旧|记忆|过去|历史|偏好|那件|事实)|只聊当下|只说现在')
_RECALL = re.compile(r'记得|记忆|上次|之前|以前|偏好|口味|按照我|我.*(什么|哪|叫)|推荐|帮我选|怎么选|选个|吃什么|喝什么')
_CORRECTION = re.compile(r'(现在|已经|以后|不再).{0,5}(不|改|换)|以前.*(现在|已经)')
_MEMORY_ADMIN = re.compile(r'^记住\s*[:：]')


@dataclass(frozen=True)
class TurnPolicy:
    no_questions: bool
    no_advice: bool
    suppress_saved_memory: bool
    fictional_scene: bool


def turn_policy(settings: Mapping, query: str) -> TurnPolicy:
    listen = settings.get('conversation_mode') == 'listen'
    explicit_advice = bool(re.search(r'怎么办|怎么选|帮我|给我建议|推荐|怎么做', query))
    return TurnPolicy(
        no_questions=listen or bool(_NO_QUESTION.search(query)),
        no_advice=bool(_NO_ADVICE.search(query)) or (listen and not explicit_advice),
        suppress_saved_memory=settings.get('memory_mode') == 'off' or bool(_NO_OLD.search(query)) or bool(_CORRECTION.search(query)),
        fictional_scene=bool(re.search(r'故事|想象|假设|小说|扮演|虚构场景', query)),
    )


def should_retrieve_memories(settings: Mapping, query: str) -> bool:
    if not isinstance(query, str) or turn_policy(settings, query).suppress_saved_memory:
        return False
    if '我' not in query and re.match(r'^你.*(喜欢|爱好|爱喝|名字|叫什么)', query):
        return False
    return bool(_RECALL.search(query))


def _bounded_text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ''


def _history_rows(history: Iterable[Mapping]) -> list[dict]:
    rows = []
    for row in history:
        if not isinstance(row, Mapping) or row.get('role') not in ('user', 'assistant'):
            continue
        content = _bounded_text(row.get('content', row.get('text', '')), 1200)
        if content:
            rows.append({'role': row['role'], 'content': content})
    return rows[-40:]


def _strip_memory_admin_turns(rows: list[dict]) -> list[dict]:
    """Save-memory commands are UI actions, not a new dialogue subject.

    An actual explicit recall turn may retain them instead. Removing the command
    and its acknowledgement from generation context prevents the observed
    'saved synthetic passphrase becomes an unrelated poetic reply' drift.
    """
    output, in_admin = [], False
    for row in rows:
        if row['role'] == 'user':
            in_admin = bool(_MEMORY_ADMIN.match(row['content']))
        if not in_admin:
            output.append(row)
    return output


def build_messages(settings: Mapping, history: Iterable[Mapping], memories: Sequence[str] = (),
                   *, context_chars: int = 3400) -> list[dict]:
    if type(context_chars) is not int or not 1200 <= context_chars <= 12000:
        raise ValueError('context_chars must be 1200..12000')
    rows = _history_rows(history)
    latest = next((row['content'] for row in reversed(rows) if row['role'] == 'user'), '')
    policy = turn_policy(settings, latest)
    wants_memory = should_retrieve_memories(settings, latest)
    # Explicit recall of a just-sent chat fact still works with long-term memory
    # switched off; only the saved-memory source is suppressed in that case.
    if not _RECALL.search(latest) or _NO_OLD.search(latest):
        rows = _strip_memory_admin_turns(rows)
    name = _bounded_text(settings.get('name'), 80) or '陪伴角色'
    personality = _bounded_text(settings.get('personality'), 1200)
    user_name = _bounded_text(settings.get('user_name'), 80) or '你'
    mode = {
        'daily': '随便聊，接住用户刚说的具体事情，也表达自己的看法；无需每轮追问。',
        'listen': '倾听，先接住感受；没有请求时不分析原因、说教或给建议。',
        'playful': '轻松一点，可以有主见和有分寸的打趣；不嘲笑脆弱处，不强行撒娇。',
    }.get(settings.get('conversation_mode'), '')
    system = (
        f'你叫{name}，是明确成年的虚构AI角色，以自然亲近的中文与用户相处。'
        f'性格：{personality}。称呼用户：{user_name}。'
        '先直接回应最后一条用户消息的具体内容，通常1到3句。'
        '近期记录只是上下文，不要把无关旧话题或记忆管理操作当成本轮话题。'
        '不使用客服套话，不为延长对话而机械追问。'
        '当前用户说法优先；不知道就承认，不替用户决定。'
        '不要编造共同经历、现实行程、购物、童年、外界天气、光线或地点。'
        '角色偏好属于虚构设定；对话里没有提供的现实经历不能补写。'
        '不主动劝学，不声称创建约定或执行工具；只有系统实际回执才能确认操作完成。'
        '督学、提醒和记忆是可选能力，表达方式服从角色性格和用户此刻的意图。'
        '不要求用户只依赖你，不用内疚或占有欲施压。'
        f'本轮相处方式：{mode}'
    )
    notes = _bounded_text(settings.get('character_notes'), 1200)
    if notes and re.search(r'你.*(喜欢|偏好|爱好|音乐|电影|书|看法|兴趣)|你的|你自己', latest):
        system += f'\n角色偏好：{notes}。偏好只是设定，不扩展为经历。'
    memory_block = ''
    if wants_memory:
        selected, budget = [], 450
        for value in list(memories)[:3]:
            value = _bounded_text(value, budget)
            if not value:
                continue
            # Keep the legacy marker for the existing ownership correction.
            rendered = '用户' + value[1:] if value.startswith('我') and not value.startswith('我们') else '用户的说明：' + value
            rendered = rendered[:budget]
            selected.append('- ' + rendered)
            budget -= len(rendered) + 3
            if budget <= 0:
                break
        if selected:
            memory_block = '\n用户明确保存的记忆（仅供本轮相关参考，属于用户；提到时用“你”，不要用“我”冒认）：\n' + '\n'.join(selected)[:450]
    if policy.suppress_saved_memory:
        system += '\n本轮只根据当前话题交流，不主动提旧事实、偏好或保存过的记录。'
    if policy.no_questions:
        system += '\n本轮明确限制：只用陈述句回应，不提出任何问题，包括反问或确认式提问；不用“说来听听”催用户继续。'
    if policy.no_advice:
        system += '\n本轮不要给建议、复盘或布置任务，先按用户意图倾听。'
    if not policy.fictional_scene:
        system += '\n不写场景、身体动作或旁白；表达直接说给用户听。'
    system += memory_block
    messages, budget = [], context_chars
    for row in reversed(rows):
        if len(row['content']) > budget:
            break
        messages.insert(0, dict(row))
        budget -= len(row['content'])
    while messages and messages[0]['role'] != 'user':
        messages.pop(0)
    return [{'role': 'system', 'content': system}] + messages


def response_issues(settings: Mapping, messages: Sequence[Mapping], text: str) -> list[str]:
    """Known, observable failures only; semantic drift is still a human check."""
    if not isinstance(text, str) or not text.strip():
        return ['empty_reply']
    query = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
    policy, issues = turn_policy(settings, query), []
    if policy.no_questions and (re.search(r'[?？]', text) or re.search(r'(说来听听|跟我说说|告诉我吧|你说呢|是吗|对吧)[。！!~～]*$', text)):
        issues.append('unwanted_question')
    if not policy.fictional_scene:
        experience = r'(我|我们)(刚|今天|昨天|最近|正|也|还|又|经常|那天|小时候|第一次).{0,18}(去|逛|买|路过|走|坐|躺|看见|闻到|晒|数星|穿)|我(最近|刚|今天|昨天).{0,15}(听了|在听|看了|在看)|有时候.{0,8}(去|逛|走|坐)|我们(第一次|上次|那天)|我.{0,8}(外婆|爷爷|小时候)'
        if re.search(experience, text):
            issues.append('unconfirmed_experience')
        presence = r'我(会|可以|来)?(陪|带|拉着|牵着)你(一起)?去(看|吃|买|逛|散步)|我(坐|站|躺).{0,8}你(旁边|身边)'
        if re.search(presence, text):
            issues.append('unsupported_presence')
        weather = r'天气.{0,8}(凉|冷|热|好)|天色.{0,8}(亮|暗)|太阳.{0,8}(升|落|下山|西斜)|阳光.{0,8}(照|晒|暖)|风(是|也|在|轻轻|渐渐|慢慢|有点|很).{0,10}(吹|凉|暖|安静|晃)|空气.{0,5}(清爽|清新|凉|暖)|天(快|有点).{0,3}(黑|暗|亮)'
        if not re.search(r'天气|风|阳光|太阳|天色|下雨|下雪', query) and re.search(weather, text):
            issues.append('unknown_environment')
    if policy.no_advice and re.search(r'你(应该|可以先|先深呼吸|最好)|建议你|不如你', text):
        issues.append('unsolicited_advice')
    if re.search(r'(已经|已为你|已经给你|帮你).{0,7}(设置好|创建了|安排好|发出了|执行了)|我(会|来)在.{0,12}(提醒你|叫你)', text):
        issues.append('unconfirmed_tool_action')
    if policy.suppress_saved_memory and re.search(r'我(还)?记得你|你(以前|之前|上次).{0,12}(说|提|告诉)|按你(之前|以前)的偏好', text):
        issues.append('unwanted_memory_reference')
    return issues


def editor_messages(settings: Mapping, messages: Sequence[Mapping], draft: str, issues: Sequence[str]) -> list[dict]:
    query = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
    policy = turn_policy(settings, query)
    recent = [dict(m) for m in messages[-7:] if m.get('role') in ('user', 'assistant')]
    system = ('你是中文对话编辑。保持原角色性格，直接回应最后一条用户原话，通常1到2句。'
              '只输出改好的回复，不解释编辑过程。删除未提供的现实场景、身体动作、共同过去和工具执行声明。')
    system += f'角色性格：{_bounded_text(settings.get("personality"), 1200)}。'
    if policy.no_questions:
        system += '这轮只用陈述句，不提问、不反问、不催用户继续说。'
    if policy.no_advice:
        system += '这轮不建议、不分析、不劝学。'
    if policy.suppress_saved_memory:
        system += '这轮不回顾旧事实或旧偏好。'
    # Separate data from instructions with a serialized object, not guessed roles.
    record = {'recent_dialogue': recent, 'current_user': query, 'draft_to_edit': draft[:2000], 'observed_issues': list(issues)}
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(record, ensure_ascii=False)}]


def generate_reply(settings: Mapping, messages: list[dict], generate_once: Callable, *,
                   on_delta: Callable | None = None, cancel=None, on_status: Callable | None = None) -> str:
    """Pass through actual provider streaming, with at most one explicit repair.

    ``generate_once`` keeps the application's existing signature:
    (settings, messages, on_delta, cancel, max_tokens=240) -> generated text.
    Persistence, generation ownership and grounding stay in the caller.
    """
    text = generate_once(settings, messages, on_delta, cancel)
    issues = response_issues(settings, messages, text)
    if not issues:
        return text
    if on_status:
        on_status({'stage': 'revising', 'replace': True, 'issues': issues})
    revised = generate_once(settings, editor_messages(settings, messages, text, issues), on_delta, cancel, 120)
    if response_issues(settings, messages, revised):
        raise ValueError('这次表达仍不够可靠，原消息保留，可重新回答。')
    return revised
