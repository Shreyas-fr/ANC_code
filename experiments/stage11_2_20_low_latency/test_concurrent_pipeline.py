from __future__ import annotations

import time
import unittest

import numpy as np

from concurrent_pipeline import run_concurrent_pipeline


class IdentityAdapter:
    n_fft = 512

    def __init__(self, delay_s: float = 0.0):
        self.delay_s = delay_s
        self.closed = False

    def process_chunk(self, audio, *, final=False):
        if self.closed:
            raise RuntimeError("adapter used after final chunk")
        if self.delay_s:
            time.sleep(self.delay_s)
        if final:
            self.closed = True
        return np.asarray(audio, dtype=np.float32).copy()


class ThreadedPipelineTests(unittest.TestCase):
    def run_pipeline(self, delay_s: float):
        return run_concurrent_pipeline(
            IdentityAdapter(delay_s),
            duration_s=4,
            chunk_samples=256,
            capture_capacity_samples=512,
            playback_capacity_samples=512,
            playback_reservation_samples=256,
            final_output_reservation_samples=512,
        )

    def test_paced_pipeline_preserves_samples_and_capacity(self):
        result = self.run_pipeline(0.0)
        self.assertEqual(result["producer_generated_samples"], 64000)
        self.assertEqual(result["accepted_input_samples"], 64000)
        self.assertEqual(result["processed_input_samples"], 64000)
        self.assertEqual(result["generated_output_samples"], 64000)
        self.assertEqual(result["delivered_output_samples"], 64000)
        self.assertEqual(result["lost_samples"], 0)
        self.assertLessEqual(result["capture_high_water_samples"], 512)
        self.assertLessEqual(result["playback_high_water_samples"], 512)

    def test_slow_consumer_backpressures_without_dropping_or_reordering(self):
        result = self.run_pipeline(0.020)
        self.assertGreater(result["producer_backpressure_events"], 0)
        self.assertEqual(result["lost_samples"], 0)
        self.assertEqual(result["output_cursor"], 64000)
        self.assertEqual(result["delivered_output_samples"], 64000)
        self.assertLessEqual(result["capture_high_water_samples"], 512)
        self.assertLessEqual(result["playback_high_water_samples"], 512)


if __name__ == "__main__":
    unittest.main(verbosity=2)
