import os
import csv
from pathlib import Path
import soundfile as sf

def append_audioset():
    search_dir = Path("data/raw/noise")
    test_manifest_path = "data/manifests/noise_test.csv"
    
    existing = set()
    if os.path.exists(test_manifest_path):
        with open(test_manifest_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row["path"])
                
    paths = list(search_dir.rglob("*.wav"))
    rows = []
    
    for p in paths:
        path_str = str(p)
        if path_str in existing:
            continue
            
        try:
            info = sf.info(path_str)
            dur = info.frames / info.samplerate
            if dur == 0: continue
            
            # Subfolders dictate whether it's impulsive or stationary
            category = "nonstationary"
            if "impulsive" in path_str: category = "impulsive"
            elif "stationary" in path_str: category = "stationary"
            
            rows.append([path_str, category, "audioset_eval", info.samplerate, f"{dur:.2f}"])
        except:
            continue
            
    if rows:
        file_exists = os.path.exists(test_manifest_path)
        with open(test_manifest_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["path", "category", "dataset", "sample_rate", "duration"])
            for r in rows:
                writer.writerow(r)
        print(f"Appended {len(rows)} AudioSet clips to {test_manifest_path}")
    else:
        print("No new AudioSet clips to append.")

if __name__ == "__main__":
    append_audioset()
