"""小岚 · 单用户本地陪伴应用。Python 3.10+，HTTP/SQLite 仅使用标准库。"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import http.cookies
import importlib.util
import io
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
STATIC = Path(getattr(sys,'_MEIPASS',str(ROOT))) / 'static'
DATA = Path(os.environ.get('COMPANION_DATA', str(ROOT / 'data')))
MODEL_DIR = Path(os.environ.get('COMPANION_MODELS', str(ROOT / 'models')))
VOICE_DIR = Path(os.environ.get('COMPANION_VOICES', str(ROOT / 'voices')))
QUALITY_MODEL = MODEL_DIR / 'qwen3-4b-instruct-2507-q4_k_m.gguf'
LIGHT_MODEL = MODEL_DIR / 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
MODEL = QUALITY_MODEL if QUALITY_MODEL.exists() or not LIGHT_MODEL.exists() else LIGHT_MODEL
VERSION = '0.3.0-dev1'
DEFAULT = {
    'name':'小岚', 'user_name':'你', 'personality':'温柔但有自己的主见，偶尔俏皮，喜欢自然简短的聊天。',
    'engine':'local', 'api_base':'https://api.deepseek.com/v1', 'api_model':'deepseek-chat',
    'quiet_start':23, 'quiet_end':8, 'proactive':False, 'study':False,
    'voice':True, 'voice_rate':1.0,
    'memory_mode':'relevant', 'conversation_mode':'daily',
    'character_notes':'偏爱轻快民谣，电影更喜欢带幽默的生活题材；喜欢有分寸的玩笑，不太喜欢刻意煽情。这些是设定偏好，不是现实经历。',
}
MODEL_LOCK = threading.Lock()
DB_LOCK = threading.RLock()
DISPATCH_LOCK = threading.RLock()
LOCAL_LLM = None
MODEL_STATUS = 'not_loaded'
MODEL_ERROR = ''
TTS_LOCK = threading.Lock()
LOCAL_VOICE = None
G2P = None
AUTH = secrets.token_urlsafe(32)
STOP = threading.Event()
ACTIVE_LOCK = threading.RLock()
ACTIVE = {}

# Keep the existing application runnable without installing model dependencies.
# Network ingress must never receive this private scope or the browser cookie.
sys.path.insert(0, str(ROOT.parent / 'src'))
from companion_runtime.lifecycle import Scope, GenerationRegistry, GenerationCapacityError
PRIVATE_SCOPE = Scope('private', 'local-private')
GENERATIONS = GenerationRegistry(max_entries=256, retention_seconds=600)

class Cancelled(Exception):pass

def check_cancel(cancel):
    if cancel and cancel.is_set():raise Cancelled()

class AppError(Exception):
    def __init__(self,message,status=400):
        super().__init__(message); self.status=status

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

@contextlib.contextmanager
def db():
    with DB_LOCK:
        conn=sqlite3.connect(DATA/'companion.db',timeout=10)
        conn.row_factory=sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

def init():
    DATA.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,role TEXT NOT NULL,text TEXT NOT NULL,created TEXT NOT NULL,request_id TEXT,kind TEXT DEFAULT 'chat');
        CREATE INDEX IF NOT EXISTS msg_request ON messages(request_id);
        CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT NOT NULL,created TEXT NOT NULL,source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,due REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'reminder');
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forgotten(digest TEXT PRIMARY KEY,created TEXT NOT NULL);
        ''')
        for k,v in DEFAULT.items():c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM messages LIMIT 1').fetchone():
            c.execute('INSERT INTO messages(role,text,created,kind) VALUES(?,?,?,?)',('assistant','嗨，我是小岚。你可以跟我说说今天的事，也可以慢慢告诉我，你喜欢怎样相处。',now(),'welcome'))
    with contextlib.suppress(OSError):os.chmod(DATA/'companion.db',0o600)

def audit(event,detail=''):
    with db() as c:c.execute('INSERT INTO audit(event,detail,created) VALUES(?,?,?)',(event,str(detail)[:180],now()))

def settings():
    with db() as c:return {r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}

def secret_key():
    path=DATA/'api-key'
    return path.read_text().strip() if path.exists() else ''

def set_settings(payload):
    fields={'name','user_name','personality','engine','api_base','api_model','quiet_start','quiet_end','proactive','study','voice','voice_rate','memory_mode','conversation_mode','character_notes'}
    s=settings()
    for k in fields:
        if k not in payload:continue
        v=payload[k]
        if k in {'name','user_name','personality','character_notes','api_base','api_model'}:
            if not isinstance(v,str):raise AppError('设置格式不正确。')
            v=v.strip()
            if len(v)>(1200 if k in {'personality','character_notes'} else 300):raise AppError('设置内容过长。')
            if k in {'name','api_model'} and not v:raise AppError('名字和模型名不能为空。')
        if k=='engine' and v not in {'local','api'}:raise AppError('请选择本地模型或 API。')
        if k=='memory_mode' and v not in {'relevant','off'}:raise AppError('请选择按需记忆或只聊当下。')
        if k=='conversation_mode' and v not in {'daily','listen','playful'}:raise AppError('相处方式不正确。')
        if k in {'quiet_start','quiet_end'}:
            if not isinstance(v,int) or not 0<=v<=23:raise AppError('安静时段请使用 0–23 点。')
        if k in {'voice','proactive','study'} and not isinstance(v,bool):raise AppError('开关格式不正确。')
        if k=='voice_rate':
            if not isinstance(v,(float,int)) or not .6<=v<=1.5:raise AppError('语速范围为 0.6–1.5。')
        s[k]=v
    if s['engine']=='api':validate_base(s['api_base'])
    if 'api_key' in payload and (not isinstance(payload['api_key'],str) or len(payload['api_key'])>4096):
        raise AppError('密钥格式不正确。')
    with db() as c:
        for k in fields:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(s[k],ensure_ascii=False)))
        if payload.get('study') is False:
            c.execute("UPDATE tasks SET status='paused' WHERE kind='study' AND status='pending'")
    if 'api_key' in payload:
        v=payload['api_key']
        if v.strip():
            path=DATA/'api-key'
            path.write_text(v.strip());os.chmod(path,0o600)
    if payload.get('clear_api_key'):
        (DATA/'api-key').unlink(missing_ok=True)
    audit('settings_changed',','.join(sorted(fields & payload.keys())))

def validate_base(base):
    parsed=urllib.parse.urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:raise AppError('API 地址不能包含账号、查询参数或片段。')
    if parsed.scheme not in {'https','http'} or not parsed.hostname:raise AppError('API 地址需要是完整的 HTTPS 地址。')
    local=parsed.hostname in {'localhost','127.0.0.1','::1'}
    if parsed.scheme=='http' and not local:raise AppError('仅本机服务允许使用 HTTP。')
    if parsed.hostname in {'169.254.169.254','metadata.google.internal','0.0.0.0'}:raise AppError('这个地址不能用作模型服务。')
    return base.rstrip('/')

def load_model():
    global LOCAL_LLM,MODEL_STATUS,MODEL_ERROR
    if LOCAL_LLM is not None:return LOCAL_LLM
    if not MODEL.exists():raise AppError('尚未安装本地模型。运行「安装本地模型」，或在设置里连接模型 API。',503)
    try:
        from llama_cpp import Llama
    except ImportError:raise AppError('尚未安装本地推理组件。运行安装脚本，或切换到 API。',503)
    MODEL_STATUS='loading'
    try:
        LOCAL_LLM=Llama(model_path=str(MODEL),n_ctx=4096,n_threads=min(4,os.cpu_count() or 2),n_batch=256,verbose=False)
        MODEL_STATUS='ready';MODEL_ERROR=''
        return LOCAL_LLM
    except Exception:
        MODEL_STATUS='error';MODEL_ERROR='模型加载失败，请检查文件、内存和推理组件版本。'
        raise AppError(MODEL_ERROR,503)

def select_memories(s,query):
    """Bounded lexical retrieval, with no irrelevant fallback and no model call."""
    if s.get('memory_mode')=='off':return []
    stop={'我喜','喜欢','最喜','你喜','我的','你的','我是','你是','今天','现在','什么','可以','一下','一个','还有','我们','记得','记忆','不想','已经','以前','的事','想起','告诉'}
    query=re.sub(r'\s+','',query.lower())
    if '我' not in query and re.match(r'^你.*(喜欢|爱好|爱喝|名字|叫什么)',query):return []
    if re.search(r'(现在|已经|以后|不再).{0,5}(不|改|换)|以前.*(现在|已经)',query):return []
    if not re.search(r'记得|记忆|上次|之前|以前|偏好|口味|按照我|我.*(什么|哪|叫)|推荐|帮我选|怎么选|选个|吃什么|喝什么',query):return []
    grams={query[i:i+2] for i in range(len(query)-1) if query[i:i+2] not in stop and all(c.isalnum() for c in query[i:i+2])}
    direct=bool(re.search(r'(记得我|关于我|我的.*(什么|哪|叫)|我.*(爱好|饮品|名字).*(什么|哪|叫))',query))
    with db() as c:rows=[dict(r) for r in c.execute('SELECT id,text FROM memories ORDER BY id DESC LIMIT 60')]
    ranked=[]
    for row in rows:
        score=sum(g in row['text'].lower() for g in grams)
        if direct and any(w in query for w in ['喝','饮品','饮料']):
            score+=sum(w in row['text'] for w in ['饮品','饮料','喝','茶','咖啡'])
        if score or (direct and query in {'你还记得我吗','记得我吗','关于我','你记得我什么','你还记得关于我的什么'}):
            ranked.append((score,row))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return [row['text'] for score,row in ranked[:3]]

def build_prompt(s,upto_id=None):
    with db() as c:
        query="SELECT role,text FROM messages WHERE kind='chat'";args=[]
        if upto_id is not None:query+=' AND id<=?';args.append(upto_id)
        raw=[dict(r) for r in c.execute(query+' ORDER BY id DESC LIMIT 20',args)][::-1]
    latest=next((r['text'] for r in reversed(raw) if r['role']=='user'),'')
    memories=select_memories(s,latest)
    def perspective(x):
        return '用户'+x[1:] if x.startswith('我') and not x.startswith('我们') else '用户的说明：'+x
    mode={
        'daily':'随便聊，接住用户具体说的内容，也表达自己的看法，不必每轮追问。',
        'listen':'倾听，先回应感受，不分析原因、说教或给建议。',
        'playful':'轻松一点，可以有主见、轻微打趣，不嘲笑脆弱处，不强行撒娇。',
    }.get(s.get('conversation_mode'),'')
    system=(f'你叫{s["name"]}，是成年女性AI角色，以亲近自然的中文陪用户聊天。'
        f'性格：{s["personality"]}。称呼用户：{s["user_name"]}。'
        '直接回应用户，通常1到3句，不用客服套话，不反复追问。'
        '不要编造共同经历。你仅在这个窗口交流，没有真实行程、购物或童年经历。'
        '不编造外界天气、光线或地点，不写场景、动作和旁白。'
        '用户当前说法优先于旧记录；不知道就承认，不替用户决定。'
        '不主动劝学或声称创建约定；不要求用户只依赖你，不用内疚或占有欲施压。'
        f'本轮相处方式：{mode}')
    if re.search(r'你.*(喜欢|偏好|爱好|音乐|电影|书|看法|兴趣)|你的|你自己',latest):
        system+=f'\n角色偏好：{s.get("character_notes","")}。偏好只是设定，不扩展为经历。'
    if memories:
        system+='\n用户明确保存的记忆（仅供本轮相关参考，属于用户；提到时用“你”，不要用“我”冒认）：\n'
        system+='\n'.join('- '+perspective(x) for x in memories)[:450]
    if s.get('conversation_mode')=='listen' or re.search(r'(别|不要|不用|不想|不必|不需要).{0,8}(问|追问|反问|问题)',latest):
        system+='\n本轮明确限制：只用陈述句回应，不提出任何问题，包括反问或确认式提问。'
    messages=[];budget=3400
    for r in reversed(raw):
        text=r['text'][:1200]
        if len(text)>budget:break
        messages.insert(0,{'role':r['role'],'content':text});budget-=len(text)
    # An old truncated assistant fragment must not lead the conversation.
    while messages and messages[0]['role']!='user':messages.pop(0)
    return [{'role':'system','content':system}]+messages

def ground_memory_owner(text,messages):
    """仅在询问用户事实且输出明确匹配已存事实时，校正开头的人称。"""
    query=messages[-1]['content'] if messages else ''
    if not ('我' in query and any(w in query for w in ['喜欢','饮品','爱好','名字','爱喝','爱吃'])):
        return text
    if not any(w in query for w in ['什么','哪','谁','记得','叫']):return text
    replacements=[('我的最爱','你的最爱'),('我最喜欢','你最喜欢'),('我的爱好','你的爱好'),('我的名字','你的名字'),('我喜欢','你喜欢'),('我叫','你叫')]
    pair=next((x for x in replacements if text.startswith(x[0])),None)
    if not pair:return text
    _,marker,source=messages[0]['content'].partition('用户明确保存的记忆（')
    if not marker:return text
    source=source.split('：\n',1)[-1]
    stop={'用户','户的','户喜','户最','的最','最喜','喜欢','的饮','饮品','品是','的爱','爱好','好是','最爱','爱是','的名','名字','字是','户叫','叫我'}
    grams={source[i:i+2] for i in range(len(source)-1) if source[i:i+2] not in stop and all('\u4e00'<=c<='\u9fff' for c in source[i:i+2])}
    if not any(g in text for g in grams):return text
    audit('memory_owner_corrected','matched saved fact; second-person rendering')
    return pair[1]+text[len(pair[0]):]

def response_issues(s,messages,text):
    """Conservative checks for observable breaches, not a truth/quality score."""
    query=messages[-1]['content'];issues=[]
    no_questions=bool(re.search(r'(别|不要|不用|不想|不必|不需要).{0,8}(问|追问|反问|问题)',query)) or s.get('conversation_mode')=='listen'
    if no_questions and ('？' in text or '?' in text):issues.append('unwanted_question')
    if not re.search(r'故事|想象|假设|小说|扮演',query):
        fabricated=re.search(r'(我|我们)(刚|今天|昨天|最近|正|也|还|又|经常|那天|小时候|第一次).{0,18}(去|逛|买|路过|走|坐|躺|看见|闻到|晒|数星|穿)|我(最近|刚|今天|昨天).{0,15}(听了|在听|看了|在看)|有时候.{0,8}(去|逛|走|坐)|我们(第一次|上次|那天)|我.{0,8}(外婆|爷爷|小时候)',text)
        if fabricated:issues.append('unconfirmed_experience')
        weather=r'天气.{0,8}(凉|冷|热|好)|天色.{0,8}(亮|暗)|太阳.{0,8}(升|落|下山|西斜)|阳光.{0,8}(照|晒|暖)|风(是|也|在|轻轻|渐渐|慢慢|有点|很).{0,10}(吹|凉|暖|安静|晃)|空气.{0,5}(清爽|清新|凉|暖)|天(快|有点).{0,3}(黑|暗|亮)'
        if not re.search(r'天气|风|阳光|太阳|天色|下雨|下雪',query) and re.search(weather,text):issues.append('unknown_environment')
    no_advice=bool(re.search(r'(别|不要|不用|不想).{0,8}(建议|分析|道理|劝)',query))
    if no_advice or (s.get('conversation_mode')=='listen' and not re.search(r'怎么办|怎么选|帮我|给我建议|推荐|怎么做',query)):
        if re.search(r'你(应该|可以先|先深呼吸|最好)|建议你|不如你',text):issues.append('unsolicited_advice')
    return issues

class NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        old=urllib.parse.urlsplit(request.full_url);new=urllib.parse.urlsplit(newurl)
        if old.netloc!=new.netloc or (old.scheme=='https' and new.scheme!='https'):
            raise AppError('模型地址跳转不安全，已停止以保护密钥。',502)
        return super().redirect_request(request,fp,code,msg,headers,newurl)

def remote_tokens(s,messages,cancel,max_tokens=240):
    base=validate_base(s['api_base']);key=secret_key()
    if not key and urllib.parse.urlsplit(base).hostname not in {'localhost','127.0.0.1','::1'}:
        raise AppError('请先在设置里填写模型 API 密钥。密钥只保存在本机。',503)
    body=json.dumps({'model':s['api_model'],'messages':messages,'max_tokens':max_tokens,'temperature':.75,'stream':True}).encode()
    headers={'Content-Type':'application/json','Accept':'text/event-stream'}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request(base+'/chat/completions',data=body,headers=headers,method='POST')
    try:
        with urllib.request.build_opener(NoCrossHostRedirect).open(req,timeout=20) as response:
            if 'application/json' in response.headers.get('Content-Type',''):
                result=json.loads(response.read(2_000_001));check_cancel(cancel)
                yield result['choices'][0]['message']['content'];return
            size=0
            for line in response:
                check_cancel(cancel);size+=len(line)
                if size>2_000_000:raise AppError('模型返回过长，已停止。',502)
                if not line.startswith(b'data:'):continue
                data=line[5:].strip()
                if data==b'[DONE]':break
                if not data:continue
                obj=json.loads(data)
                if 'error' in obj:raise AppError('模型服务中断了回复，请重试。',502)
                choices=obj.get('choices',[])
                if choices:
                    content=choices[0].get('delta',{}).get('content')
                    if content:yield content
    except urllib.error.HTTPError as e:raise AppError(f'模型服务返回 HTTP {e.code}。请检查地址、模型名、密钥和额度。',502)
    except (urllib.error.URLError,TimeoutError,OSError):
        check_cancel(cancel)
        raise AppError('模型连接失败或超时。消息已保留，可点“重新回答”。',502)
    except (KeyError,IndexError,AttributeError,TypeError,ValueError):raise AppError('模型服务返回了无法识别的内容。',502)

def generate_once(s,messages,on_delta=None,cancel=None,max_tokens=240):
    started=time.monotonic();first=None;parts=[];check_cancel(cancel)
    if s['engine']=='local':
        llm=load_model();check_cancel(cancel)
        # Preserve the current user message and complete recent turns.
        while len(llm.tokenize(json.dumps(messages,ensure_ascii=False).encode()))>3450:
            if len(messages)>2:
                messages.pop(1)
                while len(messages)>2 and messages[1]['role']!='user':messages.pop(1)
            else:raise AppError('这条消息超出本地模型容量，请分成短一些的消息。')
        tokens=llm.create_chat_completion(messages=messages,max_tokens=max_tokens,temperature=.65,top_p=.9,repeat_penalty=1.1,stream=True)
        def local_tokens():
            for item in tokens:
                check_cancel(cancel)
                value=item['choices'][0].get('delta',{}).get('content')
                if value:yield value
        source=local_tokens()
    else:source=remote_tokens(s,messages,cancel,max_tokens)
    try:
        for token in source:
            check_cancel(cancel)
            if not isinstance(token,str):raise AppError('模型返回的文字格式不正确。',502)
            if first is None:first=time.monotonic()-started
            parts.append(token)
            if on_delta:on_delta(token)
    finally:
        if hasattr(source,'close'):source.close()
        if s['engine']=='local' and hasattr(tokens,'close'):tokens.close()
    check_cancel(cancel)
    text=''.join(parts).strip()
    if not text:raise AppError('模型没有返回文字，请重新回答。',502)
    audit('generation_completed',f'engine={s["engine"]};seconds={time.monotonic()-started:.3f};first_token={first:.3f}')
    return ground_memory_owner(text,messages)

def generate(s,messages,on_delta=None,cancel=None,on_status=None):
    text=generate_once(s,messages,on_delta,cancel)
    issues=response_issues(s,messages,text)
    if not issues:return text
    # At most one editorial pass. No canned dialogue, no extra memory retrieval.
    audit('reply_revision',','.join(issues))
    if on_status:on_status({'stage':'revising','replace':True})
    query=messages[-1]['content']
    recent='\n'.join(m['content'] for m in messages[1:-1])[-1000:]
    editor=[{'role':'system','content':
        '你是中文聊天文字编辑。把草稿改成自然、亲近、简短的回复，只输出改好的回复。'
        '删除捏造的现实场景、天气、身体动作、亲历与共同过去。'
        '用户不要提问时全部使用陈述句，倾听时不追问、不说教或给建议。不要解释修改理由。'},
        {'role':'user','content':f'相处方式：{s.get("conversation_mode")}\n近期原话：{recent}\n用户原话：{query}\n草稿：{text}\n请直接回应用户，改写成1到2句，不编造额外事实。'}]
    editor[0]['content']+=f'表达性格：{s["personality"]}。'
    if '角色偏好：' in messages[0]['content']:editor[0]['content']+=f'设定偏好：{s.get("character_notes","")}。偏好不是经历。'
    if '用户明确保存的记忆（' in messages[0]['content']:
        editor[1]['content']+='\n本轮已提供的用户事实：'+messages[0]['content'].split('用户明确保存的记忆（',1)[-1][:550]
    revised=generate_once(s,editor,on_delta,cancel,120)
    if response_issues(s,messages,revised):raise AppError('这次表达不够可靠，消息已保留，可以重新回答。',502)
    return ground_memory_owner(revised,messages)

def validate_private_scope(payload):
    """The authenticated local browser is the only implemented HTTP ingress."""
    for key, expected in (('channel', 'private'), ('source', 'web'), ('session_id', 'local-private')):
        if key in payload and payload[key] != expected:
            raise AppError('此入口只接受本机私人会话。', 403)
    if any(key in payload for key in ('role', 'owner', 'permissions', 'scope')):
        raise AppError('不能通过消息声明身份或权限。', 403)


def cancel_chat(payload):
    validate_private_scope(payload)
    rid = payload.get('request_id')
    gid = payload.get('generation_id')
    if not isinstance(rid, str) or not 1 <= len(rid) <= 80:
        raise AppError('缺少有效消息标识。')
    if gid is not None and (not isinstance(gid, str) or not 1 <= len(gid) <= 160):
        raise AppError('生成标识格式不正确。')
    with ACTIVE_LOCK:
        status = GENERATIONS.cancel(PRIVATE_SCOPE, request_id=rid, generation_id=gid)
    # This acknowledges invalidation, not interruption of an uncooperative provider.
    return {'ok': True, 'stopping': status == 'accepted', 'cancel_status': status}


def speech_for_payload(payload):
    """Bind auto speech to the completed reply; check late results before delivery."""
    validate_private_scope(payload)
    handle = None
    message_id = payload.get('message_id')
    gid, rid = payload.get('generation_id'), payload.get('request_id')
    if gid is not None or rid is not None:
        if message_id is not None or not isinstance(gid, str) or not isinstance(rid, str):
            raise AppError('语音需要成对的生成与请求标识。')
        handle = GENERATIONS.resolve(PRIVATE_SCOPE, generation_id=gid, request_id=rid)
        if handle is None:
            raise AppError('这轮声音已停止或过期。', 409)
        with db() as c:
            row = c.execute("SELECT id,text FROM messages WHERE request_id=? AND role='assistant' AND kind='chat' ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
        if row is None or payload.get('text') != row['text'][:700]:
            raise AppError('声音必须对应已完成的回复。', 409)
        text, message_id = row['text'][:700], row['id']
    elif message_id is not None:
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id < 1:
            raise AppError('消息标识格式不正确。')
        if 'text' in payload:
            raise AppError('历史朗读由服务器读取消息内容。')
        with db() as c:
            row = c.execute("SELECT text FROM messages WHERE id=? AND role='assistant'", (message_id,)).fetchone()
        if row is None:
            raise AppError('这条回复已经不存在。', 404)
        text = row['text'][:700]
    else:
        # Explicit voice preview stays available to the authenticated local owner.
        text = payload.get('text', '')
    if handle is not None and not GENERATIONS.is_current(handle):
        raise AppError('这轮声音已停止或过期。', 409)
    audio = synthesize(text)
    if handle is not None and not GENERATIONS.is_current(handle):
        audit('audio_discarded', 'generation invalidated during synthesis')
        raise AppError('这轮声音已停止，迟到音频已丢弃。', 409)
    if message_id is not None:
        with db() as c:
            row = c.execute("SELECT text FROM messages WHERE id=? AND role='assistant'", (message_id,)).fetchone()
        if row is None or row['text'][:700] != text:
            raise AppError('消息已经改变，声音已丢弃。', 409)
    return audio


def chat(payload,on_delta=None,on_meta=None,on_status=None):
    validate_private_scope(payload)
    text=str(payload.get('text','')).strip();rid=payload.get('request_id', '')
    retry_id=payload.get('retry_message_id')
    if not isinstance(rid, str) or not 1 <= len(rid) <= 80:raise AppError('缺少有效消息标识。')
    if retry_id is None and (not text or len(text)>1200):raise AppError('请输入 1–1200 字。')
    if not MODEL_LOCK.acquire(blocking=False):raise AppError('上一条回复还没结束，稍等一下。',409)
    handle = None
    completed = False
    try:
        existing = None
        cached = None
        with db() as c:
            cached = c.execute("SELECT * FROM messages WHERE request_id=? AND role='assistant' AND kind='chat'", (rid,)).fetchone()
            if cached:
                original = c.execute("SELECT * FROM messages WHERE role='user' AND kind='chat' AND id<? ORDER BY id DESC LIMIT 1", (cached['id'],)).fetchone()
                if not original or (retry_id is None and text != original['text']):
                    raise AppError('消息标识重复，请重新发送。', 409)
                if retry_id is not None and (isinstance(retry_id, bool) or not isinstance(retry_id, int) or retry_id != original['id'] or (text and text != original['text'])):
                    raise AppError('重试目标与消息标识不匹配。', 409)
                user = dict(original)
            elif retry_id is not None:
                last = c.execute("SELECT * FROM messages WHERE role='user' AND kind='chat' ORDER BY id DESC LIMIT 1").fetchone()
                if isinstance(retry_id, bool) or not isinstance(retry_id, int) or not last or last['id'] != retry_id:
                    raise AppError('只能重新回答最近一条消息。', 409)
                # A failed original request may already own this id; it cannot be
                # recycled as a retry for a different user turn.
                prior_user = c.execute("SELECT id FROM messages WHERE request_id=? AND role='user'", (rid,)).fetchone()
                if prior_user and prior_user['id'] != last['id']:
                    raise AppError('消息标识属于另一条消息。', 409)
                text, user = last['text'], dict(last)
            else:
                existing = c.execute("SELECT * FROM messages WHERE request_id=? AND role='user'", (rid,)).fetchone()
                if existing:
                    if existing['text'] != text:
                        raise AppError('消息标识重复，请重新发送。', 409)
                    latest = c.execute("SELECT max(id) FROM messages WHERE role='user' AND kind='chat'").fetchone()[0]
                    if existing['id'] != latest:
                        raise AppError('这条消息已过期，请重新回答最近一条。', 409)
                    user = dict(existing)
        # No invalid/colliding request may invalidate current media.
        try:
            with ACTIVE_LOCK:
                handle = GENERATIONS.begin(PRIVATE_SCOPE, rid)
                cancel = handle.cancel_event
                ACTIVE[rid] = cancel
        except GenerationCapacityError:
            raise AppError('生成状态已满，请稍后重试。', 503)
        if cached:
            if on_meta:
                on_meta({'user': user, 'request_id': rid, 'generation_id': handle.generation_id})
            with ACTIVE_LOCK:
                check_cancel(cancel)
                completed = GENERATIONS.complete(handle)
            return {'message': dict(cached), 'cached': True, 'generation_id': handle.generation_id, 'request_id': rid}
        if retry_id is None and not existing:
            with db() as c:
                cur = c.execute('INSERT INTO messages(role,text,created,request_id) VALUES(?,?,?,?)', ('user', text, now(), rid))
                user = dict(c.execute('SELECT * FROM messages WHERE id=?', (cur.lastrowid,)).fetchone())
        s=settings();messages=build_prompt(s,user['id'])
        if on_meta:on_meta({'user':user,'request_id':rid,'generation_id':handle.generation_id})
        check_cancel(cancel)
        if text.startswith(('记住：','记住:')):
            fact=text[3:].strip()
            if not fact:raise AppError('把想让我记住的事写在冒号后面。')
            if retry_id is None and not existing:
                add_memory(fact,'explicit-chat')
            answer='好，我记住了。'+('当前只聊当下，不会引用长期记忆。' if s['memory_mode']=='off' else '需要时再提起，不会每次都翻旧事。')
            if on_delta:on_delta(answer)
        else:answer=generate(s,messages,on_delta,cancel,on_status)
        # Cancellation and commit share a lock, so Stop never races a new saved answer.
        with ACTIVE_LOCK:
            check_cancel(cancel)
            with db() as c:
                if retry_id is not None:
                    c.execute("DELETE FROM messages WHERE id>? AND role='assistant' AND kind='chat'",(user['id'],))
                cur=c.execute('INSERT INTO messages(role,text,created,request_id) VALUES(?,?,?,?)',('assistant',answer,now(),rid))
                row=dict(c.execute('SELECT * FROM messages WHERE id=?',(cur.lastrowid,)).fetchone())
            completed = GENERATIONS.complete(handle)
        return {'message':row,'generation_id':handle.generation_id,'request_id':rid}
    except Cancelled:
        audit('generation_cancelled','user stopped; partial answer not saved')
        return {'cancelled':True,'generation_id':handle.generation_id if handle else None,'request_id':rid}
    finally:
        with ACTIVE_LOCK:
            if handle is not None and not completed:
                GENERATIONS.cancel(PRIVATE_SCOPE, generation_id=handle.generation_id, request_id=rid)
            ACTIVE.pop(rid,None)
        MODEL_LOCK.release()

def add_memory(text,source='manual'):
    text=str(text).strip()
    if not text or len(text)>300:raise AppError('每条记忆请输入 1–300 字。')
    with db() as c:
        if c.execute('SELECT count(*) FROM memories').fetchone()[0]>=60:raise AppError('记忆已达到初版上限 60 条，请先整理。')
        c.execute('INSERT INTO memories(text,created,source) VALUES(?,?,?)',(text,now(),source))
    audit('memory_added')

def quiet(s,stamp=None):
    hour=dt.datetime.fromtimestamp(stamp or time.time()).hour
    a,b=s['quiet_start'],s['quiet_end']
    if a==b:return False
    return (a<=hour<b) if a<b else (hour>=a or hour<b)

def local_day_start_utc(stamp):
    local=dt.datetime.fromtimestamp(stamp).astimezone()
    return local.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(dt.timezone.utc).isoformat(timespec='seconds')

def schedule(payload):
    title=str(payload.get('title','')).strip()
    delay=payload.get('minutes',25)
    if not title or len(title)>100:raise AppError('任务标题请输入 1–100 字。')
    if not isinstance(delay,(int,float)) or not 1/60<=delay<=10080:raise AppError('提醒时间范围是 1 秒到 7 天。')
    kind='study' if payload.get('kind')=='study' else 'reminder'
    if kind=='study' and not settings()['study']:raise AppError('先在设置中开启督学，或创建普通提醒。')
    with db() as c:c.execute('INSERT INTO tasks(title,due,status,created,kind) VALUES(?,?,?,?,?)',(title,time.time()+delay*60,'pending',now(),kind))
    audit('task_created',kind)

def change_task(payload,action):
    task_id=int(payload['id'])
    with DISPATCH_LOCK:
        with db() as c:
            row=c.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            if not row:raise AppError('约定不存在。',404)
            if action=='complete':
                if row['status']=='cancelled':raise AppError('已取消的约定不能标记完成。')
                c.execute("UPDATE tasks SET status='completed' WHERE id=?",(task_id,))
            elif action=='delay':
                minutes=payload.get('minutes',5)
                if not isinstance(minutes,(int,float)) or not 1<=minutes<=10080:raise AppError('延期范围为 1 分钟到 7 天。')
                if row['status'] in {'cancelled','completed'}:raise AppError('这个约定已经结束，请新建约定。')
                if row['kind']=='study' and not settings()['study']:raise AppError('督学已关闭，开启后才能重新约定。')
                c.execute("UPDATE tasks SET status='pending',due=? WHERE id=?",(time.time()+minutes*60,task_id))
            elif action=='cancel':
                c.execute("UPDATE tasks SET status='cancelled' WHERE id=? AND status IN ('pending','paused','quiet','done','expired')",(task_id,))
            else:raise AppError('约定操作不正确。')
    audit('task_'+action,f'task={task_id};user initiated')

def scheduler_tick(stamp=None):
    stamp=stamp or time.time();s=settings()
    with DISPATCH_LOCK:
        with db() as c:
            rows=c.execute("SELECT * FROM tasks WHERE status='pending' AND due<=?",(stamp,)).fetchall()
            for task in rows:
                if task['kind']=='study' and not s['study']:
                    c.execute("UPDATE tasks SET status='paused' WHERE id=?",(task['id'],));continue
                if quiet(s,stamp):
                    c.execute("UPDATE tasks SET status='quiet' WHERE id=?",(task['id'],));continue
                if stamp-task['due']>3600:
                    c.execute("UPDATE tasks SET status='expired' WHERE id=?",(task['id'],));continue
                content=f'到了约好的时间啦：{task["title"]}。准备好了就开始，晚一点也可以。'
                c.execute("INSERT INTO messages(role,text,created,kind) VALUES('assistant',?,?,'reminder')",(content,now()))
                c.execute("UPDATE tasks SET status='done' WHERE id=? AND status='pending'",(task['id'],))
                c.execute('INSERT INTO audit(event,detail,created) VALUES(?,?,?)',('reminder_shown',f'task={task["id"]};channel=in-app',now()))
        if s['proactive'] and not quiet(s,stamp):
            with db() as c:
                last=c.execute('SELECT created FROM messages ORDER BY id DESC LIMIT 1').fetchone()
                past=c.execute("SELECT count(*) FROM messages WHERE kind='proactive' AND created>=?",(local_day_start_utc(stamp),)).fetchone()[0]
                if last and stamp-dt.datetime.fromisoformat(last[0]).timestamp()>7200 and past<2:
                    greetings={
                        'daily':['路过留一句问候。希望你这会儿过得还不错。','有空的话，来随便聊聊吧。忙你的也没关系。'],
                        'listen':['如果今天有些话没地方说，可以在这里慢慢讲。','给你留个安静的位置。想说的时候，我在。'],
                        'playful':['今日份小小问候，轻轻放在这里。','想找个人分享一点小事的话，这里随时开门。'],
                    }
                    content=greetings.get(s.get('conversation_mode'),greetings['daily'])[past%2]
                    c.execute("INSERT INTO messages(role,text,created,kind) VALUES('assistant',?,?,'proactive')",(content,now()))

def scheduler_loop():
    while not STOP.wait(1):
        try:scheduler_tick()
        except Exception:audit('scheduler_error','tick failed')

def forget_digest(text):return hashlib.sha256(text.strip().encode()).hexdigest()

def synthesize(text):
    global LOCAL_VOICE,G2P
    if not isinstance(text,str) or not 1<=len(text)<=700:raise AppError('朗读文字需在 700 字以内。')
    path=VOICE_DIR/'kokoro-v1.0.onnx'
    voices=VOICE_DIR/'voices-v1.0.bin'
    if not path.exists() or not voices.exists() or not importlib.util.find_spec('kokoro_onnx'):
        raise AppError('未安装本地音色，请使用系统中文语音，或安装你有权使用的本地音色。',503)
    if not TTS_LOCK.acquire(False):raise AppError('上一段声音正在合成，请稍后重试。',409)
    try:
        if LOCAL_VOICE is None:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from kokoro_onnx import Kokoro
            from misaki import zh
            LOCAL_VOICE=Kokoro(str(path),str(voices))
            G2P=zh.ZHG2P()
        output=io.BytesIO()
        phonemes,_=G2P(text)
        samples,sample_rate=LOCAL_VOICE.create(phonemes,voice='zf_xiaobei',speed=settings()['voice_rate'],is_phonemes=True)
        import numpy as np
        pcm=(np.clip(samples,-1,1)*32767).astype('<i2').tobytes()
        with wave.open(output,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(sample_rate);wav.writeframes(pcm)
        return output.getvalue()
    except AppError:raise
    except Exception:raise AppError('本地语音合成失败，请切换系统音色。',503)
    finally:TTS_LOCK.release()

def restore(payload):
    backup=payload.get('backup')
    if not isinstance(backup,dict):raise AppError('不是有效的备份文件。')
    ms=backup.get('messages',[]);facts=backup.get('memories',[]);tasks=backup.get('tasks',[])
    if not all(isinstance(x,list) for x in [ms,facts,tasks]) or len(ms)>160 or len(facts)>60 or len(tasks)>60:
        raise AppError('备份结构或大小不正确。')
    for m in ms:
        if not isinstance(m,dict) or m.get('role') not in {'user','assistant'} or not isinstance(m.get('text'),str) or len(m['text'])>5000:raise AppError('聊天备份格式不正确。')
    for m in facts:
        if not isinstance(m,dict) or not isinstance(m.get('text'),str) or not 1<=len(m['text'])<=300:raise AppError('记忆备份格式不正确。')
    for t in tasks:
        if not isinstance(t,dict) or not isinstance(t.get('title'),str) or len(t['title'])>100 or not isinstance(t.get('due'),(int,float)):raise AppError('约定备份格式不正确。')
    if not MODEL_LOCK.acquire(False):raise AppError('请等当前回复结束后恢复。',409)
    try:
        with DISPATCH_LOCK:
            with db() as c:
                denied={r['digest'] for r in c.execute('SELECT digest FROM forgotten')}
                c.execute('DELETE FROM messages');c.execute('DELETE FROM memories');c.execute('DELETE FROM tasks')
                if not denied:
                    for m in ms:c.execute('INSERT INTO messages(role,text,created,kind) VALUES(?,?,?,?)',(m['role'],m['text'],now(),'chat'))
                for m in facts:
                    if forget_digest(m['text']) not in denied:c.execute('INSERT INTO memories(text,created,source) VALUES(?,?,?)',(m['text'],now(),'restore'))
                for t in tasks:
                    status='paused' if t.get('status') in {'pending','paused','quiet'} else (t['status'] if t.get('status') in {'done','completed','expired'} else 'cancelled')
                    c.execute('INSERT INTO tasks(title,due,status,created,kind) VALUES(?,?,?,?,?)',(t['title'],t['due'],status,now(),'study' if t.get('kind')=='study' else 'reminder'))
                profile=backup.get('settings',{})
                if isinstance(profile,dict):
                    for k in ['name','user_name','personality','character_notes']:
                        if isinstance(profile.get(k),str) and 0<len(profile[k])<=1200:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(profile[k],ensure_ascii=False)))
        audit('backup_restored',f'chat_skipped={bool(denied)}')
        return {'ok':True,'chat_skipped':bool(denied)}
    finally:MODEL_LOCK.release()

def state():
    s=settings()
    with db() as c:
        result={
            'settings':s,
            'messages':[dict(r) for r in c.execute('SELECT * FROM messages ORDER BY id DESC LIMIT 160')][::-1],
            'memories':[dict(r) for r in c.execute('SELECT * FROM memories ORDER BY id DESC')],
            'tasks':[dict(r) for r in c.execute('SELECT * FROM tasks ORDER BY id DESC LIMIT 60')],
        }
    with ACTIVE_LOCK:active_id=next(iter(ACTIVE),'')
    result.update({'version':VERSION,'model_status':MODEL_STATUS,'model_installed':MODEL.exists(),
                   'model_label':'Qwen3 4B' if MODEL.name==QUALITY_MODEL.name else 'Qwen2.5 1.5B · 轻量',
                   'runtime_installed':bool(importlib.util.find_spec('llama_cpp')),'has_api_key':bool(secret_key()),
                   'local_voice_available':(VOICE_DIR/'kokoro-v1.0.onnx').exists() and (VOICE_DIR/'voices-v1.0.bin').exists() and bool(importlib.util.find_spec('kokoro_onnx')),
                   'model_busy':MODEL_LOCK.locked(),'active_request_id':active_id,'timezone':str(dt.datetime.now().astimezone().tzinfo),
                   'wechat_available':False})
    return result

class Handler(BaseHTTPRequestHandler):
    server_version='Companion/'+VERSION
    def log_message(self,fmt,*args):
        # URL/请求体/密钥不写访问日志。
        pass
    def reply(self,status,data,ctype='application/json; charset=utf-8',cookie=False):
        body=json.dumps(data,ensure_ascii=False).encode() if ctype.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
        if cookie:self.send_header('Set-Cookie',f'companion={AUTH}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers();self.wfile.write(body)
    def allowed_host(self):
        host=self.headers.get('Host','').split(':')[0]
        return host in {'127.0.0.1','localhost'}
    def authenticated(self):
        try:
            cookie=http.cookies.SimpleCookie(self.headers.get('Cookie',''))
            return 'companion' in cookie and secrets.compare_digest(cookie['companion'].value,AUTH)
        except Exception:return False
    def stream_chat(self,payload):
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.close_connection=True
        def emit(kind,data):
            try:
                self.wfile.write(('data: '+json.dumps({'type':kind,**data},ensure_ascii=False)+'\n\n').encode())
                self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):raise Cancelled()
        try:
            result=chat(payload,lambda token:emit('delta',{'text':token}),lambda meta:emit('meta',meta),lambda stage:emit('status',stage))
            emit('done',result)
        except Cancelled:pass
        except AppError as e:
            with contextlib.suppress(Cancelled):emit('error',{'error':str(e),'status':e.status})
        except Exception:
            audit('stream_error','internal failure; partial not saved')
            with contextlib.suppress(Cancelled):emit('error',{'error':'回复中断，消息已保留，可以重新回答。','status':500})
    def do_GET(self):
        if not self.allowed_host():return self.reply(403,{'error':'此应用只允许本机访问。'})
        path=urllib.parse.urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self.authenticated():return self.reply(401,{'error':'请先打开应用首页。'})
            if path=='/api/state':return self.reply(200,state())
            if path=='/api/export':
                data=state();data.pop('has_api_key',None)
                self.reply(200,data);audit('data_exported','user initiated');return
            return self.reply(404,{'error':'接口不存在。'})
        if path=='/':path='/index.html'
        if path not in {'/index.html','/app.js','/style.css','/avatar.svg'}:return self.reply(404,b'Not found','text/plain')
        file=STATIC/path.lstrip('/')
        if not file.is_file():return self.reply(404,b'Not found','text/plain')
        self.reply(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream',cookie=path=='/index.html')
    def do_POST(self):
        if not self.allowed_host() or not self.authenticated():return self.reply(403,{'error':'访问未授权。'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
            return self.reply(403,{'error':'请求来源不正确。'})
        if self.headers.get('X-Companion')!='local-app':return self.reply(403,{'error':'缺少本机请求标识。'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            max_size=1_000_000 if urllib.parse.urlsplit(self.path).path=='/api/restore' else 20000
            if size<0 or size>max_size:raise AppError('请求过大。',413)
            data=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data,dict):raise AppError('请求格式不正确。')
            path=urllib.parse.urlsplit(self.path).path
            validate_private_scope(data)
            if path=='/api/speech':
                return self.reply(200,speech_for_payload(data),'audio/wav')
            elif path=='/api/chat/stream':return self.stream_chat(data)
            elif path=='/api/chat/stop':result=cancel_chat(data)
            elif path=='/api/chat':result=chat(data)
            elif path=='/api/settings':
                set_settings(data);result={'ok':True}
            elif path=='/api/memories':
                add_memory(data.get('text',''));result={'ok':True}
            elif path=='/api/memories/update':
                value=str(data.get('text','')).strip()
                if not value or len(value)>300:raise AppError('记忆请输入 1–300 字。')
                if not MODEL_LOCK.acquire(False):raise AppError('请等当前回复结束再修改记忆。',409)
                try:
                    with db() as c:
                        old=c.execute('SELECT text FROM memories WHERE id=?',(int(data['id']),)).fetchone()
                        if old:c.execute('INSERT OR IGNORE INTO forgotten VALUES(?,?)',(forget_digest(old['text']),now()))
                        c.execute('UPDATE memories SET text=?,source=? WHERE id=?',(value,'manual-correction',int(data['id'])))
                        c.execute("DELETE FROM messages WHERE kind='chat'")
                    audit('memory_corrected','chat context cleared')
                finally:MODEL_LOCK.release()
                result={'ok':True}
            elif path=='/api/memories/delete':
                if not data.get('clear_context'):raise AppError('忘记时需要同时清空当前对话上下文。')
                if not MODEL_LOCK.acquire(False):raise AppError('请等当前回复结束再忘记。',409)
                try:
                    with db() as c:
                        old=c.execute('SELECT text FROM memories WHERE id=?',(int(data['id']),)).fetchone()
                        if old:c.execute('INSERT OR IGNORE INTO forgotten VALUES(?,?)',(forget_digest(old['text']),now()))
                        c.execute('DELETE FROM memories WHERE id=?',(int(data['id']),))
                        c.execute("DELETE FROM messages WHERE kind='chat'")
                    audit('memory_deleted','chat context cleared')
                finally:MODEL_LOCK.release()
                result={'ok':True}
            elif path=='/api/tasks':schedule(data);result={'ok':True}
            elif path=='/api/restore':result=restore(data)
            elif path=='/api/tasks/cancel':
                change_task(data,'cancel');result={'ok':True}
            elif path=='/api/tasks/delay':change_task(data,'delay');result={'ok':True}
            elif path=='/api/tasks/complete':change_task(data,'complete');result={'ok':True}
            elif path=='/api/conversation/clear':
                if not MODEL_LOCK.acquire(False):raise AppError('请等当前回复结束再清空。',409)
                try:
                    with db() as c:c.execute('DELETE FROM messages')
                    audit('conversation_cleared')
                finally:MODEL_LOCK.release()
                result={'ok':True}
            else:raise AppError('接口不存在。',404)
            self.reply(200,result)
        except AppError as e:self.reply(e.status,{'error':str(e)})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.reply(400,{'error':'输入格式不正确。'})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            audit('request_error','internal error')
            self.reply(500,{'error':'处理失败，数据已保留。请重试或查看运行终端。'})

def main():
    parser=argparse.ArgumentParser(description='小岚 · 本地虚拟女友')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    init()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    threading.Thread(target=scheduler_loop,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'小岚 {VERSION} 已启动：{url}',flush=True)
    print('仅本机访问。关闭终端或按 Ctrl+C 停止；聊天和记忆保存在 data/。',flush=True)
    if not args.no_browser:
        import webbrowser
        webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:STOP.set();server.shutdown();server.server_close()

if __name__=='__main__':main()
