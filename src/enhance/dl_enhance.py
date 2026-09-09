import os
import torch
import soundfile as sf
import numpy as np
from denoiser import pretrained
from denoiser.dsp import convert_audio

def enhance_audio(input_path, output_path):
    print(f"Loading {input_path}...")
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    # Load the pretrained Facebook Denoiser model (a highly capable CRN-style model)
    print("Loading pretrained Facebook Denoiser model...")
    model = pretrained.dns64().cpu()
    model.eval()

    # Load audio
    wav_np, sr = sf.read(input_path)
    if len(wav_np.shape) == 1:
        wav_np = wav_np[None, :]
    else:
        wav_np = wav_np.T
        
    wav = torch.from_numpy(wav_np).float()
    
    # Convert audio to model's expected sample rate and channels
    print("Applying Deep Learning speech enhancement...")
    wav = convert_audio(wav, sr, model.sample_rate, model.chin)
    
    with torch.no_grad():
        # The model expects a batch dimension
        enhanced = model(wav[None])[0]

    enhanced_np = enhanced.squeeze().numpy()

    # Normalize audio slightly to prevent clipping
    max_val = np.abs(enhanced_np).max()
    if max_val > 0:
        enhanced_np = enhanced_np / max_val * 0.9

    print("Saving output...")
    # Save the enhanced output
    sf.write(output_path, enhanced_np, model.sample_rate)
    print(f"Deep Learning Enhancement complete! Cleaned audio saved to {output_path}")

if __name__ == "__main__":
    enhance_audio("output_tactical.wav", "output_cleaned_dl.wav")
