import os
import csv
import soundfile as sf
import numpy as np
from datasets import load_dataset
from tqdm import tqdm

def fetch_impulsive_data():
    print("Loading ESC-50 from Hugging Face...")
    ds = load_dataset("ashraq/esc50", split="train")
    
    # Check classes
    unique_classes = set(ds['category'])
    print("Available classes in ESC-50:", unique_classes)
    
    # Select impulsive-like classes
    impulsive_classes = [
        'fireworks', 'crackling_fire', 'glass_breaking', 
        'door_wood_knock', 'mouse_click', 'keyboard_typing'
    ] # Add any other impulsive ones we find
    
    # Filter dataset
    impulsive_ds = ds.filter(lambda x: x['category'] in impulsive_classes)
    
    out_dir = "data/raw/noise/impulsive/hf_esc50"
    os.makedirs(out_dir, exist_ok=True)
    
    test_manifest_path = "data/manifests/noise_test.csv"
    
    # We will append these files directly to the test manifest so they are forced into the test set
    rows = []
    
    print(f"Downloading {len(impulsive_ds)} impulsive samples...")
    for i, item in enumerate(tqdm(impulsive_ds)):
        audio_array = item['audio']['array']
        sr = item['audio']['sampling_rate']
        
        # Resample to 16000 if needed (ESC50 is usually 44.1k or 16k)
        if sr != 16000:
            import librosa
            audio_array = librosa.resample(audio_array, orig_sr=sr, target_sr=16000)
            sr = 16000
            
        file_path = os.path.join(out_dir, f"{item['category']}_{i}.wav")
        sf.write(file_path, audio_array, sr)
        
        duration = len(audio_array) / sr
        rows.append([file_path, "impulsive", "hf_esc50", 16000, f"{duration:.2f}"])
        
    if len(rows) > 0:
        # Append to noise_test.csv
        file_exists = os.path.exists(test_manifest_path)
        with open(test_manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["path", "category", "dataset", "sample_rate", "duration"])
            for r in rows:
                writer.writerow(r)
        print(f"Added {len(rows)} impulsive samples to test set.")
    else:
        print("No impulsive samples found.")

if __name__ == "__main__":
    fetch_impulsive_data()
