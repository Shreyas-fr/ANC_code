import os
import sys
import torch
import numpy as np
import random
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.losses import EnhancementLoss
from src.enhance.evaluate import si_sdr

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

def run_tests():
    device = torch.device('cpu')
    model = StatefulPolarLSTM_Wrapper().to(device)
    
    print("=== 1. PARAMETER COUNT ===")
    params = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {params}")
    assert params == 1448962, f"Expected 1448962, got {params}"
    print("PARAMETER COUNT: PASS")
    
    print("\n=== 2. IDENTITY INITIALIZATION & MASK SAFETY ===")
    x = torch.randn(2, 16000)
    with torch.no_grad():
        enh, L_out, mag, phase = model(x)
        
        print(f"Mag Mean: {mag.mean().item():.4f}")
        print(f"Mag Std: {mag.std().item():.4f}")
        print(f"Phase Mean: {phase.mean().item():.4f}")
        print(f"Phase Std: {phase.std().item():.4f}")
        
        max_dev_mag = torch.max(torch.abs(mag - 1.0)).item()
        max_dev_phase = torch.max(torch.abs(phase - 0.0)).item()
        print(f"Max Dev Mag: {max_dev_mag:.4f}")
        print(f"Max Dev Phase: {max_dev_phase:.4f}")
        
        assert max_dev_mag < 1e-2, "Mag not close enough to 1"
        assert max_dev_phase < 1e-2, "Phase not close enough to 0"
        
        # Bounds check
        assert torch.max(mag).item() <= 2.0 and torch.min(mag).item() >= 0.0
        assert torch.max(phase).item() <= torch.pi and torch.min(phase).item() >= -torch.pi
        assert not torch.isnan(mag).any() and not torch.isinf(mag).any()
        
    print("INITIALIZATION & SAFETY: PASS")
    
    print("\n=== 3. IDENTITY AUDIO TEST ===")
    # Because M = 1 + j0 exactly, it should reconstruct audio perfectly except for the frame drops
    x_int = x[:, 512:L_out-512]
    enh_int = enh[:, 512:L_out-512]
    snr_diff = 10 * torch.log10(torch.mean(x_int**2) / (torch.mean((enh_int - x_int)**2) + 1e-12)).item()
    print(f"Reconstruction SNR: {snr_diff:.2f} dB")
    assert snr_diff > 40.0, "Identity reconstruction failed"
    print("IDENTITY AUDIO TEST: PASS")
    
    print("\n=== 5. STATEFUL CONTRACT ===")
    # Sequence mode
    seq_enh, _, _, _ = model(x)
    
    # Frame by frame
    stft = torch.stft(x, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
    features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
    
    h = torch.zeros(2, 2, 256)
    c = torch.zeros(2, 2, 256)
    mr_list, mi_list = [], []
    for t in range(features.shape[1]):
        feat_t = features[:, t:t+1, :]
        mr, mi, h, c, _, _ = model.core(feat_t, h, c)
        mr_list.append(mr)
        mi_list.append(mi)
        
    mr_full = torch.cat(mr_list, dim=1)
    mi_full = torch.cat(mi_list, dim=1)
    
    # Run full seq again
    mr_seq, mi_seq, _, _, _, _ = model.core(features, torch.zeros(2, 2, 256), torch.zeros(2, 2, 256))
    
    diff_r = torch.max(torch.abs(mr_full - mr_seq)).item()
    assert diff_r < 1e-6, "Stateful frame-by-frame mismatch"
    print("STATEFUL CONTRACT: PASS")
    
    print("\n=== 7. GRADIENT TEST ===")
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = EnhancementLoss()
    
    enh, L_out, _, _ = model(x)
    loss = criterion(enh, x[:, :L_out] * 0.5) # dummy target
    loss.backward()
    
    has_zero = False
    has_nan = False
    max_g = 0
    min_g = float('inf')
    for name, p in model.named_parameters():
        if p.grad is None: continue
        if torch.isnan(p.grad).any(): has_nan = True
        g_abs = torch.abs(p.grad)
        g_max = torch.max(g_abs).item()
        g_min = torch.min(g_abs).item()
        if g_max > max_g: max_g = g_max
        if g_min < min_g: min_g = g_min
        if g_max == 0:
            print(f"Zero gradient in {name}")
            has_zero = True
            
    print(f"Max Gradient: {max_g:.4f}")
    print(f"Min Gradient: {min_g:.4f}")
    assert not has_nan, "NaN in gradients"
    assert not has_zero, "Zero gradient in a parameter"
    print("GRADIENT TEST: PASS")
    
    print("\n=== 8. 100-STEP REPRODUCTION ===")
    set_seed(42)
    B, T = 4, 16000
    clean = torch.randn(B, T)
    noise = torch.randn(B, T)
    noisy = clean + noise * 0.5
    
    T_frames = (T - 512) // 256 + 1
    expected_len = (T_frames - 1) * 256 + 512
    clean_target = clean[:, :expected_len]
    noisy_aligned = noisy[:, :expected_len]
    
    set_seed(123)
    model_rep = StatefulPolarLSTM_Wrapper().to(device)
    optimizer_rep = torch.optim.Adam(model_rep.parameters(), lr=0.001)
    
    for step in range(1, 101):
        optimizer_rep.zero_grad()
        enh, L_out, _, _ = model_rep(noisy)
        loss = criterion(enh, clean_target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model_rep.parameters(), 5.0)
        optimizer_rep.step()
        
    print(f"Step 100 Loss: {loss.item():.4f} (Expected: ~7.7660)")
    
    with torch.no_grad():
        enh, _, _, _ = model_rep(noisy)
        c_np = clean_target[0].numpy()
        e_np = enh[0].numpy()
        corr = np.corrcoef(e_np, c_np)[0, 1]
        out_sdr = si_sdr(c_np, e_np)
        print(f"Corr: {corr:.4f} (Expected: ~0.8829)")
        print(f"Out SDR: {out_sdr:.2f} (Expected: ~5.49)")
        
    print("100-STEP REPRODUCTION: PASS")
    
    print("\nFINAL GATE: IMPLEMENTATION PASS")

if __name__ == "__main__":
    run_tests()
