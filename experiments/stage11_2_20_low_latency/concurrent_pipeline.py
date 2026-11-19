"""Threaded, synthetic-only host pipeline used for Stage 11.2.20 latency tests."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import statistics
import threading
import time
import tracemalloc
from typing import Any

import numpy as np


@dataclass
class AudioBlock:
    start_sample: int
    samples: np.ndarray
    accepted_at: float
    final: bool

    @property
    def end_sample(self) -> int:
        return self.start_sample + int(self.samples.size)


def _pctl(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0


def run_concurrent_pipeline(
    adapter: Any,
    *,
    duration_s: int,
    chunk_samples: int,
    capture_capacity_samples: int,
    playback_capacity_samples: int,
    playback_reservation_samples: int | None = None,
    final_output_reservation_samples: int | None = None,
    seed: int = 26052,
) -> dict[str, Any]:
    """Run paced producer, actual GTCRN consumer, and timed sink concurrently.

    Producer blocking retries the exact same synthetic chunk. The consumer
    reserves `chunk + n_fft` playback capacity before it mutates adapter
    state. Playback occupancy includes the block currently being played.
    """
    sample_rate = 16000
    total_samples = duration_s * sample_rate
    if total_samples % chunk_samples:
        raise ValueError("duration must be divisible by caller chunk size")
    if capture_capacity_samples < chunk_samples:
        raise ValueError("capture capacity must fit one source chunk")
    reserve_samples = int(
        playback_reservation_samples
        if playback_reservation_samples is not None
        else chunk_samples + int(adapter.n_fft)
    )
    if reserve_samples <= 0:
        raise ValueError("playback reservation must be positive")
    final_reserve = int(final_output_reservation_samples or reserve_samples)
    if final_reserve <= 0 or final_reserve > playback_capacity_samples:
        raise ValueError("final playback reservation must fit playback capacity")
    if playback_capacity_samples < reserve_samples:
        raise ValueError("playback capacity cannot fit one conservative output reservation")

    rng = np.random.default_rng(seed)
    time_axis = np.arange(total_samples, dtype=np.float32) / sample_rate
    source = (0.035 * np.sin(2 * np.pi * 220 * time_axis)
              + 0.006 * rng.standard_normal(total_samples)).astype(np.float32)

    cv = threading.Condition()
    capture: deque[AudioBlock] = deque()
    playback: deque[AudioBlock] = deque()
    capture_occupancy = 0
    playback_occupancy = 0
    capture_hwm = 0
    playback_hwm = 0
    capture_area = 0.0
    playback_area = 0.0
    capture_last = 0.0
    playback_last = 0.0
    capture_age: list[float] = []
    playback_age: list[float] = []
    e2e_ms: list[float] = []
    e2e_sink_clock_ms: list[float] = []
    sink_deadline_lateness_ms: list[float] = []
    producer_lag_ms: list[float] = []
    process_ms: list[float] = []
    producer_bp_events = 0
    producer_bp_duration = 0.0
    consumer_bp_events = 0
    consumer_bp_duration = 0.0
    generated_samples = 0
    accepted_samples = 0
    processed_samples = 0
    output_samples = 0
    delivered_samples = 0
    delivered_cursor = 0
    adapter_output_cursor = 0
    producer_done = False
    consumer_done = False
    failure: list[BaseException] = []
    t0 = time.monotonic()
    tracemalloc.start()

    def update_capture(now: float) -> None:
        nonlocal capture_area, capture_last
        capture_area += capture_occupancy * (now - capture_last)
        capture_last = now

    def update_playback(now: float) -> None:
        nonlocal playback_area, playback_last
        playback_area += playback_occupancy * (now - playback_last)
        playback_last = now

    def fail(exc: BaseException) -> None:
        with cv:
            if not failure:
                failure.append(exc)
            cv.notify_all()

    def producer_worker() -> None:
        nonlocal capture_occupancy, capture_hwm, generated_samples
        nonlocal accepted_samples, producer_bp_events, producer_bp_duration
        try:
            for start in range(0, total_samples, chunk_samples):
                stop = start + chunk_samples
                scheduled = t0 + start / sample_rate
                wait_s = scheduled - time.monotonic()
                if wait_s > 0:
                    time.sleep(wait_s)
                chunk = source[start:stop]
                generated_samples += int(chunk.size)
                blocked_at: float | None = None
                with cv:
                    while capture_occupancy + chunk.size > capture_capacity_samples:
                        if failure:
                            return
                        if blocked_at is None:
                            blocked_at = time.monotonic()
                            producer_bp_events += 1
                        cv.wait(timeout=0.25)
                    now = time.monotonic()
                    if blocked_at is not None:
                        producer_bp_duration += now - blocked_at
                    update_capture(now - t0)
                    capture.append(AudioBlock(start, chunk, now, stop == total_samples))
                    capture_occupancy += int(chunk.size)
                    capture_hwm = max(capture_hwm, capture_occupancy)
                    accepted_samples += int(chunk.size)
                    producer_lag_ms.append(max(0.0, now - scheduled) * 1000)
                    cv.notify_all()
        except BaseException as exc:  # propagate thread failures to the controller
            fail(exc)
        finally:
            with cv:
                nonlocal producer_done
                producer_done = True
                cv.notify_all()

    def consumer_worker() -> None:
        nonlocal capture_occupancy, playback_occupancy, playback_hwm
        nonlocal processed_samples, output_samples, adapter_output_cursor
        nonlocal consumer_done, consumer_bp_events, consumer_bp_duration
        try:
            while True:
                blocked_at: float | None = None
                with cv:
                    while True:
                        if failure:
                            return
                        current_reserve = (
                            final_reserve if capture and capture[0].final else reserve_samples
                        )
                        if capture and playback_capacity_samples - playback_occupancy >= current_reserve:
                            now = time.monotonic()
                            if blocked_at is not None:
                                consumer_bp_duration += now - blocked_at
                            update_capture(now - t0)
                            block = capture.popleft()
                            capture_occupancy -= int(block.samples.size)
                            capture_age.append(max(0.0, now - block.accepted_at) * 1000)
                            update_playback(now - t0)
                            cv.notify_all()
                            break
                        if producer_done and not capture:
                            return
                        if capture and playback_capacity_samples - playback_occupancy < reserve_samples:
                            if blocked_at is None:
                                blocked_at = time.monotonic()
                                consumer_bp_events += 1
                        cv.wait(timeout=0.25)

                started = time.perf_counter()
                enhanced = adapter.process_chunk(block.samples, final=block.final)
                elapsed = time.perf_counter() - started
                process_ms.append(elapsed * 1000)
                processed_samples += int(block.samples.size)
                enhanced = np.asarray(enhanced, dtype=np.float32)
                if enhanced.ndim != 1 or not np.isfinite(enhanced).all():
                    raise RuntimeError("adapter returned invalid synthetic output")
                block_reserve = final_reserve if block.final else reserve_samples
                if enhanced.size > block_reserve:
                    raise RuntimeError(
                        f"adapter output {enhanced.size} exceeded validated reservation {block_reserve}"
                    )
                if enhanced.size:
                    out_block = AudioBlock(
                        adapter_output_cursor, enhanced, time.monotonic() - t0,
                        block.final,
                    )
                    adapter_output_cursor += int(enhanced.size)
                    with cv:
                        update_playback(time.monotonic() - t0)
                        if playback_occupancy + enhanced.size > playback_capacity_samples:
                            raise RuntimeError("playback reservation failed after inference")
                        playback.append(out_block)
                        playback_occupancy += int(enhanced.size)
                        playback_hwm = max(playback_hwm, playback_occupancy)
                        output_samples += int(enhanced.size)
                        cv.notify_all()
        except BaseException as exc:
            fail(exc)
        finally:
            with cv:
                nonlocal consumer_done
                consumer_done = True
                cv.notify_all()

    def sink_worker() -> None:
        nonlocal playback_occupancy, delivered_samples, delivered_cursor
        sink_clock_end_s: float | None = None
        try:
            while True:
                with cv:
                    while not playback and not consumer_done and not failure:
                        cv.wait(timeout=0.25)
                    if failure:
                        return
                    if not playback and consumer_done:
                        return
                    block = playback[0]
                    enqueued_rel = block.accepted_at
                    sink_start_rel = max(
                        enqueued_rel,
                        sink_clock_end_s if sink_clock_end_s is not None else enqueued_rel,
                    )
                    sink_clock_end_s = sink_start_rel + block.samples.size / sample_rate
                    target_done = t0 + sink_clock_end_s
                # Use an absolute sample-clock deadline. Repeated relative
                # sleeps accumulate scheduler overshoot and falsely make a
                # simulated 16 ms device take longer than 16 ms per block.
                remaining = target_done - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                done = time.monotonic()
                with cv:
                    if playback[0] is not block:
                        raise RuntimeError("playback FIFO order changed during sink service")
                    update_playback(done - t0)
                    playback.popleft()
                    playback_occupancy -= int(block.samples.size)
                    playback_age.append((done - t0 - block.accepted_at) * 1000)
                    sink_deadline_lateness_ms.append(max(0.0, done - target_done) * 1000)
                    if block.start_sample != delivered_cursor:
                        raise RuntimeError(
                            f"output discontinuity {block.start_sample}!={delivered_cursor}"
                        )
                    delivered_cursor = block.end_sample
                    delivered_samples += int(block.samples.size)
                    e2e_ms.append(max(0.0, done - t0 - block.end_sample / sample_rate) * 1000)
                    e2e_sink_clock_ms.append(max(0.0, sink_clock_end_s - block.end_sample / sample_rate) * 1000)
                    cv.notify_all()
        except BaseException as exc:
            fail(exc)

    threads = [
        threading.Thread(target=producer_worker, name="synthetic-producer"),
        threading.Thread(target=consumer_worker, name="gtcrn-consumer"),
        threading.Thread(target=sink_worker, name="timed-playback-sink"),
    ]
    wall_start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=duration_s + 60)
    wall_elapsed = time.perf_counter() - wall_start
    if any(thread.is_alive() for thread in threads):
        fail(TimeoutError("threaded synthetic pipeline did not finish before timeout"))
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if failure:
        raise RuntimeError("threaded synthetic pipeline failed") from failure[0]

    now = time.monotonic() - t0
    update_capture(now)
    update_playback(now)
    if not (generated_samples == accepted_samples == processed_samples
            == output_samples == delivered_samples == delivered_cursor == total_samples):
        raise RuntimeError(
            "threaded sample accounting mismatch: "
            f"generated={generated_samples}, accepted={accepted_samples}, "
            f"processed={processed_samples}, output={output_samples}, "
            f"delivered={delivered_samples}, cursor={delivered_cursor}, expected={total_samples}"
        )

    elapsed_sim = now
    return {
        "duration_s": duration_s,
        "chunk_samples": chunk_samples,
        "sample_rate_hz": sample_rate,
        "capture_capacity_samples": capture_capacity_samples,
        "playback_capacity_samples": playback_capacity_samples,
        "playback_reservation_samples": reserve_samples,
        "final_output_reservation_samples": final_reserve,
        "capture_capacity_ms": capture_capacity_samples / sample_rate * 1000,
        "playback_capacity_ms": playback_capacity_samples / sample_rate * 1000,
        "capture_mean_occupancy_samples": capture_area / elapsed_sim,
        "capture_high_water_samples": capture_hwm,
        "capture_mean_age_ms": statistics.fmean(capture_age) if capture_age else 0.0,
        "capture_p95_age_ms": _pctl(capture_age, 95),
        "capture_p99_age_ms": _pctl(capture_age, 99),
        "capture_max_age_ms": max(capture_age, default=0.0),
        "playback_mean_occupancy_samples": playback_area / elapsed_sim,
        "playback_high_water_samples": playback_hwm,
        "playback_mean_age_ms": statistics.fmean(playback_age) if playback_age else 0.0,
        "playback_p95_age_ms": _pctl(playback_age, 95),
        "playback_p99_age_ms": _pctl(playback_age, 99),
        "playback_max_age_ms": max(playback_age, default=0.0),
        "producer_backpressure_events": producer_bp_events,
        "producer_backpressure_duration_ms": producer_bp_duration * 1000,
        "consumer_playback_backpressure_events": consumer_bp_events,
        "consumer_playback_backpressure_duration_ms": consumer_bp_duration * 1000,
        "producer_schedule_lag_mean_ms": statistics.fmean(producer_lag_ms) if producer_lag_ms else 0.0,
        "producer_schedule_lag_p99_ms": _pctl(producer_lag_ms, 99),
        "source_to_playout_mean_ms": statistics.fmean(e2e_ms) if e2e_ms else 0.0,
        "source_to_playout_p95_ms": _pctl(e2e_ms, 95),
        "source_to_playout_p99_ms": _pctl(e2e_ms, 99),
        "source_to_playout_max_ms": max(e2e_ms, default=0.0),
        "sample_clock_source_to_playout_mean_ms": statistics.fmean(e2e_sink_clock_ms) if e2e_sink_clock_ms else 0.0,
        "sample_clock_source_to_playout_p95_ms": _pctl(e2e_sink_clock_ms, 95),
        "sample_clock_source_to_playout_p99_ms": _pctl(e2e_sink_clock_ms, 99),
        "sample_clock_source_to_playout_max_ms": max(e2e_sink_clock_ms, default=0.0),
        "sink_deadline_lateness_p99_ms": _pctl(sink_deadline_lateness_ms, 99),
        "sink_deadline_lateness_max_ms": max(sink_deadline_lateness_ms, default=0.0),
        "processing_calls": len(process_ms),
        "processing_mean_ms": statistics.fmean(process_ms) if process_ms else 0.0,
        "processing_p95_ms": _pctl(process_ms, 95),
        "processing_p99_ms": _pctl(process_ms, 99),
        "processing_max_ms": max(process_ms, default=0.0),
        "processing_deadline_ms": chunk_samples / sample_rate * 1000,
        "processing_deadline_misses": sum(
            1 for value in process_ms if value > chunk_samples / sample_rate * 1000
        ),
        "host_wall_elapsed_s": wall_elapsed,
        "host_rtf": wall_elapsed / duration_s,
        "producer_generated_samples": generated_samples,
        "accepted_input_samples": accepted_samples,
        "processed_input_samples": processed_samples,
        "generated_output_samples": output_samples,
        "delivered_output_samples": delivered_samples,
        "lost_samples": 0,
        "output_cursor": delivered_cursor,
        "tracemalloc_current_bytes": current_bytes,
        "tracemalloc_peak_bytes": peak_bytes,
    }
