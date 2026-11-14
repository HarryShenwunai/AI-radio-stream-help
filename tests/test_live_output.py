"""Deterministic state-boundary tests; synthetic events, not platform delivery."""
import unittest
from companion_runtime.live_output import LiveOutput, OutputError


class LiveOutputTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.output = LiveOutput(clock=lambda:self.now)
        self.output.set_material('M1: f(x)=x², f′(x)=2x.', True)
        self.event = {'source':'bilibili-open-live','room_id':'123','event_id':'e1','text':'x=3时斜率？','expires_at':130.}
        self.auth = 'Bearer '+self.output.open()

    def reviewed(self):
        job = self.output.begin(self.event)
        return self.output.finish(job['id'], '根据M1，f′(3)=6。', 'generation-1')

    def ready(self):
        job = self.reviewed()
        self.output.prepare(job['id'], True)
        self.output.ready(job['id'], b'fixture-wave')
        return job

    def test_no_output_without_manual_confirmation(self):
        job = self.reviewed()
        self.assertIsNone(self.output.poll(self.auth, 'client-one')['item'])
        with self.assertRaises(OutputError):self.output.prepare(job['id'], False)

    def test_duplicate_event_and_approval_and_completion_rejected(self):
        job = self.ready()
        with self.assertRaises(OutputError):self.output.begin(self.event)
        with self.assertRaises(OutputError):self.output.prepare(job['id'], True)
        self.output.poll(self.auth, 'client-one')
        self.output.receipt(self.auth, job['id'], 'client-one', 'playing')
        result = self.output.receipt(self.auth, job['id'], 'client-one', 'completed')
        self.assertFalse(result['delivered'])
        with self.assertRaises(OutputError):self.output.receipt(self.auth, job['id'], 'client-one', 'completed')
        self.assertIsNone(self.output.poll(self.auth, 'client-one')['item'])

    def test_cancel_invalidates_late_generation_audio_and_token(self):
        job = self.reviewed();self.output.prepare(job['id'], True);self.output.cancel()
        with self.assertRaises(OutputError):self.output.ready(job['id'], b'late')
        with self.assertRaises(OutputError):self.output.poll(self.auth, 'client-one')
        self.assertEqual(self.output.jobs[job['id']]['state'], 'cancelled')

    def test_changed_material_rejects_old_result(self):
        job = self.output.begin(self.event)
        self.output.set_material('另一章', True)
        with self.assertRaises(OutputError):self.output.finish(job['id'], '旧章答案', 'late')

    def test_expiration_and_disconnected_consumer_never_replay(self):
        job = self.ready();self.output.poll(self.auth, 'client-one')
        self.assertIsNone(self.output.poll(self.auth, 'client-two')['item'])
        self.now += 3
        self.assertIsNone(self.output.poll(self.auth, 'client-two')['item'])
        self.assertEqual(self.output.jobs[job['id']]['state'], 'failed')
        self.event['event_id'] = 'e2';job = self.ready();self.now = 131
        self.assertIsNone(self.output.poll(self.auth, 'client-one')['item'])
        self.assertEqual(self.output.jobs[job['id']]['state'], 'expired')

    def test_claim_does_not_allow_another_client_to_read_audio(self):
        job = self.ready();self.output.poll(self.auth, 'client-one')
        with self.assertRaises(OutputError):self.output.audio(self.auth, job['id'], 'client-two')
        with self.assertRaises(OutputError):self.output.receipt(self.auth, job['id'], 'client-two', 'playing')

    def test_expired_audio_without_a_consumer_cannot_block_next_approval(self):
        first=self.ready();self.now=131
        self.event.update(event_id='fresh',expires_at=161)
        second=self.reviewed()
        self.output.prepare(second['id'],True)
        self.assertEqual(self.output.jobs[first['id']]['state'],'expired')
        self.assertNotIn('audio',self.output.jobs[first['id']])

    def test_status_reaps_expired_review_and_lost_consumer(self):
        job=self.ready();self.output.poll(self.auth,'client-one')
        self.output.receipt(self.auth,job['id'],'client-one','playing')
        self.now+=3
        self.assertEqual(self.output.status()['jobs'][0]['state'],'failed')
        self.event.update(event_id='second',expires_at=110)
        job=self.reviewed();self.now=111
        self.assertEqual(self.output.status()['jobs'][-1]['state'],'expired')

    def test_invalid_material_cannot_cancel_existing_output(self):
        job=self.ready();session=self.output.session
        with self.assertRaises(OutputError):self.output.set_material('\ud800',True)
        self.assertEqual(self.output.session,session)
        self.assertEqual(self.output.jobs[job['id']]['state'],'ready')

    def test_known_bad_missing_cancel_mutant_is_rejected_by_invariant(self):
        job = self.reviewed();self.output.prepare(job['id'], True)
        self.output.cancel = lambda:None  # negative control: deliberately broken cancellation
        self.output.cancel();self.output.ready(job['id'], b'late')
        with self.assertRaises(AssertionError):
            self.assertEqual(self.output.jobs[job['id']]['state'], 'cancelled')

if __name__ == '__main__':unittest.main()
