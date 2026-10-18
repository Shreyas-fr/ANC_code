import os
import csv
from pathlib import Path
import soundfile as sf
from tqdm import tqdm
import random
from collections import defaultdict

def get_duration(file_path):
    try:
        info = sf.info(str(file_path))
        return info.frames / info.samplerate
    except:
        return 0.0

def write_rows(output_csv, kind, rows):
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if kind == "clean":
            writer.writerow(["path", "speaker", "dataset", "sample_rate", "duration"])
        elif kind == "noise":
            writer.writerow(["path", "category", "dataset", "sample_rate", "duration"])
        elif kind == "rir":
            writer.writerow(["path", "dataset", "sample_rate", "duration"])
        for r in rows:
            writer.writerow(r)

def build_manifest(search_dir, output_prefix, kind):
    print(f"Building manifest for {search_dir} (Source-level holdout)...")
    paths = list(Path(search_dir).rglob("*.wav"))
    if not paths:
        print(f"No WAV files found in {search_dir}")
        return
        
    # Group by source
    groups = defaultdict(list)
    for p in paths:
        if kind == "clean":
            # Group by speaker
            speaker = p.parts[5] if len(p.parts) > 5 else "unknown"
            groups[speaker].append(p)
        else:
            # Group by parent folder to avoid splitting clips from the same recording
            groups[str(p.parent)].append(p)
            
    group_keys = list(groups.keys())
    random.shuffle(group_keys)
    
    split_idx_train = int(len(group_keys) * 0.8)
    split_idx_val = int(len(group_keys) * 0.9)
    train_groups = group_keys[:split_idx_train]
    val_groups = group_keys[split_idx_train:split_idx_val]
    test_groups = group_keys[split_idx_val:]
    
    train_paths = []
    for g in train_groups: train_paths.extend(groups[g])
        
    val_paths = []
    for g in val_groups: val_paths.extend(groups[g])
        
    test_paths = []
    for g in test_groups: test_paths.extend(groups[g])
    
    def process_paths(p_list):
        rows = []
        for p in tqdm(p_list, desc="Processing"):
            dur = get_duration(p)
            if dur == 0:
                continue
            path_str = str(p)
            dataset = p.parts[2] if len(p.parts) > 2 else "unknown"
            
            if kind == "clean":
                speaker = p.parts[5] if len(p.parts) > 5 else "unknown"
                rows.append([path_str, speaker, dataset, 16000, f"{dur:.2f}"])
            elif kind == "noise":
                category = p.parts[2] if len(p.parts) > 2 else "unknown"
                rows.append([path_str, category, dataset, 16000, f"{dur:.2f}"])
            elif kind == "rir":
                rows.append([path_str, dataset, 16000, f"{dur:.2f}"])
        return rows
        
    train_rows = process_paths(train_paths)
    val_rows = process_paths(val_paths)
    test_rows = process_paths(test_paths)
    
    write_rows(f"{output_prefix}_train.csv", kind, train_rows)
    write_rows(f"{output_prefix}_val.csv", kind, val_rows)
    write_rows(f"{output_prefix}_test.csv", kind, test_rows)
    print(f"Saved {output_prefix}_train.csv ({len(train_rows)}), _val.csv ({len(val_rows)}), and _test.csv ({len(test_rows)})")

def main():
    manifests_dir = Path("data/manifests")
    manifests_dir.mkdir(parents=True, exist_ok=True)
    
    if Path("data/clean").exists():
        build_manifest("data/clean", str(manifests_dir / "clean"), "clean")
    
    if Path("data/noise").exists():
        build_manifest("data/noise", str(manifests_dir / "noise"), "noise")
        
    if Path("data/rir").exists():
        build_manifest("data/rir", str(manifests_dir / "rir"), "rir")

if __name__ == "__main__":
    main()
