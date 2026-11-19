#!/usr/bin/env python3
"""Synthetic queue/backpressure stress test around the existing GTCRN adapter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import resource
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "third_party/gtcrn_stage5"))
sys.path.insert(0, str(ROOT / "experiments/stage11_2_17_gtcrn_streaming/compat"))
sys.path.insert(0, str(ROOT / "experiments/stage11_2_17_gtcrn_streaming"))
sys.path.insert(0, str(HERE))

from gtcrn import GTCRN  # noqa: E402
from bounded_pipeline import AudioChunk, BoundedGTCRNPipeline, OfferResult  # noqa: E402
from gtcrn_stream_adapter import GTCRNStreamAdapter  # noqa: E402
from synthetic_producer import ProducerConfig, SyntheticProducer  # noqa: E402


EXPECTED = {
    "step500": "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27",
    "fullsubnet": "482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0",
    "gtcrn": "a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79",
    "manifest": "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4",
    "ensemble_summary": "8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5",
    "ensemble_per_clip": "b1f8ce8b21622672eb744b9ae0b1d7279579908265636ac0fe59e6825b372190",
    "v10_config": "6fd82652cef2b90375512df15cf028040ac09f9ce353792a4b8ff24e43222b9b",
    "v10_checkpoint": "57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c",
}

PROTECTED_PATHS = {
    "step500": ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt",
    "fullsubnet": ROOT / "checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar",
    "gtcrn": ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar",
    "manifest": ROOT / "runs/sih26052_canonical_validation/manifest.csv",
    "ensemble_summary": ROOT / "runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/summary.json",
    "ensemble_per_clip": ROOT / "runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/per_clip.csv",
    "v10_config": ROOT / "runs/stage11_2_16_v10_causal_candidate/model_config/config.ini",
    "v10_checkpoint": ROOT / "runs/stage11_2_16_v10_causal_candidate/causal_v10_r0_step500_weights.hk",
    "gtcrn_adapter": ROOT / "experiments/stage11_2_17_gtcrn_streaming/gtcrn_stream_adapter.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protected_hashes() -> dict[str, str]:
    result = {}
    for name, path in PROTECTED_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required protected artifact unavailable: {name} at {path}")
        digest = sha256(path)
        if name in EXPECTED and digest != EXPECTED[name]:
            raise RuntimeError(f"Protected artifact hash mismatch for {name}: {digest}")
        result[name] = digest
    # The deployed Step-500 Tract archive is intentionally not substituted by
    # another export. Its known expected hash is recorded as unavailable.
    result["step500_tract_archive"] = "unavailable; expected hash 99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d"
    return result


def git_state() -> dict[str, object]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    modified = [line for line in status if not line.startswith("??")]
    untracked = [line for line in status if line.startswith("??")]
    return {
        "head": head,
        "modified_entry_count": len(modified),
        "modified_entries": modified,
        "untracked_entry_count": len(untracked),
        # The run started after 97 existing untracked entries had been observed.
        # Names are not repeated here to avoid a second broad workspace inventory.
        "untracked_entries_at_stage_start": 97,
        "stage_directory_absent_at_stage_start": True,
    }


class IdentityAdapter:
    max_chunk_samples = 4096
    n_fft = 512

    def __init__(self, fail_on_call: int | None = None):
        self.fail_on_call = fail_on_call
        self.calls = 0
        self.state_samples = 0

    def process_chunk(self, audio: np.ndarray, *, final: bool = False) -> np.ndarray:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("injected deterministic consumer failure")
        self.state_samples += len(audio)
        return np.asarray(audio, dtype=np.float32).copy()

    def reset_session(self) -> None:
        self.state_samples = 0


def make_chunk(session: str, start: int, n: int, *, final: bool = False) -> AudioChunk:
    index = np.arange(start, start + n, dtype=np.float64)
    x = (0.2 * np.sin(2 * np.pi * 313.0 * index / 16000.0)).astype(np.float32)
    return AudioChunk(session, start, x, 0.0, final)


def run_policy_probes() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    sessions: list[dict[str, object]] = []

    # Capture queue exactly full, one chunk over, then retry after a dequeue.
    adapter = IdentityAdapter()
    p = BoundedGTCRNPipeline(
        adapter, session_id="capture_retry", capture_capacity_samples=512,
        playback_capacity_samples=1536, max_chunk_samples=512,
    )
    accepted = [make_chunk("capture_retry", 0, 256), make_chunk("capture_retry", 256, 256)]
    for item in accepted:
        assert p.offer_capture(item, 0.0) == OfferResult.ACCEPTED
    pending = make_chunk("capture_retry", 512, 128, final=True)
    first = p.offer_capture(pending, 0.001)
    assert first == OfferResult.BACKPRESSURE
    assert p.capture.occupancy_samples == p.capture.capacity_samples == 512
    p.process_one(0.01)
    retry = p.offer_capture(pending, 0.02)
    assert retry == OfferResult.ACCEPTED
    p.process_one(0.03)
    p.process_one(0.04)
    while p.playback.peek() is not None:
        p.pop_playback(0.05)
    rows.append({
        "case": "capture_full_retry_same_chunk",
        "result": "PASS",
        "capture_capacity_samples": p.capture.capacity_samples,
        "capture_high_water_samples": p.capture.high_water_samples,
        "capture_backpressure_events": p.capture_backpressure_events,
        "playback_backpressure_events": p.playback_backpressure_events,
        "accepted_samples": p.accepted_input_samples,
        "processed_samples": p.processed_input_samples,
        "delivered_samples": p.delivered_output_samples,
        "lost_input_samples": p.lost_input_samples,
        "lost_output_samples": p.lost_output_samples,
        "recovery": "same timestamped chunk retried after capture dequeue",
    })

    # An unpausable upstream source fails closed, with exact loss intervals.
    p = BoundedGTCRNPipeline(
        IdentityAdapter(), session_id="capture_abort", capture_capacity_samples=512,
        playback_capacity_samples=1024, max_chunk_samples=512,
    )
    p.offer_capture(make_chunk("capture_abort", 0, 256), 0)
    p.offer_capture(make_chunk("capture_abort", 256, 256), 0)
    pending = make_chunk("capture_abort", 512, 17)
    assert p.offer_capture(pending, 1) == OfferResult.BACKPRESSURE
    p.abort_unretriable_capture(pending, 1.1)
    assert p.lost_input_samples == 529
    loss_ranges = [(x.start_sample, x.end_sample) for x in p.losses if x.direction == "input"]
    assert sorted(loss_ranges) == [(0, 256), (256, 512), (512, 529)]
    p.reset_session("capture_abort_recovery", 529, 2)
    assert p.offer_capture(make_chunk("capture_abort_recovery", 529, 300, final=True), 2) == OfferResult.ACCEPTED
    assert p.process_one(2.1)
    rows.append({
        "case": "unpausable_capture_overflow_abort",
        "result": "PASS",
        "capture_capacity_samples": p.capture.capacity_samples,
        "capture_high_water_samples": p.capture.high_water_samples,
        "capture_backpressure_events": p.capture_backpressure_events,
        "playback_backpressure_events": p.playback_backpressure_events,
        "accepted_samples": p.accepted_input_samples,
        "processed_samples": p.processed_input_samples,
        "delivered_samples": p.delivered_output_samples,
        "lost_input_samples": 529,
        "lost_output_samples": p.lost_output_samples,
        "recovery": "session terminated; exact loss ranges recorded; new session starts at sample 529",
    })

    # Playback saturation stops the consumer; draining the sink resumes it.
    p = BoundedGTCRNPipeline(
        IdentityAdapter(), session_id="playback_stall", capture_capacity_samples=2048,
        playback_capacity_samples=1536, max_chunk_samples=256,
    )
    for i in range(5):
        assert p.offer_capture(make_chunk("playback_stall", i * 256, 256, final=i == 4), i * .01) == OfferResult.ACCEPTED
    for idx in range(4):
        assert p.process_one(0.1 + idx * .1)
    blocked = not p.process_one(0.4)
    assert blocked and p.playback.occupancy_samples == 1024
    p.pop_playback(0.5)
    assert p.process_one(0.6)
    while p.playback.peek() is not None:
        p.pop_playback(.8)
    assert p.generated_output_samples == 1280
    rows.append({
        "case": "playback_full_consumer_backpressure",
        "result": "PASS",
        "capture_capacity_samples": p.capture.capacity_samples,
        "capture_high_water_samples": p.capture.high_water_samples,
        "capture_backpressure_events": p.capture_backpressure_events,
        "playback_capacity_samples": p.playback.capacity_samples,
        "playback_high_water_samples": p.playback.high_water_samples,
        "playback_backpressure_events": p.playback_backpressure_events,
        "accepted_samples": p.accepted_input_samples,
        "processed_samples": p.processed_input_samples,
        "delivered_samples": p.delivered_output_samples,
        "lost_input_samples": p.lost_input_samples,
        "lost_output_samples": p.lost_output_samples,
        "recovery": "sink drain released bounded playback capacity; consumer resumed in order",
    })

    # Consumer failure: fail session, clear stale queues, then reset/recover.
    adapter = IdentityAdapter(fail_on_call=1)
    p = BoundedGTCRNPipeline(
        adapter, session_id="consumer_failure", capture_capacity_samples=512,
        playback_capacity_samples=1024, max_chunk_samples=256,
    )
    p.offer_capture(make_chunk("consumer_failure", 0, 256), 0)
    p.offer_capture(make_chunk("consumer_failure", 256, 256, final=True), 0)
    assert not p.process_one(.1) and p.status == "failed" and p.lost_input_samples == 512
    p.reset_session("consumer_recovery", 512, .2)
    p.offer_capture(make_chunk("consumer_recovery", 512, 256, final=True), .2)
    assert p.process_one(.3)
    recovered = p.pop_playback(.4)
    assert recovered is not None and recovered.session_id == "consumer_recovery"
    rows.append({
        "case": "consumer_exception_and_recovery",
        "result": "PASS",
        "capture_capacity_samples": p.capture.capacity_samples,
        "capture_high_water_samples": p.capture.high_water_samples,
        "capture_backpressure_events": p.capture_backpressure_events,
        "playback_backpressure_events": p.playback_backpressure_events,
        "accepted_samples": p.accepted_input_samples,
        "processed_samples": p.processed_input_samples,
        "delivered_samples": p.delivered_output_samples,
        "lost_input_samples": 512,
        "lost_output_samples": p.lost_output_samples,
        "recovery": "adapter reset; old session queues cleared; fresh session output tagged with new session ID",
    })

    # Repeated sessions confirm the adapter reset reaches model state.
    class StateAdapter(IdentityAdapter):
        def process_chunk(self, audio, *, final=False):
            self.state_samples += 1
            return np.asarray(audio, np.float32) + self.state_samples

    adapter = StateAdapter()
    p = BoundedGTCRNPipeline(
        adapter, session_id="session_A", capture_capacity_samples=512,
        playback_capacity_samples=1024, max_chunk_samples=256,
    )
    same_samples = np.full(256, 0.25, dtype=np.float32)
    first = AudioChunk("session_A", 0, same_samples, 0.0, True)
    p.offer_capture(first, 0)
    p.process_one(.1)
    out_a = p.pop_playback(.2).samples.copy()
    p.reset_session("session_B", 10_000, .3)
    second = AudioChunk("session_B", 10_000, same_samples.copy(), .3, True)
    p.offer_capture(second, .3)
    p.process_one(.4)
    out_b = p.pop_playback(.5).samples.copy()
    assert np.array_equal(out_a, out_b)
    sessions.append({
        "case": "repeated_session_state_reset",
        "result": "PASS",
        "session_a_start_sample": 0,
        "session_b_start_sample": 10000,
        "output_samples_each": 256,
        "cross_session_sample_leakage": 0,
        "reset_proof": "stateful synthetic adapter output after reset equals fresh-state output",
    })
    return rows, sessions


def load_gtcrn_model() -> GTCRN:
    checkpoint = ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar"
    model = GTCRN().cpu().eval()
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    result = model.load_state_dict(saved["model"], strict=True)
    if result.missing_keys or result.unexpected_keys:
        raise RuntimeError(f"strict checkpoint load failed: {result}")
    return model


def append_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rss_high_water_bytes() -> int:
    """Read the process RSS high-water mark using only the standard library."""
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if platform.system() == "Darwin" else peak * 1024


def run_stress_pipeline(adapter: GTCRNStreamAdapter, out: Path, duration_s: int) -> dict[str, object]:
    cfg = ProducerConfig(total_samples=duration_s * 16000)
    producer = SyntheticProducer("stress_20s", cfg)
    pipeline = BoundedGTCRNPipeline(
        adapter, session_id="stress_20s", capture_capacity_samples=8192,
        playback_capacity_samples=8192, start_sample=0,
    )

    baseline_rss = rss_high_water_bytes()
    tracemalloc.start()
    peak_rss = baseline_rss
    memory_rows: list[dict[str, object]] = []
    telemetry: list[dict[str, object]] = []
    now = 0.0
    next_producer = producer.next_chunk()
    consumer_ready_s = 0.0
    sink_finish_s: float | None = None
    sink_rate = 16000.0
    processed_chunks = 0
    pending_blocked = False
    blocked_capture_dequeues = 0
    blocked_playback_dequeues = 0
    last_memory_bucket = -1
    seen_output_cursor = 0
    source_end = cfg.total_samples

    def record_memory(bucket: int) -> None:
        nonlocal peak_rss
        current = rss_high_water_bytes()
        peak_rss = max(peak_rss, current)
        py_current, py_peak = tracemalloc.get_traced_memory()
        state = adapter.state_summary()
        memory_rows.append({
            "audio_seconds_processed": min(duration_s, pipeline.processed_input_samples / 16000.0),
            "simulated_time_s": now,
            "rss_high_water_bytes": current,
            "rss_delta_from_stream_baseline_bytes": current - baseline_rss,
            "tracemalloc_current_bytes": py_current,
            "tracemalloc_peak_bytes": py_peak,
            "capture_occupancy_samples": pipeline.capture.occupancy_samples,
            "playback_occupancy_samples": pipeline.playback.occupancy_samples,
            "adapter_input_ring_samples": state["input_ring_samples"],
            "adapter_ola_ring_samples": state["ola_ring_samples"],
            "adapter_frames_seen": state["frames_seen"],
            "checkpoint_bucket": bucket,
        })

    telemetry.append(pipeline.snapshot(now, event="start"))
    iterations = 0
    while True:
        iterations += 1
        if iterations > 2_000_000:
            raise RuntimeError("event simulation exceeded deterministic safety bound")
        progressed = False

        if sink_finish_s is not None and sink_finish_s <= now + 1e-12:
            sink_item = pipeline.pop_playback(now)
            if sink_item is None:
                raise RuntimeError("scheduled playback item disappeared")
            if sink_item.start_sample != seen_output_cursor:
                raise RuntimeError(
                    f"output timestamp discontinuity: {sink_item.start_sample}!={seen_output_cursor}"
                )
            seen_output_cursor = sink_item.end_sample
            sink_finish_s = None
            consumer_ready_s = min(consumer_ready_s, now)
            telemetry.append(pipeline.snapshot(now, event="playback_drained"))
            progressed = True

        capture_head = pipeline.capture.peek()
        if capture_head is not None and consumer_ready_s <= now + 1e-12:
            current_samples = int(capture_head.samples.size)
            if pipeline.process_one(now):
                processed_chunks += 1
                modeled_service = current_samples / 8000.0  # consumer at 0.5x sample real-time
                if processed_chunks % 13 == 0:
                    modeled_service += 0.20  # deterministic consumer stall
                consumer_ready_s = now + modeled_service
                telemetry.append(pipeline.snapshot(now, event="consumer_processed"))
                progressed = True
            else:
                consumer_ready_s = math.inf

        if sink_finish_s is None and pipeline.playback.peek() is not None:
            sink_item = pipeline.playback.peek()
            sink_finish_s = now + len(sink_item.samples) / sink_rate
            progressed = True

        pending_ready = next_producer is not None and next_producer.arrival_s <= now + 1e-12
        may_retry = (
            not pending_blocked
            or pipeline.capture.dequeue_count != blocked_capture_dequeues
            or pipeline.playback.dequeue_count != blocked_playback_dequeues
        )
        if pending_ready and may_retry:
            result = pipeline.offer_capture(next_producer, now)
            telemetry.append(pipeline.snapshot(now, event=f"producer_{result.value}"))
            if result == OfferResult.ACCEPTED:
                pending_blocked = False
                next_producer = producer.next_chunk()
                progressed = True
            elif result == OfferResult.BACKPRESSURE:
                pending_blocked = True
                blocked_capture_dequeues = pipeline.capture.dequeue_count
                blocked_playback_dequeues = pipeline.playback.dequeue_count
                progressed = True
            else:
                raise RuntimeError(
                    "synthetic producer encountered unexpected result: "
                    f"{result}; pipeline_status={pipeline.status}; "
                    f"last_failure={pipeline.last_failure}; producer_generated="
                    f"{producer.generated_samples}/{cfg.total_samples}; "
                    f"accepted={pipeline.accepted_input_samples}; "
                    f"next_start={next_producer.start_sample if next_producer else None}"
                )

        if next_producer is None and pipeline.capture.peek() is None and pipeline.playback.peek() is None and sink_finish_s is None:
            break

        sample_bucket = pipeline.processed_input_samples // 80000
        if sample_bucket > last_memory_bucket:
            record_memory(sample_bucket)
            last_memory_bucket = sample_bucket
        candidates: list[float] = []
        if next_producer is not None and not pending_blocked:
            candidates.append(float(next_producer.arrival_s))
        if pipeline.capture.peek() is not None and math.isfinite(consumer_ready_s):
            candidates.append(float(consumer_ready_s))
        if sink_finish_s is not None:
            candidates.append(float(sink_finish_s))
        future = [event for event in candidates if event > now + 1e-12]
        if future:
            now = min(future)
        elif progressed:
            # Another zero-time pass can consume/drain/offer after a state change.
            continue
        else:
            raise RuntimeError(
                "pipeline deadlock: pending work has no producer, consumer, or playback event"
            )

    telemetry.append(pipeline.snapshot(now, event="complete"))
    record_memory(duration_s // 4)
    tracemalloc.stop()
    summary = pipeline.summary(now)
    summary.update({
        "producer_generated_samples": producer.generated_samples,
        "producer_generated_chunks": producer.generated_chunks,
        "producer_max_pending_samples": producer.max_pending_samples,
        "producer_config": {
            "sample_rate_hz": cfg.sample_rate,
            "burst_chunks": cfg.burst_chunks,
            "burst_period_s": cfg.burst_period_s,
            "burst_spacing_s": cfg.burst_spacing_s,
            "chunk_pattern_samples": list(cfg.chunk_pattern),
            "seed": cfg.seed,
        },
        "simulated_elapsed_s": now,
        "producer_accepted_rate_samples_per_s": producer.generated_samples / now if now else 0.0,
        "modeled_consumer_rate": "sample duration / 0.5 plus a 200 ms stall every 13 consumed chunks",
        "sink_rate_samples_per_s": sink_rate,
        "iterations": iterations,
        "peak_rss_bytes_during_stream": peak_rss,
        "rss_baseline_before_stream_bytes": baseline_rss,
        "rss_growth_peak_bytes": peak_rss - baseline_rss,
        "adapter_final_state": adapter.state_summary(),
        "expected_input_samples": source_end,
        "output_timestamp_cursor": seen_output_cursor,
    })
    if producer.generated_samples != source_end:
        raise RuntimeError("producer did not generate exactly the configured sample count")
    if not (
        summary["accepted_input_samples"] == summary["processed_input_samples"]
        == summary["generated_output_samples"] == summary["delivered_output_samples"]
        == source_end
    ):
        raise RuntimeError(
            "end-to-end sample accounting did not close exactly: "
            f"generated_by_producer={producer.generated_samples}, "
            f"accepted={summary['accepted_input_samples']}, "
            f"processed={summary['processed_input_samples']}, "
            f"generated_output={summary['generated_output_samples']}, "
            f"delivered={summary['delivered_output_samples']}, "
            f"cursor={seen_output_cursor}, expected={source_end}, "
            f"status={summary['status']}"
        )
    if summary["lost_input_samples"] or summary["lost_output_samples"] or seen_output_cursor != source_end:
        raise RuntimeError("stream completed with unreported loss or timestamp discontinuity")
    if pipeline.capture.high_water_samples > pipeline.capture.capacity_samples:
        raise RuntimeError("capture queue exceeded configured capacity")
    if pipeline.playback.high_water_samples > pipeline.playback.capacity_samples:
        raise RuntimeError("playback queue exceeded configured capacity")
    if summary["adapter_final_state"]["max_input_ring_samples"] > 576:
        raise RuntimeError("GTCRN adapter input ring exceeded the Stage 11.2.18 observed bound")
    if summary["adapter_final_state"]["max_ola_ring_samples"] > 512:
        raise RuntimeError("GTCRN adapter overlap ring exceeded the Stage 11.2.18 observed bound")

    append_csv(out / "queue_telemetry.csv", telemetry)
    append_csv(out / "memory_telemetry.csv", memory_rows)
    (out / "pipeline_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def run_actual_adapter_session_reset(model: GTCRN) -> dict[str, object]:
    signal = np.random.default_rng(26053).normal(0, 0.05, 8192).astype(np.float32)
    adapter = GTCRNStreamAdapter(model)
    p = BoundedGTCRNPipeline(
        adapter, session_id="actual_A", capture_capacity_samples=8192,
        playback_capacity_samples=8192,
    )
    cursor = 0
    for start in range(0, 4096, 256):
        part = signal[start:start + 256]
        final = start + len(part) == 4096
        item = AudioChunk("actual_A", cursor, part, start / 16000.0, final)
        if p.offer_capture(item, start / 16000.0) != OfferResult.ACCEPTED:
            raise RuntimeError("unexpected capture backpressure in short reset probe")
        cursor += len(part)
        if not p.process_one((start + 256) / 16000.0):
            raise RuntimeError("actual GTCRN consumer failed session A")
    while p.playback.peek() is not None:
        p.pop_playback(1.0)
    p.reset_session("actual_B", 100_000, 1.1)

    parts_b = signal[4096:]
    cursor = 100_000
    streamed: list[np.ndarray] = []
    for start in range(0, len(parts_b), 256):
        part = parts_b[start:start + 256]
        final = start + len(part) == len(parts_b)
        event_time = 2.1 + start / 16000.0
        item = AudioChunk("actual_B", cursor, part, event_time, final)
        if p.offer_capture(item, event_time) != OfferResult.ACCEPTED:
            raise RuntimeError("unexpected capture backpressure in session B")
        cursor += len(part)
        if not p.process_one(event_time + .001):
            raise RuntimeError("actual GTCRN consumer failed session B")
        while p.playback.peek() is not None:
            output = p.pop_playback(event_time + .002)
            if output.session_id != "actual_B":
                raise RuntimeError("stale output from prior session escaped after reset")
            streamed.append(output.samples)
    y_stream = np.concatenate(streamed)

    fresh = GTCRNStreamAdapter(model)
    fresh_parts = [fresh.process_chunk(parts_b[i:i + 256], final=(i + 256 >= len(parts_b)))
                   for i in range(0, len(parts_b), 256)]
    y_fresh = np.concatenate(fresh_parts)
    if y_stream.shape != y_fresh.shape:
        raise RuntimeError("actual adapter reset changed output sample count")
    max_abs = float(np.max(np.abs(y_stream - y_fresh)))
    if not np.allclose(y_stream, y_fresh, atol=1e-5, rtol=1e-5):
        raise RuntimeError("actual adapter output after pipeline reset differs from fresh state")
    return {
        "result": "PASS",
        "session_a_input_samples": 4096,
        "session_b_input_samples": int(len(parts_b)),
        "session_b_output_samples": int(len(y_stream)),
        "session_b_start_sample": 100_000,
        "max_abs_diff_vs_fresh_adapter": max_abs,
        "cross_session_output_samples": 0,
        "status_after_b": p.status,
        "stage17_adapter_state_after_reset_stream": adapter.state_summary(),
    }


def write_hashes(out: Path, source_paths: list[Path]) -> None:
    paths = source_paths + [
        p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"
    ]
    def ledger_path(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    lines = [f"{sha256(p)}  {ledger_path(p)}" for p in sorted(set(paths))]
    (out / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r1",
    )
    parser.add_argument("--duration-s", type=int, default=20)
    args = parser.parse_args()
    if args.duration_s < 20:
        parser.error("duration-s must be at least 20 seconds to qualify as the required soak")
    out = args.output_dir.expanduser().resolve()
    if out.exists():
        parser.error(f"refusing to overwrite existing evidence directory: {out}")

    before = protected_hashes()
    out.mkdir(parents=True)
    rss_before_model = rss_high_water_bytes()
    torch.manual_seed(26052)
    torch.set_num_threads(1)
    model = load_gtcrn_model()
    rss_after_model = rss_high_water_bytes()

    policy_rows, session_rows = run_policy_probes()
    append_csv(out / "overflow_recovery_results.csv", policy_rows)
    append_csv(out / "session_isolation_results.csv", session_rows)
    actual_session = run_actual_adapter_session_reset(model)
    (out / "actual_gtcrn_session_reset.json").write_text(
        json.dumps(actual_session, indent=2) + "\n", encoding="utf-8"
    )
    adapter = GTCRNStreamAdapter(model)
    stress_summary = run_stress_pipeline(adapter, out, args.duration_s)
    after = protected_hashes()
    if before != after:
        raise RuntimeError("protected artifact hashes changed during Stage 11.2.19")

    git = git_state()
    git["stage_start_snapshot_note"] = (
        "Before Stage 11.2.19 changes: HEAD 242e24c6fd803729314a5636d63ae0be235ce2e4; "
        "2 modified tracked entries (REPORT.md, system_diagrams.md); 97 untracked entries; "
        "this Stage 11.2.19 experiment directory did not exist. A same-turn audit hardening "
        "module/report were already among those untracked entries."
    )
    metadata = {
        "stage": "11.2.19",
        "scope": "synthetic host pipeline only; no project recording or hardware",
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "rss_sampler": "resource.getrusage(ru_maxrss), cumulative process RSS high-water",
            "torch_threads": torch.get_num_threads(),
            "rss_before_model_load_bytes": rss_before_model,
            "rss_after_model_load_bytes": rss_after_model,
        },
        "seed": 26052,
        "command": [sys.executable, *sys.argv],
        "git_state": git,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "gtcrn_checkpoint_strict_load": "PASS",
        "policy_probe_count": len(policy_rows),
        "policy_probe_failures": [r["case"] for r in policy_rows if r["result"] != "PASS"],
        "actual_gtcrn_session_reset": actual_session,
        "stress_summary": stress_summary,
        "limitations": [
            "The simulation uses a flow-controlled producer; physical microphones cannot be assumed to pause.",
            "Queue capacity and queue-age limits are not end-to-end deadline guarantees.",
            "Consumer service and sink timing are deterministic simulated rates; GTCRN wall time is measured separately.",
            "No Raspberry Pi, ALSA, USB/I2S, live audio, canonical validation or gold data was accessed.",
            "This verifies only bounded host queues and sample accounting under the tested synthetic workload.",
        ],
    }
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    sources = [
        HERE / "bounded_pipeline.py",
        HERE / "synthetic_producer.py",
        HERE / "test_bounded_pipeline.py",
        HERE / "run_stage11_2_19.py",
        ROOT / "experiments/stage11_2_17_gtcrn_streaming/gtcrn_stream_adapter.py",
        ROOT / "third_party/gtcrn_stage5/gtcrn.py",
    ]
    write_hashes(out, sources)
    print(json.dumps({
        "output_dir": str(out),
        "accepted_samples": stress_summary["accepted_input_samples"],
        "lost_input_samples": stress_summary["lost_input_samples"],
        "lost_output_samples": stress_summary["lost_output_samples"],
        "capture_high_water": stress_summary["capture_queue"]["high_water_samples"],
        "playback_high_water": stress_summary["playback_queue"]["high_water_samples"],
        "rss_peak_bytes": stress_summary["peak_rss_bytes_during_stream"],
        "policy_probes": len(policy_rows),
        "protected_hashes_unchanged": before == after,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
