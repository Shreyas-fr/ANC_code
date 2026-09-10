import sys
import os
import torch
import numpy as np
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.complex_crn import ComplexCRN
from src.enhance.evaluate import pesq, stoi, si_sdr

def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = ComplexCRN().to(device)
    
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    else:
        print("Warning: best.pt not found, evaluating untrained model.")
        
    model.eval()

    val_dataset = AntigravityDataset(
        clean_manifest="data/manifests/clean_val.csv",
        noise_manifest="data/manifests/noise_val.csv",
        rir_manifest="data/manifests/rir_val.csv",
        epoch_size=200,  # Evaluate on a larger subset to populate buckets
        is_val=True,
        return_metadata=True
    )

    # Metrics structured as: metrics['snr'][value]['pesq'] = []
    # Metrics structured as: metrics['cat'][category]['pesq'] = []
    snr_buckets = defaultdict(lambda: {'pesq_n': [], 'pesq': [], 'stoi_n': [], 'stoi': [], 'sisdr_n': [], 'sisdr': []})
    cat_buckets = defaultdict(lambda: {'pesq_n': [], 'pesq': [], 'stoi_n': [], 'stoi': [], 'sisdr_n': [], 'sisdr': []})
    
    print("Evaluating 200 samples from validation set for granular analysis...")
    with torch.no_grad():
        for i in range(200):
            noisy, clean, meta = val_dataset[i]
            snr = meta['snr']
            cat = meta['category']
            
            noise_only = noisy - clean
            if torch.max(torch.abs(noise_only)) < 1e-4:
                continue

            noisy_t = noisy.unsqueeze(0).to(device)
            enhanced = model(noisy_t).squeeze(0).cpu()
            
            clean_np = clean.numpy()
            noisy_np = noisy.numpy()
            enhanced_np = enhanced.numpy()
            
            sisdr_n = si_sdr(clean_np, noisy_np)
            sisdr_e = si_sdr(clean_np, enhanced_np)
            
            if sisdr_n > 40:
                continue
                
            clean_norm = clean_np / (np.max(np.abs(clean_np)) + 1e-8)
            noisy_norm = noisy_np / (np.max(np.abs(noisy_np)) + 1e-8)
            enhanced_norm = enhanced_np / (np.max(np.abs(enhanced_np)) + 1e-8)

            s_n = stoi(clean_norm, noisy_norm, 16000, extended=False)
            s_e = stoi(clean_norm, enhanced_norm, 16000, extended=False)
            
            p_n, p_e = 0.0, 0.0
            try:
                p_n = pesq(16000, clean_norm, noisy_norm, 'wb')
                p_e = pesq(16000, clean_norm, enhanced_norm, 'wb')
            except:
                pass
                
            # Append to buckets
            for bucket in (snr_buckets[snr], cat_buckets[cat]):
                bucket['sisdr_n'].append(sisdr_n)
                bucket['sisdr'].append(sisdr_e)
                bucket['stoi_n'].append(s_n)
                bucket['stoi'].append(s_e)
                if p_n > 0: bucket['pesq_n'].append(p_n)
                if p_e > 0: bucket['pesq'].append(p_e)
                
            if (i+1) % 50 == 0:
                print(f"Processed {i+1}/200...")

    # Print Report
    print("\n================== SNR BREAKDOWN ==================")
    print(f"{'SNR (dB)':<10} | {'PESQ (N -> E)':<18} | {'STOI (N -> E)':<18} | {'SI-SDR (N -> E) [Median]':<25}")
    print("-" * 80)
    for snr in sorted(snr_buckets.keys()):
        b = snr_buckets[snr]
        if not b['sisdr']: continue
        print(f"{snr:<10} | {np.mean(b['pesq_n']):.2f} -> {np.mean(b['pesq']):.2f}  | {np.mean(b['stoi_n']):.2f} -> {np.mean(b['stoi']):.2f}  | {np.median(b['sisdr_n']):.1f} -> {np.median(b['sisdr']):.1f}")

    print("\n================ CATEGORY BREAKDOWN ===============")
    print(f"{'Category':<15} | {'PESQ (N -> E)':<18} | {'STOI (N -> E)':<18} | {'SI-SDR (N -> E) [Median]':<25}")
    print("-" * 85)
    for cat in sorted(cat_buckets.keys()):
        b = cat_buckets[cat]
        if not b['sisdr']: continue
        print(f"{cat:<15} | {np.mean(b['pesq_n']):.2f} -> {np.mean(b['pesq']):.2f}  | {np.mean(b['stoi_n']):.2f} -> {np.mean(b['stoi']):.2f}  | {np.median(b['sisdr_n']):.1f} -> {np.median(b['sisdr']):.1f}")
    print("===================================================\n")

if __name__ == "__main__":
    main()
