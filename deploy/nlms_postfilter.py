import numpy as np
import sys
import os
import torch
import pandas as pd
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset, MixerConfig
from src.enhance.complex_crn import ComplexCRN_Wrapper
from src.enhance.evaluate import si_sdr

class NLMSPostFilter:
    def __init__(self, filter_len=256, mu=0.01, mode='A'):
        self.filter_len = filter_len
        self.mu = mu
        self.mode = mode # 'A' or 'B'
        self.w = np.zeros(filter_len, dtype=np.float32)
        self.x_buf = np.zeros(filter_len, dtype=np.float32)
        
    def step(self, primary, reference):
        self.x_buf[1:] = self.x_buf[:-1]
        self.x_buf[0] = reference
        y_est = np.dot(self.w, self.x_buf)
        error = primary - y_est
        norm = np.dot(self.x_buf, self.x_buf) + 1e-6
        self.w += self.mu * error * self.x_buf / norm
        return error
        
    def process(self, primary_sig, reference_sig):
        out = np.zeros_like(primary_sig)
        for i in range(len(primary_sig)):
            out[i] = self.step(primary_sig[i], reference_sig[i])
        return out

def evaluate_nlms():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = ComplexCRN_Wrapper().to(device)
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        state_dict = torch.load(checkpoint_path, map_location=device)
        new_state_dict = {("core."+k if not k.startswith("core.") else k): v for k,v in state_dict.items()}
        model.load_state_dict(new_state_dict)
    model.eval()
    
    if not os.path.exists("data/manifests/noise_test.csv"): return
    
    config = MixerConfig(
        clean_manifest="data/manifests/clean_test.csv",
        noise_manifest="data/manifests/noise_test.csv",
        epoch_size=50,
        is_val=True,
        snr_levels=[5],
        snr_probs=[1.0]
    )
    ds = AntigravityDataset(config=config)
    nlms = NLMSPostFilter(filter_len=128, mu=0.05, mode='A')
    
    sisdr_base = []
    sisdr_nlms = []
    
    with torch.no_grad():
        for i in tqdm(range(50), desc="NLMS Eval"):
            noisy, clean = ds[i]
            noisy_t = noisy.unsqueeze(0).to(device)
            enhanced = model(noisy_t).squeeze(0).cpu().numpy()
            
            c = clean.numpy()
            n = noisy.numpy()
            
            # Mode A: reference is the estimated noise (noisy - enhanced)
            est_noise = n - enhanced
            nlms_out = nlms.process(enhanced, est_noise)
            
            sisdr_base.append(si_sdr(c, enhanced))
            sisdr_nlms.append(si_sdr(c, nlms_out))
            
    print(f"Base CRN SI-SDR: {np.median(sisdr_base):.2f} dB")
    print(f"CRN + NLMS SI-SDR: {np.median(sisdr_nlms):.2f} dB")

if __name__ == "__main__":
    evaluate_nlms()
