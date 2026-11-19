"""End-to-end sender test: fake capture -> sender subprocess -> local UDP receivers.
Verifies wire format, sequence continuity, raw/resampled/dfn3 plumbing and telemetry.
dfn3 mode uses an identity stand-in for the model (the real model is not needed to test plumbing)."""
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
rng = np.random.default_rng(7)
ph = rng.uniform(0, 6.28, 6); fr = np.array([200, 500, 1100, 2400, 3900, 5600])
n = 0
t_next = time.monotonic()
while True:
    t = (np.arange(256) + n) / 16000.0
    x = sum(0.08 * np.sin(2*np.pi*f*t + p) for f, p in zip(fr, ph)).astype(np.float32)
    sys.stdout.buffer.write(x.tobytes()); sys.stdout.buffer.flush()
    n += 256; t_next += 0.016
    time.sleep(max(0, t_next - time.monotonic()))
'''

FAKE_DFN3 = '''
import numpy as np
FROZEN_SHA256 = "0" * 64
def sha256_file(p): return "f" * 64
def make_dfn3_enhance_fn(path, threads=3):
    return lambda w: w.copy()
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
        self.pkts, self.run_flag = [], True

    def run(self):
        while self.run_flag:
            try:
                self.pkts.append(self.s.recvfrom(4096)[0])
            except socket.timeout:
                pass


def run_sender(mode, extra=(), duration=4):
    tmp = tempfile.mkdtemp()
    for f in ("streaming_core.py", "pi_sender_v2.py"):
        shutil.copy(os.path.join(HERE, f), tmp)
    open(os.path.join(tmp, "dfn3_enhance.py"), "w").write(FAKE_DFN3)
    open(os.path.join(tmp, "gen.py"), "w").write(GEN)
    ports = [free_port() for _ in range(3)]
    rx = [Rx(p) for p in ports]
    [r.start() for r in rx]
    cmd = [sys.executable, os.path.join(tmp, "pi_sender_v2.py"), "--mode", mode, "--target-ip", "127.0.0.1",
           "--capture-cmd", "%s %s" % (shlex.quote(sys.executable), shlex.quote(os.path.join(tmp, "gen.py"))),
           "--audio-port", str(ports[0]), "--telemetry-port", str(ports[1]), "--input-port", str(ports[2]),
           "--duration", str(duration), "--model", "x.hk", "--force", *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    time.sleep(0.5)
    for x in rx:
        x.run_flag = False
    assert r.returncode == 0, r.stderr + r.stdout
    audio, tel, inp = rx[0].pkts, rx[1].pkts, rx[2].pkts
    return audio, tel, inp


def decode(pkts):
    seqs = [struct.unpack("<Q", p[:8])[0] for p in pkts]
    x = np.concatenate([np.frombuffer(p[8:], dtype=np.float32) for p in pkts])
    return seqs, x


def common_checks(audio, tel, inp):
    assert len(audio) >= 100 and len(audio) == len(inp)
    assert all(len(p) == 1032 for p in audio + inp)
    sa, xa = decode(audio)
    si, xi = decode(inp)
    assert sa == list(range(len(sa))) and si == sa          # no loss, contiguous, same seq on both streams
    last = json.loads(tel[-1])
    for k in ("model", "backend", "model_sha", "bluetooth_connected", "mode", "latency_median_ms",
              "p95_ms", "algorithmic_latency_ms", "dropped_frames", "nan_inf_events", "temperature_c"):
        assert k in last
    return xa, xi, last


def snr_db(ref, est):
    return 10 * np.log10(np.mean(ref ** 2) / np.mean((ref - est) ** 2 + 1e-20))


def test_raw_mode_is_bit_exact_passthrough():
    xa, xi, last = common_checks(*run_sender("raw"))
    np.testing.assert_array_equal(xa, xi)
    assert last["model_active"] is False and "raw" in last["model"]


def test_resampled_mode_is_clean_delayed_copy():
    xa, xi, last = common_checks(*run_sender("resampled"))
    d = int(round(last["algorithmic_latency_ms"] * 16))
    seg = slice(8000, len(xa) - 100)
    assert snr_db(xi[seg.start - d: seg.stop - d], xa[seg]) > 40
    assert last["out"]["boundary_clicks"] == 0 and last["out"]["nonfinite"] == 0


def test_dfn3_mode_plumbing_with_identity_model():
    audio, tel, inp = run_sender("dfn3", ["--block-ms", "100", "--context-ms", "60"], duration=5)
    xa, xi, last = common_checks(audio, tel, inp)
    assert last["model"] == "DeepFilterNet3 (fine-tuned)" and last["model_sha"] == "f" * 64
    assert last["model_sha_matches_frozen"] is False       # fake sha differs -> flagged, as intended
    assert last["algorithmic_latency_ms"] == pytest.approx(164.0, abs=0.5)
    d = int(round(last["algorithmic_latency_ms"] * 16))
    seg = slice(d + 4000, len(xa) - 100)
    assert snr_db(xi[seg.start - d: seg.stop - d], xa[seg]) > 40
    assert last["windows"] > 0 and last["enhance_errors"] == 0 and last["model_active"] is True
