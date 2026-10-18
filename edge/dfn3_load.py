import sys
import os
import time
import json
import torch
import soundfile as sf
import numpy as np

sys.path.insert(0, os.path.expanduser("~/sih26052_edge/anc_fix_v2/anc_fix"))
from streaming_core import AudioChain, BlockBackend
from dfn3_enhance import make_dfn3_enhance_fn

threads = int(sys.argv[1])
seconds = int(sys.argv[2])

torch.set_num_threads(threads)

model_path = os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk")
fn = make_dfn3_enhance_fn(model_path, threads)
backend = BlockBackend(fn, block_ms=500, context_ms=300)
chain = AudioChain(backend)

data, sr = sf.read(os.path.expanduser("~/anc_logs/D_in.wav"))
if data.ndim > 1:
    data = data[:, 0]
if sr != 48000:
    print("Warning: unexpected sr")

chunk_size = 256
pos = 0
total_samples = len(data)
csv_path = os.path.expanduser(f"~/anc_logs/dfn3_blocks_t{threads}.csv")
json_path = os.path.expanduser(f"~/anc_logs/dfn3_load_t{threads}.json")

import signal

block_times = []
start_time = time.time()
total_audio_frames = 0
csv_fd = os.open(csv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)

# pre-allocate to avoid GC in the loop
chunk = np.zeros(chunk_size, dtype=np.float32)

def save_json():
    total_compute_time = time.time() - start_time
    total_audio_time = total_audio_frames / 48000.0
    rtf = total_compute_time / total_audio_time if total_audio_time > 0 else 0

    bt = np.array(block_times)
    if len(bt) > 0:
        p50 = np.percentile(bt, 50)
        p95 = np.percentile(bt, 95)
        p99 = np.percentile(bt, 99)
        max_ms = np.max(bt)
    else:
        p50 = p95 = p99 = max_ms = 0.0

    res = {
        "count": len(bt),
        "p50_ms": float(p50),
        "p95_ms": float(p95),
        "p99_ms": float(p99),
        "max_ms": float(max_ms),
        "rtf": float(rtf)
    }
    with open(json_path, "w") as f:
        json.dump(res, f)

def handle_sigterm(signum, frame):
    save_json()
    os.close(csv_fd)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

line_count = 0
last_save_time = start_time
while time.time() - start_time < seconds:
    end_pos = pos + chunk_size
    if end_pos > total_samples:
        pos = 0
        end_pos = chunk_size
    
    # avoid data allocation if possible
    chunk[:] = data[pos:end_pos]
    pos = end_pos
    
    t0 = time.perf_counter()
    out = chain.process(chunk)
    t1 = time.perf_counter()
    
    duration_ms = (t1 - t0) * 1000
    if duration_ms > 50:
        block_times.append(duration_ms)
        line = f"{time.time()},{duration_ms:.2f}\n".encode('utf-8')
        os.write(csv_fd, line)
        line_count += 1
        if line_count % 10 == 0:
            os.fsync(csv_fd)
            
    total_audio_frames += chunk_size
    
    if time.time() - last_save_time > 10:
        save_json()
        last_save_time = time.time()

os.close(csv_fd)
save_json()
