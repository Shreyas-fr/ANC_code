"""Stateful linear resampling with a fractional input pointer.

Keeps remainder samples so adjacent blocks are continuous. Used for the
16 kHz <-> 48 kHz live path instead of recreating a resampler per packet.
"""
from __future__ import annotations

import numpy as np


class StatefulLinearResampler:
    def __init__(self, in_sr: int, out_sr: int):
        if in_sr <= 0 or out_sr <= 0:
            raise ValueError("sample rates must be positive")
        self.in_sr = int(in_sr)
        self.out_sr = int(out_sr)
        self.ratio = self.out_sr / float(self.in_sr)
        self.frac = 0.0
        self.buf = np.zeros(0, dtype=np.float64)

    def reset(self) -> None:
        self.frac = 0.0
        self.buf = np.zeros(0, dtype=np.float64)

    def process(self, chunk: np.ndarray) -> np.ndarray:
        if chunk is None or len(chunk) == 0:
            return np.zeros(0, dtype=np.float32)
        x = np.asarray(chunk, dtype=np.float64).reshape(-1)
        if self.in_sr == self.out_sr:
            return x.astype(np.float32)

        self.buf = np.concatenate([self.buf, x]) if len(self.buf) else x.copy()
        if len(self.buf) < 2:
            return np.zeros(0, dtype=np.float32)

        out = []
        step = 1.0 / self.ratio
        last_index = len(self.buf) - 1
        while self.frac + 1e-12 < last_index:
            i = int(self.frac)
            f = self.frac - i
            y = self.buf[i] * (1.0 - f) + self.buf[i + 1] * f
            out.append(y)
            self.frac += step

        drop = int(self.frac)
        if drop > 0:
            drop = min(drop, len(self.buf) - 1)
            self.buf = self.buf[drop:]
            self.frac -= drop
        return np.asarray(out, dtype=np.float32)
