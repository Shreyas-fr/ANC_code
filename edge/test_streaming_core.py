import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streaming_core import (AudioChain, BlockBackend, IdentityBackend, SampleFifo,
                            StageProbe, StatefulResampler, HOP_48K)
from jitter_buffer import JitterBuffer


def bandlimited(n, fs=16000, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = sum(rng.uniform(0.05, 0.15) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))
            for f in (180, 440, 1000, 2300, 3700, 5200, 6500))
    return x.astype(np.float32)


# ---------------- resampler ----------------
@pytest.mark.parametrize("up,down,fs,blk", [(3, 1, 16000, 256), (1, 3, 48000, 480), (1, 3, 48000, 768)])
def test_chunked_equals_oneshot(up, down, fs, blk):
    x = np.random.default_rng(1).standard_normal(blk * 40).astype(np.float32) * 0.1
    whole = StatefulResampler(up, down, fs).process(x)
    r = StatefulResampler(up, down, fs)
    chunked = np.concatenate([r.process(x[i:i + blk]) for i in range(0, len(x), blk)])
    assert len(whole) == len(chunked)
    np.testing.assert_allclose(whole, chunked, atol=1e-6)


@pytest.mark.parametrize("f", [300, 1000, 6000])
def test_roundtrip_gain_and_delay(f):
    fs = 16000
    n = fs * 2
    x = (0.5 * np.sin(2 * np.pi * f * np.arange(n) / fs)).astype(np.float32)
    up, down = StatefulResampler(3, 1, fs), StatefulResampler(1, 3, 48000)
    y = np.concatenate([down.process(up.process(x[i:i + 256])) for i in range(0, n, 256)])
    delay = int(round((up.delay_s + down.delay_s) * fs))
    seg = slice(4000, 20000)
    err = y[seg] - x[seg.start - delay: seg.stop - delay]
    assert 20 * np.log10(np.abs(x[seg]).max() / np.abs(err).max()) > 40


# ---------------- chain ----------------
def test_chain_length_contract_and_no_underrun():
    chain = AudioChain(IdentityBackend())
    x = bandlimited(256 * 3000)
    outs = [chain.process(x[i:i + 256]) for i in range(0, len(x), 256)]
    assert all(len(o) == 256 for o in outs)
    assert chain.underruns == 0


def test_chain_identity_is_clean_delayed_copy():
    chain = AudioChain(IdentityBackend())
    x = bandlimited(256 * 1500)
    y = np.concatenate([chain.process(x[i:i + 256]) for i in range(0, len(x), 256)])
    lat = chain.latency_ms()
    d = int(round(lat["algorithmic_total_ms"] * 16))
    seg = slice(8000, 80000)
    err = y[seg] - x[seg.start - d: seg.stop - d]
    snr = 10 * np.log10(np.mean(x[seg] ** 2) / np.mean(err ** 2))
    assert snr > 40, (snr, lat)


def test_stateful_beats_per_packet_resampling():
    """Independent per-packet resampling (scipy stand-in for the old torchaudio call)
    leaves edge errors at every packet boundary; the stateful chain does not."""
    from scipy.signal import resample_poly
    x = bandlimited(256 * 400)
    chain = AudioChain(IdentityBackend())
    y = np.concatenate([chain.process(x[i:i + 256]) for i in range(0, len(x), 256)])
    d = int(round(chain.latency_ms()["algorithmic_total_ms"] * 16))
    naive = np.concatenate([resample_poly(resample_poly(x[i:i + 256], 3, 1), 1, 3)
                            for i in range(0, len(x), 256)])
    seg = slice(4000, 90000)
    snr = lambda a, b: 10 * np.log10(np.mean(a ** 2) / np.mean((a - b) ** 2))
    good = snr(x[seg.start - d: seg.stop - d], y[seg])
    bad = snr(x[seg], naive[seg])
    assert good > 60 and good - bad > 20, (good, bad)


# ---------------- block backend ----------------
def make_block(fn, **kw):
    return BlockBackend(fn, block_ms=kw.get("block_ms", 100), context_ms=kw.get("context_ms", 60),
                        guard_ms=40, xfade_ms=10)


def run_frames(backend, x48):
    return np.concatenate([backend.process(x48[i:i + HOP_48K]) for i in range(0, len(x48), HOP_48K)])


def test_block_identity_is_exact_delay():
    be = make_block(lambda w: w.copy())
    x = np.random.default_rng(3).standard_normal(HOP_48K * 400).astype(np.float32) * 0.1
    y = run_frames(be, x)
    D = be.delay_samples_48k
    assert D % HOP_48K == 0
    np.testing.assert_allclose(y[D:], x[:len(x) - D], atol=1e-6)


def test_block_discards_warmup_and_guard_garbage():
    g = 200

    def fn(w):
        y = w * 0.5
        y[:g] = 100.0            # start-of-window transient
        y[-HOP_48K * 2:] = -100.0  # end-of-window transient (inside R guard)
        return y

    be = make_block(fn)
    x = np.random.default_rng(4).standard_normal(HOP_48K * 300).astype(np.float32) * 0.1
    y = run_frames(be, x)
    D = be.delay_samples_48k
    assert np.abs(y[D + g:]).max() < 1.0   # no garbage leaks except the very first window start


def test_block_crossfade_is_continuous():
    k = {"n": 0}

    def fn(w):
        k["n"] += 1
        return w * 0 + 0.01 * k["n"]   # different offset every window

    be = make_block(fn)
    y = run_frames(be, np.zeros(HOP_48K * 300, np.float32))
    y = y[be.delay_samples_48k:]
    assert np.abs(np.diff(y)).max() < 0.01 / be.X * 1.05


def test_block_failure_falls_back_to_passthrough():
    def boom(w):
        raise RuntimeError("x")
    be = make_block(boom)
    x = np.random.default_rng(5).standard_normal(HOP_48K * 100).astype(np.float32) * 0.1
    y = run_frames(be, x)
    D = be.delay_samples_48k
    np.testing.assert_allclose(y[D:], x[:len(x) - D], atol=1e-6)
    assert be.errors > 0


def test_full_chain_with_block_backend_latency_reported():
    chain = AudioChain(make_block(lambda w: w.copy()))
    x = bandlimited(256 * 600)
    outs = [chain.process(x[i:i + 256]) for i in range(0, len(x), 256)]
    assert all(len(o) == 256 for o in outs) and chain.underruns == 0
    assert chain.latency_ms()["backend_ms"] > 100


# ---------------- fifo / probe ----------------
def test_fifo_exact():
    f = SampleFifo()
    f.push(np.arange(5, dtype=np.float32))
    f.push(np.arange(5, 12, dtype=np.float32))
    np.testing.assert_array_equal(f.pop(8), np.arange(8))
    assert f.pop(5) is None
    np.testing.assert_array_equal(f.pop(4), np.arange(8, 12))


def test_probe_detects_clip_nan_click():
    p = StageProbe("t")
    p.update(np.full(256, 0.01, np.float32))
    p.update(np.concatenate([[1.0], np.full(255, 0.01)]).astype(np.float32))
    s = p.summary()
    assert s["clip_pct"] > 0 and s["boundary_clicks"] == 1
    p.update(np.array([np.nan, 0.0, 0.0], np.float32))
    assert p.summary()["nonfinite"] == 1


# ---------------- jitter buffer ----------------
def test_jb_compat_semantics():
    buf = JitterBuffer(16000, 48, 500)
    x = np.ones(256, np.float32) * 0.5
    buf.write(x)
    assert buf.get_level_ms() == pytest.approx(16.0, rel=1e-2)
    np.testing.assert_allclose(buf.read(256), x)
    assert buf.get_level_ms() == 0.0
    b2 = JitterBuffer(16000, 48)
    np.testing.assert_allclose(b2.read(128), np.zeros(128))
    assert b2.underrun_count == 128


def test_jb_ring_wraparound_preserves_order():
    buf = JitterBuffer(16000, 48, 250)
    ref, got = [], []
    rng = np.random.default_rng(0)
    for _ in range(500):
        x = rng.standard_normal(256).astype(np.float32)
        buf.write(x)
        ref.append(x)
        got.append(buf.read(256))
    np.testing.assert_allclose(np.concatenate(got), np.concatenate(ref))
    assert buf.underrun_count == 0 and buf.overflow_count == 0


def test_jb_overflow_trims_to_target_once():
    buf = JitterBuffer(16000, 48, 100)   # cap 1600, target 768
    for _ in range(10):
        buf.write(np.ones(256, np.float32))
    assert buf.get_level_ms() <= 100.0
    assert buf.overflow_count > 0


def test_jb_prebuffer_gates_then_recovers_without_click():
    buf = JitterBuffer(16000, 48, 250, prebuffer=True)
    assert not buf.read(256).any()               # holding
    for _ in range(2):
        buf.write(np.full(256, 0.5, np.float32))
    assert not buf.read(256).any()               # 32 ms < 48 ms target, still holding
    buf.write(np.full(256, 0.5, np.float32))
    assert buf.read(256).any()                   # target reached, plays
    buf.read(256); buf.read(256)                 # drain -> underrun
    out = buf.read(256)
    assert buf.underrun_events >= 1 and buf.prebuffer_events >= 1
    assert np.abs(np.diff(out)).max() < 0.1      # faded, not a hard cut
