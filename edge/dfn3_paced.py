import sys
import os
import time
import json
import torch
import soundfile as sf
import numpy as np
import signal
import queue
import threading

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

chunk_size = 256
pos = 0
total_samples = len(data)
csv_path = os.path.expanduser(f"~/anc_logs/dfn3_paced_t{threads}.csv")
json_path = os.path.expanduser(f"~/anc_logs/dfn3_paced_t{threads}.json")

csv_fd = os.open(csv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)

backlog_ms_history = []
block_times = []
start_time = time.time()
q = queue.Queue()

worker_running = True

def save_json():
    bt = np.array(block_times)
    bg = np.array(backlog_ms_history)
    
    if len(bt) > 0:
        p50 = np.percentile(bt, 50)
        p95 = np.percentile(bt, 95)
        p99 = np.percentile(bt, 99)
        max_ms = np.max(bt)
    else:
        p50 = p95 = p99 = max_ms = 0.0

    if len(bg) > 0:
        bg_p50 = np.percentile(bg, 50)
        bg_p95 = np.percentile(bg, 95)
        bg_max = np.max(bg)
        bg_over_300 = int(np.sum(bg > 300))
        bg_over_1000 = int(np.sum(bg > 1000))
    else:
        bg_p50 = bg_p95 = bg_max = 0.0
        bg_over_300 = bg_over_1000 = 0
        
    res = {
        "count": len(bt),
        "p50_ms": float(p50),
        "p95_ms": float(p95),
        "p99_ms": float(p99),
        "max_ms": float(max_ms),
        "backlog_p50_ms": float(bg_p50),
        "backlog_p95_ms": float(bg_p95),
        "backlog_max_ms": float(bg_max),
        "backlog_over_300": bg_over_300,
        "backlog_over_1000": bg_over_1000
    }
    with open(json_path, "w") as f:
        json.dump(res, f)

def handle_sigterm(signum, frame):
    global worker_running
    worker_running = False
    save_json()
    os.close(csv_fd)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def worker():
    line_count = 0
    while worker_running:
        try:
            chunk, enqueue_time = q.get(timeout=0.1)
        except queue.Empty:
            continue
            
        t0 = time.perf_counter()
        chain.process(chunk)
        t1 = time.perf_counter()
        
        comp_time = t1 - t0
        duration_ms = comp_time * 1000
        output_time = time.perf_counter()
        backlog_ms = (output_time - enqueue_time) * 1000
        backlog_ms_history.append(backlog_ms)
        
        if duration_ms > 50:
            block_times.append(duration_ms)
            
        line = f"{time.time()},{duration_ms:.2f},{backlog_ms:.2f}\n".encode('utf-8')
        os.write(csv_fd, line)
        line_count += 1
        if line_count % 10 == 0:
            os.fsync(csv_fd)

w_thread = threading.Thread(target=worker)
w_thread.start()

last_save_time = time.time()
start_perf = time.perf_counter()
chunk_duration = 0.016
next_tick = start_perf + chunk_duration

while time.time() - start_time < seconds:
    end_pos = pos + chunk_size
    if end_pos > total_samples:
        pos = 0
        end_pos = chunk_size
        
    chunk = data[pos:end_pos].copy()
    q.put((chunk, time.perf_counter()))
    pos = end_pos
    
    now = time.perf_counter()
    if now < next_tick:
        time.sleep(next_tick - now)
    else:
        next_tick = now
    next_tick += chunk_duration
    
    if time.time() - last_save_time > 10:
        save_json()
        last_save_time = time.time()

worker_running = False
w_thread.join()
os.close(csv_fd)
save_json()
