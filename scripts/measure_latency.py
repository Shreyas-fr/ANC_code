import numpy as np
import sys
import os

def measure_algorithmic_latency():
    # Simulate the exact OLA buffer pipeline from test_streaming.py
    n_fft = 512
    hop_length = 256
    window = np.hanning(n_fft).astype(np.float32)
    
    # 1. Create an impulse at sample index 0
    test_len = 16000 # 1 second
    impulse = np.zeros(test_len, dtype=np.float32)
    impulse[0] = 1.0
    
    in_buffer = np.zeros(n_fft, dtype=np.float32)
    out_buffer = np.zeros(n_fft, dtype=np.float32)
    
    output = []
    num_hops = test_len // hop_length
    
    for i in range(num_hops):
        chunk = impulse[i*hop_length : (i+1)*hop_length]
        
        # Shift in
        in_buffer[:-hop_length] = in_buffer[hop_length:]
        in_buffer[-hop_length:] = chunk
        
        # Window & FFT
        framed = in_buffer * window
        stft = np.fft.rfft(framed)
        
        # Pass-through (Model does nothing in this test to measure pure algorithmic delay)
        mask_complex = np.ones_like(stft, dtype=np.complex64)
        enhanced_stft = stft * mask_complex
        
        # IFFT
        enhanced_frame = np.fft.irfft(enhanced_stft) * window
        
        # Overlap-Add
        out_buffer += enhanced_frame
        
        # Shift out
        output_hop = out_buffer[:hop_length].copy()
        output.append(output_hop)
        
        out_buffer[:-hop_length] = out_buffer[hop_length:]
        out_buffer[-hop_length:] = 0.0
        
    output = np.concatenate(output)
    
    # Find the peak in the output to see how many samples it was delayed
    peak_idx = np.argmax(output)
    
    # Calculate algorithmic latency in ms
    latency_ms = (peak_idx / 16000.0) * 1000.0
    
    print(f"Impulse placed at sample 0")
    print(f"Impulse emerged at sample {peak_idx}")
    print(f"Algorithmic Latency (Delay): {latency_ms:.2f} ms")

if __name__ == "__main__":
    measure_algorithmic_latency()
