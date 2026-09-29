import os
import torch
import torchaudio
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper

def main():
    input_file = "youtube_test.wav"
    output_file = "youtube_test_enhanced.wav"
    ckpt_path = "runs/sih26052_polar_gpu/checkpoint_25000.pt"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    device = torch.device('cpu')
    model = StatefulPolarLSTM_Wrapper().to(device)
    model.load_state_dict(torch.load(ckpt_path, map_location=device, weights_only=False))
    model.eval()
    
    print(f"Loading audio {input_file}...")
    wav, sr = torchaudio.load(input_file)
    
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
        print("Converted to mono.")
        
    if sr != 16000:
        resampler = torchaudio.transforms.Resample(sr, 16000)
        wav = resampler(wav)
        print(f"Resampled from {sr} to 16000 Hz.")
        
    # Process in chunks if it's very long, or process the whole thing if it's short enough.
    # We will process the first 30 seconds for speed if it's longer than 30s.
    max_len = 16000 * 30 
    if wav.shape[1] > max_len:
        print(f"Audio is {wav.shape[1]/16000:.2f}s long. Trimming to first 30s for fast testing.")
        wav = wav[:, :max_len]
        
    print("Running model inference (Stateful)...")
    with torch.no_grad():
        enh_wav, _, _, _ = model(wav)
        
    print(f"Saving to {output_file}...")
    torchaudio.save(output_file, enh_wav, 16000)
    print("Done!")

if __name__ == "__main__":
    main()
