import time
import numpy as np

def run_benchmark():
    print("Initializing Raspberry Pi ONNX Benchmark...")
    try:
        import onnxruntime as ort
    except ImportError:
        print("ERROR: onnxruntime is not installed.")
        print("Please install it on your Raspberry Pi: pip3 install onnxruntime")
        return

    # Look for the exported model
    model_path = "checkpoints/dtln/model.onnx"
    import os
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}. Please copy it to the Pi.")
        return

    # Use CPUExecutionProvider for ARM
    print("Loading ONNX session with CPUExecutionProvider...")
    providers = ['CPUExecutionProvider']
    session = ort.InferenceSession(model_path, providers=providers)
    
    input_name = session.get_inputs()[0].name
    
    # 512 samples = 32ms at 16kHz
    frame_size = 512
    iterations = 1000
    
    # Pre-allocate random frame
    print("Warming up...")
    dummy_input = np.random.randn(1, frame_size).astype(np.float32)
    
    for _ in range(50):
        session.run(None, {input_name: dummy_input})
        
    print(f"\nBenchmarking {iterations} iterations...")
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        session.run(None, {input_name: dummy_input})
        
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_latency_ms = (total_time / iterations) * 1000.0
    budget_ms = (frame_size / 16000.0) * 1000.0
    
    print("\n================== HARDWARE RESULTS ==================")
    print(f"Hardware        : Raspberry Pi (via ARM CPUExecutionProvider)")
    print(f"Frame Size      : {frame_size} samples ({budget_ms:.1f} ms budget)")
    print(f"Average Latency : {avg_latency_ms:.2f} ms per frame")
    
    rtf = avg_latency_ms / budget_ms
    print(f"Streaming RTF   : {rtf:.4f}")
    
    if rtf < 1.0:
        print(f"Status          : PASS ({(budget_ms - avg_latency_ms):.2f} ms headroom per frame)")
    else:
        print(f"Status          : FAIL (Exceeds real-time budget by {(avg_latency_ms - budget_ms):.2f} ms)")
    print("======================================================")

if __name__ == "__main__":
    run_benchmark()
