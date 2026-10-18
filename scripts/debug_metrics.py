import os
import torch
import soundfile as sf
import sys
import traceback

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.evaluate import si_sdr, pesq, stoi

def test_metrics():
    clean_path = "runs/sih26052_canonical_validation/clean_audio/0000_clean.wav"
    noisy_path = "runs/sih26052_canonical_validation/noisy_audio/0000_noisy.wav"
    
    clean, sr = sf.read(clean_path)
    noisy, sr2 = sf.read(noisy_path)
    
    print(f"Clean shape: {clean.shape}, dtype: {clean.dtype}, sr: {sr}")
    print(f"Noisy shape: {noisy.shape}, dtype: {noisy.dtype}, sr: {sr2}")
    
    t_clean = torch.tensor(clean, dtype=torch.float32)
    t_noisy = torch.tensor(noisy, dtype=torch.float32)
    
    print(f"t_clean shape: {t_clean.shape}, dtype: {t_clean.dtype}")
    
    print("Testing SI-SDR...")
    try:
        sdr = si_sdr(t_clean, t_noisy)
        print(f"SI-SDR Success: {sdr}")
    except Exception as e:
        print(f"SI-SDR Failed: {e}")
        traceback.print_exc()
        
    print("\nTesting STOI...")
    try:
        st = stoi(t_clean.unsqueeze(0), t_noisy.unsqueeze(0), sr)
        print(f"STOI Success: {st}")
    except Exception as e:
        print(f"STOI Failed: {e}")
        traceback.print_exc()
        
    print("\nTesting PESQ...")
    try:
        pq = pesq(t_clean.unsqueeze(0), t_noisy.unsqueeze(0), sr)
        print(f"PESQ Success: {pq}")
    except Exception as e:
        print(f"PESQ Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_metrics()
