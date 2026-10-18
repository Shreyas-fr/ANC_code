"""v5 end-to-end: fake capture -> pi_sender_v5 subprocess -> local UDP receivers.
The model is a stand-in that sleeps (simulating a slow Pi) and returns the window unchanged,
so alignment, cadence, fallback and telemetry can be measured without the real model."""
import json
import os
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

GEN = r'''
import sys, time, numpy as np
from scipy.signal import firwin, lfilter
rng = np.random.default_rng(7)
x = lfilter(firwin(101, 0.7), [1], rng.standard_normal(256 * 4000) * 0.1).astype(np.float32)
i = 0
t_next = time.monotonic()
while True:
    c = x[(i % 4000) * 256:(i % 4000 + 1) * 256]
    sys.stdout.buffer.write(c.tobytes()); sys.stdout.buffer.flush()
    i += 1; t_next += 0.016
    time.sleep(max(0, t_next - time.monotonic()))
'''

FAKE_DFN3 = '''
import time
FROZEN_SHA256 = "0" * 64
def sha256_file(p): return "f" * 64
def make_dfn3_enhance_fn(path, threads=3):
    def fn(w):
        time.sleep(SLEEP)
        return w.copy()
    return fn
'''


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Rx(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("127.0.0.1", port))
        self.s.settimeout(0.3)
        self.pkts, self.go = [], True

    def run(self):
        while self.go:
            try:
                self.pkts.append(self.s.recvfrom(4096)[0])
            except socket.timeout:
                pass


def run_v5(mode, sleep_s=0.0, extra=(), duration=7):
    tmp = tempfile.mkdtemp()
    for f in ("streaming_core.py", "pi_sender_v2.py", "pi_sender_v5.py", "playout.py"):
        shutil.copy(os.path.join(HERE, f), tmp)
    
    open(os.path.join(tmp, "dfn3_enhance.py"), "w").write("SLEEP = %r\n" % sleep_s + FAKE_DFN3)
    open(os.path.join(tmp, "gen.py"), "w").write(GEN)
    ports = [free_port() for _ in range(3)]
    rx = [Rx(p) for p in ports]
    [r.start() for r in rx]
    cmd = [sys.executable, os.path.join(tmp, "pi_sender_v5.py"), "--mode", mode, "--target-ip", "127.0.0.1",
           "--capture-cmd", "%s %s" % (shlex.quote(sys.executable), shlex.quote(os.path.join(tmp, "gen.py"))),
           "--audio-port", str(ports[0]), "--telemetry-port", str(ports[1]), "--input-port", str(ports[2]),
           "--duration", str(duration), "--model", "x.hk", "--force", *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    time.sleep(0.5)
    for x in rx:
        x.go = False
    assert r.returncode == 0, r.stderr + r.stdout
    return rx[0].pkts, rx[1].pkts, rx[2].pkts


def decode(pkts):
    seqs = [struct.unpack("<Q", p[:8])[0] for p in pkts]
    return seqs, np.concatenate([np.frombuffer(p[8:], dtype=np.float32) for p in pkts])


def snr(ref, est):
    return 10 * np.log10(np.mean(ref ** 2) / (np.mean((ref - est) ** 2) + 1e-20))


def check(audio, tel, inp, delay_key="total_latency_ms", min_snr=35):
    assert all(len(p) == 1032 for p in audio + inp)
    sa, xa = decode(audio)
    si, xi = decode(inp)
    assert sa == list(range(len(sa))) and si == sa
    last = json.loads(tel[-1])
    D = int(round(last[delay_key] / 16.0)) * 256
    seg = slice(D + 8000, len(xa) - 100)
    assert snr(xi[seg.start - D: seg.stop - D], xa[seg]) > min_snr, last
    return xa, xi, last


def test_raw_is_true_raw_and_unlimited():
    a, t, i = run_v5("raw", duration=4)
    xa, xi, last = check(a, t, i, delay_key="total_latency_ms")
    np.testing.assert_array_equal(xa, xi)
    assert last["model_active"] is False and last["total_latency_ms"] == 0


def test_resampled_aligned_and_telemetry_complete():
    a, t, i = run_v5("resampled", duration=5)
    xa, xi, last = check(a, t, i)
    for k in ("latency_median_ms", "p95_ms", "p99_ms", "max_ms", "nan_inf_events", "deadline_misses",
              "model_sha_matches_frozen", "model_active", "fallback_frames", "total_latency_ms",
              "send_interval_p99", "temperature_c", "throttled", "backlog_max", "late_results"):
        assert k in last, k
    assert last["fallback_pct"] < 5 and last["dropped_frames"] == 0


def test_slow_model_within_budget_never_falls_back():
    # one window per 0.5 s, each costs 0.12 s (RTF ~0.24, stall 120 ms < 320 ms budget) -> always on time
    a, t, i = run_v5("dfn3", sleep_s=0.12, duration=11)
    xa, xi, last = check(a, t, i)
    assert last["worker_errors"] == 0 and last["dropped_frames"] == 0
    assert last["fallback_pct"] < 5, last["fallback_pct"]
    assert last["model_sha"] == "f" * 64 and last["model_active"] is True
    assert last["max_ms"] > 100                                  # the stall really happened in the worker
    assert last["send_interval_max"] < 120                       # ...but it never blocked sending


def test_overloaded_model_keeps_timeline_and_counts_fallback():
    # a window every 0.1 s costs 0.5 s (RTF 5): permanently overloaded. Must stay contiguous and aligned,
    # keep sending raw fallback, drop nothing, and NOT let the worker queue grow without bound.
    a, t, i = run_v5("dfn3", sleep_s=0.5,
                     extra=["--block-ms", "100", "--context-ms", "60", "--jitter-ms", "64",
                            "--worker-backlog-max", "40"], duration=12)
    xa, xi, last = check(a, t, i, min_snr=25)
    assert last["fallback_pct"] > 50 and last["dropped_frames"] == 0
    assert last["chain_resets"] >= 1
    assert last["worker_backlog"] <= 45
    assert last["send_interval_max"] < 150
