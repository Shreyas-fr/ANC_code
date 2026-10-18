import threading

import numpy as np


class JitterBuffer:
    """
    Thread-safe numpy ring buffer for real-time playback (mono float32).

    Compared with the old deque-of-Python-floats version:
      * write()/read() are vectorised (the old per-sample loops ran under the
        lock inside the sound-card callback).
      * Overflow trims back to `target_buffer_ms` once, instead of dropping the
        oldest samples on every packet when sitting at the cap.
      * Optional prebuffering (`prebuffer=True`): playback holds silence until the
        buffer reaches `target_buffer_ms`, and re-enters that state after an
        underrun, so a stall gives one clean gap instead of "ch-ch-ch" stutter.
      * Underruns fade the last real samples out (and fade back in) instead of
        cutting to hard zeros, which removes the click at each dropout edge.
      * Counters are exposed for telemetry: underrun_count (samples, kept for
        compatibility), underrun_events (callbacks), overflow_count (samples),
        prebuffer_events.
    """

    def __init__(self, sample_rate: int = 16000, target_buffer_ms: int = 48,
                 max_buffer_ms: int = 250, prebuffer: bool = False, fade_samples: int = 32):
        self.sample_rate = sample_rate
        self.target_samples = int(target_buffer_ms / 1000.0 * sample_rate)
        self.max_samples = max(int(max_buffer_ms / 1000.0 * sample_rate), self.target_samples + 1)
        self.prebuffer = prebuffer
        self.fade_samples = fade_samples

        self._cap = self.max_samples + 4096
        self._buf = np.zeros(self._cap, dtype=np.float32)
        self._r = 0
        self._n = 0
        self.lock = threading.Lock()

        self._holding = prebuffer      # waiting to fill up to target
        self._last_out = 0.0
        self._need_fade_in = False

        self.underrun_count = 0
        self.underrun_events = 0
        self.overflow_count = 0
        self.prebuffer_events = 0

    # ring helpers (call with lock held)
    def _push(self, x: np.ndarray) -> None:
        n = len(x)
        w = (self._r + self._n) % self._cap
        first = min(n, self._cap - w)
        self._buf[w:w + first] = x[:first]
        if first < n:
            self._buf[:n - first] = x[first:]
        self._n += n

    def _pop(self, n: int) -> np.ndarray:
        out = np.empty(n, dtype=np.float32)
        first = min(n, self._cap - self._r)
        out[:first] = self._buf[self._r:self._r + first]
        if first < n:
            out[first:] = self._buf[:n - first]
        self._r = (self._r + n) % self._cap
        self._n -= n
        return out

    def write(self, samples: np.ndarray) -> None:
        if samples is None or len(samples) == 0:
            return
        x = np.asarray(samples, dtype=np.float32)
        with self.lock:
            if len(x) > self.max_samples:      # absurdly large write: keep newest
                self.overflow_count += len(x) - self.max_samples
                x = x[-self.max_samples:]
            self._push(x)
            if self._n > self.max_samples:     # trim back to target in one step
                drop = self._n - self.target_samples
                self._pop(drop)
                self.overflow_count += drop

    def read(self, num_samples: int) -> np.ndarray:
        with self.lock:
            if self._holding:
                if self._n >= self.target_samples:
                    self._holding = False
                    self._need_fade_in = self._last_out != 0.0
                else:
                    return self._silence(num_samples)

            n = min(num_samples, self._n)
            out = np.zeros(num_samples, dtype=np.float32)
            if n:
                out[:n] = self._pop(n)
                if self._need_fade_in:
                    k = min(self.fade_samples, n)
                    out[:k] *= np.linspace(0.0, 1.0, k, endpoint=False, dtype=np.float32)
                    self._need_fade_in = False

            if n < num_samples:
                self.underrun_count += num_samples - n
                self.underrun_events += 1
                start = out[n - 1] if n else self._last_out
                k = min(self.fade_samples, num_samples - n)
                if start != 0.0 and k:
                    out[n:n + k] = start * np.linspace(1.0, 0.0, k, endpoint=False, dtype=np.float32)
                if self.prebuffer:
                    self._holding = True
                    self.prebuffer_events += 1
            self._last_out = float(out[-1]) if num_samples else self._last_out
            return out

    def _silence(self, num_samples: int) -> np.ndarray:
        out = np.zeros(num_samples, dtype=np.float32)
        k = min(self.fade_samples, num_samples)
        if self._last_out != 0.0 and k:
            out[:k] = self._last_out * np.linspace(1.0, 0.0, k, endpoint=False, dtype=np.float32)
        self._last_out = 0.0
        return out

    def get_level_ms(self) -> float:
        with self.lock:
            return self._n / self.sample_rate * 1000.0

    def get_stats(self) -> dict:
        with self.lock:
            return {
                "level_ms": self._n / self.sample_rate * 1000.0,
                "underrun_samples": self.underrun_count,
                "underrun_events": self.underrun_events,
                "overflow_samples": self.overflow_count,
                "prebuffer_events": self.prebuffer_events,
            }

    def clear(self) -> None:
        with self.lock:
            self._r = 0
            self._n = 0
            self._holding = self.prebuffer
            self._last_out = 0.0
            self._need_fade_in = False
            self.underrun_count = 0
            self.underrun_events = 0
            self.overflow_count = 0
            self.prebuffer_events = 0
