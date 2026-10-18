#!/usr/bin/env python3
"""
pi_sender_v2.py - HFP mic -> (raw | resampled | DFN3) -> UDP, with honest telemetry.

  --mode raw        HFP -> UDP                  (is the capture itself clean?)
  --mode resampled  HFP -> 48k -> 16k -> UDP    (is the resampler/framing clean?)
  --mode dfn3       HFP -> DFN3 chain -> UDP    (is the model path clean?)

Wire format is unchanged (frontend/PROTOCOL.md): 5005 enhanced, 5007 raw input
(1032 B = uint64 seq + 256 float32 @16 kHz), 5006 telemetry JSON.

Run the three modes in order A -> B -> C. The first one that sounds bad is the stage to fix.
"""
import argparse
import collections
import fcntl
import json
import os
import queue
import re
import shlex
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streaming_core import AudioChain, BlockBackend, IdentityBackend, StageProbe  # noqa: E402

FRAME = 256
FRAME_BYTES = FRAME * 4
FRAME_MS = FRAME / 16.0
LOCK_PATH = "/tmp/sih26052_sender.lock"


# ----------------------------------------------------------------------------- #
# Guards
# ----------------------------------------------------------------------------- #
def acquire_single_instance():
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another sender already holds %s. Stop it first (pgrep -af pi_sender)." % LOCK_PATH)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def refuse_if_legacy_service_active(force: bool):
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", "sih26052-edge"], timeout=3)
    except Exception:
        return
    if r.returncode == 0 and not force:
        sys.exit("systemd service 'sih26052-edge' (old PolarLSTM anc_stream.py) is active and would "
                 "compete for the headset.\n  sudo systemctl disable --now sih26052-edge\n"
                 "or pass --force.")


# ----------------------------------------------------------------------------- #
# Bluetooth source discovery (by stable node.name, not by volatile numeric id)
# ----------------------------------------------------------------------------- #
def find_bt_sources(name_match: str):
    out = subprocess.check_output(["pw-dump"], text=True, timeout=5)
    found = []
    for o in json.loads(out):
        if o.get("type") != "PipeWire:Interface:Node":
            continue
        p = o.get("info", {}).get("props", {})
        name = p.get("node.name", "")
        if p.get("media.class") != "Audio/Source" or not name.startswith("bluez_input."):
            continue  # bluez_input.* sources only exist for HFP/HSP (A2DP has no mic)
        text = " ".join([name, p.get("node.description", ""), p.get("node.nick", "")])
        if name_match and not re.search(name_match, text, re.I):
            continue
        found.append((name, p.get("node.description", "")))
    return found


class Capture(threading.Thread):
    """Reads exact 1024-byte packets, reconnects forever, never blocks the processor."""

    def __init__(self, args, q, stop):
        super().__init__(daemon=True)
        self.args, self.q, self.stop, self.proc = args, q, stop, None
        self.connected = False
        self.source = ""
        self.reconnects = 0
        self.bad_reads = 0

    def _cmd(self):
        if self.args.capture_cmd:
            self.source = "custom"
            return shlex.split(self.args.capture_cmd)
        srcs = find_bt_sources(self.args.name_match)
        if not srcs:
            return None
        if len(srcs) > 1:
            print("WARNING: %d bluez sources match, using first: %s" % (len(srcs), srcs), flush=True)
        self.source = srcs[0][0]
        return ["pw-record", "-a", "--target", srcs[0][0], "--rate", "16000",
                "--channels", "1", "--format", "f32", "-"]

    def run(self):
        while not self.stop.is_set():
            try:
                cmd = self._cmd()
            except Exception as e:
                print("source discovery failed: %s" % e, flush=True)
                cmd = None
            if cmd is None:
                self.connected = False
                time.sleep(1.0)
                continue
            print("capture: %s" % " ".join(cmd), flush=True)
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except OSError as e:   # e.g. bad --capture-cmd; never let this thread die silently
                print("capture launch failed: %s -> %s" % (cmd, e), flush=True)
                self.connected = False
                time.sleep(1.0)
                continue
            self.connected = True
            while not self.stop.is_set():
                buf = self.proc.stdout.read(FRAME_BYTES)  # BufferedReader: full read or EOF
                if len(buf) < FRAME_BYTES:
                    self.bad_reads += 1
                    break
                self.q.put((time.monotonic(), np.frombuffer(buf, dtype=np.float32).copy()))
            self.connected = False
            self.reconnects += 1
            try:
                self.proc.terminate()
            except Exception:
                pass
            time.sleep(0.5)

    def shutdown(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


# ----------------------------------------------------------------------------- #
# Telemetry helpers
# ----------------------------------------------------------------------------- #
def read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def read_throttled():
    try:
        out = subprocess.check_output(["vcgencmd", "get_throttled"], text=True, timeout=2)
        return out.strip().split("=")[-1]
    except Exception:
        return None


def pct(vals, p):
    return float(np.percentile(vals, p)) if vals else 0.0


# ----------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["raw", "resampled", "dfn3"], default="dfn3")
    ap.add_argument("--target-ip", default=os.environ.get("SIH_PC_IP"), required=not os.environ.get("SIH_PC_IP"))
    ap.add_argument("--name-match", default="", help="regex on bluez source name/description, e.g. 'Rockerz'")
    ap.add_argument("--capture-cmd", default="", help="override capture (testing): command writing f32 mono 16k to stdout")
    ap.add_argument("--model", default=os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk"))
    ap.add_argument("--expect-sha", default=None, help="default: frozen SHA from final_model/model.sha256")
    ap.add_argument("--strict-sha", action="store_true", help="exit if the model SHA differs from the frozen one")
    ap.add_argument("--block-ms", type=int, default=500)
    ap.add_argument("--context-ms", type=int, default=300)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--max-backlog", type=int, default=32, help="packets; older audio is dropped (and counted)")
    ap.add_argument("--duration", type=float, default=0, help="seconds, 0 = until Ctrl+C")
    ap.add_argument("--report", default="", help="write final JSON summary here")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--audio-port", type=int, default=5005)
    ap.add_argument("--telemetry-port", type=int, default=5006)
    ap.add_argument("--input-port", type=int, default=5007)
    args = ap.parse_args()

    _lock = acquire_single_instance()  # noqa: F841 (kept open for process lifetime)
    refuse_if_legacy_service_active(args.force)

    # ---- model / chain ----
    model_name, backend_name, model_sha, sha_ok = "none (mode=%s)" % args.mode, "none", "", None
    chain, backend = None, None
    if args.mode == "resampled":
        backend = IdentityBackend()
        chain = AudioChain(backend)
        backend_name = "resample-only (stateful FIR)"
    elif args.mode == "dfn3":
        from dfn3_enhance import FROZEN_SHA256, make_dfn3_enhance_fn, sha256_file
        model_sha = sha256_file(args.model)
        expect = args.expect_sha or FROZEN_SHA256
        sha_ok = model_sha == expect
        print("model sha256 %s (%s frozen)" % (model_sha, "MATCHES" if sha_ok else "DIFFERS FROM"), flush=True)
        if not sha_ok and args.strict_sha:
            sys.exit("model SHA mismatch")
        fn = make_dfn3_enhance_fn(args.model, args.threads)
        backend = BlockBackend(fn, block_ms=args.block_ms, context_ms=args.context_ms)
        chain = AudioChain(backend)
        model_name = "DeepFilterNet3 (fine-tuned)"
        backend_name = "PyTorch block-window, block=%dms ctx=%dms" % (args.block_ms, args.context_ms)
    lat = chain.latency_ms() if chain else {"algorithmic_total_ms": 0.0}
    print("algorithmic latency (excl. network/OS/playback): %s" % lat, flush=True)

    # ---- io ----
    stop = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stop.set())
    q = queue.Queue()
    cap = Capture(args, q, stop)
    cap.start()
    ip = args.target_ip
    s_out, s_in, s_tel = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3))
    probe_in, probe_out = StageProbe("in"), StageProbe("out")

    seq = frames = dropped = misses = nonfinite = clipped = 0
    proc_ms = collections.deque(maxlen=500)
    total_proc_s = 0.0
    queue_delay_ms = 0.0
    throttled, last_thr = None, 0.0
    t_start, last_tel = time.monotonic(), 0.0

    def telemetry():
        nonlocal throttled, last_thr
        now = time.monotonic()
        if now - last_thr > 5.0:
            throttled, last_thr = read_throttled(), now
        bs = backend.stats() if backend else {}
        d = {
            "model": model_name, "backend": backend_name, "model_sha": model_sha,
            "model_sha_matches_frozen": sha_ok, "mode": args.mode,
            "model_active": args.mode == "dfn3" and bs.get("enhance_errors", 0) == 0,
            "bluetooth_connected": cap.connected, "source": cap.source,
            "frame": frames, "latency_ms": round(proc_ms[-1], 2) if proc_ms else 0.0,
            "latency_median_ms": round(pct(proc_ms, 50), 2), "p95_ms": round(pct(proc_ms, 95), 2),
            "p99_ms": round(pct(proc_ms, 99), 2), "max_ms": round(max(proc_ms), 2) if proc_ms else 0.0,
            "avg_rtf": round(total_proc_s / (frames * FRAME_MS / 1000.0), 3) if frames else 0.0,
            "algorithmic_latency_ms": lat["algorithmic_total_ms"], "latency_breakdown": lat,
            "queue_delay_ms": round(queue_delay_ms, 1), "queue_backlog": q.qsize(),
            "dropped_frames": dropped, "deadline_misses": misses,
            "nan_inf_events": nonfinite, "clipped_samples": clipped, "state_resets": 0,
            "reconnects": cap.reconnects, "temperature_c": read_temp_c(), "throttled": throttled,
            "in": probe_in.summary(), "out": probe_out.summary(),
        }
        d.update(bs)
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
            while q.qsize() > args.max_backlog:       # bounded latency: drop oldest, count it
                dropped += 1
                ts, chunk = q.get_nowait()
            queue_delay_ms = (time.monotonic() - ts) * 1000.0

            t0 = time.perf_counter()
            out = chunk.copy() if args.mode == "raw" else chain.process(chunk)
            dt = time.perf_counter() - t0
            total_proc_s += dt
            proc_ms.append(dt * 1000.0)
            if dt * 1000.0 > FRAME_MS:
                misses += 1

            if not np.isfinite(out).all():
                nonfinite += 1
                out = chunk.copy()
            clipped += int((np.abs(out) > 1.0).sum())
            out = np.clip(out, -1.0, 1.0).astype(np.float32)
            probe_in.update(chunk)
            probe_out.update(out)

            hdr = struct.pack("<Q", seq)
            s_out.sendto(hdr + out.tobytes(), (ip, args.audio_port))
            s_in.sendto(hdr + chunk.tobytes(), (ip, args.input_port))
            seq += 1
            frames += 1
            if frames % 50 == 0:
                telemetry()
                last_tel = time.monotonic()
    finally:
        stop.set()
        cap.shutdown()
        final = telemetry()
        print("\n=== SUMMARY ===")
        print(json.dumps({k: final[k] for k in (
            "mode", "model", "backend", "frame", "latency_median_ms", "p95_ms", "p99_ms", "max_ms", "avg_rtf",
            "algorithmic_latency_ms", "dropped_frames", "deadline_misses", "nan_inf_events", "clipped_samples",
            "reconnects", "temperature_c", "throttled", "in", "out")}, indent=2))
        if args.report:
            with open(args.report, "w") as f:
                json.dump(final, f, indent=2)


if __name__ == "__main__":
    main()
