"""
streaming_core.py - deterministic 16 kHz <-> 48 kHz audio chain for the Pi sender.

Fixes over the old live path:
  * Resampling is STATEFUL (FIR state carried across packets) instead of one
    torchaudio.resample() call per 16 ms packet, which put an edge
    discontinuity at every packet boundary.
  * Explicit framing: 256 samples @16k in -> 768 @48k -> 480-sample hops
    -> 160 @16k out -> always exactly 256 @16k out per call.
  * Backends are pluggable; the latency of every stage is reported honestly.
  * BlockBackend runs a *whole-signal-correct* enhance() on overlapping windows
    with left context, right guard and crossfade. df.enhance() is an offline
    call (it resets GRU state and trims STFT delay on every call), so calling it
    on single 16 ms chunks is not a valid streaming implementation.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Callable, Optional

import numpy as np
from scipy import signal

HOP_48K = 480           # DeepFilterNet3 hop: 10 ms @ 48 kHz
FS_IO = 16000
FS_PROC = 48000


# --------------------------------------------------------------------------- #
# Stateful rational resampler
# --------------------------------------------------------------------------- #
class StatefulResampler:
    """Zero-stuff by `up`, linear-phase FIR low-pass, keep every `down`-th sample.

    The FIR delay line (and decimation phase) persists between calls, so
    process(a); process(b) == process(concat(a, b)) exactly.
    """

    def __init__(self, up: int, down: int, fs_in: int, numtaps: int = 193, beta: float = 8.0):
        assert numtaps % 2 == 1
        self.up, self.down, self.fs_in = up, down, fs_in
        cutoff = 0.9 / max(up, down)  # fraction of Nyquist of the high-rate stream
        self.b = signal.firwin(numtaps, cutoff, window=("kaiser", beta)) * up
        self.zi = np.zeros(numtaps - 1)
        self._pos = 0  # global index of next filtered sample (decimation phase)
        self.numtaps = numtaps

    @property
    def delay_s(self) -> float:
        return ((self.numtaps - 1) / 2) / (self.fs_in * self.up)

    def process(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        if self.up > 1:
            y = np.zeros(len(x) * self.up)
            y[:: self.up] = x
        else:
            y = x
        y, self.zi = signal.lfilter(self.b, [1.0], y, zi=self.zi)
        first = (-self._pos) % self.down
        self._pos += len(y)
        return y[first:: self.down].astype(np.float32)


class SampleFifo:
    def __init__(self):
        self._chunks: deque = deque()
        self._n = 0

    def __len__(self) -> int:
        return self._n

    def push(self, a: np.ndarray) -> None:
        a = np.asarray(a, dtype=np.float32)
        if a.size:
            self._chunks.append(a)
            self._n += a.size

    def pop(self, n: int) -> Optional[np.ndarray]:
        if self._n < n:
            return None
        out = np.empty(n, dtype=np.float32)
        filled = 0
        while filled < n:
            c = self._chunks[0]
            take = min(n - filled, c.size)
            out[filled:filled + take] = c[:take]
            if take == c.size:
                self._chunks.popleft()
            else:
                self._chunks[0] = c[take:]
            filled += take
        self._n -= n
        return out


# --------------------------------------------------------------------------- #
# Backends (all work on 480-sample frames @ 48 kHz)
# --------------------------------------------------------------------------- #
class IdentityBackend:
    name = "identity"
    delay_samples_48k = 0

    def process(self, frame: np.ndarray) -> np.ndarray:
        return frame

    def stats(self) -> dict:
        return {}


class BlockBackend:
    """Windowed offline-quality enhancement with continuous output.

    enhance_fn(window48: float32[N]) -> float32[N]   (time-aligned, same length)

    Per window k:   input  [w, b+R)   w = max(0, committed - C),  b = committed + B + X
                    emits  X samples crossfaded with the previous window's tail,
                           then B - X samples directly; saves the last X as tail.
    Worst-case algorithmic delay = B + X + R. Output is primed with that many
    zeros so every process() call returns exactly one frame.
    """

    name = "block"

    def __init__(self, enhance_fn: Callable[[np.ndarray], np.ndarray], block_ms=500,
                 context_ms=300, guard_ms=40, xfade_ms=10, hop=HOP_48K, fs=FS_PROC):
        up = lambda ms: max(hop, int(math.ceil(ms * fs / 1000.0 / hop)) * hop)
        self.hop, self.fn = hop, enhance_fn
        self.B, self.C, self.R, self.X = up(block_ms), up(context_ms), up(guard_ms), up(xfade_ms)
        assert self.B > self.X
        self.delay_samples_48k = self.B + self.X + self.R
        self._inp = np.zeros(0, np.float32)
        self._inp_start = 0          # absolute index of _inp[0]
        self._n_in = 0
        self._committed = 0
        self._tail: Optional[np.ndarray] = None
        self._fifo = SampleFifo()
        self._fifo.push(np.zeros(self.delay_samples_48k, np.float32))
        self._fade_in = np.linspace(0.0, 1.0, self.X, endpoint=False, dtype=np.float32)
        self.windows = 0
        self.errors = 0
        self.enhance_s = 0.0
        self.last_window_ms = 0.0

    def process(self, frame: np.ndarray) -> np.ndarray:
        self._inp = np.concatenate([self._inp, frame.astype(np.float32, copy=False)])
        self._n_in += len(frame)
        while self._n_in >= self._committed + self.B + self.X + self.R:
            self._run_window()
        out = self._fifo.pop(len(frame))
        assert out is not None, "BlockBackend FIFO underrun (priming bug)"
        return out

    def _run_window(self) -> None:
        c, B, X, R = self._committed, self.B, self.X, self.R
        w = max(0, c - self.C)
        b = c + B + X
        win = self._inp[w - self._inp_start: b + R - self._inp_start]
        t0 = time.perf_counter()
        try:
            y = np.asarray(self.fn(win), dtype=np.float32)
            if y.shape != win.shape or not np.all(np.isfinite(y)):
                raise ValueError("bad enhance output")
        except Exception:
            self.errors += 1
            y = win.copy()  # pass-through fallback, never silence
        dt = time.perf_counter() - t0
        self.enhance_s += dt
        self.last_window_ms = dt * 1000
        self.windows += 1

        head = y[c - w: c - w + X]
        if self._tail is None:
            self._fifo.push(head)
        else:
            self._fifo.push(self._tail * (1.0 - self._fade_in) + head * self._fade_in)
        self._fifo.push(y[c - w + X: c - w + B])
        self._tail = y[c - w + B: c - w + B + X].copy()
        self._committed = c + B

        keep_from = max(0, self._committed - self.C)
        drop = keep_from - self._inp_start
        if drop > 0:
            self._inp = self._inp[drop:]
            self._inp_start = keep_from

    def stats(self) -> dict:
        audio_s = self.windows * self.B / FS_PROC
        return {
            "windows": self.windows,
            "enhance_errors": self.errors,
            "last_window_ms": round(self.last_window_ms, 1),
            "compute_rtf": round(self.enhance_s / audio_s, 3) if audio_s else 0.0,
        }


# --------------------------------------------------------------------------- #
# Full chain: 256 @16k in -> 256 @16k out, deterministic
# --------------------------------------------------------------------------- #
class AudioChain:
    def __init__(self, backend, fs_io: int = FS_IO, fs_proc: int = FS_PROC, align_to: Optional[int] = None):
        assert fs_proc % fs_io == 0
        ratio = fs_proc // fs_io
        self.backend, self.ratio = backend, ratio
        self.up = StatefulResampler(ratio, 1, fs_io)
        self.down = StatefulResampler(1, ratio, fs_proc)
        self.in_fifo, self.out_fifo = SampleFifo(), SampleFifo()
        self.prime_io = int(math.ceil((HOP_48K - 1) / ratio))
        self.out_fifo.push(np.zeros(self.prime_io, np.float32))
        self.fs_io = fs_io
        self.underruns = 0

        resamp_delay = int(round((self.up.delay_s + self.down.delay_s) * self.fs_io))
        be_delay_io = self.backend.delay_samples_48k // self.ratio
        raw_delay = be_delay_io + resamp_delay + self.prime_io

        if align_to is not None:
            rem = raw_delay % align_to
            pad = (align_to - rem) % align_to
            if pad > 0:
                self.out_fifo.push(np.zeros(pad, np.float32))
            self._delay_samples_io = raw_delay + pad
        else:
            self._delay_samples_io = raw_delay

    @property
    def delay_samples_io(self) -> int:
        return self._delay_samples_io

    def process(self, x16: np.ndarray) -> np.ndarray:
        self.in_fifo.push(self.up.process(x16))
        while True:
            fr = self.in_fifo.pop(HOP_48K)
            if fr is None:
                break
            self.out_fifo.push(self.down.process(self.backend.process(fr)))
        out = self.out_fifo.pop(len(x16))
        if out is None:  # should never happen; keep length contract anyway
            self.underruns += 1
            avail = self.out_fifo.pop(len(self.out_fifo)) if len(self.out_fifo) else np.zeros(0, np.float32)
            out = np.concatenate([avail, np.zeros(len(x16) - len(avail), np.float32)])
        return out

    def latency_ms(self) -> dict:
        d = {
            "reframe_ms": 1000.0 * self.prime_io / self.fs_io,
            "resample_ms": 1000.0 * (self.up.delay_s + self.down.delay_s),
            "backend_ms": 1000.0 * self.backend.delay_samples_48k / FS_PROC,
        }
        d["algorithmic_total_ms"] = round(1000.0 * self._delay_samples_io / self.fs_io, 2)
        return {k: round(v, 2) for k, v in d.items()}


# --------------------------------------------------------------------------- #
# Stage probes for A/B/C diagnosis
# --------------------------------------------------------------------------- #
class StageProbe:
    """Cheap per-stage health stats: RMS, peak, clipping, DC, non-finite, packet-boundary clicks."""

    def __init__(self, name: str):
        self.name = name
        self.n = 0
        self.sumsq = 0.0
        self.sum = 0.0
        self.peak = 0.0
        self.clip = 0
        self.nonfinite = 0
        self.clicks = 0
        self.click_max = 0.0
        self._last: Optional[float] = None

    def update(self, x: np.ndarray) -> None:
        fin = np.isfinite(x)
        self.nonfinite += int((~fin).sum())
        if not fin.all():
            x = np.where(fin, x, 0.0)
        self.n += x.size
        self.sumsq += float(np.dot(x, x))
        self.sum += float(x.sum())
        self.peak = max(self.peak, float(np.abs(x).max()))
        self.clip += int((np.abs(x) >= 0.999).sum())
        if self._last is not None and x.size > 2:
            local = float(np.abs(np.diff(x)).mean()) + 1e-6
            ratio = abs(float(x[0]) - self._last) / local
            self.click_max = max(self.click_max, ratio)
            if ratio > 10.0:
                self.clicks += 1
        self._last = float(x[-1])

    def summary(self) -> dict:
        n = max(self.n, 1)
        return {
            "rms": round(math.sqrt(self.sumsq / n), 5),
            "peak": round(self.peak, 4),
            "clip_pct": round(100.0 * self.clip / n, 4),
            "dc": round(self.sum / n, 6),
            "nonfinite": self.nonfinite,
            "boundary_clicks": self.clicks,
            "boundary_click_max": round(self.click_max, 1),
        }
