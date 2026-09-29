import os
import csv
import hashlib
from pathlib import Path
import soundfile as sf
from collections import defaultdict
import random

def compute_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_duration(file_path):
    try:
        info = sf.info(str(file_path))
        return info.frames / info.samplerate
    except:
        return 0.0

def build_manifests():
    random.seed(42)
    raw_dir = Path("data/raw")
    manifests_dir = Path("data/clean_manifests")
    manifests_dir.mkdir(exist_ok=True)
    
    # We will build clean, noise, and rir inventories
    inventories = {
        "clean": [],
        "noise": [],
        "rir": []
    }
    
    # 1. Gather all files and compute hashes
    all_files = list(raw_dir.rglob("*.wav")) + list(raw_dir.rglob("*.flac"))
    print(f"Found {len(all_files)} total audio files.")
    
    unique_files = {}
    for p in all_files:
        path_str = str(p)
        h = compute_sha256(path_str)
        if h in unique_files:
            continue # Skip exact duplicates
        unique_files[h] = p
        
    print(f"Found {len(unique_files)} unique audio files by SHA-256.")
    
    # 2. Categorize and determine source IDs
    for h, p in unique_files.items():
        dur = get_duration(p)
        if dur <= 0: continue
        
        path_str = str(p)
        path_lower = path_str.lower()
        
        # Default fields
        role = "unknown"
        source_id = h # fallback
        dataset = "unknown"
        category = "unknown"
        
        if "librispeech" in path_lower:
            role = "clean"
            dataset = "librispeech"
            # In LibriSpeech, filename is speaker-chapter-utterance.flac
            # Safest is to just split the filename
            source_id = p.stem.split("-")[0]
        elif "musan" in path_str:
            role = "noise"
            dataset = "musan"
            source_id = p.parent.name
            category = "nonstationary"
        elif "demand" in path_str.lower():
            role = "noise"
            dataset = "demand"
            source_id = p.parent.name
            category = "stationary"
        elif "rir_" in path_str:
            role = "rir"
            dataset = "sim_rir"
            source_id = p.parent.name
        elif "hf_train" in path_str or "hf_esc50" in path_str:
            role = "noise"
            dataset = "esc50"
            source_id = h # We lost the fold info, so we use hash. Hash-based splitting prevents leakage.
            category = "impulsive" if "impulsive" in path_str else "nonstationary"
        elif "kaggle_eval" in path_str:
            role = "noise"
            dataset = "urbansound8k"
            source_id = h
            category = "nonstationary"
        else:
            continue # ignore unknown
            
        record = {
            "file_path": path_str,
            "file_hash": h,
            "source_dataset": dataset,
            "source_recording_id": source_id,
            "source_class": category,
            "role": role,
            "sample_rate": 16000,
            "duration": f"{dur:.2f}"
        }
        inventories[role].append(record)
        
    # 3. Source-level splitting
    splits = {"clean": {}, "noise": {}, "rir": {}}
    
    for role, records in inventories.items():
        groups = defaultdict(list)
        for r in records:
            groups[r["source_recording_id"]].append(r)
            
        group_keys = sorted(list(groups.keys()))
        random.shuffle(group_keys)
        
        # Ratios: 80% train, 10% val, 10% test
        n_train = int(len(group_keys) * 0.8)
        n_val = int(len(group_keys) * 0.1)
        
        train_keys = group_keys[:n_train]
        val_keys = group_keys[n_train:n_train+n_val]
        test_keys = group_keys[n_train+n_val:]
        
        train_records = []
        for k in train_keys:
            for r in groups[k]: r["split"] = "train"; train_records.append(r)
        val_records = []
        for k in val_keys:
            for r in groups[k]: r["split"] = "val"; val_records.append(r)
        test_records = []
        for k in test_keys:
            for r in groups[k]: r["split"] = "test"; test_records.append(r)
            
        splits[role]["train"] = train_records
        splits[role]["val"] = val_records
        splits[role]["test"] = test_records
        
    # 4. Write CSVs
    fieldnames = ["file_path", "file_hash", "source_dataset", "source_recording_id", "source_class", "role", "split", "sample_rate", "duration"]
    
    for role in ["clean", "noise", "rir"]:
        for split in ["train", "val", "test"]:
            out_path = manifests_dir / f"{role}_{split}.csv"
            with open(out_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in splits[role][split]:
                    writer.writerow(r)
            print(f"Wrote {out_path} ({len(splits[role][split])} records)")

if __name__ == "__main__":
    build_manifests()
