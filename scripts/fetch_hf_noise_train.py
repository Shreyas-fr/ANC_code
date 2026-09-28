import os
import csv
import soundfile as sf
from datasets import load_dataset
from tqdm import tqdm

def fetch_hf_train():
    print("Loading ESC-50 from Hugging Face for Training...")
    ds = load_dataset("ashraq/esc50", split="train")
    
    # Select stationary / non-stationary noise classes
    noise_classes = [
        'engine', 'train', 'helicopter', 'chainsaw', 'rain', 
        'wind', 'insects', 'sea_waves', 'crickets', 'thunderstorm'
    ]
    
    train_ds = ds.filter(lambda c: c in noise_classes, input_columns=['category'])
    
    out_dir = "data/raw/noise/hf_train"
    os.makedirs(out_dir, exist_ok=True)
    
    train_manifest_path = "data/manifests/noise_train.csv"
    rows = []
    
    print(f"Downloading {len(train_ds)} noise samples for training...")
    for i, item in enumerate(tqdm(train_ds)):
        audio_array = item['audio']['array']
        sr = item['audio']['sampling_rate']
        
        if sr != 16000:
            import librosa
            audio_array = librosa.resample(audio_array, orig_sr=sr, target_sr=16000)
            sr = 16000
            
        file_path = os.path.join(out_dir, f"{item['category']}_{i}.wav")
        sf.write(file_path, audio_array, sr)
        
        duration = len(audio_array) / sr
        rows.append([file_path, "nonstationary", "hf_esc50_train", 16000, f"{duration:.2f}"])
        
    if len(rows) > 0:
        file_exists = os.path.exists(train_manifest_path)
        with open(train_manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["path", "category", "dataset", "sample_rate", "duration"])
            for r in rows:
                writer.writerow(r)
        print(f"Added {len(rows)} noise samples to train set.")

if __name__ == "__main__":
    fetch_hf_train()
