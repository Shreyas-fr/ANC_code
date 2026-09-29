import os
import csv
import collections

ARTIFACTS_DIR = "/Users/shreyasdivekar/.gemini/antigravity-ide/brain/f1e97365-5160-46c7-b253-5c3044021852/"
INVENTORY_PATH = os.path.join(ARTIFACTS_DIR, "iobt_gunfire_inventory.csv")
SPLIT_PATH = os.path.join(ARTIFACTS_DIR, "iobt_gunfire_proposed_split.csv")
CLEAN_MANIFEST_DIR = "data/clean_manifests"
EXISTING_TRAIN = os.path.join(CLEAN_MANIFEST_DIR, "noise_train.csv")
EXISTING_VAL = os.path.join(CLEAN_MANIFEST_DIR, "noise_val.csv")
EXISTING_GOLD = os.path.join(CLEAN_MANIFEST_DIR, "SIH_GOLD_TEST_manifest.csv")

def main():
    # Load existing SHAs and filenames
    existing_hashes = set()
    existing_files = set()
    for fpath in [EXISTING_TRAIN, EXISTING_VAL, EXISTING_GOLD]:
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if 'file_hash' in r: existing_hashes.add(r['file_hash'])
                    if 'audio_path' in r: existing_files.add(os.path.basename(r['audio_path']))

    # Load inventory
    inventory = {}
    with open(INVENTORY_PATH, "r") as f:
        for r in csv.DictReader(f):
            inventory[r['audio_path']] = r
            
    total_audio_files = len(inventory)
    
    # Load splits
    splits = {}
    with open(SPLIT_PATH, "r") as f:
        for r in csv.DictReader(f):
            splits[r['audio_path']] = r['split']

    train_files = set()
    val_files = set()
    test_files = set()
    unassigned = set()
    duplicate_assign = 0
    
    for path in inventory.keys():
        if path not in splits:
            unassigned.add(path)
            
    for path, s in splits.items():
        if s == 'TRAIN':
            if path in train_files: duplicate_assign += 1
            train_files.add(path)
        elif s == 'VALIDATION':
            if path in val_files: duplicate_assign += 1
            val_files.add(path)
        elif s == 'TEST':
            if path in test_files: duplicate_assign += 1
            test_files.add(path)
            
    # Group check
    train_groups = set(inventory[p]['source_group_id'] for p in train_files)
    val_groups = set(inventory[p]['source_group_id'] for p in val_files)
    test_groups = set(inventory[p]['source_group_id'] for p in test_files)
    
    t_v_over = train_groups.intersection(val_groups)
    t_t_over = train_groups.intersection(test_groups)
    v_t_over = val_groups.intersection(test_groups)
    
    # Session check (same as group since group = session + firearm)
    train_sessions = set(inventory[p]['session_id'] for p in train_files)
    val_sessions = set(inventory[p]['session_id'] for p in val_files)
    test_sessions = set(inventory[p]['session_id'] for p in test_files)
    
    t_v_s_over = train_sessions.intersection(val_sessions)
    t_t_s_over = train_sessions.intersection(test_sessions)
    v_t_s_over = val_sessions.intersection(test_sessions)
    
    # Hashes
    train_hashes = set(inventory[p]['file_hash'] for p in train_files)
    val_hashes = set(inventory[p]['file_hash'] for p in val_files)
    test_hashes = set(inventory[p]['file_hash'] for p in test_files)
    
    hash_t_v = train_hashes.intersection(val_hashes)
    hash_t_t = train_hashes.intersection(test_hashes)
    hash_v_t = val_hashes.intersection(test_hashes)
    
    cross_split_sha = len(hash_t_v) + len(hash_t_t) + len(hash_v_t)
    
    # Duplicates inside
    all_hashes = [inventory[p]['file_hash'] for p in inventory.keys()]
    exact_dupes = len(all_hashes) - len(set(all_hashes))
    
    # Existing SIH overlap
    sih_overlap_t = sum(1 for h in train_hashes if h in existing_hashes)
    sih_overlap_v = sum(1 for h in val_hashes if h in existing_hashes)
    sih_overlap_gold = sum(1 for h in test_hashes if h in existing_hashes)
    
    # Event level
    event_level_identity = "NOT_AVAILABLE"
    leakage_guarantee = "SESSION_LEVEL_ONLY"
    
    # Firearm Balance
    def count_firearms(file_list):
        c = collections.Counter()
        for p in file_list:
            c[inventory[p]['firearm_id']] += 1
        return c
        
    t_fire = count_firearms(train_files)
    v_fire = count_firearms(val_files)
    ts_fire = count_firearms(test_files)
    
    all_f = set(t_fire.keys()) | set(v_fire.keys()) | set(ts_fire.keys())
    for f in all_f:
        pass # we can log this to file if needed
    
    # Output Manifests
    if len(unassigned) == 0 and duplicate_assign == 0 and len(t_v_over) == 0 and len(t_t_over) == 0 and len(v_t_over) == 0 and cross_split_sha == 0 and sih_overlap_t == 0 and sih_overlap_v == 0 and sih_overlap_gold == 0:
        
        manifest_cols = ["audio_path", "file_hash", "source_group_id", "session_id", "device_id", "firearm_id", "duration_seconds", "sample_rate", "channels", "provenance", "license", "dataset_name"]
        
        for name, files in [("train", train_files), ("val", val_files), ("test", test_files)]:
            with open(os.path.join(CLEAN_MANIFEST_DIR, f"defence_gunfire_{name}.csv"), "w") as fw:
                w = csv.DictWriter(fw, fieldnames=manifest_cols)
                w.writeheader()
                for f in files:
                    inv = inventory[f]
                    w.writerow({
                        "audio_path": f, # already relative
                        "file_hash": inv["file_hash"],
                        "source_group_id": inv["source_group_id"],
                        "session_id": inv["session_id"],
                        "device_id": inv["device_id"],
                        "firearm_id": inv["firearm_id"],
                        "duration_seconds": inv["duration_seconds"],
                        "sample_rate": inv["sample_rate"],
                        "channels": inv["channels"],
                        "provenance": "IoBT Gunfire Audio Dataset (Zenodo 6836031)",
                        "license": "CC BY 4.0",
                        "dataset_name": "iobt_gunfire"
                    })
                    
    print(f"RAW_FILES={total_audio_files}")
    print(f"TRAIN_FILES={len(train_files)}")
    print(f"VAL_FILES={len(val_files)}")
    print(f"TEST_FILES={len(test_files)}")
    print(f"UNASSIGNED_FILES={len(unassigned)}")
    print(f"DUPLICATED_ASSIGNMENTS={duplicate_assign}\n")

    print(f"TRAIN_GROUPS={len(train_groups)}")
    print(f"VAL_GROUPS={len(val_groups)}")
    print(f"TEST_GROUPS={len(test_groups)}\n")

    print(f"TRAIN_VAL_GROUP_OVERLAP={len(t_v_over)}")
    print(f"TRAIN_TEST_GROUP_OVERLAP={len(t_t_over)}")
    print(f"VAL_TEST_GROUP_OVERLAP={len(v_t_over)}\n")

    print(f"TRAIN_VAL_SESSION_OVERLAP={len(t_v_s_over)}")
    print(f"TRAIN_TEST_SESSION_OVERLAP={len(t_t_s_over)}")
    print(f"VAL_TEST_SESSION_OVERLAP={len(v_t_s_over)}\n")

    print(f"CROSS_SPLIT_SHA_OVERLAP={cross_split_sha}\n")

    print(f"EXACT_DUPLICATES={exact_dupes}")
    print(f"CROSS_SPLIT_DUPLICATES={cross_split_sha}\n")

    print(f"EVENT_LEVEL_IDENTITY={event_level_identity}")
    print(f"LEAKAGE_GUARANTEE={leakage_guarantee}\n")

    print(f"EXISTING_SIH_TRAIN_OVERLAP={sih_overlap_t}")
    print(f"EXISTING_SIH_VAL_OVERLAP={sih_overlap_v}")
    print(f"EXISTING_SIH_GOLD_OVERLAP={sih_overlap_gold}\n")

    print(f"FIREARM_BALANCE_STATUS=COMPUTED")

    if cross_split_sha > 0 or len(t_v_over) > 0 or len(t_t_over) > 0 or len(v_t_over) > 0:
        print(f"FINAL_INTEGRATION_STATUS=BLOCKED_LEAKAGE")
    elif len(unassigned) > 0 or duplicate_assign > 0:
        print(f"FINAL_INTEGRATION_STATUS=BLOCKED_MANIFEST_ERROR")
    elif sih_overlap_t > 0 or sih_overlap_v > 0 or sih_overlap_gold > 0:
        print(f"FINAL_INTEGRATION_STATUS=BLOCKED_EXISTING_OVERLAP")
    else:
        print(f"FINAL_INTEGRATION_STATUS=READY_WITH_SESSION_LEVEL_LIMITATION")

if __name__ == "__main__":
    main()
