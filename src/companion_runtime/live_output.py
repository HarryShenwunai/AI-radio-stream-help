"""Manually approved, ephemeral public output. No platform delivery claims.

One claimed output is never automatically replayed after browser failure.
Deadlines use a monotonic clock; tokens never grant access to private context.
"""
from collections import deque
import hashlib
import secrets
import threading
import time


class OutputError(ValueError):
    pass


class LiveOutput:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.session = secrets.token_hex(16)
        self.material = None
        self.jobs = {}
        self.seen = set()
        self.token = None
        self.audit = deque(maxlen=500)

    def transition(self, job, state):
        job['state'] = state
        self.audit.append({'id': job['id'], 'state': state, 'at': self.clock()})

    def cancel(self):
        with self.lock:
            for job in self.jobs.values():
                if job['state'] not in {'completed', 'cancelled', 'expired', 'failed'}:
                    self.transition(job, 'cancelled')
                job.pop('audio', None)
            self.session = secrets.token_hex(16)
            self.token = None

    def set_material(self, text, approved):
        if approved is not True or not isinstance(text, str) or not 1 <= len(text.strip()) <= 8000:
            raise OutputError('需要明确允许公开的教材（1–8000字符）。')
        try:digest = hashlib.sha256(text.strip().encode('utf-8')).hexdigest()
        except UnicodeError:raise OutputError('教材含无效字符，原教材未修改。')
        with self.lock:
            self.cancel()
            self.material = {'text': text.strip(), 'sha256': digest}
            return dict(self.material)

    def begin(self, event):
        with self.lock:
            if not self.material:raise OutputError('请先设置允许公开的教材。')
            key = (event['source'], event['room_id'], event['event_id'])
            if key in self.seen:raise OutputError('本场次已处理此问题，请勿重复生成或播放。')
            if event['expires_at'] <= self.clock():raise OutputError('问题已过期。')
            if len(self.jobs) >= 100:raise OutputError('本场次已达到100条记录上限，请重新连接直播间。')
            self.seen.add(key)
            job = {'id': secrets.token_hex(16), 'session': self.session, 'event_id': event['event_id'],
                   'room_id': event['room_id'], 'source': event['source'], 'question': event['text'],
                   'expires_at': event['expires_at'], 'material_sha256': self.material['sha256'],
                   'material': self.material['text'], 'state': 'generating', 'delivered': False}
            self.jobs[job['id']] = job
            self.transition(job, 'generating')
            return dict(job)

    def reap(self):
        """Called under the owner lock, even when no output consumer is polling."""
        now = self.clock()
        for job in self.jobs.values():
            if job['state'] in {'completed', 'cancelled', 'expired', 'failed'}:continue
            if job['expires_at'] <= now:
                self.transition(job, 'expired');job.pop('audio', None)
            elif job['state'] in {'claimed', 'playing'} and now-job['heartbeat'] > 2:
                job['failure_reason'] = 'consumer_timeout'
                self.fail(job['id'])

    def current(self, ident, state):
        self.reap()
        job = self.jobs.get(ident)
        if not job or job['session'] != self.session or job['state'] != state:
            raise OutputError('输出已取消、已使用或状态不匹配。')
        if job['expires_at'] <= self.clock():
            self.transition(job, 'expired');job.pop('audio', None)
            raise OutputError('问题已过期，不再输出。')
        return job

    def finish(self, ident, text, generation_id):
        with self.lock:
            job = self.current(ident, 'generating')
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 700:raise OutputError('回答需为1–700字符。')
            job.update(text=text, generation_id=generation_id, mode='local_preview')
            self.transition(job, 'review')
            return self.public(job)

    def prepare(self, ident, confirmed):
        with self.lock:
            if confirmed is not True:raise OutputError('需要主播逐条确认字幕与语音输出。')
            if not self.token:raise OutputError('请先打开本机输出页。')
            job = self.current(ident, 'review')
            if any(j['state'] in {'synthesizing', 'ready', 'claimed', 'playing'} for j in self.jobs.values()):
                raise OutputError('上一条输出未结束，请等待或停止。')
            self.transition(job, 'synthesizing')
            return job['text']

    def ready(self, ident, audio):
        with self.lock:
            job = self.current(ident, 'synthesizing')
            if not isinstance(audio, bytes) or not audio or len(audio) > 20_000_000:raise OutputError('音频无效。')
            job['audio'] = audio
            self.transition(job, 'ready')
            return self.public(job)

    def fail(self, ident):
        with self.lock:
            job = self.jobs.get(ident)
            if job and job['state'] not in {'completed', 'cancelled', 'expired', 'failed'}:
                self.transition(job, 'failed');job.pop('audio', None)

    def open(self):
        with self.lock:
            if not self.token:self.token = secrets.token_urlsafe(32)
            return self.token

    def authenticate(self, authorization):
        if not self.token or not secrets.compare_digest(authorization or '', 'Bearer '+self.token):
            raise OutputError('输出会话未授权或已停止。')

    def poll(self, authorization, client):
        with self.lock:
            self.authenticate(authorization)
            if not isinstance(client, str) or not 8 <= len(client) <= 100:raise OutputError('输出客户端标识无效。')
            for job in self.jobs.values():
                if job['state'] in {'ready', 'claimed', 'playing'}:
                    try:self.current(job['id'], job['state'])
                    except OutputError:continue
                    if job['state'] in {'claimed', 'playing'}:
                        if self.clock() - job['heartbeat'] > 2:
                            self.fail(job['id']);continue
                        if job['client'] != client:return {'item': None}
                    else:
                        job['client'] = client
                        self.transition(job, 'claimed')
                    job['heartbeat'] = self.clock()
                    return {'item': self.public(job)}
            return {'item': None}

    def audio(self, authorization, ident, client):
        with self.lock:
            self.authenticate(authorization)
            job = self.current(ident, 'claimed')
            if job['client'] != client:raise OutputError('非当前输出客户端。')
            return job['audio']

    def receipt(self, authorization, ident, client, state):
        with self.lock:
            self.authenticate(authorization)
            job = self.jobs.get(ident)
            if not job or job.get('client') != client:raise OutputError('非当前输出客户端。')
            allowed = {'claimed': {'playing', 'failed'}, 'playing': {'completed', 'failed'}}
            if state not in allowed.get(job['state'], set()):raise OutputError('播放状态不匹配。')
            self.current(ident, job['state'])
            self.transition(job, state)
            if state in {'completed', 'failed'}:job.pop('audio', None)
            return self.public(job)

    @staticmethod
    def public(job):
        return {k:v for k,v in job.items() if k not in {'audio', 'client', 'heartbeat', 'material'}}

    def status(self):
        with self.lock:
            self.reap()
            return {'session': self.session, 'material': self.material,
                    'jobs': [self.public(j) for j in self.jobs.values()], 'audit': list(self.audit),
                    'viewer_received': False, 'output_open': bool(self.token)}
