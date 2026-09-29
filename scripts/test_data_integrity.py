import os
import csv
import sys

def load_manifest(path):
    if not os.path.exists(path): return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))

def test_integrity():
    roles = ["clean", "noise", "rir"]
    splits = ["train", "val", "test"]
    
    # Store sets for intersection tests
    hashes = {r: {s: set() for s in splits} for r in roles}
    source_ids = {r: {s: set() for s in splits} for r in roles}
    
    for r in roles:
        for s in splits:
            records = load_manifest(f"data/clean_manifests/{r}_{s}.csv")
            for rec in records:
                hashes[r][s].add(rec["file_hash"])
                source_ids[r][s].add(rec["source_recording_id"])
                
    # 1. Check Source/Hash Leakage
    failures = 0
    for r in roles:
        # Train vs Val
        h_tv = hashes[r]["train"].intersection(hashes[r]["val"])
        s_tv = source_ids[r]["train"].intersection(source_ids[r]["val"])
        if h_tv: print(f"FAIL: Hash leak {r} train/val ({len(h_tv)})"); failures += 1
        if s_tv: print(f"FAIL: Source leak {r} train/val ({len(s_tv)})"); failures += 1
        
        # Train vs Test
        h_tt = hashes[r]["train"].intersection(hashes[r]["test"])
        s_tt = source_ids[r]["train"].intersection(source_ids[r]["test"])
        if h_tt: print(f"FAIL: Hash leak {r} train/test ({len(h_tt)})"); failures += 1
        if s_tt: print(f"FAIL: Source leak {r} train/test ({len(s_tt)})"); failures += 1
        
        # Val vs Test
        h_vt = hashes[r]["val"].intersection(hashes[r]["test"])
        s_vt = source_ids[r]["val"].intersection(source_ids[r]["test"])
        if h_vt: print(f"FAIL: Hash leak {r} val/test ({len(h_vt)})"); failures += 1
        if s_vt: print(f"FAIL: Source leak {r} val/test ({len(s_vt)})"); failures += 1

    # 2. Check Gold Test Parent Leakage
    gold_records = load_manifest("data/clean_manifests/SIH_GOLD_TEST_manifest.csv")
    if not gold_records:
        print("FAIL: SIH_GOLD_TEST_manifest.csv not found.")
        failures += 1
    else:
        for rec in gold_records:
            c_parent = rec["parent_clean_id"]
            n_parent = rec["parent_noise_id"]
            
            if c_parent in source_ids["clean"]["train"] or c_parent in source_ids["clean"]["val"]:
                print(f"FAIL: Gold clean parent {c_parent} leaked to train/val")
                failures += 1
            if n_parent in source_ids["noise"]["train"] or n_parent in source_ids["noise"]["val"]:
                print(f"FAIL: Gold noise parent {n_parent} leaked to train/val")
                failures += 1
                
            # SNR tolerance check
            achieved = float(rec["achieved_snr"])
            target = float(rec["target_snr"])
            if abs(achieved - target) > 1.0: # 1 dB tolerance
                print(f"WARN: SNR out of tolerance for {rec['file_hash']}: Target {target:.2f}, Achieved {achieved:.2f}")

    if failures == 0:
        print("ALL DATA INTEGRITY TESTS PASSED.")
        
        # Print a short report
        print("\n--- LEAKAGE REPORT ---")
        for r in roles:
            t = len(source_ids[r]['train'])
            v = len(source_ids[r]['val'])
            test = len(source_ids[r]['test'])
            print(f"[{r.upper()}] Unique Sources -> Train: {t} | Val: {v} | Test: {test}")
            
        sys.exit(0)
    else:
        print(f"FAILED WITH {failures} ERRORS.")
        sys.exit(1)

if __name__ == "__main__":
    test_integrity()
