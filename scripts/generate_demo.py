import torch
import soundfile as sf
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper

m = StatefulPolarLSTM_Wrapper()
m.load_state_dict(torch.load("runs/sih26052_final_demo/selected_checkpoint.pt", map_location="cpu"))
m.eval()

val_dir = "runs/sih26052_canonical_validation"
clean_path = os.path.join(val_dir, "clean_audio", "0000_clean.wav")
noisy_path = os.path.join(val_dir, "noisy_audio", "0000_noisy.wav")

clean, _ = sf.read(clean_path)
noisy, sr = sf.read(noisy_path)

n_t = torch.tensor(noisy, dtype=torch.float32).unsqueeze(0)
pad_len = (256 - (n_t.shape[1] % 256)) % 256
if pad_len != 0:
    n_t = torch.nn.functional.pad(n_t, (0, pad_len))

with torch.no_grad():
    out, _, _, _ = m(n_t)
    
out = out.squeeze(0).numpy()[:len(noisy)]

sf.write("runs/sih26052_final_demo/clean_reference.wav", clean, sr)
sf.write("runs/sih26052_final_demo/noisy_input.wav", noisy, sr)
sf.write("runs/sih26052_final_demo/enhanced_output.wav", out, sr)
print("Demonstration audio saved.")
