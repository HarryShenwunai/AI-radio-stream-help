"""Receipt ownership, interruption, expiry and concurrent terminal transitions."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from companion_runtime.playback import PlaybackError, PlaybackTracker, context_for, merge_receipts


class Clock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tracker = PlaybackTracker(clock=self.clock)
        self.full = "第一句是确实合成的。第二句仍未播放。"

    def begin(self, **kwargs):
        return self.tracker.begin("character-A", "skin-A", 1, self.full, **kwargs)

    def report(self, start, status, position, duration=4, **kwargs):
        return self.tracker.receipt(start["playback_id"], start["nonce"],
            character_id=start["character_id"], appearance_id=start["appearance_id"],
            position_seconds=position, duration_seconds=duration, status=status, **kwargs)

    def test_complete_confirms_full_text_but_does_not_claim_human_attention(self):
        start = self.begin(duration_seconds=4)
        self.assertNotIn(self.full, str(start))
        running = self.report(start, "playing", 1)
        self.assertEqual(running["confirmed_text"], "")
        completed = self.report(start, "completed", 4)
        self.assertEqual(completed["confirmed_text"], self.full)
        self.assertIn("not_human_attention", completed["evidence"])
        self.assertNotIn("nonce", completed)
        context = context_for(self.full, completed, message_id=1)
        self.assertTrue(context["applied"])
        self.assertFalse(context["truncated"])
        self.assertEqual(context["text"], self.full)

    def test_interruption_never_uses_position_to_guess_words(self):
        start = self.begin()
        self.report(start, "playing", 3.9)
        stopped = self.report(start, "stopped", 3.99)
        self.assertEqual(stopped["confirmed_text"], "")
        context = context_for(self.full, stopped)
        self.assertEqual(context["text"], "")
        self.assertTrue(context["truncated"] and context["interrupted"])
        self.assertEqual(self.full, "第一句是确实合成的。第二句仍未播放。")

    def test_completed_synthesized_prefix_leaves_unsynthesized_tail_out(self):
        prefix = "第一句是确实合成的。"
        start = self.begin(audible_text=prefix)
        complete = self.report(start, "completed", 4)
        self.assertEqual(complete["text_sha"], start["text_sha"])
        self.assertEqual(complete["confirmed_text"], prefix)
        self.assertTrue(complete["truncated"])
        context = context_for(self.full, complete)
        self.assertEqual(context["text"], prefix)
        self.assertTrue(context["truncated"])
        self.assertFalse(context["interrupted"])
        for invalid in ("not a prefix", "", 123):
            with self.assertRaises(PlaybackError):
                self.begin(audible_text=invalid)

    def test_nonce_owner_profile_appearance_and_message_binding(self):
        start = self.begin()
        variants = [{"nonce": "x" * 43}, {"owner_id": "other-browser"},
                    {"character_id": "character-B"}, {"appearance_id": "skin-B"},
                    {"message_id": 2}, {"playback_id": "unknown"}]
        for changes in variants:
            args = dict(playback_id=start["playback_id"], nonce=start["nonce"],
                character_id="character-A", appearance_id="skin-A", position_seconds=1,
                duration_seconds=4, status="playing")
            args.update(changes)
            with self.assertRaises(PlaybackError) as error:
                self.tracker.receipt(**args)
            self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.report(start, "completed", 4)["confirmed_text"], self.full)

    def test_nonfinite_negative_huge_boolean_and_invalid_status_rejected(self):
        start = self.begin()
        for value in (float("nan"), float("inf"), -1, 181, True, "1", 10**500):
            for field in ("position_seconds", "duration_seconds"):
                args = dict(playback_id=start["playback_id"], nonce=start["nonce"],
                    character_id="character-A", appearance_id="skin-A", position_seconds=1,
                    duration_seconds=4, status="playing")
                args[field] = value
                with self.assertRaises(PlaybackError):
                    self.tracker.receipt(**args)
        for status in ("heard", "pending", [], None):
            with self.assertRaises(PlaybackError):
                self.report(start, status, 1)

    def test_monotonic_duration_bound_and_premature_completion(self):
        start = self.begin(duration_seconds=4)
        self.report(start, "playing", 2)
        for status, position, duration in (("playing", 1, 4), ("playing", 5, 4),
            ("completed", 3.99, 4), ("completed", 4, 4.01), ("playing", 3, 6)):
            with self.assertRaises(PlaybackError):
                self.report(start, status, position, duration)
        self.assertEqual(self.report(start, "completed", 4)["status"], "completed")
        duplicate = self.report(start, "completed", 4)
        self.assertFalse(duplicate["should_persist"])

    def test_stopped_before_metadata_can_have_unknown_duration(self):
        start = self.begin()
        result = self.report(start, "stopped", 0, None)
        self.assertIsNone(result["duration_seconds"])
        self.assertEqual(result["confirmed_text"], "")
        with self.assertRaises(PlaybackError):
            self.report(start, "completed", 4)

    def test_new_playback_returns_original_scope_stopped_receipt(self):
        first = self.begin()
        second = self.tracker.begin("character-B", None, 2, "新角色的回答")
        stopped = second["stopped_receipts"]
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["character_id"], "character-A")
        self.assertEqual(stopped[0]["message_id"], 1)
        self.assertEqual(stopped[0]["confirmed_text"], "")
        late = self.report(first, "completed", 4)
        self.assertTrue(late["stale"])
        self.assertFalse(late["accepted"] or late["should_persist"])
        self.assertEqual(late["confirmed_text"], "")
        self.assertNotIn(self.full, str(late))
        self.assertEqual(self.report(second, "completed", 4)["confirmed_text"], "新角色的回答")

    def test_switch_away_and_back_never_revives_old_nonce_text(self):
        start = self.begin()
        stops = self.tracker.invalidate(character_id="character-A", appearance_id="skin-A", reason="switch")
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["status"], "stopped")
        again = self.begin()
        self.assertNotEqual(start["nonce"], again["nonce"])
        self.assertNotEqual(start["playback_id"], again["playback_id"])
        self.assertEqual(self.report(start, "completed", 4)["confirmed_text"], "")
        self.assertEqual(self.report(again, "completed", 4)["confirmed_text"], self.full)

    def test_expiry_is_absolute_and_capacity_does_not_cancel_another_owner(self):
        tracker = PlaybackTracker(max_entries=2, ttl_seconds=10, clock=self.clock)
        a = tracker.begin("A", None, 1, "a", owner_id="one")
        tracker.begin("B", None, 2, "b", owner_id="two")
        with self.assertRaises(PlaybackError) as error:
            tracker.begin("C", None, 3, "c", owner_id="three")
        self.assertEqual(error.exception.status, 429)
        self.clock.now += 9
        tracker.receipt(a["playback_id"], a["nonce"], owner_id="one", character_id="A", appearance_id=None,
                        status="playing", position_seconds=1, duration_seconds=4)
        self.clock.now += 1
        with self.assertRaises(PlaybackError) as error:
            tracker.receipt(a["playback_id"], a["nonce"], owner_id="one", character_id="A", appearance_id=None,
                            status="completed", position_seconds=4, duration_seconds=4)
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(tracker.size(), 0)

    def test_same_owner_capacity_can_reclaim_its_previous_entry(self):
        tracker = PlaybackTracker(max_entries=1)
        first = tracker.begin("A", None, 1, "a")
        second = tracker.begin("B", None, 2, "b")
        self.assertEqual(tracker.size(), 1)
        self.assertEqual(second["stopped_receipts"][0]["playback_id"], first["playback_id"])

    def test_replay_interruption_preserves_prior_full_confirmation(self):
        first = self.begin()
        full = self.report(first, "completed", 4)
        second = self.begin()
        stopped = self.report(second, "stopped", .5)
        merged = merge_receipts(full, stopped)
        self.assertEqual(merged["status"], "stopped")
        self.assertEqual(merged["confirmed_text"], self.full)
        self.assertFalse(context_for(self.full, merged)["truncated"])
        self.assertEqual(context_for(self.full, merged)["text"], self.full)

    def test_merge_retains_longest_server_prefix_and_rejects_wrong_binding(self):
        first = self.begin(audible_text=self.full[:5])
        short = self.report(first, "completed", 4)
        second = self.begin(audible_text=self.full[:10])
        longer = self.report(second, "completed", 4)
        self.assertEqual(merge_receipts(short, longer)["confirmed_text"], self.full[:10])
        self.assertEqual(merge_receipts(longer, short)["confirmed_text"], self.full[:10])
        for field, value in (("character_id", "B"), ("message_id", 99), ("text_sha", "x" * 64), ("confirmed_text", "unrelated")):
            bad = dict(longer, **{field: value})
            with self.assertRaises(PlaybackError):
                merge_receipts(short, bad)

    def test_context_sha_id_and_prefix_mismatch_leave_chat_unchanged(self):
        start = self.begin()
        stop = self.report(start, "stopped", 1)
        for bad in (None, {}, dict(stop, text_sha="x" * 64), dict(stop, confirmed_text="wrong"),
                    dict(stop, status=[]), dict(stop, message_id=None)):
            result = context_for(self.full, bad, message_id=1)
            self.assertEqual(result["text"], self.full)
            self.assertFalse(result["applied"])

    def test_racing_complete_and_invalidate_have_one_terminal_outcome(self):
        for _ in range(20):
            tracker = PlaybackTracker()
            start = tracker.begin("A", None, 1, self.full)
            barrier = threading.Barrier(2)
            def complete():
                barrier.wait()
                return tracker.receipt(start["playback_id"], start["nonce"], character_id="A", appearance_id=None,
                    status="completed", position_seconds=4, duration_seconds=4)
            def invalidate():
                barrier.wait()
                return tracker.invalidate(character_id="A", reason="new_chat")
            with ThreadPoolExecutor(2) as pool:
                a, b = pool.submit(complete), pool.submit(invalidate)
                receipt, stops = a.result(), b.result()
            if receipt["accepted"]:
                self.assertEqual(receipt["confirmed_text"], self.full)
                self.assertEqual(stops, [])
            else:
                self.assertTrue(receipt["stale"])
                self.assertEqual(receipt["confirmed_text"], "")
                self.assertEqual(len(stops), 1)
            late = tracker.receipt(start["playback_id"], start["nonce"], character_id="A", appearance_id=None,
                status="completed", position_seconds=4, duration_seconds=4)
            self.assertTrue(late["stale"])
            self.assertEqual(late["confirmed_text"], "")

    def test_parallel_begins_and_receipts_remain_bounded(self):
        tracker = PlaybackTracker(max_entries=8)
        with ThreadPoolExecutor(8) as pool:
            starts = list(pool.map(lambda i: tracker.begin("A", None, i + 1, "text"), range(40)))
        self.assertLessEqual(tracker.size(), 8)
        self.assertEqual(len({s["playback_id"] for s in starts}), 40)
        # Executor result order is submission order; find the sole current token
        # from receipt acceptance instead of assuming thread scheduling order.
        accepted = 0
        for s in starts:
            try:
                r = tracker.receipt(s["playback_id"], s["nonce"], character_id="A", appearance_id=None,
                    status="playing", position_seconds=1, duration_seconds=4)
                accepted += r["accepted"]
            except PlaybackError as error:
                self.assertEqual(error.status, 404)
        self.assertEqual(accepted, 1)


if __name__ == "__main__":
    unittest.main()
