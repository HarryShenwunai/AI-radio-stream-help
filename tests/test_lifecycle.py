"""Lifecycle invariants exercised with synthetic scopes, no provider connection."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from uuid import UUID

from companion_runtime.lifecycle import (
    GenerationCapacityError, GenerationHandle, GenerationRegistry, Scope,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.private = Scope("private", "fixture-private")
        self.other = Scope("private", "fixture-other")
        self.live = Scope("live", "fixture-private")
        self.clock = FakeClock()
        self.registry = GenerationRegistry(max_entries=4, retention_seconds=10, clock=self.clock)

    def test_fresh_attempts_have_distinct_uuid_and_latest_is_current(self):
        first = self.registry.begin(self.private, "same-request")
        second = self.registry.begin(self.private, "same-request")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(UUID(first.id).version, 4)
        self.assertTrue(first.cancel_event.is_set())
        self.assertFalse(self.registry.is_current(first))
        self.assertIs(self.registry.current(self.private), second)

    def test_scope_isolation_covers_channel_and_session(self):
        handle = self.registry.begin(self.private, "r")
        for scope in (self.other, self.live):
            self.assertEqual(self.registry.cancel(scope, generation_id=handle.id), "not_found")
            self.assertEqual(self.registry.cancel(scope, request_id="r"), "not_found")
            self.assertIsNone(self.registry.resolve(scope, generation_id=handle.id))
        self.assertFalse(handle.cancel_event.is_set())
        self.assertTrue(self.registry.is_current(handle))

    def test_both_ids_must_match_before_cancel(self):
        handle = self.registry.begin(self.private, "first")
        self.assertEqual(self.registry.cancel(self.private, generation_id=handle.id, request_id="wrong"), "not_found")
        self.assertTrue(self.registry.is_current(handle))
        self.assertIsNone(self.registry.resolve(self.private, generation_id=handle.id, request_id="wrong"))

    def test_completion_allows_media_but_explicit_cancel_rejects_late_media(self):
        handle = self.registry.begin(self.private, "r")
        self.assertTrue(self.registry.complete(handle))
        self.assertIs(self.registry.resolve(self.private, generation_id=handle.id, request_id="r"), handle)
        self.assertEqual(self.registry.cancel(self.private, generation_id=handle.id), "accepted")
        self.assertIsNone(self.registry.current(self.private))
        self.assertFalse(self.registry.complete(handle))
        self.assertEqual(self.registry.cancel(self.private, request_id="r"), "already_done")

    def test_unknown_and_expired_ids_do_not_revive(self):
        handle = self.registry.begin(self.private, "r")
        self.assertEqual(self.registry.cancel(self.private, generation_id="missing"), "not_found")
        self.registry.complete(handle)
        self.clock.value = 9.999
        self.assertTrue(self.registry.is_current(handle))
        self.clock.value = 10
        self.assertFalse(self.registry.is_current(handle))
        self.assertTrue(handle.cancel_event.is_set())
        self.assertEqual(self.registry.cancel(self.private, generation_id=handle.id), "not_found")
        self.assertEqual(len(self.registry), 0)

    def test_repeat_completion_does_not_extend_media_lease(self):
        handle = self.registry.begin(self.private, "r")
        self.registry.complete(handle)
        self.clock.value = 9
        self.assertTrue(self.registry.complete(handle))
        self.clock.value = 10
        self.assertFalse(self.registry.is_current(handle))

    def test_running_generation_does_not_expire_to_free_cache(self):
        registry = GenerationRegistry(max_entries=1, retention_seconds=10, clock=self.clock)
        handle = registry.begin(self.private, "r")
        self.clock.value = 1000
        with self.assertRaises(GenerationCapacityError):
            registry.begin(self.other, "other")
        self.assertTrue(registry.is_current(handle))
        self.assertFalse(handle.cancel_event.is_set())

    def test_capacity_does_not_evict_valid_completed_media(self):
        registry = GenerationRegistry(max_entries=1, retention_seconds=10, clock=self.clock)
        handle = registry.begin(self.private, "r")
        registry.complete(handle)
        with self.assertRaises(GenerationCapacityError):
            registry.begin(self.live, "other")
        self.assertTrue(registry.is_current(handle))
        self.clock.value = 10
        self.assertIsNotNone(registry.begin(self.live, "other"))

    def test_same_scope_replacement_and_tombstones_stay_bounded(self):
        registry = GenerationRegistry(max_entries=1)
        first = registry.begin(self.private, "r")
        for i in range(100):
            handle = registry.begin(self.private, f"r-{i}")
            self.assertLessEqual(len(registry), 1)
        self.assertTrue(first.cancel_event.is_set())
        self.assertTrue(registry.is_current(handle))

    def test_cancelled_tombstone_can_be_evicted_without_harming_other_scope(self):
        registry = GenerationRegistry(max_entries=2)
        private = registry.begin(self.private, "private")
        other = registry.begin(self.other, "other")
        registry.cancel(self.private, generation_id=private.id)
        live = registry.begin(self.live, "live")
        self.assertTrue(registry.is_current(other))
        self.assertTrue(registry.is_current(live))
        self.assertEqual(len(registry), 2)

    def test_concurrent_cancel_wins_over_late_completion(self):
        handle = self.registry.begin(self.private, "r")
        release = threading.Event()
        started = threading.Event()

        def late_worker():
            started.set()
            self.assertTrue(release.wait(2))
            return self.registry.complete(handle), self.registry.is_current(handle)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(late_worker)
            self.assertTrue(started.wait(2))
            self.registry.cancel(self.private, generation_id=handle.id)
            release.set()
            self.assertEqual(future.result(timeout=2), (False, False))

    def test_concurrent_replacement_has_only_one_usable_handle(self):
        registry = GenerationRegistry(max_entries=8)
        barrier = threading.Barrier(8)

        def begin(i):
            barrier.wait(timeout=3)
            return registry.begin(self.private, f"r-{i}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            handles = list(executor.map(begin, range(8)))
        self.assertEqual(sum(registry.is_current(h) for h in handles), 1)
        self.assertEqual(sum(not h.cancel_event.is_set() for h in handles), 1)
        self.assertLessEqual(len(registry), 8)

    def test_matching_ids_cannot_forge_handle_identity(self):
        handle = self.registry.begin(self.private, "r")
        forged = GenerationHandle(handle.id, handle.request_id, handle.scope)
        self.assertFalse(self.registry.is_current(forged))
        self.assertFalse(self.registry.complete(forged))
        self.assertTrue(self.registry.is_current(handle))

    def test_direct_cooperative_event_is_respected(self):
        handle = self.registry.begin(self.private, "r")
        handle.cancel_event.set()
        self.assertIsNone(self.registry.current(self.private))
        self.assertFalse(self.registry.complete(handle))
        self.assertEqual(self.registry.cancel(self.private, request_id="r"), "already_done")

    def test_validation_has_no_state_side_effects(self):
        for scope in (("private", ""), ("private", " " * 3), ("admin", "session")):
            with self.assertRaises(ValueError):
                Scope(*scope)
        for kwargs in ({"max_entries": 0}, {"max_entries": True}, {"retention_seconds": 0},
                       {"retention_seconds": float("nan")}, {"retention_seconds": float("inf")}):
            with self.assertRaises(ValueError):
                GenerationRegistry(**kwargs)
        with self.assertRaises(TypeError):
            self.registry.begin({"channel": "private", "session_id": "r"}, "r")
        with self.assertRaises(ValueError):
            self.registry.begin(self.private, "")
        with self.assertRaises(ValueError):
            self.registry.cancel(self.private)
        self.assertEqual(len(self.registry), 0)


if __name__ == "__main__":
    unittest.main()
