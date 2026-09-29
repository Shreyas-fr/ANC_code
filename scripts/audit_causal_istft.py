import torch
import torch.nn.functional as F_nn
import numpy as np

# Copied from stateful_lstm.py for isolated testing
def causal_istft(stft_matrix, n_fft, hop_length, window):
    B, F_bins, T_frames = stft_matrix.shape
    frames = torch.fft.irfft(stft_matrix, n=n_fft, dim=1)
    frames = frames * window.view(1, -1, 1).to(stft_matrix.device)
    
    output_len = (T_frames - 1) * hop_length + n_fft
    frames_fold = frames
    
    output = F_nn.fold(frames_fold, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    output = output.squeeze(1).squeeze(1)
    
    window_sq = window ** 2
    window_sq_exp = window_sq.view(1, -1, 1).repeat(1, 1, T_frames).to(stft_matrix.device)
    env = F_nn.fold(window_sq_exp, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    env = env.squeeze(1).squeeze(1)
    
    # Store raw env for testing before clamping
    raw_env = env.clone()
    
    env = env.clamp(min=1e-8)
    return output / env, raw_env

def run_tests():
    n_fft = 512
    hop = 256
    window = torch.hann_window(n_fft)
    
    print("=== 2. WINDOW / HOP NOLA ANALYSIS ===")
    x = torch.ones(1, 16000)
    stft = torch.stft(x, n_fft=n_fft, hop_length=hop, window=window, center=False, return_complex=True)
    _, env = causal_istft(stft, n_fft, hop, window)
    env = env[0]
    
    print(f"Min envelope interior: {env[n_fft:-n_fft].min().item()}")
    print(f"Max envelope: {env.max().item()}")
    print(f"Min envelope boundaries: {min(env[:hop].min().item(), env[-hop:].min().item())}")
    
    zeros = (env == 0).nonzero(as_tuple=True)[0]
    print(f"Locations where env == 0: {zeros.tolist() if len(zeros) < 20 else str(len(zeros)) + ' locations'}")
    smalls = (env < 1e-6).nonzero(as_tuple=True)[0]
    print(f"Locations where env < 1e-6: {smalls.tolist() if len(smalls) < 20 else str(len(smalls)) + ' locations'}")

    print("\n=== 1. RECONSTRUCTION TEST ===")
    def test_recon(sig, name):
        s = torch.stft(sig, n_fft=n_fft, hop_length=hop, window=window, center=False, return_complex=True)
        y, _ = causal_istft(s, n_fft, hop, window)
        
        # Valid region is from n_fft to output_len - n_fft where NOLA is fully satisfied
        # Wait, standard NOLA for Hann 512/256 is satisfied after hop (256).
        # Let's check from hop to length - hop.
        valid_start = hop
        valid_end = y.shape[-1] - hop
        
        sig_slice = sig[0, valid_start:valid_end]
        y_slice = y[0, valid_start:valid_end]
        
        max_err = torch.abs(sig_slice - y_slice).max().item()
        rms_err = torch.sqrt(torch.mean((sig_slice - y_slice)**2)).item()
        sig_rms = torch.sqrt(torch.mean(sig_slice**2)).item() + 1e-8
        snr = 20 * np.log10(sig_rms / rms_err) if rms_err > 0 else float('inf')
        
        print(f"{name:15} | MaxErr: {max_err:.2e} | RMS: {rms_err:.2e} | SNR: {snr:.1f} dB")

    t = torch.linspace(0, 1, 16000)
    test_recon(torch.zeros(1, 16000), "Silence")
    test_recon(torch.ones(1, 16000), "Constant")
    test_recon(torch.randn(1, 16000), "White Noise")
    test_recon(torch.sin(2 * np.pi * 440 * t).unsqueeze(0), "Sine 440Hz")
    imp = torch.zeros(1, 16000); imp[0, 8000] = 1.0
    test_recon(imp, "Impulse Mid")
    imp_start = torch.zeros(1, 16000); imp_start[0, 0] = 1.0
    test_recon(imp_start, "Impulse 0") # Won't be in valid region, but let's see.

    print("\n=== 8. DELAY VERIFICATION ===")
    # Impulse at hop_length
    imp_align = torch.zeros(1, 16000)
    imp_align[0, 1000] = 1.0
    stft_imp = torch.stft(imp_align, n_fft=n_fft, hop_length=hop, window=window, center=False, return_complex=True)
    y_imp, _ = causal_istft(stft_imp, n_fft, hop, window)
    
    max_idx = torch.argmax(y_imp[0]).item()
    print(f"Input impulse at: 1000")
    print(f"Output impulse at: {max_idx}")
    print(f"Measured Delay: {max_idx - 1000} samples")

    print("\n=== 4. STREAMING EQUIVALENCE ===")
    x_stream = torch.randn(1, 16000)
    stft_stream = torch.stft(x_stream, n_fft=n_fft, hop_length=hop, window=window, center=False, return_complex=True)
    y_batch, _ = causal_istft(stft_stream, n_fft, hop, window)
    
    T_frames = stft_stream.shape[-1]
    y_stream = torch.zeros(1, (T_frames - 1) * hop + n_fft)
    env_stream = torch.zeros(1, (T_frames - 1) * hop + n_fft)
    
    for i in range(T_frames):
        frame_stft = stft_stream[:, :, i:i+1] # [1, 257, 1]
        frame_time = torch.fft.irfft(frame_stft, n=n_fft, dim=1).squeeze(-1) # [1, 512]
        frame_time = frame_time * window.unsqueeze(0)
        
        start = i * hop
        end = start + n_fft
        y_stream[0, start:end] += frame_time[0]
        env_stream[0, start:end] += window**2
        
    env_stream = env_stream.clamp(min=1e-8)
    y_stream = y_stream / env_stream
    
    diff_stream = torch.abs(y_batch - y_stream).max().item()
    print(f"Batch vs Streaming Max Error: {diff_stream:.2e}")

    print("\n=== 10. GRADIENT TEST ===")
    stft_grad = stft_stream.clone().requires_grad_(True)
    y_grad, _ = causal_istft(stft_grad, n_fft, hop, window)
    
    target = torch.randn_like(y_grad)
    loss = F_nn.l1_loss(y_grad, target)
    loss.backward()
    
    print(f"Loss finite: {loss.isfinite().item()}")
    print(f"Grads exist: {stft_grad.grad is not None}")
    if stft_grad.grad is not None:
        print(f"Grads finite: {stft_grad.grad.isfinite().all().item()}")
        print(f"Max grad magnitude: {stft_grad.grad.abs().max().item():.2e}")

    print("\n=== 11. LENGTH / ALIGNMENT CONTRACT ===")
    lens = [100, 512, 513, 768, 1000, 16000]
    for L in lens:
        try:
            x_L = torch.randn(1, L)
            s_L = torch.stft(x_L, n_fft=n_fft, hop_length=hop, window=window, center=False, return_complex=True)
            y_L, _ = causal_istft(s_L, n_fft, hop, window)
            print(f"Input: {L} | Frames: {s_L.shape[-1]} | Output: {y_L.shape[-1]}")
        except Exception as e:
            print(f"Input: {L} | STFT Failed: {e}")

if __name__ == "__main__":
    run_tests()
