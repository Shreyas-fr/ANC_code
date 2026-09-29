import torch
import torch.nn.functional as F
import time
import os
import sys
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_lstm import StatefulComplexLSTM_Wrapper, causal_istft
from src.enhance.losses import EnhancementLoss

def main():
    print("=== SIH26052 FAILURE DIAGNOSIS ===")
    
    device = torch.device('cpu')
    model = StatefulComplexLSTM_Wrapper().to(device)
    model.eval()
    
    # 2. IDENTITY MASK TEST
    print("\n--- 2. IDENTITY MASK TEST ---")
    x = torch.randn(1, 16000)
    stft = torch.stft(x, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
    # Identity mask
    M_real = torch.ones_like(stft.real)
    M_imag = torch.zeros_like(stft.imag)
    M = torch.complex(M_real, M_imag)
    
    enhanced_stft = stft * M
    y = causal_istft(enhanced_stft, 512, 256, model.window)
    
    expected_len = (stft.shape[-1] - 1) * 256 + 512
    x_aligned = x[:, :expected_len]
    
    # Ignore first and last 512 samples for exact reconstruction
    y_int = y[:, 512:-512]
    x_int = x_aligned[:, 512:-512]
    rms_err = torch.sqrt(torch.mean((y_int - x_int)**2)).item()
    max_err = torch.max(torch.abs(y_int - x_int)).item()
    
    sig_power = torch.mean(x_int**2).item()
    noise_power = rms_err**2
    snr = 10 * torch.log10(torch.tensor(sig_power / (noise_power + 1e-12))).item()
    
    print(f"IDENTITY_RMS_ERROR={rms_err:.4e}")
    print(f"IDENTITY_MAX_ERROR={max_err:.4e}")
    print(f"IDENTITY_SNR_ERROR={snr:.2f} dB")
    # Actually if SNR is > 100 dB, then it's perfect reconstruction.
    if max_err > 1e-3:
        print("IDENTITY_RECONSTRUCTION_STATUS=FAIL")
    else:
        print("IDENTITY_RECONSTRUCTION_STATUS=PASS")
        
    # 3. ZERO MASK TEST
    print("\n--- 3. ZERO MASK TEST ---")
    M_zero = torch.zeros_like(stft)
    y_zero = causal_istft(stft * M_zero, 512, 256, model.window)
    zero_rms = torch.sqrt(torch.mean(y_zero**2)).item()
    print(f"ZERO_OUTPUT_RMS={zero_rms:.4e}")
    if zero_rms < 1e-6:
        print("ZERO_MASK_STATUS=PASS")
    else:
        print("ZERO_MASK_STATUS=FAIL")

    # 4. COMPLEX MASK VERIFICATION
    print("\n--- 4. UNITY-PHASE MASK TEST ---")
    M_90 = torch.complex(torch.zeros_like(stft.real), torch.ones_like(stft.imag))
    y_90_stft = stft * M_90
    expected = torch.complex(-stft.imag, stft.real)
    diff = torch.max(torch.abs(y_90_stft - expected)).item()
    print(f"90-DEGREE ROTATION MAX ERROR: {diff:.4e}")
    if diff < 1e-6:
        print("COMPLEX_MASK_IMPLEMENTATION=PASS")
    else:
        print("COMPLEX_MASK_IMPLEMENTATION=FAIL")

    # 5. OUTPUT MAGNITUDE AUDIT
    print("\n--- 5. OUTPUT MAGNITUDE AUDIT ---")
    # We load the actual untrained checkpoint for this to see what it predicts
    model.load_state_dict(torch.load("runs/sih26052_baseline/best.pt", weights_only=False))
    
    x = torch.randn(1, 16000)
    with torch.no_grad():
        stft_x = torch.stft(x, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
        features = torch.cat([stft_x.transpose(1, 2).real, stft_x.transpose(1, 2).imag], dim=-1)
        h_in = torch.zeros(2, 1, 256)
        c_in = torch.zeros(2, 1, 256)
        mask_real, mask_imag, _, _ = model.core(features, h_in, c_in)
        mask_mag = torch.sqrt(mask_real**2 + mask_imag**2)
        
    print(f"mask_real: min={mask_real.min():.4f}, max={mask_real.max():.4f}, mean={mask_real.mean():.4f}, std={mask_real.std():.4f}")
    print(f"mask_imag: min={mask_imag.min():.4f}, max={mask_imag.max():.4f}, mean={mask_imag.mean():.4f}, std={mask_imag.std():.4f}")
    print(f"mask_mag : min={mask_mag.min():.4f}, max={mask_mag.max():.4f}, mean={mask_mag.mean():.4f}, std={mask_mag.std():.4f}")
    
    # 9. ONE BATCH GRADIENT DIRECTION
    print("\n--- 9. ONE-BATCH GRADIENT DIRECTION TEST ---")
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = EnhancementLoss()
    
    c = torch.randn(1, 16000)
    n = torch.randn(1, 16000)
    noisy = c + n * 0.5
    
    optimizer.zero_grad()
    enh, L_out = model(noisy)
    loss = criterion(enh, c[:, :L_out])
    loss.backward()
    
    grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
    print(f"Initial Loss: {loss.item():.4f}, Grad Norm: {grad_norm:.4f}")
    optimizer.step()
    
    optimizer.zero_grad()
    enh, L_out = model(noisy)
    loss2 = criterion(enh, c[:, :L_out])
    print(f"Step 2 Loss: {loss2.item():.4f}")

    # 10. STRONGER TINY OVERFIT
    print("\n--- 10. TINY OVERFIT (STRONGER) ---")
    c_target = c[:, :L_out]
    for step in range(200):
        optimizer.zero_grad()
        enh, _ = model(noisy)
        loss = criterion(enh, c_target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        
    print(f"Step 200 Loss: {loss.item():.4f}")
    # Compute SI-SDR
    from src.enhance.evaluate import si_sdr
    c_np = c_target[0].detach().numpy()
    e_np = enh[0].detach().numpy()
    final_sisdr = si_sdr(c_np, e_np)
    print(f"Overfit Final SI-SDR: {final_sisdr:.2f} dB")
    if loss.item() < 10.0 and final_sisdr > 5.0:
        print("TINY_OVERFIT_WAVEFORM=PASS")
    else:
        print("TINY_OVERFIT_WAVEFORM=FAIL")

    # 13. LATENCY MEASUREMENT
    print("\n--- 13. LATENCY MEASUREMENT ---")
    model.eval()
    with torch.no_grad():
        x_lat = torch.randn(1, 16000)
        # Warmup
        for _ in range(5): model(x_lat)
        
        times_stft, times_model, times_istft = [], [], []
        
        for _ in range(50):
            t0 = time.perf_counter()
            stft = torch.stft(x_lat, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
            t1 = time.perf_counter()
            
            features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            h_in = torch.zeros(2, 1, 256)
            c_in = torch.zeros(2, 1, 256)
            mr, mi, _, _ = model.core(features, h_in, c_in)
            mask_complex = torch.complex(mr, mi).transpose(1, 2)
            enh_stft = stft * mask_complex
            t2 = time.perf_counter()
            
            _ = causal_istft(enh_stft, 512, 256, model.window)
            t3 = time.perf_counter()
            
            times_stft.append(t1 - t0)
            times_model.append(t2 - t1)
            times_istft.append(t3 - t2)
            
        print(f"STFT_MS={np.mean(times_stft)*1000 / 61:.4f}")
        print(f"MODEL_MS={np.mean(times_model)*1000 / 61:.4f}")
        print(f"ISTFT_MS={np.mean(times_istft)*1000 / 61:.4f}")
        total = (np.mean(times_stft) + np.mean(times_model) + np.mean(times_istft))*1000 / 61
        print(f"TOTAL_PIPELINE_MS={total:.4f}")

if __name__ == "__main__":
    main()
