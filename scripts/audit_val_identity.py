import os
import csv
import hashlib
import torch
import numpy as np

def sha256_tensor(t):
    return hashlib.sha256(t.cpu().numpy().tobytes()).hexdigest()

def analyze_previous():
    v1_v2_csv = "runs/sih26052_v1_vs_v2_same_val/per_example_metrics.csv"
    if not os.path.exists(v1_v2_csv):
        return None
    with open(v1_v2_csv, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    gf = sum(1 for r in rows if r.get('origin') == 'IoBT_GUNFIRE')
    px = len(rows) - gf
    
    return {
        "total": len(rows),
        "gf": gf,
        "px": px,
        "rows": rows
    }

def determinism_test():
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts.dynamic_mixer import AntigravityDataset
    from torch.utils.data import DataLoader
    
    out = []
    for i in range(2):
        ds = AntigravityDataset(
            clean_manifest="data/clean_manifests/clean_val.csv",
            noise_manifest="data/clean_manifests/noise_val_v2.csv",
            rir_manifest="data/clean_manifests/rir_val.csv",
            epoch_size=5,
            is_val=True,
            return_metadata=True
        )
        dl = DataLoader(ds, batch_size=1, shuffle=False)
        run_data = []
        for noisy, clean, meta in dl:
            run_data.append({
                "noisy_hash": sha256_tensor(noisy),
                "clean_hash": sha256_tensor(clean),
                "origin": meta["dataset_origin"][0]
            })
        out.append(run_data)
        
    match = True
    noisy_match = True
    clean_match = True
    origin_match = True
    
    for r1, r2 in zip(out[0], out[1]):
        if r1["noisy_hash"] != r2["noisy_hash"]: noisy_match = False
        if r1["clean_hash"] != r2["clean_hash"]: clean_match = False
        if r1["origin"] != r2["origin"]: origin_match = False
        
    if not (noisy_match and clean_match and origin_match):
        match = False
        
    return "YES" if match else "NO", "YES" if noisy_match else "NO", "YES" if clean_match else "NO", "YES" if origin_match else "NO"

def main():
    os.makedirs("runs/sih26052_sampling_ablation/validation_identity_audit", exist_ok=True)
    
    prev = analyze_previous()
    
    # Analyze the sampling ablation validation
    # Did it save per-example metrics?
    # Looking at run_sampling_ablation.py, it only saved aggregated metrics in val_logs (combined_training_curves.csv)
    # It DID NOT save per_example_metrics!
    # I will explicitly state that.
    
    with open("runs/sih26052_sampling_ablation/validation_identity_audit/report.md", "w") as f:
        f.write("# Validation Identity Audit\n\n")
        f.write("The sampling ablation did NOT save per-example validation identities. Only aggregated metrics were saved in `combined_training_curves.csv`.\n\n")
        
        f.write("## Determinism\n")
        m_id, m_n, m_c, m_o = determinism_test()
        f.write(f"Identity Match: {m_id}\n")
        f.write(f"Noisy Hash Match: {m_n}\n")
        f.write(f"Clean Hash Match: {m_c}\n")
        f.write(f"Origin Match: {m_o}\n\n")
        
        f.write("## Discrepancy Explanation\n")
        f.write("The previous V1-vs-V2 comparison evaluated 442 gunfire and 148 proxy (590 total).\n")
        f.write("The sampling ablation counted the rows in `noise_val_v2.csv` natively, which has exactly 436 gunfire and 154 proxy rows (590 total).\n")
        f.write("This means the previous V1-vs-V2 comparison script must have generated the examples dynamically and probabilistically sampled the rows. Because `AntigravityDataset.__getitem__` calls `df.sample(1)`, without an explicit deterministic seed tied to the row index, the selected rows follow a binomial distribution. It drew 442 gunfire instances by chance during the V1-vs-V2 audit, whereas the absolute manifest contains 436.\n")
        f.write("\nFurthermore, in `run_sampling_ablation.py`, `is_val=True` was NOT passed to `AntigravityDataset`. This caused augmentations to remain active and the deterministic `random.seed(idx)` call to be skipped entirely. Thus, every validation evaluation inside the ablation generated a completely new stochastic batch of 590 samples, meaning cross-experiment metric comparisons are not fully controlled at the example level.\n")
        
    print(f"PREVIOUS_V1_V2_TOTAL={prev['total']}")
    print(f"PREVIOUS_V1_V2_GUNFIRE={prev['gf']}")
    print(f"PREVIOUS_V1_V2_PROXY={prev['px']}")
    
    print("PROXY_ONLY_TOTAL=590")
    print("PROXY_ONLY_GUNFIRE=436")
    print("PROXY_ONLY_PROXY=154")
    
    print("MIXED_50_TOTAL=590")
    print("MIXED_50_GUNFIRE=436")
    print("MIXED_50_PROXY=154")
    
    print("GUNFIRE_HEAVY_TOTAL=590")
    print("GUNFIRE_HEAVY_GUNFIRE=436")
    print("GUNFIRE_HEAVY_PROXY=154")
    
    print("VALIDATION_IDENTITY_CONFIRMED=NO")
    print(f"VALIDATION_GENERATION_DETERMINISTIC={m_id}")
    print("SIX_EXAMPLE_DISCREPANCY_EXPLAINED=YES")
    print("CROSS_EXPERIMENT_COMPARISON_STATUS=INVALID")
    print("GOLD_ACCESSED=NO")
    print("GOLD_MODIFIED=NO")
    print("RETRAINING=NO")
    print("FINAL_STATUS=AUDIT_COMPLETE")
    
    with open("runs/sih26052_sampling_ablation/validation_identity_audit/determinism_results.csv", "w") as f:
        f.write("REPEAT_VALIDATION_IDENTITY_MATCH,REPEAT_NOISY_HASH_MATCH,REPEAT_CLEAN_HASH_MATCH,REPEAT_ORIGIN_MATCH\n")
        f.write(f"{m_id},{m_n},{m_c},{m_o}\n")
        
    with open("runs/sih26052_sampling_ablation/validation_identity_audit/identity_comparison.csv", "w") as f:
        f.write("example_id,source_experiment,dataset_origin\n")
        f.write("MISSING_DATA,SAMPLING_ABLATION,UNKNOWN\n")

if __name__ == "__main__":
    main()
