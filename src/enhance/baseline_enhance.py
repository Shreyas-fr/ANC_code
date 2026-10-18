import os
import librosa
import soundfile as sf
import noisereduce as nr
import numpy as np
import scipy.signal

def enhance_audio(input_path, output_path):
    print(f"Loading {input_path}...")
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return
        
    wav, sr = librosa.load(input_path, sr=16000)

    print("Applying Spectral Gating Noise Reduction...")
    # Perform noise reduction
    # We use stationary=False because the noise includes impulsive gunshots and variable engine hum
    reduced_noise = nr.reduce_noise(y=wav, sr=sr, stationary=False, prop_decrease=0.85)

    print("Applying High-Pass filter to suppress tank rumble...")
    # Apply a light high-pass filter to remove remaining low-freq tank rumble
    b, a = scipy.signal.butter(4, 300, btype='highpass', fs=sr)
    cleaned_audio = scipy.signal.filtfilt(b, a, reduced_noise)

    # Normalize audio to prevent clipping
    if np.max(np.abs(cleaned_audio)) > 0:
        cleaned_audio = cleaned_audio / np.max(np.abs(cleaned_audio))

    sf.write(output_path, cleaned_audio, sr)
    print(f"Enhancement complete! Cleaned audio saved to {output_path}")

if __name__ == "__main__":
    enhance_audio("output_tactical.wav", "output_cleaned.wav")
