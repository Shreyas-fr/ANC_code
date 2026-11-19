"""Deterministic timestamped synthetic producer with configurable bursts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bounded_pipeline import AudioChunk


@dataclass(frozen=True)
class ProducerConfig:
    total_samples: int = 320_000  # 20 seconds at 16 kHz
    sample_rate: int = 16_000
    chunk_pattern: tuple[int, ...] = (1024, 256, 2048, 512, 4096, 160, 320, 3072, 2048, 4096)
    burst_chunks: int = 10
    burst_period_s: float = 0.6
    burst_spacing_s: float = 0.001
    seed: int = 26052

    def __post_init__(self) -> None:
        if self.total_samples <= 0 or self.sample_rate <= 0:
            raise ValueError("producer duration and sample rate must be positive")
        if not self.chunk_pattern or any(size <= 0 for size in self.chunk_pattern):
            raise ValueError("chunk pattern must contain positive sizes")
        if any(size > 4096 for size in self.chunk_pattern):
            raise ValueError("producer chunk pattern exceeds the adapter's 4096-sample limit")
        if self.burst_chunks <= 0 or self.burst_period_s <= 0 or self.burst_spacing_s < 0:
            raise ValueError("invalid producer burst configuration")
        if self.burst_spacing_s * self.burst_chunks > self.burst_period_s:
            raise ValueError("burst spacing exceeds burst period")


class SyntheticProducer:
    """Generate mono float32 noise-plus-tone chunks lazily, retaining at most one."""

    def __init__(self, session_id: str, config: ProducerConfig = ProducerConfig()):
        self.session_id = session_id
        self.config = config
        self.generated_samples = 0
        self.generated_chunks = 0
        self.max_pending_samples = 0
        self._rng = np.random.default_rng(config.seed)

    def next_chunk(self) -> AudioChunk | None:
        if self.generated_samples >= self.config.total_samples:
            return None
        pattern_size = self.config.chunk_pattern[
            self.generated_chunks % len(self.config.chunk_pattern)
        ]
        count = min(pattern_size, self.config.total_samples - self.generated_samples)
        start = self.generated_samples
        indices = np.arange(start, start + count, dtype=np.float64)
        t = indices / self.config.sample_rate
        noise = self._rng.normal(0.0, 0.003, count)
        signal = (
            0.18 * np.sin(2.0 * np.pi * 440.0 * t)
            + 0.06 * np.sin(2.0 * np.pi * 1370.0 * t)
            + noise
        ).astype(np.float32)
        group, offset = divmod(self.generated_chunks, self.config.burst_chunks)
        arrival_s = group * self.config.burst_period_s + offset * self.config.burst_spacing_s
        final = start + count == self.config.total_samples
        chunk = AudioChunk(self.session_id, start, signal, arrival_s, final)
        self.generated_samples += count
        self.generated_chunks += 1
        self.max_pending_samples = max(self.max_pending_samples, count)
        return chunk
