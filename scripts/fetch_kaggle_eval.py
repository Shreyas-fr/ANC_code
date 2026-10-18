import os
import csv
import soundfile as sf
from datasets import load_dataset
from tqdm import tqdm

def fetch_kaggle():
    print("Loading UrbanSound8K (Kaggle Dataset) from Hugging Face mirror...")
    try:
        ds = load_dataset("danavery/urbansound8K", split="train")
    except Exception as e:
        print("Failed loading danavery/urbansound8K, trying MahiA/UrbanSound8K...")
        ds = load_dataset("MahiA/UrbanSound8K", split="train")
        
    out_dir = "data/raw/noise/kaggle_eval"
    os.makedirs(out_dir, exist_ok=True)
    
    test_manifest_path = "data/manifests/noise_test.csv"
    rows = []
    
    # We will grab just 100 random clips so we don't take forever
    print("Extracting Kaggle evaluation clips...")
    for i, item in enumerate(tqdm(ds)):
        if i >= 150: break
        
        if 'audio' not in item or item['audio'] is None:
            continue
            
        audio_array = item['audio']['array']
        sr = item['audio']['sampling_rate']
        category = str(item.get('class', 'kaggle_noise'))
        
        if sr != 16000:
            import librosa
            audio_array = librosa.resample(audio_array, orig_sr=sr, target_sr=16000)
            sr = 16000
            
        file_path = os.path.join(out_dir, f"kaggle_{category}_{i}.wav")
        sf.write(file_path, audio_array, sr)
        
        duration = len(audio_array) / sr
        rows.append([file_path, "nonstationary", "kaggle_urbansound", 16000, f"{duration:.2f}"])
        
    if len(rows) > 0:
        file_exists = os.path.exists(test_manifest_path)
        with open(test_manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["path", "category", "dataset", "sample_rate", "duration"])
            for r in rows:
                writer.writerow(r)
        print(f"Added {len(rows)} Kaggle samples to test set manifest.")

if __name__ == "__main__":
    fetch_kaggle()
