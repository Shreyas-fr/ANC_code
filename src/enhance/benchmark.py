import torch
import time
import sys
import os
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.enhance.complex_crn import ComplexCRN

def benchmark(segment_seconds=4.0, sample_rate=16000):
    model = ComplexCRN()
    model.eval()
    
    # Dummy input representing segment_seconds of audio
    # Shape: [Batch, Time]
    dummy_input = torch.randn(1, int(segment_seconds * sample_rate))
    
    # Warmup
    print("Warming up...")
    with torch.no_grad():
        for _ in range(5):
            _ = model(dummy_input)
            
    # Benchmark
    print("Benchmarking...")
    num_runs = 50
    start_time = time.time()
    
    with torch.no_grad():
        for _ in range(num_runs):
            _ = model(dummy_input)
            
    total_time = time.time() - start_time
    avg_inference_time = total_time / num_runs
    
    # Real-Time Factor (RTF)
    rtf = avg_inference_time / segment_seconds
    
    # Count parameters
    num_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    # Streaming Benchmark
    print("Benchmarking Streaming Latency (Frame-by-Frame)...")
    num_frames = 100
    frame_size = model.n_fft
    dummy_frame = torch.randn(1, frame_size)
    
    start_time = time.time()
    with torch.no_grad():
        for _ in range(num_frames):
            _ = model(dummy_frame)
    total_time = time.time() - start_time
    avg_frame_time = total_time / num_frames
    
    frame_seconds = frame_size / sample_rate
    streaming_rtf = avg_frame_time / frame_seconds
    
    print("\n=== ComplexCRN CPU Benchmark ===")
    print(f"Parameters:        {num_params:,}")
    print(f"Audio Segment:     {segment_seconds} seconds")
    print(f"Batched Inf Time:  {avg_inference_time:.4f} seconds")
    print(f"Batched RTF:       {rtf:.4f}")
    print("---")
    print(f"Frame Size:        {frame_size} samples ({frame_seconds*1000:.1f} ms)")
    print(f"Streaming Latency: {avg_frame_time*1000:.2f} ms per frame")
    print(f"Streaming RTF:     {streaming_rtf:.4f}")
    print("================================\n")
    
    if streaming_rtf < 1.0:
        print("-> Status: PASS! Dev CPU RTF suggests wide headroom, pending actual Pi validation.")
    else:
        print("-> Status: FAIL! Model is too heavy for real-time processing.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    benchmark(args.seconds)
