"""Bounded, sample-accounted host pipeline for the frozen GTCRN adapter.

This module has no device or dataset access. The producer and sink are explicit
callers; a full queue returns BACKPRESSURE and retains no hidden copy. The
producer must retry the same timestamped chunk. An unpausable producer must
abort the session and report its exact discontinuity instead of continuing as
though the output were continuous.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
import math
import time
from typing import Any, Protocol

import numpy as np


class StreamingAdapter(Protocol):
    max_chunk_samples: int
    n_fft: int

    def process_chunk(self, audio: np.ndarray, *, final: bool = False) -> np.ndarray: ...

    def reset_session(self) -> None: ...


@dataclass(frozen=True)
class AudioChunk:
    session_id: str
    start_sample: int
    samples: np.ndarray
    arrival_s: float
    final: bool = False

    @property
    def end_sample(self) -> int:
        return self.start_sample + int(self.samples.size)


class OfferResult(str, Enum):
    ACCEPTED = "accepted"
    BACKPRESSURE = "backpressure_retry_same_chunk"
    REJECTED_INVALID = "rejected_invalid_no_state_change"
    FAILED_SESSION = "failed_session_discontinuous"
    CLOSED = "closed_session"


@dataclass
class LossRecord:
    session_id: str
    direction: str
    start_sample: int
    end_sample: int
    reason: str

    @property
    def samples(self) -> int:
        return max(0, self.end_sample - self.start_sample)


@dataclass
class QueueItem:
    session_id: str
    start_sample: int
    samples: np.ndarray
    enqueued_at_s: float
    final: bool = False

    @property
    def end_sample(self) -> int:
        return self.start_sample + int(self.samples.size)


class BoundedAudioQueue:
    """FIFO bounded in samples, with time-weighted occupancy and age telemetry."""

    def __init__(self, name: str, capacity_samples: int, *, expected_start: int = 0):
        if capacity_samples <= 0:
            raise ValueError("queue capacity must be positive")
        self.name = name
        self.capacity_samples = int(capacity_samples)
        self._items: deque[QueueItem] = deque()
        self.occupancy_samples = 0
        self.high_water_samples = 0
        self.enqueue_count = 0
        self.dequeue_count = 0
        self.backpressure_attempts = 0
        self.backpressured_samples = 0
        self._expected_start = int(expected_start)
        self._last_observe_s: float | None = None
        self._observed_duration_s = 0.0
        self._occupancy_area_sample_seconds = 0.0
        # Retain only a fixed-size sample for percentiles. Exact mean and
        # count remain streaming accumulators, so long sessions do not grow
        # telemetry memory with the number of chunks.
        self._dequeue_ages_s: deque[float] = deque(maxlen=4096)
        self._dequeue_age_sum_s = 0.0
        self._dequeue_age_count = 0
        self._max_oldest_age_s = 0.0

    def observe(self, now_s: float) -> None:
        now_s = float(now_s)
        if not math.isfinite(now_s) or now_s < 0:
            raise ValueError("queue clock must be finite and non-negative")
        if self._last_observe_s is not None:
            if now_s < self._last_observe_s:
                raise ValueError("queue clock moved backwards")
            dt = now_s - self._last_observe_s
            self._observed_duration_s += dt
            self._occupancy_area_sample_seconds += self.occupancy_samples * dt
        self._last_observe_s = now_s
        self._max_oldest_age_s = max(self._max_oldest_age_s, self.oldest_age_s(now_s))

    def try_put(self, item: QueueItem, now_s: float) -> bool:
        self.observe(now_s)
        n = int(item.samples.size)
        if n <= 0:
            raise ValueError("zero-length items are not queued")
        if item.start_sample != self._expected_start:
            raise ValueError(
                f"{self.name} timestamp discontinuity: expected {self._expected_start}, "
                f"received {item.start_sample}"
            )
        if self.occupancy_samples + n > self.capacity_samples:
            self.backpressure_attempts += 1
            self.backpressured_samples += n
            return False
        self._items.append(item)
        self.occupancy_samples += n
        self._expected_start = item.end_sample
        self.enqueue_count += 1
        self.high_water_samples = max(self.high_water_samples, self.occupancy_samples)
        return True

    def peek(self) -> QueueItem | None:
        return self._items[0] if self._items else None

    def pop(self, now_s: float) -> QueueItem | None:
        self.observe(now_s)
        if not self._items:
            return None
        item = self._items.popleft()
        self.occupancy_samples -= int(item.samples.size)
        self.dequeue_count += 1
        age = max(0.0, float(now_s) - item.enqueued_at_s)
        self._dequeue_ages_s.append(age)
        self._dequeue_age_sum_s += age
        self._dequeue_age_count += 1
        self._max_oldest_age_s = max(self._max_oldest_age_s, age)
        return item

    def oldest_age_s(self, now_s: float) -> float:
        if not self._items:
            return 0.0
        return max(0.0, float(now_s) - self._items[0].enqueued_at_s)

    def clear(self, now_s: float, *, next_start: int) -> list[QueueItem]:
        self.observe(now_s)
        removed = list(self._items)
        self._items.clear()
        self.occupancy_samples = 0
        self._expected_start = int(next_start)
        return removed

    def set_expected_start(self, start_sample: int) -> None:
        if self._items:
            raise RuntimeError("cannot change queue timestamp origin while non-empty")
        self._expected_start = int(start_sample)

    def telemetry(self, now_s: float) -> dict[str, Any]:
        self.observe(now_s)
        ages = np.asarray(self._dequeue_ages_s, dtype=np.float64)
        duration = self._observed_duration_s
        return {
            "name": self.name,
            "capacity_samples": self.capacity_samples,
            "occupancy_samples": self.occupancy_samples,
            "occupancy_fraction": self.occupancy_samples / self.capacity_samples,
            "mean_occupancy_samples": (
                self._occupancy_area_sample_seconds / duration
                if duration > 0 else float(self.occupancy_samples)
            ),
            "high_water_samples": self.high_water_samples,
            "oldest_age_s": self.oldest_age_s(now_s),
            "mean_dequeue_age_s": (
                self._dequeue_age_sum_s / self._dequeue_age_count
                if self._dequeue_age_count else 0.0
            ),
            "dequeue_age_percentile_sample_count": int(ages.size),
            "p95_dequeue_age_s": float(np.percentile(ages, 95)) if ages.size else 0.0,
            "p99_dequeue_age_s": float(np.percentile(ages, 99)) if ages.size else 0.0,
            "max_observed_age_s": self._max_oldest_age_s,
            "enqueue_count": self.enqueue_count,
            "dequeue_count": self.dequeue_count,
            "backpressure_attempts": self.backpressure_attempts,
            "backpressured_attempt_samples": self.backpressured_samples,
        }


class BoundedGTCRNPipeline:
    """Single-session ordering/accounting around an existing GTCRN adapter."""

    def __init__(
        self,
        adapter: StreamingAdapter,
        *,
        session_id: str,
        capture_capacity_samples: int = 8192,
        playback_capacity_samples: int = 8192,
        start_sample: int = 0,
        max_chunk_samples: int | None = None,
    ):
        self.adapter = adapter
        adapter_limit = int(adapter.max_chunk_samples)
        self.max_chunk_samples = min(adapter_limit, int(max_chunk_samples or adapter_limit))
        if self.max_chunk_samples <= 0:
            raise ValueError("max chunk size must be positive")
        if capture_capacity_samples < self.max_chunk_samples:
            raise ValueError("capture capacity must fit one maximum-size input chunk")
        # A non-final centered-STFT call can retain samples until a frame
        # center; the next call can therefore emit its own chunk plus up to one
        # FFT window of prior output. Reserve this conservative bound on every
        # call so playback capacity is guaranteed before adapter state mutates.
        self.output_tail_reservation_samples = int(
            getattr(adapter, "max_output_tail_samples", int(adapter.n_fft))
        )
        self.max_output_reservation = (
            self.max_chunk_samples + self.output_tail_reservation_samples
        )
        if playback_capacity_samples < self.max_output_reservation:
            raise ValueError(
                "playback capacity must fit one maximum output reservation "
                f"({self.max_output_reservation} samples)"
            )
        self.capture = BoundedAudioQueue(
            "capture", capture_capacity_samples, expected_start=start_sample
        )
        self.playback = BoundedAudioQueue(
            "playback", playback_capacity_samples, expected_start=start_sample
        )
        self.session_id = str(session_id)
        self.session_origin = int(start_sample)
        self.next_input_sample = int(start_sample)
        self.next_output_sample = int(start_sample)
        self.status = "active"
        self.final_input_accepted = False
        self.final_input_processed = False
        self.discontinuities = 0
        self.invalid_inputs = 0
        self.consumer_failures = 0
        self.last_failure: str | None = None
        self.capture_backpressure_events = 0
        self.playback_backpressure_events = 0
        self.backpressure_duration_s = 0.0
        self.playback_backpressure_duration_s = 0.0
        self._capture_blocked_since_s: float | None = None
        self._playback_blocked_since_s: float | None = None
        self.accepted_input_samples = 0
        self.session_accepted_input_samples = 0
        self.processed_input_samples = 0
        self.generated_output_samples = 0
        self.session_generated_output_samples = 0
        self.delivered_output_samples = 0
        self.input_offer_attempts = 0
        self.losses: list[LossRecord] = []
        self.processing_wall_s: deque[float] = deque(maxlen=4096)
        self.processing_wall_count = 0
        self.processing_wall_sum_s = 0.0
        self.processing_wall_max_s = 0.0
        self.telemetry_rows: deque[dict[str, Any]] = deque(maxlen=4096)

    def _record_processing_time(self, elapsed_s: float) -> None:
        elapsed_s = float(elapsed_s)
        self.processing_wall_s.append(elapsed_s)
        self.processing_wall_count += 1
        self.processing_wall_sum_s += elapsed_s
        self.processing_wall_max_s = max(self.processing_wall_max_s, elapsed_s)

    def _record_loss(self, direction: str, start: int, end: int, reason: str) -> None:
        if end > start:
            self.losses.append(
                LossRecord(self.session_id, direction, int(start), int(end), reason)
            )

    @property
    def lost_input_samples(self) -> int:
        return sum(r.samples for r in self.losses if r.direction == "input")

    @property
    def lost_output_samples(self) -> int:
        return sum(r.samples for r in self.losses if r.direction == "output")

    def _validate_input(self, chunk: AudioChunk) -> np.ndarray:
        if chunk.session_id != self.session_id:
            raise ValueError("chunk belongs to a different session")
        if not isinstance(chunk.start_sample, (int, np.integer)) or chunk.start_sample < 0:
            raise ValueError("start_sample must be a non-negative integer")
        if not math.isfinite(float(chunk.arrival_s)) or chunk.arrival_s < 0:
            raise ValueError("arrival timestamp must be finite and non-negative")
        raw = np.asarray(chunk.samples)
        if raw.ndim != 1:
            raise ValueError("audio must be mono one-dimensional samples")
        if not np.issubdtype(raw.dtype, np.number) or np.issubdtype(
            raw.dtype, np.complexfloating
        ):
            raise ValueError("audio must have a real numeric dtype")
        if raw.size == 0 or raw.size > self.max_chunk_samples:
            raise ValueError(
                f"audio chunk size must be in 1..{self.max_chunk_samples} samples"
            )
        if not np.isfinite(raw).all():
            raise ValueError("audio contains NaN or infinity")
        return np.ascontiguousarray(raw, dtype=np.float32).copy()

    def offer_capture(self, chunk: AudioChunk, now_s: float) -> OfferResult:
        self.input_offer_attempts += 1
        if self.status != "active" or self.final_input_accepted:
            return OfferResult.CLOSED
        try:
            samples = self._validate_input(chunk)
        except (TypeError, ValueError, OverflowError):
            self.invalid_inputs += 1
            return OfferResult.REJECTED_INVALID

        if chunk.start_sample != self.next_input_sample:
            self.discontinuities += 1
            if chunk.start_sample > self.next_input_sample:
                # The unknown gap and the rejected current chunk are one exact
                # discontinuous interval from the next expected sample onward.
                self._record_loss(
                    "input", self.next_input_sample, chunk.start_sample + len(samples),
                    "producer_timestamp_gap_or_unaccepted_chunk",
                )
            else:
                # A duplicate/reordered chunk is observable but is not counted
                # as new lost audio because those sample indices were seen.
                self.losses.append(LossRecord(
                    self.session_id, "incident", int(chunk.start_sample),
                    int(chunk.start_sample + len(samples)), "duplicate_or_reordered_input",
                ))
            self._abort("producer_discontinuity", now_s)
            return OfferResult.FAILED_SESSION

        item = QueueItem(
            self.session_id, int(chunk.start_sample), samples, float(now_s), bool(chunk.final)
        )
        if not self.capture.try_put(item, now_s):
            self.capture_backpressure_events += 1
            if self._capture_blocked_since_s is None:
                self._capture_blocked_since_s = float(now_s)
            return OfferResult.BACKPRESSURE

        if self._capture_blocked_since_s is not None:
            self.backpressure_duration_s += max(0.0, float(now_s) - self._capture_blocked_since_s)
            self._capture_blocked_since_s = None
        self.next_input_sample += int(samples.size)
        self.accepted_input_samples += int(samples.size)
        self.session_accepted_input_samples += int(samples.size)
        self.final_input_accepted = bool(chunk.final)
        return OfferResult.ACCEPTED

    def abort_unretriable_capture(self, chunk: AudioChunk, now_s: float) -> None:
        """Fail closed when an upstream source cannot honor retry backpressure."""
        if self.status != "active":
            return
        try:
            samples = self._validate_input(chunk)
        except (TypeError, ValueError, OverflowError):
            self.invalid_inputs += 1
            self._abort("invalid_unretriable_capture", now_s)
            return
        if chunk.start_sample != self.next_input_sample:
            self.discontinuities += 1
            self._record_loss(
                "input", min(self.next_input_sample, chunk.start_sample),
                max(self.next_input_sample, chunk.start_sample + len(samples)),
                "unretriable_capture_timestamp_discontinuity",
            )
        else:
            self.discontinuities += 1
            self._record_loss(
                "input", chunk.start_sample, chunk.start_sample + len(samples),
                "unretriable_capture_overflow",
            )
        self._abort("unretriable_capture_overflow", now_s)

    def can_process(self, now_s: float) -> bool:
        item = self.capture.peek()
        if self.status != "active" or item is None:
            return False
        reserve = int(item.samples.size) + self.output_tail_reservation_samples
        reserve = min(reserve, self.playback.capacity_samples)
        return self.playback.capacity_samples - self.playback.occupancy_samples >= reserve

    def process_one(self, now_s: float) -> bool:
        if self.status != "active":
            return False
        item = self.capture.peek()
        if item is None:
            return False
        reserve = int(item.samples.size) + self.output_tail_reservation_samples
        if self.playback.capacity_samples - self.playback.occupancy_samples < reserve:
            self.playback_backpressure_events += 1
            if self._playback_blocked_since_s is None:
                self._playback_blocked_since_s = float(now_s)
            return False

        started = time.perf_counter()
        timing_recorded = False
        try:
            output = np.asarray(self.adapter.process_chunk(item.samples, final=item.final))
            elapsed = time.perf_counter() - started
            self._record_processing_time(elapsed)
            timing_recorded = True
            if output.ndim != 1 or not np.issubdtype(output.dtype, np.number):
                raise RuntimeError("adapter output is not real one-dimensional audio")
            if np.iscomplexobj(output) or not np.isfinite(output).all():
                raise RuntimeError("adapter output is complex or non-finite")
            if output.size > reserve:
                raise RuntimeError(
                    f"adapter output exceeded reserved bound: {output.size}>{reserve}"
                )
            output = np.ascontiguousarray(output, dtype=np.float32)
            if self._playback_blocked_since_s is not None:
                self.playback_backpressure_duration_s += max(
                    0.0, float(now_s) - self._playback_blocked_since_s
                )
                self._playback_blocked_since_s = None
            if output.size:
                out_item = QueueItem(
                    self.session_id, self.next_output_sample, output.copy(), float(now_s), False
                )
                if not self.playback.try_put(out_item, now_s):
                    raise RuntimeError("reserved playback capacity was not available")
                self.next_output_sample += int(output.size)
                self.generated_output_samples += int(output.size)
                self.session_generated_output_samples += int(output.size)
            removed = self.capture.pop(now_s)
            if removed is not item:
                raise RuntimeError("capture queue head changed during single-consumer processing")
            self.processed_input_samples += int(item.samples.size)
            if item.final:
                self.final_input_processed = True
                if self.capture.occupancy_samples != 0:
                    raise RuntimeError("input was queued after final chunk")
                if self.session_generated_output_samples != self.session_accepted_input_samples:
                    raise RuntimeError(
                        "final adapter flush did not emit exactly the accepted input sample count: "
                        f"{self.session_generated_output_samples}!={self.session_accepted_input_samples}"
                    )
                self.status = "closed"
            return True
        except Exception as exc:
            if not timing_recorded:
                self._record_processing_time(time.perf_counter() - started)
            self.consumer_failures += 1
            self.last_failure = f"{type(exc).__name__}: {exc}"
            self._abort("consumer_exception_or_output_contract_violation", now_s)
            return False

    def pop_playback(self, now_s: float) -> QueueItem | None:
        item = self.playback.pop(now_s)
        if item is not None:
            self.delivered_output_samples += int(item.samples.size)
        return item

    def _abort(self, reason: str, now_s: float) -> None:
        queued_input = self.capture.clear(
            now_s, next_start=self.next_input_sample
        )
        for item in queued_input:
            self._record_loss("input", item.start_sample, item.end_sample, reason)
        queued_output = self.playback.clear(
            now_s, next_start=self.next_output_sample
        )
        for item in queued_output:
            self._record_loss("output", item.start_sample, item.end_sample, reason)
        try:
            self.adapter.reset_session()
        finally:
            self.status = "failed"
            self.final_input_accepted = True
            self._capture_blocked_since_s = None
            self._playback_blocked_since_s = None

    def reset_session(
        self,
        new_session_id: str,
        start_sample: int,
        now_s: float,
        *,
        pending_unaccepted: AudioChunk | None = None,
    ) -> None:
        if str(new_session_id) == self.session_id:
            raise ValueError("session reset requires a new session_id")
        if start_sample < 0:
            raise ValueError("start_sample must be non-negative")
        if pending_unaccepted is not None and pending_unaccepted.session_id != self.session_id:
            raise ValueError("pending chunk belongs to a different session")
        queued_input = self.capture.clear(now_s, next_start=start_sample)
        for item in queued_input:
            self._record_loss("input", item.start_sample, item.end_sample, "session_reset")
        if pending_unaccepted is not None:
            pending_size = int(np.asarray(pending_unaccepted.samples).size)
            if pending_size:
                self._record_loss(
                    "input", pending_unaccepted.start_sample,
                    pending_unaccepted.start_sample + pending_size,
                    "session_reset_pending_unaccepted_chunk",
                )
        queued_output = self.playback.clear(now_s, next_start=start_sample)
        for item in queued_output:
            self._record_loss("output", item.start_sample, item.end_sample, "session_reset")
        self.adapter.reset_session()
        self.session_id = str(new_session_id)
        self.session_origin = int(start_sample)
        self.next_input_sample = int(start_sample)
        self.next_output_sample = int(start_sample)
        self.session_accepted_input_samples = 0
        self.session_generated_output_samples = 0
        self.status = "active"
        self.last_failure = None
        self.final_input_accepted = False
        self.final_input_processed = False
        self._capture_blocked_since_s = None
        self._playback_blocked_since_s = None
        self.capture.set_expected_start(start_sample)
        self.playback.set_expected_start(start_sample)

    def snapshot(self, now_s: float, *, event: str) -> dict[str, Any]:
        cap = self.capture.telemetry(now_s)
        play = self.playback.telemetry(now_s)
        row = {
            "time_s": float(now_s),
            "event": event,
            "session_id": self.session_id,
            "status": self.status,
            "capture_occupancy_samples": cap["occupancy_samples"],
            "capture_capacity_samples": cap["capacity_samples"],
            "capture_high_water_samples": cap["high_water_samples"],
            "capture_oldest_age_s": cap["oldest_age_s"],
            "playback_occupancy_samples": play["occupancy_samples"],
            "playback_capacity_samples": play["capacity_samples"],
            "playback_high_water_samples": play["high_water_samples"],
            "playback_oldest_age_s": play["oldest_age_s"],
        }
        self.telemetry_rows.append(row)
        return row

    def summary(self, now_s: float) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "capture_queue": self.capture.telemetry(now_s),
            "playback_queue": self.playback.telemetry(now_s),
            "input_offer_attempts": self.input_offer_attempts,
            "accepted_input_samples": self.accepted_input_samples,
            "processed_input_samples": self.processed_input_samples,
            "generated_output_samples": self.generated_output_samples,
            "delivered_output_samples": self.delivered_output_samples,
            "lost_input_samples": self.lost_input_samples,
            "lost_output_samples": self.lost_output_samples,
            "invalid_inputs": self.invalid_inputs,
            "consumer_failures": self.consumer_failures,
            "last_failure": self.last_failure,
            "discontinuities": self.discontinuities,
            "capture_backpressure_events": self.capture_backpressure_events,
            "playback_backpressure_events": self.playback_backpressure_events,
            "backpressure_duration_s": self.backpressure_duration_s,
            "playback_backpressure_duration_s": self.playback_backpressure_duration_s,
            "loss_records": [asdict(record) | {"samples": record.samples} for record in self.losses],
            "processing_wall_ms": {
                "count": self.processing_wall_count,
                "mean": self.processing_wall_sum_s / self.processing_wall_count * 1000 if self.processing_wall_count else 0.0,
                "p95": float(np.percentile(self.processing_wall_s, 95) * 1000) if self.processing_wall_s else 0.0,
                "p99": float(np.percentile(self.processing_wall_s, 99) * 1000) if self.processing_wall_s else 0.0,
                "percentile_sample_count": len(self.processing_wall_s),
                "max": self.processing_wall_max_s * 1000,
            },
        }
