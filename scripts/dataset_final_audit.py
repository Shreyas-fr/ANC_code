import os
import csv
import sys
import numpy as np
from pathlib import Path

def load_manifest(path):
    if not os.path.exists(path): return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))

def main():
    splits = ["train", "val", "test"]
    clean_manifests = {s: load_manifest(f"data/clean_manifests/clean_{s}.csv") for s in splits}
    noise_manifests = {s: load_manifest(f"data/clean_manifests/noise_{s}.csv") for s in splits}
    gold_manifest = load_manifest("data/clean_manifests/SIH_GOLD_TEST_manifest.csv")
    
    # 2. Dataset Counts
    print("=== DATASET COUNTS ===")
    print(f"Clean Train: {len(clean_manifests['train'])}")
    print(f"Clean Val: {len(clean_manifests['val'])}")
    print(f"Clean Test: {len(clean_manifests['test'])}")
    print(f"Noise Train: {len(noise_manifests['train'])}")
    print(f"Noise Val: {len(noise_manifests['val'])}")
    print(f"Noise Test: {len(noise_manifests['test'])}")
    print(f"Gold Test Mixtures: {len(gold_manifest)}")
    
    # Impulsive and Nonstationary counts
    imp_test = [r for r in noise_manifests["test"] if r["source_class"] == "impulsive"]
    nonstat_test = [r for r in noise_manifests["test"] if r["source_class"] == "nonstationary"]
    print(f"Impulsive Noise (Test): {len(imp_test)}")
    print(f"Nonstationary Noise (Test): {len(nonstat_test)}")
    
    # Gold test impulsive / nonstationary counts
    gold_imp = [r for r in gold_manifest if r["parent_noise_class"] == "impulsive"]
    gold_nonstat = [r for r in gold_manifest if r["parent_noise_class"] == "nonstationary"]
    print(f"Gold Test Impulsive Mixtures: {len(gold_imp)}")
    print(f"Gold Test Nonstationary Mixtures: {len(gold_nonstat)}")
    
    # 3. Source Leakage
    def get_sources(manifests_dict):
        return {s: set(r["source_recording_id"] for r in manifests_dict[s]) for s in splits}
        
    c_sources = get_sources(clean_manifests)
    n_sources = get_sources(noise_manifests)
    
    print("\n=== SOURCE LEAKAGE ===")
    print(f"Clean Train/Val Overlap: {len(c_sources['train'] & c_sources['val'])}")
    print(f"Clean Train/Test Overlap: {len(c_sources['train'] & c_sources['test'])}")
    print(f"Clean Val/Test Overlap: {len(c_sources['val'] & c_sources['test'])}")
    print(f"Noise Train/Val Overlap: {len(n_sources['train'] & n_sources['val'])}")
    print(f"Noise Train/Test Overlap: {len(n_sources['train'] & n_sources['test'])}")
    print(f"Noise Val/Test Overlap: {len(n_sources['val'] & n_sources['test'])}")
    
    # Parent leakage for Gold Test
    c_gold_parents = set(r["parent_clean_id"] for r in gold_manifest)
    n_gold_parents = set(r["parent_noise_id"] for r in gold_manifest)
    print(f"Gold Clean Train Overlap: {len(c_gold_parents & c_sources['train'])}")
    print(f"Gold Clean Val Overlap: {len(c_gold_parents & c_sources['val'])}")
    print(f"Gold Noise Train Overlap: {len(n_gold_parents & n_sources['train'])}")
    print(f"Gold Noise Val Overlap: {len(n_gold_parents & n_sources['val'])}")
    
    # 4. ESC-50 Leakage
    def get_esc50_sources(manifest_list):
        return set(r["source_recording_id"] for r in manifest_list if r["source_dataset"] == "esc50")
    
    esc50_train = get_esc50_sources(noise_manifests["train"])
    esc50_val = get_esc50_sources(noise_manifests["val"])
    esc50_test = get_esc50_sources(noise_manifests["test"])
    
    print("\n=== ESC-50 LEAKAGE ===")
    print(f"ESC-50 Train Count: {len(esc50_train)}")
    print(f"ESC-50 Val Count: {len(esc50_val)}")
    print(f"ESC-50 Test Count: {len(esc50_test)}")
    print(f"ESC-50 Train/Val Overlap: {len(esc50_train & esc50_val)}")
    print(f"ESC-50 Train/Test Overlap: {len(esc50_train & esc50_test)}")
    print(f"ESC-50 Val/Test Overlap: {len(esc50_val & esc50_test)}")

    # 6. SNR Integrity
    print("\n=== SNR INTEGRITY ===")
    errors = []
    for r in gold_manifest:
        target = float(r["target_snr"])
        achieved = float(r["achieved_snr"])
        errors.append(abs(achieved - target))
    
    errors = np.array(errors)
    print(f"Mean Error: {errors.mean():.4f} dB")
    print(f"Median Error: {np.median(errors):.4f} dB")
    print(f"Std Dev: {errors.std():.4f} dB")
    print(f"Min Error: {errors.min():.4f} dB")
    print(f"Max Error: {errors.max():.4f} dB")
    print("Examples:")
    for i in range(min(3, len(gold_manifest))):
        r = gold_manifest[i]
        print(f"  Target: {r['target_snr']}, Achieved: {r['achieved_snr']}, Error: {errors[i]:.4f}")

    # 9. Defence Noise Coverage Matrix
    print("\n=== DEFENCE NOISE COVERAGE MATRIX ===")
    categories = {}
    for r in noise_manifests["test"]:
        cat = r["source_class"]
        categories[cat] = categories.get(cat, 0) + 1
    print(f"Noise classes in test set: {categories}")

if __name__ == "__main__":
    main()
