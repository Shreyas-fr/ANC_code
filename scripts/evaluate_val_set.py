import sys
import os
import torch
import torchaudio
import numpy as np
import soundfile as sf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.complex_crn import ComplexCRN
from src.enhance.evaluate import evaluate_metrics, pesq, stoi, si_sdr

def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = ComplexCRN().to(device)
    model.load_state_dict(torch.load("checkpoints/dtln/best.pt", map_location=device))
    model.eval()

    val_dataset = AntigravityDataset(
        clean_manifest="data/manifests/clean_val.csv",
        noise_manifest="data/manifests/noise_val.csv",
        rir_manifest="data/manifests/rir_val.csv",
        epoch_size=50,
        is_val=True
    )

    metrics = {'pesq': [], 'stoi': [], 'sisdr': [], 'pesq_n': [], 'stoi_n': [], 'sisdr_n': []}
    
    os.makedirs("data/eval_samples", exist_ok=True)

    print("Evaluating 50 samples from validation set...")
    with torch.no_grad():
        for i in range(50):
            noisy, clean = val_dataset[i]
            
            # Skip if noise was perfectly silent (infinite SNR artifact)
            noise_only = noisy - clean
            if torch.max(torch.abs(noise_only)) < 1e-4:
                continue

            noisy_t = noisy.unsqueeze(0).to(device)
            enhanced = model(noisy_t).squeeze(0).cpu()
            
            # Print shapes to guarantee alignment
            if i < 3:
                print(f"Sample {i} Shapes -> Clean: {clean.shape}, Noisy: {noisy.shape}, Enhanced: {enhanced.shape}")
            
            clean_np = clean.numpy()
            noisy_np = noisy.numpy()
            enhanced_np = enhanced.numpy()
            
            # Compute raw SI-SDR
            sisdr_n = si_sdr(clean_np, noisy_np)
            sisdr_e = si_sdr(clean_np, enhanced_np)
            
            # Filter out any lingering >40dB SI-SDR anomalies just in case
            if sisdr_n > 40:
                continue
                
            metrics['sisdr_n'].append(sisdr_n)
            metrics['sisdr'].append(sisdr_e)

            # Max normalization purely for PESQ/STOI perception
            clean_norm = clean_np / (np.max(np.abs(clean_np)) + 1e-8)
            noisy_norm = noisy_np / (np.max(np.abs(noisy_np)) + 1e-8)
            enhanced_norm = enhanced_np / (np.max(np.abs(enhanced_np)) + 1e-8)

            metrics['stoi_n'].append(stoi(clean_norm, noisy_norm, 16000, extended=False))
            metrics['stoi'].append(stoi(clean_norm, enhanced_norm, 16000, extended=False))
            
            try:
                metrics['pesq_n'].append(pesq(16000, clean_norm, noisy_norm, 'wb'))
                metrics['pesq'].append(pesq(16000, clean_norm, enhanced_norm, 'wb'))
            except:
                pass

    print("\n================ FINAL OBJECTIVE METRICS ================")
    print(f"STOI   | Noisy: {np.mean(metrics['stoi_n']):.4f} -> Enhanced: {np.mean(metrics['stoi']):.4f}")
    print(f"PESQ   | Noisy: {np.mean(metrics['pesq_n']):.4f} -> Enhanced: {np.mean(metrics['pesq']):.4f}")
    print(f"SI-SDR | Noisy: {np.mean(metrics['sisdr_n']):.2f} dB -> Enhanced: {np.mean(metrics['sisdr']):.2f} dB")
    print(f"SI-SDR Median | Noisy: {np.median(metrics['sisdr_n']):.2f} dB -> Enhanced: {np.median(metrics['sisdr']):.2f} dB")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
