"""Bounded exhaustive execution of real manager methods, not a full proof."""
import base64
import io
import itertools
import unittest
from PIL import Image
from companion_runtime.perception import PerceptionManager, PerceptionScope, PerceptionError


class ProtocolFixture:
    calls=0
    def status(self):return {'configured':True,'processing':'local','inference_verified':False}
    def describe(self,image,mime,prompt,cancel):
        self.calls+=1;return 'Explicit synthetic fixture; no semantic vision.'


class BoundedStateSpace(unittest.TestCase):
    def test_1296_traces_5184_operations_keep_owner_epoch_and_stop_boundaries(self):
        data=io.BytesIO();Image.new('RGB',(2,2),'white').save(data,format='PNG')
        encoded=base64.b64encode(data.getvalue()).decode()
        alphabet=('start','frame','stop','switch','disable','enable')
        count=0
        for trace in itertools.product(alphabet,repeat=4):
            scope=[PerceptionScope('owner','role','appearance',0)]
            now=[100.0]
            provider=ProtocolFixture()
            manager=PerceptionManager(provider,clock=lambda:now[0],wall_clock=lambda:200.,
                is_scope_current=lambda candidate:candidate==scope[0])
            sid=None
            stopped=set()
            for index,action in enumerate(trace):
                count+=1;now[0]+=2
                if action=='switch':
                    # ABA has the same display role, but a strictly new epoch.
                    scope[0]=PerceptionScope('owner','role','appearance',scope[0].epoch+1)
                elif action=='disable':manager.configure(None)
                elif action=='enable':manager.configure(provider)
                elif action=='start':
                    try:sid=manager.start(scope[0],'screen',consent_confirmed=True)['session_id']
                    except PerceptionError as error:self.assertEqual(error.code,'vision_not_configured',trace)
                elif action=='stop' and sid:
                    manager.stop('owner',sid);stopped.add(sid)
                elif action=='frame' and sid:
                    before=provider.calls
                    session=manager._sessions.get(sid)
                    allowed=(session is not None and sid not in stopped and not session.cancelled.is_set()
                             and session.scope==scope[0])
                    try:
                        result=manager.frame(scope[0],session_id=sid,request_id='f'+str(index),
                            image_base64=encoded,mime_type='image/png',captured_at_ms=200000)
                        self.assertTrue(allowed,trace)
                        self.assertFalse(result['retained'],trace)
                    except PerceptionError:
                        self.assertFalse(allowed,trace)
                        self.assertEqual(provider.calls,before,trace)
                self.assertLessEqual(len(manager._sessions),manager.limits.max_sessions,trace)
        self.assertEqual(count,5184)


if __name__=='__main__':unittest.main()
