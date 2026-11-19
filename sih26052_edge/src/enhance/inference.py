import torch
import torchaudio
import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.enhance.complex_crn import ComplexCRN

def run_inference(model_path, input_path, output_path):
    print(f"Loading DTLN model from {model_path}...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    model = ComplexCRN().to(device)
    try:
        model.load_state_dict(torch.load(model_path, map_location=device))
    except Exception as e:
        print(f"Failed to load model checkpoint: {e}")
        return
        
    model.eval()
    
    print(f"Processing {input_path}...")
    wav, sr = torchaudio.load(input_path)
    if sr != 16000:
        print(f"Warning: Expected 16kHz audio, got {sr}Hz.")
        
    wav = wav.to(device)
    
    with torch.no_grad():
        enhanced = model(wav)
        
    # Normalize output to prevent clipping
    max_val = enhanced.abs().max()
    if max_val > 1.0:
        enhanced = enhanced / max_val
        
    torchaudio.save(output_path, enhanced.cpu(), sr)
    print(f"Enhanced audio saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, help="Path to best.pt")
    parser.add_argument("--input", type=str, required=True, help="Path to noisy wav")
    parser.add_argument("--output", type=str, required=True, help="Path to output enhanced wav")
    args = parser.parse_args()
    
    run_inference(args.model, args.input, args.output)
