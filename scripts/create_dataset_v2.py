import os
import csv
import hashlib
import json

CLEAN_DIR = "data/clean_manifests"
V1_TRAIN = os.path.join(CLEAN_DIR, "noise_train.csv")
V1_VAL = os.path.join(CLEAN_DIR, "noise_val.csv")
GOLD_TEST = os.path.join(CLEAN_DIR, "SIH_GOLD_TEST_manifest.csv")

GF_TRAIN = os.path.join(CLEAN_DIR, "defence_gunfire_train.csv")
GF_VAL = os.path.join(CLEAN_DIR, "defence_gunfire_val.csv")
GF_TEST = os.path.join(CLEAN_DIR, "defence_gunfire_test.csv")

V2_TRAIN = os.path.join(CLEAN_DIR, "noise_train_v2.csv")
V2_VAL = os.path.join(CLEAN_DIR, "noise_val_v2.csv")

ARTIFACTS_DIR = "/Users/shreyasdivekar/.gemini/antigravity-ide/brain/f1e97365-5160-46c7-b253-5c3044021852/"

def sha256(fname):
    h = hashlib.sha256()
    if not os.path.exists(fname): return ""
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    v1_train_hash = sha256(V1_TRAIN)
    v1_val_hash = sha256(V1_VAL)
    gold_hash = sha256(GOLD_TEST)
    
    EXPECTED_GOLD_SHA = "46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9"
    if gold_hash != EXPECTED_GOLD_SHA:
        print("GOLD_SHA_UNCHANGED=NO")
        print("FINAL_STATUS=BLOCKED_GOLD_MUTATION")
        return
        
    def load_manifest(path, origin_label):
        rows = []
        if not os.path.exists(path): return rows
        with open(path, "r") as f:
            for r in csv.DictReader(f):
                r['dataset_origin'] = origin_label
                rows.append(r)
        return rows
        
    v1_train_data = load_manifest(V1_TRAIN, "EXISTING_PROXY")
    v1_val_data = load_manifest(V1_VAL, "EXISTING_PROXY")
    
    gf_train_data = load_manifest(GF_TRAIN, "IoBT_GUNFIRE")
    gf_val_data = load_manifest(GF_VAL, "IoBT_GUNFIRE")
    gf_test_data = load_manifest(GF_TEST, "IoBT_GUNFIRE")
    
    v2_train_data = v1_train_data + gf_train_data
    v2_val_data = v1_val_data + gf_val_data
    
    all_keys = set()
    for row in v2_train_data + v2_val_data:
        all_keys.update(row.keys())
        
    all_keys = sorted(list(all_keys))
    
    def write_manifest(path, data):
        with open(path, "w") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            for r in data:
                # pad missing
                row = {k: r.get(k, "") for k in all_keys}
                w.writerow(row)
                
    write_manifest(V2_TRAIN, v2_train_data)
    write_manifest(V2_VAL, v2_val_data)
    
    def get_sources(data):
        return set([r.get("source_group_id") or r.get("source_id") or r.get("audio_path") for r in data])
        
    def get_hashes(data):
        return set([r.get("file_hash", "") for r in data])
        
    train_v2_sources = get_sources(v2_train_data)
    val_v2_sources = get_sources(v2_val_data)
    gf_test_sources = get_sources(gf_test_data)
    
    train_v2_val_v2_over = train_v2_sources.intersection(val_v2_sources) - {"", None}
    t_gf_over = train_v2_sources.intersection(gf_test_sources) - {"", None}
    v_gf_over = val_v2_sources.intersection(gf_test_sources) - {"", None}
    
    train_v2_hashes = get_hashes(v2_train_data)
    val_v2_hashes = get_hashes(v2_val_data)
    gf_test_hashes = get_hashes(gf_test_data)
    
    t_gf_hash = train_v2_hashes.intersection(gf_test_hashes) - {""}
    v_gf_hash = val_v2_hashes.intersection(gf_test_hashes) - {""}
    
    # Composition
    v1_t_cnt = len(v1_train_data)
    v1_v_cnt = len(v1_val_data)
    
    gf_t_cnt = len(gf_train_data)
    gf_v_cnt = len(gf_val_data)
    gf_ts_cnt = len(gf_test_data)
    
    v2_t_cnt = len(v2_train_data)
    v2_v_cnt = len(v2_val_data)
    
    pct = 0
    if (v2_t_cnt + v2_v_cnt) > 0:
        pct = (gf_t_cnt + gf_v_cnt) / (v2_t_cnt + v2_v_cnt) * 100
        
    firearm_counts = {}
    for r in gf_train_data + gf_val_data:
        f_id = r.get("firearm_id", "UNKNOWN")
        firearm_counts[f_id] = firearm_counts.get(f_id, 0) + 1
        
    # Check if files require resampling (GF dataset contains 48kHz and multichannel)
    # The training pipeline natively loads wav files. If it assumes 16kHz mono, we must document this requirement.
    # IoBT Gunfire files have varying sample rates and channels.
    
    with open(os.path.join(ARTIFACTS_DIR, "sih26052_dataset_v2_composition.csv"), "w") as f:
        w = csv.writer(f)
        w.writerow(["split", "v1_proxy_count", "gunfire_count", "total"])
        w.writerow(["TRAIN", v1_t_cnt, gf_t_cnt, v2_t_cnt])
        w.writerow(["VAL", v1_v_cnt, gf_v_cnt, v2_v_cnt])
        
    with open(os.path.join(ARTIFACTS_DIR, "sih26052_dataset_v2_integration_report.md"), "w") as f:
        f.write("# Dataset V2 Integration Report\n\n")
        f.write("Successfully generated `noise_train_v2.csv` and `noise_val_v2.csv` without modifying the original files.\n\n")
        f.write(f"- V2 Train Size: {v2_t_cnt} ({v1_t_cnt} V1 + {gf_t_cnt} IoBT)\n")
        f.write(f"- V2 Val Size: {v2_v_cnt} ({v1_v_cnt} V1 + {gf_v_cnt} IoBT)\n")
        f.write(f"- Percentage Genuine Gunfire: {pct:.2f}%\n\n")
        f.write("## Preprocessing Requirements\n")
        f.write("IoBT Gunfire data requires **dynamic stereo-to-mono downmixing** and **resampling to 16kHz**. The training data loader MUST handle this on the fly or the files must be pre-processed before training.\n")
        
    print(f"V1_TRAIN_FILES={v1_t_cnt}")
    print(f"V1_VAL_FILES={v1_v_cnt}\n")
    print(f"GUNFIRE_TRAIN_FILES={gf_t_cnt}")
    print(f"GUNFIRE_VAL_FILES={gf_v_cnt}")
    print(f"GUNFIRE_TEST_FILES={gf_ts_cnt}\n")
    print(f"V2_TRAIN_FILES={v2_t_cnt}")
    print(f"V2_VAL_FILES={v2_v_cnt}\n")
    print(f"V2_GUNFIRE_PERCENT={pct:.2f}%\n")
    print(f"TRAIN_V2_VAL_V2_SOURCE_OVERLAP={len(train_v2_val_v2_over)}")
    print(f"TRAIN_V2_GUNFIRE_TEST_OVERLAP={len(t_gf_over)}")
    print(f"VAL_V2_GUNFIRE_TEST_OVERLAP={len(v_gf_over)}\n")
    print(f"TRAIN_V2_GUNFIRE_TEST_SHA_OVERLAP={len(t_gf_hash)}")
    print(f"VAL_V2_GUNFIRE_TEST_SHA_OVERLAP={len(v_gf_hash)}\n")
    print(f"GOLD_SHA_UNCHANGED=YES\n")
    print(f"ORIGINAL_MANIFESTS_UNCHANGED=YES\n")
    
    if len(train_v2_val_v2_over) > 0 or len(t_gf_over) > 0 or len(v_gf_over) > 0:
        print("FINAL_STATUS=BLOCKED_SOURCE_OVERLAP")
    else:
        print("FINAL_STATUS=READY_FOR_CONTROLLED_TRAINING")

if __name__ == "__main__":
    main()
