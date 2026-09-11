import time
import numpy as np
import onnxruntime as ort
import os

def run_benchmark():
    print("Initializing Raspberry Pi ONNX Benchmark with Streaming STFT...")
    model_path = "checkpoints/dtln/model.onnx"
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}.")
        return

    print("Loading ONNX session with CPUExecutionProvider (Threads=2)...")
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = 2
    session = ort.InferenceSession(model_path, sess_options=sess_options, providers=['CPUExecutionProvider'])
    
    input_name = session.get_inputs()[0].name
    
    # DSP Parameters
    n_fft = 512
    hop_length = 256
    window = np.hanning(n_fft).astype(np.float32)
    
    # Pre-allocate random 256-sample frame (16ms hops)
    dummy_input_hop = np.random.randn(hop_length).astype(np.float32)
    
    # State buffers
    in_buffer = np.zeros(n_fft, dtype=np.float32)
    out_buffer = np.zeros(n_fft, dtype=np.float32)
    
    iterations = 1000
    print("Warming up...")
    for _ in range(50):
        # Shift in
        in_buffer[:-hop_length] = in_buffer[hop_length:]
        in_buffer[-hop_length:] = dummy_input_hop
        
        # Window & FFT
        framed = in_buffer * window
        stft = np.fft.rfft(framed)
        mag = np.abs(stft).astype(np.float32)
        
        # ONNX Mask Prediction [1, 257, 1]
        mag_input = np.expand_dims(np.expand_dims(mag, axis=0), axis=2)
        mask_real, mask_imag = session.run(None, {input_name: mag_input})
        
        # Construct complex mask and apply
        mask_complex = mask_real[0, :, 0] + 1j * mask_imag[0, :, 0]
        enhanced_stft = stft * mask_complex
        
        # IFFT & Overlap-Add
        enhanced_frame = np.fft.irfft(enhanced_stft) * window
        out_buffer += enhanced_frame
        
        # Shift out
        output_hop = out_buffer[:hop_length].copy()
        out_buffer[:-hop_length] = out_buffer[hop_length:]
        out_buffer[-hop_length:] = 0.0
        
    print(f"\nBenchmarking {iterations} iterations...")
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        # Shift in
        in_buffer[:-hop_length] = in_buffer[hop_length:]
        in_buffer[-hop_length:] = dummy_input_hop
        
        # Window & FFT
        framed = in_buffer * window
        stft = np.fft.rfft(framed)
        mag = np.abs(stft).astype(np.float32)
        
        # ONNX Mask Prediction
        mag_input = np.expand_dims(np.expand_dims(mag, axis=0), axis=2)
        mask_real, mask_imag = session.run(None, {input_name: mag_input})
        
        # Construct complex mask and apply
        mask_complex = mask_real[0, :, 0] + 1j * mask_imag[0, :, 0]
        enhanced_stft = stft * mask_complex
        
        # IFFT & Overlap-Add
        enhanced_frame = np.fft.irfft(enhanced_stft) * window
        out_buffer += enhanced_frame
        
        # Shift out
        output_hop = out_buffer[:hop_length].copy()
        out_buffer[:-hop_length] = out_buffer[hop_length:]
        out_buffer[-hop_length:] = 0.0
        
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_latency_ms = (total_time / iterations) * 1000.0
    budget_ms = (hop_length / 16000.0) * 1000.0
    
    print("\n================== HARDWARE RESULTS ==================")
    print(f"Hardware        : Raspberry Pi (ARM, 2 Threads)")
    print(f"Frame Size      : {hop_length} samples ({budget_ms:.1f} ms budget)")
    print(f"Average Latency : {avg_latency_ms:.2f} ms per frame (Includes STFT/ISTFT)")
    
    rtf = avg_latency_ms / budget_ms
    print(f"Streaming RTF   : {rtf:.4f}")
    
    if rtf < 1.0:
        print(f"Status          : PASS ({(budget_ms - avg_latency_ms):.2f} ms headroom per frame)")
    else:
        print(f"Status          : FAIL (Exceeds real-time budget by {(avg_latency_ms - budget_ms):.2f} ms)")
    print("======================================================")

if __name__ == "__main__":
    run_benchmark()
