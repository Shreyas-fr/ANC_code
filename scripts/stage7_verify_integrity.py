#!/usr/bin/env python3
"""Stage 7: Verify data integrity and alignment across Step-500, FullSubNet, GTCRN, and Manifest."""

import csv
import math
import sys
from pathlib import Path

MANIFEST_P = Path("antigravity/runs/sih26052_canonical_validation/manifest.csv")
STEP500_P = Path("antigravity/runs/sih26052_candidate_step500_repro_20261113/per_clip.csv")
FULLSUBNET_P = Path("antigravity/runs/fullsubnet_baseline/per_clip.csv")
GTCRN_P = Path("antigravity/runs/gtcrn_dns3_canonical_20261113/per_clip.csv")
GTCRN_INFER_P = Path("antigravity/runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv")

def load_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main():
    print("=== Stage 7 Integrity and Alignment Check ===")
    manifest_rows = load_csv(MANIFEST_P)
    step500_rows = load_csv(STEP500_P)
    fullsubnet_rows = load_csv(FULLSUBNET_P)
    gtcrn_rows = load_csv(GTCRN_P)
    gtcrn_infer_rows = load_csv(GTCRN_INFER_P)

    # 1. Row counts
    counts = {
        "manifest": len(manifest_rows),
        "step500": len(step500_rows),
        "fullsubnet": len(fullsubnet_rows),
        "gtcrn": len(gtcrn_rows),
        "gtcrn_infer": len(gtcrn_infer_rows)
    }
    print("Row counts:", counts)
    for name, c in counts.items():
        if c != 590:
            print(f"FAILED: {name} count is {c}, expected 590", file=sys.stderr)
            sys.exit(1)

    # 2. Check unique clip IDs (val_index)
    manifest_by_id = {int(r["val_index"]): r for r in manifest_rows}
    step500_by_id = {int(r["val_index"]): r for r in step500_rows}
    fullsubnet_by_id = {int(r["val_index"]): r for r in fullsubnet_rows}
    gtcrn_by_id = {int(r["val_index"]): r for r in gtcrn_rows}
    gtcrn_infer_by_id = {int(r["val_index"]): r for r in gtcrn_infer_rows}

    expected_ids = set(range(590))
    for name, d in [
        ("manifest", manifest_by_id),
        ("step500", step500_by_id),
        ("fullsubnet", fullsubnet_by_id),
        ("gtcrn", gtcrn_by_id),
        ("gtcrn_infer", gtcrn_infer_by_id)
    ]:
        if set(d.keys()) != expected_ids:
            missing = expected_ids - set(d.keys())
            unexpected = set(d.keys()) - expected_ids
            print(f"FAILED: {name} clip IDs mismatch! Missing: {missing}, Unexpected: {unexpected}", file=sys.stderr)
            sys.exit(1)
        if len(d) != 590:
            print(f"FAILED: {name} has duplicates or missing IDs (unique count {len(d)})", file=sys.stderr)
            sys.exit(1)
    print("PASSED: All files contain exactly 590 unique canonical clip IDs [0..589].")

    # 3. Target SNR and Origin Alignment
    for i in range(590):
        m_snr = float(manifest_by_id[i]["target_snr"])
        m_orig = manifest_by_id[i]["dataset_origin"]
        
        s_snr = float(step500_by_id[i]["target_snr_db"])
        f_snr = float(fullsubnet_by_id[i]["target_snr_db"])
        g_snr = float(gtcrn_by_id[i]["target_snr_db"])

        s_orig = step500_by_id[i]["origin"]
        f_orig = fullsubnet_by_id[i]["origin"]
        g_orig = gtcrn_by_id[i]["origin"]

        if not (m_snr == s_snr == f_snr == g_snr):
            print(f"FAILED: Target SNR mismatch at clip {i}: manifest={m_snr}, step500={s_snr}, fullsubnet={f_snr}, gtcrn={g_snr}", file=sys.stderr)
            sys.exit(1)

        if not (m_orig == s_orig == f_orig == g_orig):
            print(f"FAILED: Origin mismatch at clip {i}: manifest={m_orig}, step500={s_orig}, fullsubnet={f_orig}, gtcrn={g_orig}", file=sys.stderr)
            sys.exit(1)
    print("PASSED: Target input SNR and origin labels are 100% aligned across all models and manifest.")

    # 4. Metric values finiteness
    metric_cols = ["output_snr_db", "output_si_sdr_db", "output_stoi", "output_pesq_wb"]
    for model_name, d in [("Step-500", step500_by_id), ("FullSubNet", fullsubnet_by_id), ("GTCRN", gtcrn_by_id)]:
        for i in range(590):
            r = d[i]
            for col in metric_cols:
                val = float(r[col])
                if not math.isfinite(val):
                    print(f"FAILED: Non-finite value in {model_name} at clip {i}, col {col}: {val}", file=sys.stderr)
                    sys.exit(1)
    print("PASSED: All metric values across all three models are strictly finite.")

    # 5. GTCRN inference timing finiteness
    for i in range(590):
        r = gtcrn_infer_by_id[i]
        sec = float(r["audio_seconds"])
        infer_t = float(r["inference_seconds_stft_model_istft"])
        samples = int(r["output_samples"])
        sha = r["output_sha256"]
        if not (math.isfinite(sec) and math.isfinite(infer_t) and samples == 48000 and len(sha) == 64):
            print(f"FAILED: GTCRN inference invalid at clip {i}: sec={sec}, infer_t={infer_t}, samples={samples}, sha={sha}", file=sys.stderr)
            sys.exit(1)
    print("PASSED: GTCRN inference per-clip records verified (48,000 samples @ 16 kHz = 3.0s, valid hashes).")
    print("=== All Data Integrity Checks PASSED ===")

if __name__ == "__main__":
    main()

