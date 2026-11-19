from __future__ import annotations

import unittest

import numpy as np

from bounded_pipeline import (
    AudioChunk,
    BoundedAudioQueue,
    BoundedGTCRNPipeline,
    OfferResult,
    QueueItem,
)


class FakeAdapter:
    max_chunk_samples = 4096
    n_fft = 512

    def __init__(self, *, fail_calls=()):
        self.fail_calls = set(fail_calls)
        self.calls = 0
        self.closed = False
        self.state_sum = 0.0

    def process_chunk(self, audio, *, final=False):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise RuntimeError("synthetic consumer fault")
        self.state_sum += float(np.sum(audio))
        self.closed = bool(final)
        return np.asarray(audio, dtype=np.float32).copy()

    def reset_session(self):
        self.closed = False
        self.state_sum = 0.0


def chunk(session, start, n, *, final=False, value=0.25, arrival=0.0):
    return AudioChunk(
        session, start, np.full(n, value, dtype=np.float32), arrival, final
    )


def pipeline(adapter=None, *, session="A", cap=1024, play=1536, max_chunk=1024):
    return BoundedGTCRNPipeline(
        adapter or FakeAdapter(), session_id=session,
        capture_capacity_samples=cap, playback_capacity_samples=play,
        max_chunk_samples=max_chunk,
    )


class BoundedQueueTests(unittest.TestCase):
    def test_long_telemetry_retention_is_bounded(self):
        q = BoundedAudioQueue("bounded_telemetry", 1)
        for i in range(5000):
            item = QueueItem("A", i, np.zeros(1, np.float32), float(i))
            self.assertTrue(q.try_put(item, float(i)))
            q.pop(float(i) + 0.25)
        stats = q.telemetry(5000.0)
        self.assertEqual(q.dequeue_count, 5000)
        self.assertEqual(stats["dequeue_age_percentile_sample_count"], 4096)
        self.assertAlmostEqual(stats["mean_dequeue_age_s"], 0.25)

    def test_exact_capacity_and_one_sample_overflow(self):
        q = BoundedAudioQueue("test", 4)
        self.assertTrue(q.try_put(QueueItem("A", 0, np.zeros(4, np.float32), 0), 0))
        self.assertFalse(q.try_put(QueueItem("A", 4, np.zeros(1, np.float32), 0), 0))
        self.assertEqual(q.occupancy_samples, 4)
        self.assertEqual(q.high_water_samples, 4)
        self.assertEqual(q.backpressure_attempts, 1)
        self.assertEqual(q.pop(1).start_sample, 0)
        self.assertTrue(q.try_put(QueueItem("A", 4, np.zeros(1, np.float32), 1), 1))

    def test_playback_queue_capacity_and_one_chunk_beyond(self):
        q = BoundedAudioQueue("playback", 8)
        self.assertTrue(q.try_put(QueueItem("A", 0, np.zeros(6, np.float32), 0), 0))
        self.assertTrue(q.try_put(QueueItem("A", 6, np.zeros(2, np.float32), 0), 0))
        self.assertFalse(q.try_put(QueueItem("A", 8, np.zeros(1, np.float32), 0), 0))
        self.assertEqual(q.high_water_samples, 8)
        self.assertEqual(q.occupancy_samples, 8)
        self.assertEqual(q.backpressure_attempts, 1)
        q.pop(1)
        q.pop(1)
        self.assertTrue(q.try_put(QueueItem("A", 8, np.zeros(1, np.float32), 1), 1))

    def test_reorders_are_rejected(self):
        q = BoundedAudioQueue("test", 8)
        self.assertTrue(q.try_put(QueueItem("A", 0, np.zeros(2, np.float32), 0), 0))
        with self.assertRaisesRegex(ValueError, "timestamp discontinuity"):
            q.try_put(QueueItem("A", 3, np.zeros(2, np.float32), 0), 0)

    def test_queue_age_and_time_weighted_occupancy(self):
        q = BoundedAudioQueue("test", 8)
        q.observe(0)
        q.try_put(QueueItem("A", 0, np.zeros(4, np.float32), 1), 1)
        q.observe(3)
        q.pop(3)
        stats = q.telemetry(4)
        self.assertEqual(stats["high_water_samples"], 4)
        self.assertAlmostEqual(stats["mean_occupancy_samples"], 2.0)
        self.assertAlmostEqual(stats["mean_dequeue_age_s"], 2.0)


class PipelineTests(unittest.TestCase):
    def test_processing_and_event_telemetry_storage_is_bounded(self):
        p = pipeline()
        for i in range(5000):
            p._record_processing_time(0.001 + (i % 3) * 0.0001)
            p.snapshot(float(i), event="synthetic")
        self.assertEqual(p.processing_wall_count, 5000)
        self.assertEqual(len(p.processing_wall_s), 4096)
        self.assertEqual(len(p.telemetry_rows), 4096)

    def test_normal_ordered_processing_and_sample_accounting(self):
        p = pipeline(cap=1024, play=1536, max_chunk=1024)
        source = np.concatenate((np.arange(300), np.arange(200))).astype(np.float32)
        self.assertEqual(p.offer_capture(AudioChunk("A", 0, source[:300], 0), 0), OfferResult.ACCEPTED)
        self.assertEqual(p.offer_capture(AudioChunk("A", 300, source[300:], 0.01, True), 0.01), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(0.02))
        self.assertTrue(p.process_one(0.03))
        outputs = []
        while p.playback.peek() is not None:
            outputs.append(p.pop_playback(0.04).samples)
        result = np.concatenate(outputs)
        np.testing.assert_array_equal(result, source)
        self.assertEqual(p.status, "closed")
        self.assertEqual(p.accepted_input_samples, 500)
        self.assertEqual(p.processed_input_samples, 500)
        self.assertEqual(p.generated_output_samples, 500)
        self.assertEqual(p.delivered_output_samples, 500)
        self.assertEqual(p.lost_input_samples, 0)
        self.assertEqual(p.lost_output_samples, 0)

    def test_bursty_producer_gets_retry_backpressure_without_loss(self):
        p = pipeline(cap=512, play=1536, max_chunk=512)
        self.assertEqual(p.offer_capture(chunk("A", 0, 256), 0), OfferResult.ACCEPTED)
        self.assertEqual(p.offer_capture(chunk("A", 256, 256), 0.001), OfferResult.ACCEPTED)
        pending = chunk("A", 512, 128, final=True)
        self.assertEqual(p.offer_capture(pending, 0.002), OfferResult.BACKPRESSURE)
        self.assertTrue(p.process_one(0.01))
        self.assertEqual(p.offer_capture(pending, 0.02), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(0.03))
        self.assertTrue(p.process_one(0.04))
        while p.playback.peek() is not None:
            p.pop_playback(0.05)
        self.assertEqual(p.capture_backpressure_events, 1)
        self.assertAlmostEqual(p.backpressure_duration_s, 0.018)
        self.assertEqual(p.lost_input_samples, 0)
        self.assertEqual(p.generated_output_samples, 640)

    def test_consumer_stall_fills_capture_then_recovers(self):
        p = pipeline(cap=512, play=1536, max_chunk=256)
        for i in range(2):
            self.assertEqual(p.offer_capture(chunk("A", i * 256, 256), 0), OfferResult.ACCEPTED)
        third = chunk("A", 512, 256, final=True)
        self.assertEqual(p.offer_capture(third, 0.1), OfferResult.BACKPRESSURE)
        self.assertEqual(p.capture.occupancy_samples, 512)
        self.assertTrue(p.process_one(1.0))
        self.assertEqual(p.offer_capture(third, 1.01), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(1.02))
        self.assertTrue(p.process_one(1.03))
        self.assertEqual(p.processed_input_samples, 768)
        self.assertEqual(p.lost_input_samples, 0)

    def test_capture_overflow_is_retry_not_silent_drop(self):
        p = pipeline(cap=512, play=1024, max_chunk=512)
        p.offer_capture(chunk("A", 0, 256), 0)
        p.offer_capture(chunk("A", 256, 256), 0)
        pending = chunk("A", 512, 1)
        self.assertEqual(p.offer_capture(pending, 1), OfferResult.BACKPRESSURE)
        self.assertEqual(p.accepted_input_samples, 512)
        self.assertEqual(p.lost_input_samples, 0)
        self.assertTrue(p.process_one(2))
        self.assertEqual(p.offer_capture(pending, 2.1), OfferResult.ACCEPTED)

    def test_unpausable_overflow_terminates_and_accounts_exact_ranges(self):
        p = pipeline(cap=512, play=1024, max_chunk=512)
        p.offer_capture(chunk("A", 0, 256), 0)
        p.offer_capture(chunk("A", 256, 256), 0)
        pending = chunk("A", 512, 17)
        self.assertEqual(p.offer_capture(pending, 1), OfferResult.BACKPRESSURE)
        p.abort_unretriable_capture(pending, 1.1)
        self.assertEqual(p.status, "failed")
        self.assertEqual(p.lost_input_samples, 529)
        ranges = [(r.start_sample, r.end_sample) for r in p.losses if r.direction == "input"]
        self.assertEqual(ranges, [(512, 529), (0, 256), (256, 512)])
        p.reset_session("B", 529, 2)
        self.assertEqual(p.offer_capture(chunk("B", 529, 300, final=True), 2), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(2.1))
        self.assertEqual(p.status, "closed")

    def test_playback_capacity_propagates_backpressure(self):
        p = pipeline(cap=2048, play=1536, max_chunk=256)
        for i in range(6):
            p.offer_capture(chunk("A", i * 256, 256, final=(i == 5)), i * 0.01)
        self.assertTrue(p.process_one(0.1))
        self.assertTrue(p.process_one(0.2))
        self.assertTrue(p.process_one(0.3))
        self.assertTrue(p.process_one(0.35))
        self.assertFalse(p.process_one(0.38))
        self.assertEqual(p.playback.occupancy_samples, 1024)
        self.assertEqual(p.playback_backpressure_events, 1)
        p.pop_playback(0.5)
        self.assertTrue(p.process_one(0.55))
        p.pop_playback(0.58)
        self.assertTrue(p.process_one(0.6))
        self.assertEqual(p.status, "closed")
        self.assertEqual(p.generated_output_samples, 1536)

    def test_invalid_and_oversized_chunks_do_not_reach_adapter(self):
        adapter = FakeAdapter()
        p = pipeline(adapter, cap=8192, play=8192, max_chunk=4096)
        before = (adapter.calls, p.capture.occupancy_samples, p.next_input_sample)
        bad = [
            AudioChunk("A", 0, np.zeros((2, 2), np.float32), 0),
            AudioChunk("A", 0, np.array([np.nan], np.float32), 0),
            AudioChunk("A", 0, np.zeros(4097, np.float32), 0),
            AudioChunk("A", 0, np.zeros(4, np.complex64), 0),
        ]
        for item in bad:
            self.assertEqual(p.offer_capture(item, 0), OfferResult.REJECTED_INVALID)
        self.assertEqual((adapter.calls, p.capture.occupancy_samples, p.next_input_sample), before)
        self.assertEqual(p.invalid_inputs, 4)
        self.assertEqual(p.offer_capture(chunk("A", 0, 257, final=True), 0), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(0.1))

    def test_pipeline_accepts_exact_4096_sample_adapter_limit(self):
        p = pipeline(cap=8192, play=8192, max_chunk=4096)
        item = chunk("A", 0, 4096, final=True)
        self.assertEqual(p.offer_capture(item, 0), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(0.01))
        output = p.pop_playback(0.02)
        self.assertEqual(len(output.samples), 4096)
        self.assertEqual(p.accepted_input_samples, p.delivered_output_samples)

    def test_timestamp_gap_fails_closed_and_reports_interval(self):
        p = pipeline(cap=512, play=1024, max_chunk=256)
        p.offer_capture(chunk("A", 0, 100), 0)
        result = p.offer_capture(chunk("A", 150, 50), 0.1)
        self.assertEqual(result, OfferResult.FAILED_SESSION)
        self.assertEqual(p.status, "failed")
        self.assertEqual(p.discontinuities, 1)
        self.assertEqual(p.lost_input_samples, 200)
        self.assertEqual(p.losses[0].start_sample, 100)
        self.assertEqual(p.losses[0].end_sample, 200)

    def test_consumer_exception_resets_and_new_session_recovers(self):
        adapter = FakeAdapter(fail_calls={1})
        p = pipeline(adapter, cap=512, play=1024, max_chunk=256)
        p.offer_capture(chunk("A", 0, 256), 0)
        p.offer_capture(chunk("A", 256, 256, final=True), 0)
        self.assertFalse(p.process_one(0.1))
        self.assertEqual(p.status, "failed")
        self.assertEqual(p.consumer_failures, 1)
        self.assertEqual(p.lost_input_samples, 512)
        p.reset_session("B", 512, 1)
        self.assertEqual(p.offer_capture(chunk("B", 512, 256, final=True), 1), OfferResult.ACCEPTED)
        self.assertTrue(p.process_one(1.1))
        out = p.pop_playback(1.2)
        self.assertEqual(out.session_id, "B")
        self.assertEqual(p.status, "closed")

    def test_reset_with_pending_queues_discards_and_accounts_old_session(self):
        p = pipeline(cap=512, play=1024, max_chunk=256)
        p.offer_capture(chunk("A", 0, 256), 0)
        p.process_one(0.1)
        p.offer_capture(chunk("A", 256, 256), 0.2)
        self.assertGreater(p.capture.occupancy_samples, 0)
        self.assertGreater(p.playback.occupancy_samples, 0)
        p.reset_session("B", 1000, 0.3)
        self.assertEqual(p.capture.occupancy_samples, 0)
        self.assertEqual(p.playback.occupancy_samples, 0)
        self.assertEqual(p.lost_input_samples, 256)
        self.assertEqual(p.lost_output_samples, 256)
        self.assertTrue(all(record.session_id == "A" for record in p.losses))

    def test_repeated_sessions_have_no_fake_adapter_state_leakage(self):
        class StatefulAdapter(FakeAdapter):
            def process_chunk(self, audio, *, final=False):
                self.calls += 1
                self.state_sum += 1.0
                return np.asarray(audio, dtype=np.float32) + self.state_sum

        adapter = StatefulAdapter()
        p = pipeline(adapter, cap=512, play=1024, max_chunk=256)
        p.offer_capture(chunk("A", 0, 256, final=True), 0)
        p.process_one(0.1)
        first = p.pop_playback(0.2).samples.copy()
        p.reset_session("B", 10_000, 1)
        p.offer_capture(chunk("B", 10_000, 256, final=True), 1)
        p.process_one(1.1)
        second = p.pop_playback(1.2).samples.copy()
        np.testing.assert_array_equal(first, second)

    def test_long_run_keeps_queue_capacities_fixed_and_accounted(self):
        p = pipeline(cap=8192, play=8192, max_chunk=4096)
        now = 0.0
        cursor = 0
        for i in range(2000):
            n = 128 + (i * 37) % 512
            item = chunk("A", cursor, n, final=(i == 1999))
            while p.offer_capture(item, now) == OfferResult.BACKPRESSURE:
                now += 0.001
                if p.capture.peek() is not None:
                    p.process_one(now)
                while p.playback.peek() is not None:
                    p.pop_playback(now)
            cursor += n
            now += 0.0001
            while p.capture.peek() is not None:
                p.process_one(now)
                while p.playback.peek() is not None:
                    p.pop_playback(now)
        self.assertLessEqual(p.capture.high_water_samples, p.capture.capacity_samples)
        self.assertLessEqual(p.playback.high_water_samples, p.playback.capacity_samples)
        self.assertEqual(p.accepted_input_samples, p.processed_input_samples)
        self.assertEqual(p.processed_input_samples, p.delivered_output_samples)
        self.assertEqual(p.lost_input_samples, 0)

    def test_timestamp_ordering_and_final_close(self):
        p = pipeline(cap=512, play=1024, max_chunk=256)
        p.offer_capture(chunk("A", 0, 127), 0)
        p.offer_capture(chunk("A", 127, 129, final=True), 0.01)
        self.assertTrue(p.process_one(0.02))
        self.assertTrue(p.process_one(0.03))
        starts = []
        while p.playback.peek() is not None:
            starts.append(p.pop_playback(0.04).start_sample)
        self.assertEqual(starts, [0, 127])
        self.assertEqual(p.status, "closed")
        self.assertEqual(p.delivered_output_samples, 256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
