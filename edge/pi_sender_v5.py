#!/usr/bin/env python3
"""
pi_sender_v5.py - HFP mic -> (raw | resampled | dfn3) -> UDP, inference OFF the send path.

Differences from v2/v3/v4:
  * Inference runs in a worker thread; the main loop only does cheap work, so a 200+ ms
    model call cannot stall capture or sending.
  * playout.PlayoutScheduler picks, per packet, enhanced audio or a time-aligned raw fallback
    (same source instant). Input audio is NEVER dropped before the chain; late results are
    replaced by raw audio and counted (fallback_frames). The old v3 indexing misaligned the two
    paths by ~580 ms; this is covered by test_playout.py.
  * Chain delay is padded to a whole number of packets (AudioChain(align_to=256)).
  * All subprocess calls (vcgencmd, temperature) run in a background sampler thread.
  * 5007 carries the TRUE raw input. Only the output is soft-limited; NaN/Inf is sanitised and counted.
  * Backlog trimming drops the OLDEST audio (counted) - v3 kept the stalest chunk.
  * Total added latency is reported honestly: algorithmic + jitter budget.

Not a fixed-cadence sender: packets leave when capture delivers them (capture itself is bursty).
Wire format and ports are unchanged (frontend/PROTOCOL.md).
"""
import argparse
import collections
import json
import math
import os
import queue
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pi_sender_v2 import (FRAME, FRAME_MS, Capture, acquire_single_instance,  # noqa: E402
                          pct, read_temp_c, read_throttled, refuse_if_legacy_service_active)
from playout import PlayoutScheduler  # noqa: E402
from streaming_core import AudioChain, BlockBackend, IdentityBackend, StageProbe  # noqa: E402


def soft_limit(x: np.ndarray, knee: float = 0.8):
    """Smooth limiter: identity below `knee`, tanh-shaped approach to 1.0 above it."""
    a = np.abs(x)
    m = a > knee
    if not m.any():
        return x, 0
    y = x.copy()
    y[m] = np.sign(x[m]) * (knee + (1.0 - knee) * np.tanh((a[m] - knee) / (1.0 - knee)))
    return y, int(m.sum())


def read_ext5v():
    try:
        out = subprocess.check_output(["vcgencmd", "pmic_read_adc"], text=True, timeout=2)
        for line in out.splitlines():
            if "EXT5V_V" in line:
                return float(line.split("=")[1].replace("V", "").strip())
    except Exception:
        pass
    return 0.0


class SysSampler(threading.Thread):
    """Temperature / throttle flags / 5 V rail, sampled off the send path."""

    def __init__(self, stop):
        super().__init__(daemon=True)
        self.stop = stop
        self.temperature_c = None
        self.throttled = None
        self.throttled_seen = set()
        self.ext5v = collections.deque(maxlen=4000)
        self.have_vc = shutil.which("vcgencmd") is not None

    def run(self):
        n = 0
        while not self.stop.is_set():
            self.temperature_c = read_temp_c()
            if self.have_vc:
                t = read_throttled()
                if t:
                    self.throttled = t
                    self.throttled_seen.add(t)
                if n % 2 == 0:
                    v = read_ext5v()
                    if v > 0:
                        self.ext5v.append(v)
            n += 1
            self.stop.wait(1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["raw", "resampled", "dfn3"], default="dfn3")
    ap.add_argument("--target-ip", default=os.environ.get("SIH_PC_IP"), required=not os.environ.get("SIH_PC_IP"))
    ap.add_argument("--name-match", default="")
    ap.add_argument("--capture-cmd", default="")
    ap.add_argument("--model", default=os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk"))
    ap.add_argument("--expect-sha", default=None)
    ap.add_argument("--strict-sha", action="store_true")
    ap.add_argument("--block-ms", type=int, default=500)
    ap.add_argument("--context-ms", type=int, default=300)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--jitter-ms", type=int, default=320,
                    help="slack given to slow inference before raw fallback is sent (adds this much latency)")
    ap.add_argument("--max-backlog", type=int, default=64, help="capture packets; oldest dropped beyond this")
    ap.add_argument("--worker-backlog-max", type=int, default=100,
                    help="packets; if inference is this far behind the chain is restarted and raw fallback covers the resync")
    ap.add_argument("--duration", type=float, default=0)
    ap.add_argument("--report", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--audio-port", type=int, default=5005)
    ap.add_argument("--telemetry-port", type=int, default=5006)
    ap.add_argument("--input-port", type=int, default=5007)
    args = ap.parse_args()

    _lock = acquire_single_instance()  # noqa: F841
    refuse_if_legacy_service_active(args.force)

    model_name, backend_name, model_sha, sha_ok = "none (mode=%s)" % args.mode, "none", "", None
    chain = backend = sched = None
    jitter_frames = 0
    if args.mode == "resampled":
        backend = IdentityBackend()
        backend_name = "resample-only (stateful FIR)"
        jitter_frames = 2          # lets the worker thread finish before the packet is due
    elif args.mode == "dfn3":
        from dfn3_enhance import FROZEN_SHA256, make_dfn3_enhance_fn, sha256_file
        model_sha = sha256_file(args.model)
        sha_ok = model_sha == (args.expect_sha or FROZEN_SHA256)
        print("model sha256 %s (%s frozen)" % (model_sha, "MATCHES" if sha_ok else "DIFFERS FROM"), flush=True)
        if not sha_ok and args.strict_sha:
            sys.exit("model SHA mismatch")
        enhance_fn = make_dfn3_enhance_fn(args.model, args.threads)
        backend = BlockBackend(enhance_fn, block_ms=args.block_ms, context_ms=args.context_ms)
        model_name = "DeepFilterNet3 (fine-tuned)"
        backend_name = "PyTorch block-window, block=%dms ctx=%dms" % (args.block_ms, args.context_ms)
        jitter_frames = int(math.ceil(args.jitter_ms / FRAME_MS))
    def new_chain():
        be = IdentityBackend() if args.mode == "resampled" else BlockBackend(
            enhance_fn, block_ms=args.block_ms, context_ms=args.context_ms)
        return AudioChain(be, align_to=FRAME)

    if backend is not None:
        chain = AudioChain(backend, align_to=FRAME)
        sched = PlayoutScheduler(chain.delay_samples_io // FRAME, jitter_frames, FRAME)
    lat = chain.latency_ms() if chain else {"algorithmic_total_ms": 0.0}
    total_latency_ms = (sched.total_delay_frames * FRAME_MS) if sched else 0.0
    print("algorithmic latency: %s | total sender latency incl. jitter budget: %.0f ms"
          % (lat, total_latency_ms), flush=True)

    stop = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stop.set())
    q = queue.Queue()
    cap = Capture(args, q, stop)
    cap.start()
    sampler = SysSampler(stop)
    sampler.start()
    ip = args.target_ip
    s_out, s_in, s_tel = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3))
    probe_in, probe_out = StageProbe("in"), StageProbe("out")

    seq = frames = dropped = nan_events = limited = 0
    worker_ms = collections.deque(maxlen=1000)
    worker_stats = {"errors": 0, "busy_s": 0.0}
    send_intervals = collections.deque(maxlen=1000)
    gaps = collections.deque(maxlen=2000)
    prev_ts, last_send, backlog_max = None, None, 0
    t_start, last_tel = time.monotonic(), 0.0

    worker_q = queue.Queue()
    stats_lock = threading.Lock()
    epoch = 0
    worker_stats["chain_backend"] = backend

    def worker():
        idx, local_epoch, wchain = 0, 0, chain
        while not stop.is_set():
            try:
                ep, chunk = worker_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if ep != local_epoch:                    # chain restart requested by the main loop
                wchain, local_epoch, idx = new_chain(), ep, 0
                with stats_lock:
                    worker_stats["chain_backend"] = wchain.backend
            t0 = time.perf_counter()
            try:
                out = wchain.process(chunk)
            except Exception as e:
                worker_stats["errors"] += 1
                print("worker error: %s" % e, flush=True)
                out = None
            dt = time.perf_counter() - t0
            worker_ms.append(dt * 1000.0)
            worker_stats["busy_s"] += dt
            if out is not None:
                sched.push_result(idx, out, local_epoch)
            idx += 1

    if chain is not None:
        threading.Thread(target=worker, daemon=True).start()

    def telemetry(final=False):
        with stats_lock:
            cur = worker_stats.get("chain_backend")
        bs = cur.stats() if cur else {}
        ext = list(sampler.ext5v)
        fb = sched.fallback_frames if sched else 0
        d = {
            "model": model_name, "backend": backend_name, "model_sha": model_sha,
            "model_sha_matches_frozen": sha_ok, "mode": args.mode,
            "model_active": args.mode == "dfn3" and worker_stats["errors"] == 0 and bs.get("enhance_errors", 0) == 0,
            "bluetooth_connected": cap.connected, "source": cap.source, "frame": frames,
            "latency_ms": round(worker_ms[-1], 2) if worker_ms else 0.0,
            "latency_median_ms": round(pct(worker_ms, 50), 2), "p95_ms": round(pct(worker_ms, 95), 2),
            "p99_ms": round(pct(worker_ms, 99), 2),
            "max_ms": round(max(worker_ms), 2) if worker_ms else 0.0,
            "avg_rtf": round(worker_stats["busy_s"] / (frames * FRAME_MS / 1000.0), 3) if frames else 0.0,
            "send_interval_p50": round(pct(send_intervals, 50), 2),
            "send_interval_p99": round(pct(send_intervals, 99), 2),
            "send_interval_max": round(max(send_intervals), 2) if send_intervals else 0.0,
            "algorithmic_latency_ms": lat["algorithmic_total_ms"], "latency_breakdown": lat,
            "jitter_budget_ms": round(jitter_frames * FRAME_MS, 1), "total_latency_ms": round(total_latency_ms, 1),
            "fallback_frames": fb, "deadline_misses": fb,       # an output deadline is missed when a fallback is sent
            "fallback_pct": round(100.0 * fb / frames, 2) if frames else 0.0,
            "enhanced_frames": sched.enhanced_frames if sched else 0,
            "late_results": sched.late_results if sched else 0, "switches": sched.switches if sched else 0,
            "chain_resets": sched.chain_resets if sched else 0, "resync_frames": sched.resync_frames if sched else 0,
            "stale_results": sched.stale_results if sched else 0,
            "worker_errors": worker_stats["errors"], "dropped_frames": dropped,
            "backlog_max": backlog_max, "queue_backlog": q.qsize(), "worker_backlog": worker_q.qsize(),
            "capture_gap_p99_ms": round(pct(gaps, 99), 1), "capture_gap_max_ms": round(max(gaps), 1) if gaps else 0.0,
            "nan_inf_events": nan_events, "limited_samples": limited, "state_resets": 0,
            "reconnects": cap.reconnects, "temperature_c": sampler.temperature_c,
            "throttled": sampler.throttled, "throttled_seen": sorted(sampler.throttled_seen),
            "ext5v_min": round(min(ext), 3) if ext else None, "ext5v_mean": round(float(np.mean(ext)), 3) if ext else None,
            "in": probe_in.summary(), "out": probe_out.summary(),
        }
        d.update(bs)
        if not final:
            s_tel.sendto(json.dumps(d).encode(), (ip, args.telemetry_port))
        return d

    print("streaming %s -> %s (ports %d/%d/%d)" % (args.mode, ip, args.audio_port, args.telemetry_port,
                                                   args.input_port), flush=True)
    try:
        while not stop.is_set():
            if args.duration and time.monotonic() - t_start > args.duration:
                break
            try:
                ts, chunk = q.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - last_tel > 1.0:
                    telemetry()
                    last_tel = time.monotonic()
                continue
            while q.qsize() > args.max_backlog:          # emergency only: drop OLDEST, keep newest
                dropped += 1
                ts, chunk = q.get_nowait()
            if prev_ts is not None:
                gaps.append((ts - prev_ts) * 1000.0)
            prev_ts = ts
            backlog_max = max(backlog_max, q.qsize() + 1)

            if not np.isfinite(chunk).all():
                nan_events += 1
                chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
            probe_in.update(chunk)
            hdr = struct.pack("<Q", seq)
            s_in.sendto(hdr + chunk.tobytes(), (ip, args.input_port))      # true raw

            if sched is None:
                out = chunk
            else:
                if worker_q.qsize() > args.worker_backlog_max:     # hopelessly behind: restart, don't leak/stale
                    while True:
                        try:
                            worker_q.get_nowait()
                        except queue.Empty:
                            break
                    epoch += 1
                    sched.reset_chain(seq, epoch)
                    print("worker backlog > %d packets: chain restarted (epoch %d)" % (args.worker_backlog_max, epoch),
                          flush=True)
                sched.push_input(seq, chunk)
                worker_q.put((epoch, chunk))
                out = sched.next_output(seq)
            if not np.isfinite(out).all():
                nan_events += 1
                out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
            out, nl = soft_limit(out)
            limited += nl
            out = out.astype(np.float32, copy=False)
            probe_out.update(out)
            s_out.sendto(hdr + out.tobytes(), (ip, args.audio_port))

            now = time.monotonic()
            if last_send is not None:
                send_intervals.append((now - last_send) * 1000.0)
            last_send = now
            seq += 1
            frames += 1
            if frames % 50 == 0:
                telemetry()
                last_tel = time.monotonic()
    finally:
        stop.set()
        cap.shutdown()
        final = telemetry(final=True)
        keys = ("mode", "model", "backend", "frame", "latency_median_ms", "p95_ms", "p99_ms", "max_ms", "avg_rtf",
                "algorithmic_latency_ms", "jitter_budget_ms", "total_latency_ms", "fallback_frames", "fallback_pct",
                "late_results", "switches", "chain_resets", "resync_frames", "worker_errors", "dropped_frames", "send_interval_p99",
                "send_interval_max", "backlog_max", "capture_gap_max_ms", "nan_inf_events", "limited_samples",
                "reconnects", "temperature_c", "throttled_seen", "ext5v_min", "ext5v_mean", "in", "out")
        print("\n=== SUMMARY ===")
        print(json.dumps({k: final[k] for k in keys}, indent=2))
        if args.report:
            with open(args.report, "w") as f:
                json.dump(final, f, indent=2)


if __name__ == "__main__":
    main()
