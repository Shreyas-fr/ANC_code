import numpy as np
import soundfile as sf
import torch
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.complex_crn import ComplexCRN_Wrapper

def test_streaming():
    device = torch.device('cpu')
    wrapper = ComplexCRN_Wrapper().to(device)
    
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        state_dict = torch.load(checkpoint_path, map_location=device)
        new_state_dict = {}
        for k, v in state_dict.items():
            if not k.startswith("core."):
                new_state_dict["core." + k] = v
            else:
                new_state_dict[k] = v
        wrapper.load_state_dict(new_state_dict)
    
    model = wrapper.core
    model.eval()
    
    noisy, sr = sf.read("data/eval_samples/0_noisy.wav", dtype='float32')
    if len(noisy.shape) > 1: noisy = noisy[:, 0]
    
    # DSP Parameters
    n_fft = 512
    hop_length = 256
    window = np.hanning(n_fft).astype(np.float32)
    
    # State buffers
    in_buffer = np.zeros(n_fft, dtype=np.float32)
    out_buffer = np.zeros(n_fft, dtype=np.float32)
    
    output = []
    
    num_hops = len(noisy) // hop_length
    noisy = noisy[:num_hops * hop_length]
    
    print(f"Streaming {num_hops} hops of {hop_length} samples (OLA)...")
    with torch.no_grad():
        for i in range(num_hops):
            chunk = noisy[i*hop_length : (i+1)*hop_length]
            
            # Shift in
            in_buffer[:-hop_length] = in_buffer[hop_length:]
            in_buffer[-hop_length:] = chunk
            
            # Window & FFT
            framed = in_buffer * window
            stft = np.fft.rfft(framed)
            mag = np.abs(stft).astype(np.float32)
            
            # Model prediction
            mag_t = torch.tensor(mag).unsqueeze(0).unsqueeze(2).to(device)
            mask_real, mask_imag = model(mag_t)
            mask_real = mask_real.squeeze().numpy()
            mask_imag = mask_imag.squeeze().numpy()
            
            # Mask and IFFT
            mask_complex = mask_real + 1j * mask_imag
            enhanced_stft = stft * mask_complex
            enhanced_frame = np.fft.irfft(enhanced_stft) * window
            
            out_buffer += enhanced_frame
            
            # Shift out
            output_hop = out_buffer[:hop_length].copy()
            output.append(output_hop)
            
            out_buffer[:-hop_length] = out_buffer[hop_length:]
            out_buffer[-hop_length:] = 0.0
        
    output = np.concatenate(output)
    sf.write("data/eval_samples/0_streaming_test.wav", output, sr)
    print("Saved to data/eval_samples/0_streaming_test.wav")

if __name__ == "__main__":
    test_streaming()

if __name__ == "__main__":
    test_streaming()
