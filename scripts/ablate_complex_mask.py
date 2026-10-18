import os
import torch
import torch.nn as nn
import numpy as np
import random
import time
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_lstm import causal_istft
from src.enhance.losses import EnhancementLoss
from src.enhance.evaluate import si_sdr, stoi, pesq

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

class MaskVariantModel(nn.Module):
    def __init__(self, variant):
        super().__init__()
        self.variant = variant
        self.n_fft = 512
        self.hop_length = 256
        self.register_buffer("window", torch.hann_window(self.n_fft))
        
        self.lstm = nn.LSTM(input_size=514, hidden_size=256, num_layers=2, batch_first=True)
        self.fc_real = nn.Linear(256, 257)
        self.fc_imag = nn.Linear(256, 257)
        
        if variant == 'D':
            # Initialize for Identity Stable
            nn.init.zeros_(self.fc_real.weight)
            nn.init.zeros_(self.fc_real.bias) # sigmoid(0)*2 = 1.0
            nn.init.zeros_(self.fc_imag.weight)
            nn.init.zeros_(self.fc_imag.bias) # tanh(0)*pi = 0.0

    def forward(self, x, h_in=None, c_in=None):
        B, T = x.shape
        stft_t = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop_length, window=self.window, return_complex=True, center=False)
        features = torch.cat([stft_t.transpose(1, 2).real, stft_t.transpose(1, 2).imag], dim=-1)
        
        if h_in is None:
            h_in = torch.zeros(2, B, 256).to(x.device)
            c_in = torch.zeros(2, B, 256).to(x.device)
            
        out, _ = self.lstm(features, (h_in, c_in))
        
        raw_real = self.fc_real(out)
        raw_imag = self.fc_imag(out)
        
        if self.variant == 'A':
            mr = raw_real
            mi = raw_imag
        elif self.variant == 'B':
            mr = torch.tanh(raw_real)
            mi = torch.tanh(raw_imag)
        elif self.variant in ['C', 'D']:
            # Magnitude bounded [0, 2], Phase bounded [-pi, pi]
            mag = torch.sigmoid(raw_real) * 2.0
            phase = torch.tanh(raw_imag) * torch.pi
            mr = mag * torch.cos(phase)
            mi = mag * torch.sin(phase)
            
        mask_complex = torch.complex(mr, mi).transpose(1, 2)
        enh_stft = stft_t * mask_complex
        enh_wav = causal_istft(enh_stft, self.n_fft, self.hop_length, self.window)
        return enh_wav, mr, mi

def get_stats(tensor):
    return tensor.mean().item(), tensor.std().item(), tensor.min().item(), tensor.max().item()

def run_ablation():
    device = torch.device('cpu')
    variants = ['A', 'B', 'C', 'D']
    
    # Generate exactly ONE controlled batch to test learning dynamics
    set_seed(42)
    B, T = 4, 16000
    clean = torch.randn(B, T)
    noise = torch.randn(B, T)
    noisy = clean + noise * 0.5
    
    # Calculate aligned target
    n_fft = 512
    hop_length = 256
    T_frames = (T - n_fft) // hop_length + 1
    expected_len = (T_frames - 1) * hop_length + n_fft
    clean_target = clean[:, :expected_len]
    noisy_aligned = noisy[:, :expected_len]
    
    results = {}
    
    for v in variants:
        print(f"\\n=== EVALUATING VARIANT {v} ===")
        set_seed(123)
        model = MaskVariantModel(v).to(device)
        
        param_count = sum(p.numel() for p in model.parameters())
        print(f"Parameters: {param_count}")
        
        # Identity verify
        with torch.no_grad():
            y_init, mr_init, mi_init = model(noisy)
            if v == 'D':
                mag_init = torch.sqrt(mr_init**2 + mi_init**2)
                phase_init = torch.atan2(mi_init, mr_init)
                print(f"Init Mag (D): {mag_init.mean().item():.4f}")
                print(f"Init Phase (D): {phase_init.mean().item():.4f}")
                
        # Train loop
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        criterion = EnhancementLoss()
        
        for step in range(1, 101):
            optimizer.zero_grad()
            enh, mr, mi = model(noisy)
            loss = criterion(enh, clean_target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            
        print(f"Step 100 Loss: {loss.item():.4f}")
        
        # Validation / Stats at step 100
        with torch.no_grad():
            enh, mr, mi = model(noisy)
            
            c_np = clean_target[0].numpy()
            n_np = noisy_aligned[0].numpy()
            e_np = enh[0].numpy()
            
            in_sdr = si_sdr(c_np, n_np)
            out_sdr = si_sdr(c_np, e_np)
            
            rms_c = torch.sqrt(torch.mean(clean_target**2)).item()
            rms_i = torch.sqrt(torch.mean(noisy_aligned**2)).item()
            rms_o = torch.sqrt(torch.mean(enh**2)).item()
            
            corr_in = np.corrcoef(n_np, c_np)[0, 1]
            corr_out = np.corrcoef(e_np, c_np)[0, 1]
            
            mag = torch.sqrt(mr**2 + mi**2)
            phase = torch.atan2(mi, mr)
            
            r_m, r_s, r_min, r_max = get_stats(mr)
            i_m, i_s, i_min, i_max = get_stats(mi)
            m_m, m_s, m_min, m_max = get_stats(mag)
            p_m, p_s, p_min, p_max = get_stats(phase)
            
            frac_1 = (mag > 1.0).float().mean().item()
            frac_2 = (mag > 2.0).float().mean().item()
            frac_01 = (mag < 0.1).float().mean().item()
            
            print(f"Out RMS / In RMS: {rms_o / rms_i:.4f}")
            print(f"Corr(in, c): {corr_in:.4f} | Corr(out, c): {corr_out:.4f}")
            print(f"In SI-SDR: {in_sdr:.2f} | Out SI-SDR: {out_sdr:.2f}")
            
            print(f"Mask Real: {r_m:.4f}±{r_s:.4f} [{r_min:.4f}, {r_max:.4f}]")
            print(f"Mask Imag: {i_m:.4f}±{i_s:.4f} [{i_min:.4f}, {i_max:.4f}]")
            print(f"Mask Mag: {m_m:.4f}±{m_s:.4f} [{m_min:.4f}, {m_max:.4f}]")
            print(f"Mask Phase: {p_m:.4f}±{p_s:.4f}")
            
            results[v] = {
                'loss': loss.item(),
                'in_sdr': in_sdr,
                'out_sdr': out_sdr,
                'corr': corr_out,
                'rms_ratio': rms_o / rms_i,
                'frac_1': frac_1,
                'phase_std': p_s
            }
            
    torch.save(results, "runs/mask_ablation_results.pt")

if __name__ == "__main__":
    run_ablation()
