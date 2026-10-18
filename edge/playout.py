"""
playout.py - decides, per output packet, whether to send the enhanced audio or a
time-aligned raw fallback, without ever dropping input audio.

Timeline (all in packets of 256 samples):
  chain.process() is called once per input packet, in order: call index k.
  Its output contains the audio of input packet (k - Dp), where Dp is the chain's own
  delay in whole packets (AudioChain(..., align_to=256).delay_samples_io / 256).

  At send step `seq` the scheduler outputs the content of source packet  t = seq - J - Dp :
     enhanced  = chain output of call (seq - J)       <- J packets of slack for slow inference
     fallback  = raw input packet t                   <- same source time, no model
  Enhanced and fallback therefore describe the SAME instant, so switching between them
  changes noise level, not time. A short offset-decay join removes the step at the switch.

Total sender-added delay = (Dp + J) packets.  Nothing is dropped: if inference is late,
raw audio for that instant is sent instead (counted as fallback_frames).
"""
import threading

import numpy as np


class PlayoutScheduler:
    def __init__(self, chain_delay_frames: int, jitter_frames: int, frame: int = 256, xfade: int = 128):
        assert chain_delay_frames >= 0 and jitter_frames >= 0 and 0 < xfade <= frame
        self.Dp, self.J, self.frame = chain_delay_frames, jitter_frames, frame
        self._raw = {}                 # source packet index -> raw chunk
        self._res = {}                 # chain call index -> enhanced chunk
        self._stash = {}               # chain call index -> last sample of that enhanced chunk
        self._lock = threading.Lock()
        self._state = None             # 'E' / 'F' / None (nothing sent yet)
        self._last = 0.0
        self._slope = 0.0
        self._decay = np.linspace(1.0, 0.0, xfade, endpoint=False, dtype=np.float32)
        self._zeros = np.zeros(frame, np.float32)
        self._epoch = 0                # bumps when the chain is restarted
        self._base = 0                 # input seq that chain call 0 of the current epoch corresponds to
        self._min_idx = 0              # first chain call whose output is real audio (not priming zeros)
        self.fallback_frames = 0
        self.late_results = 0
        self.switches = 0
        self.enhanced_frames = 0
        self.chain_resets = 0
        self.resync_frames = 0
        self.stale_results = 0

    @property
    def total_delay_frames(self) -> int:
        return self.Dp + self.J

    def push_input(self, seq: int, chunk: np.ndarray) -> None:
        with self._lock:
            self._raw[seq] = chunk
            self._raw.pop(seq - (self.Dp + self.J + 16), None)

    def push_result(self, call_idx: int, out: np.ndarray, epoch: int = 0) -> None:
        with self._lock:
            if epoch != self._epoch:
                self.stale_results += 1          # produced by a chain that has since been restarted
                return
            self._res[call_idx] = out

    def reset_chain(self, base_seq: int, epoch: int) -> None:
        """The worker was hopelessly behind: its queue was dropped and a FRESH chain will receive
        input packet `base_seq` as its call 0. Until that chain's priming is over (Dp calls) the
        raw fallback is sent, so the timeline stays aligned."""
        with self._lock:
            self._res.clear()
            self._stash.clear()
            self._epoch, self._base, self._min_idx = epoch, base_seq, self.Dp
            self.chain_resets += 1

    def next_output(self, seq: int) -> np.ndarray:
        with self._lock:
            idx = seq - self.J - self._base
            for k in sorted(k for k in self._res if k < idx):   # arrived too late to be used
                self._remember(k, self._res.pop(k))
                self.late_results += 1
            if seq - self.J < 0:
                return self._zeros.copy()                     # start-up: nothing to play yet
            src = seq - self.J - self.Dp
            raw = self._raw.get(src) if src >= 0 else None
            fallback = raw if raw is not None else self._zeros
            enh = self._res.pop(idx, None) if idx >= self._min_idx else None
            if idx < self._min_idx and self._base > 0:
                self.resync_frames += 1
            if enh is not None:
                self._remember(idx, enh)
                x, st = enh, "E"
                self.enhanced_frames += 1
            else:
                x, st = fallback, "F"
                self.fallback_frames += 1
            x = np.array(x, dtype=np.float32, copy=True)
            if self._state is not None and st != self._state:
                # continuity join: shift the new stream by the real difference between the
                # streams at the boundary, decaying to zero over a few ms
                n = len(self._decay)
                x[:n] += self._join_offset(seq, idx, st, x) * self._decay
                self.switches += 1
            self._state = st
            self._last = float(x[-1])
            self._slope = float(x[-1] - x[-2])
            return x

    def _remember(self, k: int, out: np.ndarray) -> None:
        self._stash[k] = float(out[-1])
        if len(self._stash) > 8:
            del self._stash[min(self._stash)]

    def _join_offset(self, seq: int, idx: int, new_state: str, x: np.ndarray) -> float:
        """last_sent - (value the NEW stream had one sample earlier)."""
        if new_state == "F":                          # enhanced -> fallback
            src_prev = seq - 1 - self.J - self.Dp
            prev = self._raw.get(src_prev) if src_prev >= 0 else None
            other = float(prev[-1]) if prev is not None else None
        else:                                         # fallback -> enhanced
            other = self._stash.get(idx - 1)
        if other is None:                             # no reference available: do not guess
            return 0.0
        return self._last - other
