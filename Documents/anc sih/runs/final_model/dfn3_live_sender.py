#!/usr/bin/env python3
"""Live DFN3 UDP sender for Raspberry Pi 5.

HFP mic -> PCM -> optional DFN3 -> UDP 5005/5007 + telemetry 5006.

Diagnostic modes:
  A raw       : protocol-rate mic audio, no DFN3
  B resample  : 16 kHz -> 48 kHz -> 16 kHz, no DFN3
  C dfn3      : hop-aligned stateful DeepFilterNet3 (default)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import time
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EDGE_ROOT = os.path.expanduser(os.environ.get("SIH_EDGE_ROOT", "~/sih26052_edge"))
sys.path.insert(0, EDGE_ROOT)

from single_instance import acquire_lock, pgrep_competitors  # noqa: E402
from stream_resample import StatefulLinearResampler  # noqa: E402

stop_processing = False
FRAME_SAMPLES = 256  # 16 ms at 16 kHz — matches frontend PROTOCOL.md
IO_SR = 16000


def signal_handler(sig, frame):
    global stop_processing
    stop_processing = True
    print("\nStopping live sender...")


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def find_hfp_source():
    """Find the current Bluetooth HFP capture node. Prefers Rockerz 512 ANC.

    On this Pi, WirePlumber exposes HFP as a Filter (`bluez_input.*`) rather
    than under Sources:. Scan the whole `wpctl status` tree.
    """
    try:
        out = subprocess.check_output(["wpctl", "status"], text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        print(f"wpctl status failed: {e}")
        return None, None

    matches = []
    for line in out.splitlines():
        if "bluez_input" not in line.lower():
            continue
        if "capture_internal" in line.lower():
            continue
        m = re.search(r"(\d+)\.\s+", line)
        if not m:
            continue
        matches.append((m.group(1), line.strip()))

    if not matches:
        return None, None

    ranked = []
    for nid, desc in matches:
        score = 0
        low = desc.lower()
        if "rockerz" in low:
            score += 5
        if "512" in low:
            score += 2
        if "hfp" in low or "headset" in low or "handsfree" in low:
            score += 3
        if "a2dp" in low:
            score -= 4
        ranked.append((score, nid, desc))
    ranked.sort(reverse=True)
    _, nid, desc = ranked[0]
    return nid, desc


def wait_for_hfp(timeout_sec=None):
    t0 = time.time()
    while not stop_processing:
        nid, desc = find_hfp_source()
        if nid:
            print(f"HFP source: id={nid}  {desc}")
            return nid, desc
        if timeout_sec is not None and (time.time() - t0) > timeout_sec:
            return None, None
        print("No Bluetooth HFP source yet (Rockerz 512 ANC). Waiting for reconnect...")
        time.sleep(1.5)
    return None, None


def read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def read_throttled():
    try:
        out = subprocess.check_output(["vcgencmd", "get_throttled"], text=True)
        return out.strip()
    except Exception:
        return "unavailable"


def cooler_hint(temp_c: float, throttled: str) -> str:
    if throttled and throttled not in ("unavailable",) and "0x0" not in throttled.replace(" ", ""):
        return "THROTTLED"
    if temp_c >= 80:
        return "HOT"
    if temp_c >= 70:
        return "WARM"
    return "OK"


def open_capture(source_id: str, rate: int):
    cmd = [
        "pw-record",
        "-a",
        "--target",
        str(source_id),
        "--rate",
        str(rate),
        "--channels",
        "1",
        "--format",
        "f32",
        "-",
    ]
    print("Capture:", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)


def drain_frames(buf: deque, n: int):
    if len(buf) < n:
        return None
    frame = np.array([buf.popleft() for _ in range(n)], dtype=np.float32)
    return frame


def send_pcm(sock, addr, seq, frame):
    header = struct.pack("<Q", seq)
    sock.sendto(header + frame.astype(np.float32).tobytes(), addr)


def main():
    parser = argparse.ArgumentParser(description="SIH26052 DFN3 live sender")
    parser.add_argument("--mode", choices=("raw", "resample", "dfn3"), default="dfn3")
    parser.add_argument("--pc-ip", default=os.environ.get("SIH_PC_IP", "10.190.58.182"))
    parser.add_argument("--port-enhanced", type=int, default=5005)
    parser.add_argument("--port-telemetry", type=int, default=5006)
    parser.add_argument("--port-input", type=int, default=5007)
    parser.add_argument("--seconds", type=float, default=0.0, help="0 = run until Ctrl+C")
    parser.add_argument("--capture-rate", type=int, default=16000)
    parser.add_argument("--replace", action="store_true", help="SIGTERM competing live processes")
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "SIH_DFN3_MODEL", os.path.expanduser("~/sih26052_edge/models/model.hk")
        ),
    )
    args = parser.parse_args()

    acquire_lock(replace=args.replace)

    leftover = pgrep_competitors()
    leftover = [(p, a) for p, a in leftover if os.getpid() != p]
    if leftover:
        print("WARNING: competitors still visible after lock:")
        for p, a in leftover:
            print(f"  {p} {a}")

    capture_to_io = None
    if args.capture_rate != IO_SR:
        capture_to_io = StatefulLinearResampler(args.capture_rate, IO_SR)

    processor = None
    loop_resampler = None
    model_name = "bypass"
    backend = "none"
    model_sha = "n/a"
    params = 0
    if args.mode == "dfn3":
        from dfn3_stream import DFN3Stream, PARAM_COUNT_CLAIM

        cfg = {
            "model_path": args.model,
            "sample_rate": IO_SR,
            "log_directory": os.path.join(EDGE_ROOT, "logs"),
            "frame_ms": 10,
        }
        os.makedirs(cfg["log_directory"], exist_ok=True)
        processor = DFN3Stream(cfg)
        model_name = "DeepFilterNet3"
        backend = "PyTorch/libdf-stateful"
        model_sha = processor.model_sha
        params = PARAM_COUNT_CLAIM
    elif args.mode == "resample":
        loop_resampler = StatefulLinearResampler(IO_SR, 48000)
        loop_down = StatefulLinearResampler(48000, IO_SR)
        model_name = "resample_only"
        backend = "linear-resampler"
        print("Mode B: 16 kHz -> 48 kHz -> 16 kHz, no DFN3.")
    else:
        print("Mode A: raw capture (no DFN3). Establishing clean HFP baseline.")

    sock_enh = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_tel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr_enh = (args.pc_ip, args.port_enhanced)
    addr_in = (args.pc_ip, args.port_input)
    addr_tel = (args.pc_ip, args.port_telemetry)

    raw_q = deque()
    out_q = deque()
    seq_enh = 0
    seq_in = 0
    times = []
    capture_short_reads = 0
    t_start = time.time()
    source_id = None
    source_desc = ""
    proc = None
    bytes_per_read = FRAME_SAMPLES * 4
    if args.capture_rate != IO_SR:
        bytes_per_read = max(256, int(args.capture_rate * 0.016)) * 4

    print(f"Streaming to {args.pc_ip} mode={args.mode}")
    print("This is AI speech enhancement / noise suppression, not acoustic ANC.")

    try:
        while not stop_processing:
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    print("Capture process died; waiting for HFP reconnect...")
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                source_id, source_desc = wait_for_hfp()
                if not source_id:
                    break
                proc = open_capture(source_id, args.capture_rate)

            raw_bytes = proc.stdout.read(bytes_per_read)
            if not raw_bytes:
                capture_short_reads += 1
                time.sleep(0.01)
                if proc.poll() is not None:
                    continue
                continue
            if len(raw_bytes) < 8:
                capture_short_reads += 1
                continue

            n = (len(raw_bytes) // 4) * 4
            chunk = np.frombuffer(raw_bytes[:n], dtype=np.float32).copy()
            if capture_to_io is not None:
                chunk = capture_to_io.process(chunk)
            if len(chunk) == 0:
                continue

            t0 = time.perf_counter()
            if args.mode == "raw":
                enhanced = chunk
            elif args.mode == "resample":
                up = loop_resampler.process(chunk)
                enhanced = loop_down.process(up) if len(up) else np.zeros(0, dtype=np.float32)
            else:
                enhanced = processor.process_pcm16k(chunk)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            times.append(elapsed_ms)
            if len(times) > 2000:
                times = times[-2000:]

            for s in chunk:
                raw_q.append(float(s))
            for s in enhanced:
                out_q.append(float(s))

            while True:
                raw_frame = drain_frames(raw_q, FRAME_SAMPLES)
                if raw_frame is None:
                    break
                send_pcm(sock_in, addr_in, seq_in, raw_frame)
                seq_in += 1

            while True:
                out_frame = drain_frames(out_q, FRAME_SAMPLES)
                if out_frame is None:
                    break
                send_pcm(sock_enh, addr_enh, seq_enh, out_frame)
                seq_enh += 1

            if seq_enh > 0 and seq_enh % 25 == 0:
                recent = times[-100:] if times else [0.0]
                tel = {
                    "model": model_name,
                    "backend": backend,
                    "model_sha": model_sha,
                    "parameters": params,
                    "model_active": args.mode == "dfn3",
                    "diag_mode": args.mode,
                    "bluetooth_connected": True,
                    "bluetooth_device": source_desc,
                    "bluetooth_source_id": source_id,
                    "frame": seq_enh,
                    "latency_ms": round(elapsed_ms, 2),
                    "latency_median_ms": round(float(np.median(recent)), 2),
                    "latency_p95_ms": round(float(np.percentile(recent, 95)), 2),
                    "latency_p99_ms": round(float(np.percentile(recent, 99)), 2),
                    "latency_max_ms": round(float(np.max(recent)), 2),
                    "processing_ms": round(elapsed_ms, 2),
                    "median_ms": round(float(np.median(recent)), 2),
                    "p95_ms": round(float(np.percentile(recent, 95)), 2),
                    "max_ms": round(float(np.max(recent)), 2),
                    "temperature_c": read_temp_c(),
                    "throttled": read_throttled(),
                    "cooler_hint": cooler_hint(read_temp_c(), read_throttled()),
                    "state_resets": getattr(processor, "state_resets", 0) if processor else 0,
                    "nan_inf_events": getattr(processor, "nan_inf_count", 0) if processor else 0,
                    "clip_count": getattr(processor, "clip_count", 0) if processor else 0,
                    "dc_events": getattr(processor, "dc_events", 0) if processor else 0,
                    "rms_events": getattr(processor, "rms_events", 0) if processor else 0,
                    "last_rms": round(getattr(processor, "last_rms", 0.0), 5) if processor else 0.0,
                    "deadline_misses": getattr(processor, "deadline_misses", 0) if processor else 0,
                    "capture_short_reads": capture_short_reads,
                    "buffer_underruns": capture_short_reads,
                    "enhanced_seq": seq_enh,
                    "input_seq": seq_in,
                    "end_to_end_latency_ms": None,
                    "end_to_end_latency_note": "NOT MEASURED",
                    "claim": "speech_enhancement_not_acoustic_anc",
                }
                sock_tel.sendto(json.dumps(tel).encode("utf-8"), addr_tel)

            if args.seconds > 0 and (time.time() - t_start) >= args.seconds:
                print(f"Reached --seconds {args.seconds}")
                break
    except Exception as e:
        print(f"Exception during processing: {e}")
        raise
    finally:
        if proc is not None:
            proc.terminate()
        sock_enh.close()
        sock_in.close()
        sock_tel.close()

    if times:
        arr = np.array(times)
        print("\n=== LIVE RUN SUMMARY (inference/processing, not end-to-end) ===")
        print(f"mode={args.mode} enhanced_frames={seq_enh} input_frames={seq_in}")
        print(f"median={np.median(arr):.2f} ms  p95={np.percentile(arr,95):.2f} ms  "
              f"p99={np.percentile(arr,99):.2f} ms  max={np.max(arr):.2f} ms")
        print(f"temp={read_temp_c():.1f} C  throttled={read_throttled()}")
        print(f"model_sha={model_sha}")


if __name__ == "__main__":
    main()
