import os
import sys

import numpy as np
import pytest
from scipy.signal import firwin, lfilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playout import PlayoutScheduler
from streaming_core import AudioChain, BlockBackend

FR = 256


def noise(n_frames, seed=1):
    rng = np.random.default_rng(seed)
    return lfilter(firwin(101, 0.7), [1], rng.standard_normal(FR * n_frames) * 0.1).astype(np.float32)


def make(enh=lambda w: w.copy(), J=6, block=100, ctx=60):
    chain = AudioChain(BlockBackend(enh, block_ms=block, context_ms=ctx, guard_ms=40, xfade_ms=10))
    delay_samples = chain.backend.delay_samples_48k // 3 + 160
    assert delay_samples % FR == 0
    return chain, PlayoutScheduler(delay_samples // FR, J)


def simulate(chain, sched, x, late=lambda seq: 0, reset_at=None, new_chain=None):
    """Synchronous simulation: result of call k becomes available `late(k)` steps after it was computed.
    reset_at: at that seq the worker is restarted with new_chain (epoch+1, call index restarts at 0)."""
    n = len(x) // FR
    pending, outs, last_arrival = [], [], 0
    epoch = cidx = 0
    for seq in range(n):
        if reset_at is not None and seq == reset_at:
            epoch, cidx, chain = epoch + 1, 0, new_chain
            # results the old chain already produced but not yet delivered may still land after the reset
            sched.reset_chain(seq, epoch)
        c = x[seq * FR:(seq + 1) * FR]
        sched.push_input(seq, c)
        arrival = max(last_arrival, seq + late(seq))      # one worker thread => results arrive IN ORDER
        last_arrival = arrival
        pending.append((arrival, epoch, cidx, chain.process(c)))
        cidx += 1
        for item in [p for p in pending if p[0] <= seq]:
            sched.push_result(item[2], item[3], item[1])
            pending.remove(item)
        outs.append(sched.next_output(seq))
    return np.concatenate(outs)


def snr(ref, est):
    return 10 * np.log10(np.mean(ref ** 2) / (np.mean((ref - est) ** 2) + 1e-20))


def test_chain_delay_is_exact_whole_packets():
    chain, _ = make()
    x = noise(300)
    y = np.concatenate([chain.process(x[i:i + FR]) for i in range(0, len(x), FR)])
    d = chain.delay_samples_io
    assert d % FR == 0
    assert snr(x[4000:30000], y[4000 + d:30000 + d]) > 40


def test_no_stall_output_matches_source_with_fixed_delay():
    chain, sched = make(J=6)
    x = noise(400)
    y = simulate(chain, sched, x)
    D = sched.total_delay_frames * FR
    assert sched.fallback_frames == 0 and sched.late_results == 0
    assert snr(x[4000:60000], y[4000 + D:60000 + D]) > 40


def test_stall_uses_aligned_fallback_and_never_drops_audio():
    chain, sched = make(J=6)
    x = noise(500)
    y = simulate(chain, sched, x, late=lambda s: 14 if 150 <= s < 170 else 0)   # inference 14 packets late
    D = sched.total_delay_frames * FR
    assert sched.fallback_frames > 0
    assert len(y) == len(x)
    # fallback and enhanced are the same source instant -> whole stream stays aligned
    assert snr(x[4000:100000], y[4000 + D:100000 + D]) > 35


def test_overloaded_worker_still_keeps_timeline():
    chain, sched = make(J=2)
    x = noise(400)
    y = simulate(chain, sched, x, late=lambda s: 30 if s % 10 < 6 else 0)        # chronically late
    D = sched.total_delay_frames * FR
    assert sched.fallback_frames > 50
    assert snr(x[4000:60000], y[4000 + D:60000 + D]) > 30


def test_switch_has_no_step_when_levels_differ():
    # enhanced is 0.4x of raw -> raw-vs-enhanced switch would be a big step without the join
    chain, sched = make(enh=lambda w: 0.4 * w, J=6)
    x = noise(500)
    y = simulate(chain, sched, x, late=lambda s: 14 if 150 <= s < 170 else 0)
    ideal_step = np.abs(np.diff(x)).max()
    energy_before = np.sum(x**2)
    energy_after = np.sum(y**2)
    print(f"Energy ratio (y/x): {energy_after / energy_before:.4f}")
    assert sched.switches >= 2
    assert np.abs(np.diff(y)).max() < 2.0 * ideal_step


def test_old_v3_indexing_is_misaligned_documented():
    """v3 looked for chain call (seq - D) and used raw (seq - D + 1): the two streams are not the same instant."""
    import collections
    chain, _ = make(J=0)
    d_frames = int(round(chain.latency_ms()["algorithmic_total_ms"] / 16.0))
    x = noise(300)
    res, dl, E, F = {}, collections.deque(maxlen=d_frames), [], []
    for seq in range(300):
        c = x[seq * FR:(seq + 1) * FR]
        res[seq] = chain.process(c)
        dl.append(c)
        tgt = seq - d_frames
        if tgt >= d_frames:
            E.append(res[tgt])
            F.append(dl[0])
    E, F = np.concatenate(E), np.concatenate(F)
    assert snr(F[2000:-2000], E[2000:-2000]) < 3        # not the same audio at all


def test_chain_reset_resyncs_timeline_and_ignores_stale_results():
    chain, sched = make(J=6)
    new_chain, _ = make(J=6)
    x = noise(500)
    # old chain results for calls ~195..205 arrive after the reset at 200 -> must be ignored
    y = simulate(chain, sched, x, late=lambda s: 12 if 195 <= s < 200 else 0, reset_at=200, new_chain=new_chain)
    D = sched.total_delay_frames * FR
    assert sched.chain_resets == 1
    assert sched.stale_results >= 1
    assert sched.resync_frames >= sched.Dp                  # raw fallback covers the new chain's priming
    # a restarted chain has its own start-up transient (no left context, fresh filters), so a bit lower
    assert snr(x[4000:100000], y[4000 + D:100000 + D]) > 30
    # and the new chain's enhanced audio takes over afterwards
    assert sched.enhanced_frames > 300
