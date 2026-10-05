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
import socket
import subprocess

sys.path.insert(0, os.path.expanduser("~/sih26052_edge/anc_fix_v2/anc_fix"))
from streaming_core import AudioChain, BlockBackend
from dfn3_enhance import make_dfn3_enhance_fn

threads = int(sys.argv[1]) if len(sys.argv) > 1 else 1
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

os.makedirs("/dev/shm/anc_run", exist_ok=True)
json_path = f"/dev/shm/anc_run/dfn3_paced2_t{threads}.json"

backlog_ms_history = []
block_times = []
start_time = time.time()
q = queue.Queue()

worker_running = True
blocks_done = 0
last_block_ms = 0.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
MAC_IP = sys.argv[3] if len(sys.argv) > 3 else "10.190.58.182"

def get_power_stats():
    try:
        pmic = subprocess.check_output("vcgencmd pmic_read_adc", shell=True).decode()
        ext5v = 0.0
        vdd = 0.0
        vdd_v = 0.0
        for line in pmic.split('\n'):
            if "EXT5V_V" in line:
                ext5v = float(line.split("=")[1].replace("V",""))
            elif "VDD_CORE_A" in line:
                vdd = float(line.split("=")[1].replace("A",""))
            elif "VDD_CORE_V" in line:
                vdd_v = float(line.split("=")[1].replace("V",""))
        throt = subprocess.check_output("vcgencmd get_throttled", shell=True).decode().strip().split("=")[1]
        temp = subprocess.check_output("vcgencmd measure_temp", shell=True).decode().strip().split("=")[1].replace("'C","")
        arm_clock = subprocess.check_output("vcgencmd measure_clock arm", shell=True).decode().strip().split("=")[1]
        mem = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    mem = int(line.split()[1])
                    break
        return ext5v, vdd, vdd_v, throt, temp, arm_clock, mem, pmic
    except:
        return 0.0, 0.0, 0.0, "0x0", "0.0", "0", 0, ""

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
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def worker():
    global blocks_done, last_block_ms
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
            blocks_done += 1
            last_block_ms = duration_ms

w_thread = threading.Thread(target=worker)
w_thread.start()

power_running = True
min_ext5v = 999.0
lowest_pmic = ""
def power_sampler():
    global min_ext5v, lowest_pmic
    with open("/dev/shm/anc_run/power.csv", "w") as f:
        f.write("epoch,uptime,ext5v,vdd_a,vdd_v,throt,temp,arm_clock,mem_avail\n")
    
    while power_running:
        t_start = time.time()
        ext5v, vdd, vdd_v, throt, temp, arm_clock, mem, pmic = get_power_stats()
        if ext5v > 0 and ext5v < min_ext5v:
            min_ext5v = ext5v
            lowest_pmic = pmic
            
        try:
            uptime = float(open("/proc/uptime").read().split()[0])
        except:
            uptime = 0.0
            
        line = f"{time.time()},{uptime},{ext5v},{vdd},{vdd_v},{throt},{temp},{arm_clock},{mem}\n"
        with open("/dev/shm/anc_run/power.csv", "a") as f:
            f.write(line)
            
        msg = f"POWER: {uptime:.2f} {ext5v}V {vdd}A {vdd_v}V {throt} {temp}C {arm_clock}Hz {mem}kB"
        sock.sendto(msg.encode(), (MAC_IP, 5099))
        
        elapsed = time.time() - t_start
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)

p_thread = threading.Thread(target=power_sampler)
p_thread.start()

last_save_time = time.time()
last_udp_time = time.time()
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
    
    now_ts = time.time()
    if now_ts - last_save_time > 10:
        save_json()
        last_save_time = now_ts
        
    if now_ts - last_udp_time > 0.25:
        try:
            uptime = float(open("/proc/uptime").read().split()[0])
        except:
            uptime = 0.0
        bg = backlog_ms_history[-1] if backlog_ms_history else 0.0
        msg = f"UDP: uptime={uptime:.2f} stage=p{threads} bg={bg:.1f}ms blk_ms={last_block_ms:.1f} blk_done={blocks_done} q={q.qsize()}"
        sock.sendto(msg.encode(), (MAC_IP, 5099))
        last_udp_time = now_ts

worker_running = False
power_running = False
w_thread.join()
p_thread.join()
save_json()

with open("/dev/shm/anc_run/lowest_pmic.txt", "w") as f:
    f.write(lowest_pmic)
