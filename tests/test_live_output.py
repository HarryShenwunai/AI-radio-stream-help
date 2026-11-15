"""Deterministic state-boundary tests; synthetic events, not platform delivery."""
import io
import struct
import unittest
import wave
from companion_runtime.live_output import LiveOutput, OutputError


def pcm_wav(frames=16000, rate=8000, channels=1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(channels);wav.setsampwidth(2);wav.setframerate(rate)
        wav.writeframes(b'\0' * (frames * channels * 2))
    return out.getvalue()


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
        self.output.ready(job['id'], pcm_wav())
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

    def test_ready_rejects_audio_that_cannot_finish_before_deadline(self):
        job = self.reviewed();self.output.prepare(job['id'], True);self.now = 129
        with self.assertRaises(OutputError):self.output.ready(job['id'], pcm_wav())
        failed = self.output.status()['jobs'][0]
        self.assertEqual(failed['state'], 'failed')
        self.assertEqual(failed['failure_reason'], 'insufficient_playback_budget')
        self.assertEqual(failed['audio_duration_seconds'], 2)
        self.assertEqual(failed['playback_budget_remaining_seconds'], 1)
        self.assertNotIn('audio', self.output.jobs[job['id']])

    def test_budget_equality_rejected_but_one_frame_more_is_enough(self):
        for remaining, allowed in [(2, False), (2 - 1/8000, False), (2 + 1/8000, True)]:
            with self.subTest(remaining=remaining):
                self.setUp();job = self.reviewed();self.output.prepare(job['id'], True)
                self.now = 130 - remaining
                if allowed:
                    self.output.ready(job['id'], pcm_wav())
                    self.assertEqual(self.output.jobs[job['id']]['state'], 'ready')
                else:
                    with self.assertRaises(OutputError):self.output.ready(job['id'], pcm_wav())

    def test_claim_rechecks_budget_after_ready_wait(self):
        job = self.ready();self.now = 128
        self.assertIsNone(self.output.poll(self.auth, 'client-one')['item'])
        self.assertEqual(self.output.jobs[job['id']]['state'], 'failed')
        self.assertEqual(self.output.jobs[job['id']]['failure_reason'], 'insufficient_playback_budget')
        self.assertNotIn('audio', self.output.jobs[job['id']])

    def test_audio_delivery_rechecks_budget_after_claim_wait(self):
        job = self.ready();self.now = 127;self.output.poll(self.auth, 'client-one');self.now = 128
        with self.assertRaises(OutputError):self.output.audio(self.auth, job['id'], 'client-one')
        self.assertEqual(self.output.jobs[job['id']]['state'], 'failed')
        self.assertEqual(self.output.jobs[job['id']]['failure_reason'], 'insufficient_playback_budget')
        self.assertNotIn('audio', self.output.jobs[job['id']])

    def test_playing_heartbeat_does_not_reapply_full_track_budget(self):
        job = self.ready();self.now = 127;self.output.poll(self.auth, 'client-one')
        self.assertEqual(self.output.audio(self.auth, job['id'], 'client-one'), pcm_wav())
        self.output.receipt(self.auth, job['id'], 'client-one', 'playing');self.now = 128.5
        self.assertEqual(self.output.poll(self.auth, 'client-one')['item']['state'], 'playing')
        self.now = 129.5
        self.assertEqual(self.output.receipt(self.auth, job['id'], 'client-one', 'completed')['state'], 'completed')

    def test_invalid_wav_never_bypasses_duration_validation(self):
        valid = pcm_wav()
        float_wav = bytearray(valid);struct.pack_into('<H', float_wav, 20, 3)
        duplicate = valid + b'data' + struct.pack('<I', 2) + b'\0\0'
        duplicate = duplicate[:4] + struct.pack('<I', len(duplicate)-8) + duplicate[8:]
        for audio in (b'fixture-wave', pcm_wav(80, 8000), valid[:-1], valid+b'extra', bytes(float_wav), duplicate,
                      b'x' * 20_000_001):
            with self.subTest(length=len(audio)):
                self.setUp();job = self.reviewed();self.output.prepare(job['id'], True)
                with self.assertRaises(OutputError):self.output.ready(job['id'], audio)
                self.assertEqual(self.output.jobs[job['id']]['state'], 'failed')
                self.assertEqual(self.output.jobs[job['id']]['failure_reason'], 'invalid_audio')
                self.assertNotIn('audio', self.output.jobs[job['id']])

    def test_external_tts_supported_stereo_96khz_is_parsed(self):
        job = self.reviewed();self.output.prepare(job['id'], True)
        self.output.ready(job['id'], pcm_wav(96000, 96000, 2))
        self.assertEqual(self.output.status()['jobs'][0]['audio_duration_seconds'], 1)

    def test_cancel_and_expiry_win_over_late_budget_rejection(self):
        for terminal in ('cancelled', 'expired'):
            with self.subTest(terminal=terminal):
                self.setUp();job = self.reviewed();self.output.prepare(job['id'], True)
                if terminal == 'cancelled':self.output.cancel()
                else:self.now = 131
                with self.assertRaises(OutputError):self.output.ready(job['id'], pcm_wav())
                self.assertEqual(self.output.jobs[job['id']]['state'], terminal)
                self.assertNotIn('failure_reason', self.output.jobs[job['id']])

    def test_known_bad_always_fits_mutant_is_rejected_by_same_budget_invariant(self):
        job = self.reviewed();self.output.prepare(job['id'], True);self.now = 129
        self.output._playback_fits = lambda job, remaining: True
        with self.assertRaises(AssertionError):
            with self.assertRaises(OutputError):self.output.ready(job['id'], pcm_wav())

    def test_known_bad_missing_cancel_mutant_is_rejected_by_invariant(self):
        job = self.reviewed();self.output.prepare(job['id'], True)
        self.output.cancel = lambda:None  # negative control: deliberately broken cancellation
        self.output.cancel();self.output.ready(job['id'], pcm_wav())
        with self.assertRaises(AssertionError):
            self.assertEqual(self.output.jobs[job['id']]['state'], 'cancelled')

if __name__ == '__main__':unittest.main()
