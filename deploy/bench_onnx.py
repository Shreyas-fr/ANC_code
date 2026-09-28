import time
import numpy as np
import onnxruntime as ort
import os
import psutil
import json
import platform

def run_benchmark(model_path, threads):
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = threads
    session = ort.InferenceSession(model_path, sess_options=sess_options, providers=['CPUExecutionProvider'])
    input_name = session.get_inputs()[0].name
    
    n_fft = 512
    hop_length = 256
    budget_ms = (hop_length / 16000.0) * 1000.0
    
    dummy_input = np.random.randn(1, int(n_fft/2)+1, 1).astype(np.float32)
    
    for _ in range(50):
        session.run(None, {input_name: dummy_input})
        
    iterations = 500
    latencies = []
    process = psutil.Process(os.getpid())
    cpu_utils = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        session.run(None, {input_name: dummy_input})
        end = time.perf_counter()
        latencies.append((end - start) * 1000.0)
        cpu_utils.append(psutil.cpu_percent(interval=None))
        
    rss_mb = process.memory_info().rss / (1024 * 1024)
    
    return {
        'threads': threads,
        'p50': np.percentile(latencies, 50),
        'p95': np.percentile(latencies, 95),
        'p99': np.percentile(latencies, 99),
        'mean': np.mean(latencies),
        'rtf': np.mean(latencies) / budget_ms,
        'peak_rss_mb': rss_mb,
        'cpu_util': np.mean(cpu_utils)
    }

def main():
    os.makedirs("results", exist_ok=True)
    model_path = "checkpoints/dtln/model.onnx"
    if not os.path.exists(model_path):
        print(f"Error: {model_path} not found.")
        return
        
    info = {
        'platform': platform.system(),
        'cpu_model': platform.processor(),
        'machine': platform.machine(),
        'note': 'Laptop (Host CPU)'
    }
    
    results = []
    for t in [1, 2, 4]:
        print(f"Testing {t} thread(s)...")
        res = run_benchmark(model_path, t)
        results.append(res)
        
    out_dict = {'device_info': info, 'results': results}
    
    with open("results/bench_onnx.json", "w") as f:
        json.dump(out_dict, f, indent=2)
        
    with open("results/bench_onnx.md", "w") as f:
        f.write(f"# ONNX Benchmark\n")
        f.write(f"**Platform**: {info['platform']} {info['machine']} ({info['cpu_model']})\n\n")
        f.write("| Threads | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | RTF | Peak RSS (MB) | CPU % |\n")
        f.write("|---------|----------|----------|----------|-----------|-----|---------------|-------|\n")
        for r in results:
            f.write(f"| {r['threads']} | {r['p50']:.2f} | {r['p95']:.2f} | {r['p99']:.2f} | {r['mean']:.2f} | {r['rtf']:.4f} | {r['peak_rss_mb']:.1f} | {r['cpu_util']:.1f} |\n")
            
        f.write("\n## Raspberry Pi 5 2GB (Reserved)\n")
        f.write("*(Numbers below are intentionally blank, pending real execution on hardware by the evaluator)*\n")
        f.write("| Threads | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | RTF | Peak RSS (MB) | CPU % |\n")
        f.write("|---------|----------|----------|----------|-----------|-----|---------------|-------|\n")
        f.write("| 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |\n")
        f.write("| 2 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |\n")
        f.write("| 4 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |\n")

if __name__ == "__main__":
    main()
