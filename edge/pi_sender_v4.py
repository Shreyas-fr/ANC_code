#!/usr/bin/env python3
"""
pi_sender_v3.py - Fixed cadence sender with asynchronous DFN3 inference.
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
from sender_policy_v4 import SenderPolicyV4

FRAME = 256
FRAME_BYTES = FRAME * 4
FRAME_MS = FRAME / 16.0
LOCK_PATH = "/tmp/sih26052_sender.lock"

def acquire_single_instance():
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another sender already holds %s. Stop it first." % LOCK_PATH)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh

def refuse_if_legacy_service_active(force: bool):
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", "sih26052-edge"], timeout=3)
    except Exception:
        return
    if r.returncode == 0 and not force:
        sys.exit("systemd service 'sih26052-edge' is active. Stop it first.")

def find_bt_sources(name_match: str):
    out = subprocess.check_output(["pw-dump"], text=True, timeout=5)
    found = []
    for o in json.loads(out):
        if o.get("type") != "PipeWire:Interface:Node":
            continue
        p = o.get("info", {}).get("props", {})
        name = p.get("node.name", "")
        if p.get("media.class") != "Audio/Source" or not name.startswith("bluez_input."):
            continue
        text = " ".join([name, p.get("node.description", ""), p.get("node.nick", "")])
        if name_match and not re.search(name_match, text, re.I):
            continue
        found.append((name, p.get("node.description", "")))
    return found

class Capture(threading.Thread):
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
            except OSError as e:
                print("capture launch failed: %s -> %s" % (cmd, e), flush=True)
                self.connected = False
                time.sleep(1.0)
                continue
            self.connected = True
            while not self.stop.is_set():
                buf = self.proc.stdout.read(FRAME_BYTES)
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

def get_uptime():
    try:
        out = subprocess.check_output(["uptime", "-s"], text=True, timeout=2)
        return out.strip()
    except Exception:
        return ""

def pct(vals, p):
    return float(np.percentile(vals, p)) if vals else 0.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["raw", "resampled", "dfn3"], default="dfn3")
    ap.add_argument("--target-ip", default=os.environ.get("SIH_PC_IP"), required=not os.environ.get("SIH_PC_IP"))
    ap.add_argument("--name-match", default="", help="regex on bluez source name/description, e.g. 'Rockerz'")
    ap.add_argument("--capture-cmd", default="", help="override capture (testing)")
    ap.add_argument("--model", default=os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk"))
    ap.add_argument("--expect-sha", default=None)
    ap.add_argument("--strict-sha", action="store_true")
    ap.add_argument("--block-ms", type=int, default=500)
    ap.add_argument("--context-ms", type=int, default=300)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--jitter-ms", type=int, default=300)
    ap.add_argument("--max-backlog", type=int, default=32)
    ap.add_argument("--duration", type=float, default=0)
    ap.add_argument("--report", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--audio-port", type=int, default=5005)
    ap.add_argument("--telemetry-port", type=int, default=5006)
    ap.add_argument("--input-port", type=int, default=5007)
    args = ap.parse_args()

    _lock = acquire_single_instance()
    refuse_if_legacy_service_active(args.force)

    model_name, backend_name, model_sha, sha_ok = "none (mode=%s)" % args.mode, "none", "", None
    chain, backend, fn = None, None, None
    if args.mode == "resampled":
        backend = IdentityBackend()
        chain = AudioChain(backend)
        backend_name = "resample-only (stateful FIR)"
    elif args.mode == "dfn3":
        from dfn3_enhance import FROZEN_SHA256, make_dfn3_enhance_fn, sha256_file
        model_sha = sha256_file(args.model)
        expect = args.expect_sha or FROZEN_SHA256
        sha_ok = model_sha == expect
        if not sha_ok and args.strict_sha:
            sys.exit("model SHA mismatch")
        fn = make_dfn3_enhance_fn(args.model, args.threads)
        backend = BlockBackend(fn, block_ms=args.block_ms, context_ms=args.context_ms)
        chain = AudioChain(backend)
        model_name = "DeepFilterNet3 (fine-tuned)"
        backend_name = "PyTorch block-window, block=%dms ctx=%dms" % (args.block_ms, args.context_ms)
    lat = chain.latency_ms() if chain else {"algorithmic_total_ms": 0.0}
    print("algorithmic latency: %s" % lat, flush=True)

    stop = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stop.set())
    q = queue.Queue()
    cap = Capture(args, q, stop)
    cap.start()
    ip = args.target_ip
    s_out, s_in, s_tel = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3))
    probe_in, probe_out = StageProbe("in"), StageProbe("out")

    seq = frames = dropped = queue_drops = fallback_frames = clipped = 0
    worker_ms = collections.deque(maxlen=500)
    send_intervals = collections.deque(maxlen=500)
    
    t_start, last_tel = time.monotonic(), 0.0
    uptime_start = get_uptime()
    throttled_start = read_throttled()

    # DFN3 Worker thread setup
    worker_q = queue.Queue()
    out_q = collections.deque()
    
    def inference_worker():
        nonlocal chain, backend
        while not stop.is_set():
            try:
                item = worker_q.get(timeout=0.1)
                item_seq, item_chunk = item
            except queue.Empty:
                continue
                
            t0 = time.perf_counter()
            out = item_chunk.copy() if args.mode == "raw" else chain.process(item_chunk)
            dt = time.perf_counter() - t0
            worker_ms.append(dt * 1000.0)
            
            out_q.append((item_seq, out))

    worker_thread = threading.Thread(target=inference_worker, daemon=True)
    if args.mode != "raw":
        worker_thread.start()

    D_samples = int(round(lat["algorithmic_total_ms"] / FRAME_MS)) * FRAME
    policy = SenderPolicyV4(D_samples=D_samples, jitter_ms=args.jitter_ms)
    
    last_send_time = None

    def read_ext5v():
        try:
            out = subprocess.check_output(["vcgencmd", "pmic_read_adc"], text=True, timeout=1)
            for line in out.splitlines():
                if "EXT5V_V" in line:
                    return float(line.split("=")[1].replace("V", ""))
        except:
            pass
        return 0.0

    ext5v_vals = []

    def telemetry(is_final=False):
        bs = backend.stats() if backend else {}
        d = {
            "model": model_name, "backend": backend_name, "model_sha": model_sha,
            "mode": args.mode, "bluetooth_connected": cap.connected, "source": cap.source,
            "frame": frames, 
            "worker_ms_p50": round(pct(worker_ms, 50), 2),
            "worker_ms_p95": round(pct(worker_ms, 95), 2),
            "worker_ms_max": round(max(worker_ms), 2) if worker_ms else 0.0,
            "send_interval_p50": round(pct(send_intervals, 50), 2),
            "send_interval_p95": round(pct(send_intervals, 95), 2),
            "send_interval_p99": round(pct(send_intervals, 99), 2),
            "send_interval_max": round(max(send_intervals), 2) if send_intervals else 0.0,
            "algorithmic_latency_ms": lat["algorithmic_total_ms"],
            "queue_delay_ms": 0.0, "queue_backlog": q.qsize(),
            "dropped_frames": dropped, "fallback_frames": policy.fallback_frames, "queue_drops": queue_drops,
            "chain_resets": policy.chain_resets, "late_frames": policy.late_frames,
            "clipped_samples": clipped,
            "reconnects": cap.reconnects, "temperature_c": read_temp_c(), 
            "throttled_start": throttled_start, "throttled_end": read_throttled(),
            "uptime_start": uptime_start, "uptime_end": get_uptime(),
            "ext5v_min": round(min(ext5v_vals), 3) if ext5v_vals else 0.0,
            "ext5v_mean": round(np.mean(ext5v_vals), 3) if ext5v_vals else 0.0,
            "in": probe_in.summary(), "out": probe_out.summary(),
        }
        d.update(bs)
        if not is_final:
            s_tel.sendto(json.dumps(d).encode(), (ip, args.telemetry_port))
        return d

    print("streaming %s -> %s (ports %d/%d/%d)" % (args.mode, ip, args.audio_port, args.telemetry_port, args.input_port), flush=True)
    
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
                
            while q.qsize() > args.max_backlog:
                dropped += 1
                q.get_nowait()
                
            if frames % 100 == 0:
                v = read_ext5v()
                if v > 0: ext5v_vals.append(v)
            
            # 1. Hard limiter on input
            clipped += int((np.abs(chunk) > 0.99).sum())
            chunk = np.clip(chunk, -0.99, 0.99).astype(np.float32)
            
            probe_in.update(chunk)
            hdr = struct.pack("<Q", seq)
            s_in.sendto(hdr + chunk.tobytes(), (ip, args.input_port))
            
            if args.mode == "raw":
                out = chunk
            else:
                # 2. Enqueue and handle reset
                t_ms = (time.monotonic() - t_start) * 1000.0
                backlog_ms = worker_q.qsize() * 16.0
                reset = policy.enqueue(seq, chunk, t_ms, backlog_ms)
                if reset and args.mode == "dfn3":
                    backend = BlockBackend(fn, block_ms=args.block_ms, context_ms=args.context_ms)
                    chain = AudioChain(backend)
                    out_q.clear()
                    
                worker_q.put((seq, chunk))
                
                # 3. Pull from policy
                out = policy.get_output(seq, out_q)

            clipped += int((np.abs(out) > 0.99).sum())
            out = np.clip(out, -0.99, 0.99).astype(np.float32)
            
            probe_out.update(out)
            s_out.sendto(hdr + out.tobytes(), (ip, args.audio_port))
            
            now = time.monotonic()
            if last_send_time is not None:
                send_intervals.append((now - last_send_time) * 1000.0)
            last_send_time = now
            last_sample = out[-1]
            
            seq += 1
            frames += 1
            if frames % 50 == 0:
                telemetry()
                last_tel = time.monotonic()
                
    finally:
        stop.set()
        cap.shutdown()
        final = telemetry(is_final=True)
        print("\n=== SUMMARY ===")
        print(json.dumps({k: final[k] for k in (
            "mode", "model", "backend", "frame", "worker_ms_p50", "worker_ms_p95", "worker_ms_max",
            "send_interval_p50", "send_interval_p95", "send_interval_p99", "send_interval_max",
            "algorithmic_latency_ms", "dropped_frames", "fallback_frames", "chain_resets", "late_frames", "queue_drops", "clipped_samples",
            "reconnects", "temperature_c", "throttled_start", "throttled_end", "uptime_start", "uptime_end", "ext5v_min", "ext5v_mean", "in", "out")}, indent=2))
        if args.report:
            with open(args.report, "w") as f:
                json.dump(final, f, indent=2)

if __name__ == "__main__":
    main()
