#!/usr/bin/env python3
"""Stage 7: Low-SNR Failure Analysis and Data Processing Script.
Generates:
  - research/STAGE7_SNR_BIN_SUMMARY.csv
  - research/STAGE7_PAIRED_COMPARISONS.csv
  - research/STAGE7_FAILURE_CLIP_TABLE.csv
"""

import csv
import json
import math
import numpy as np
from pathlib import Path

# Paths
MANIFEST_P = Path("antigravity/runs/sih26052_canonical_validation/manifest.csv")
STEP500_P = Path("antigravity/runs/sih26052_candidate_step500_repro_20261113/per_clip.csv")
FULLSUBNET_P = Path("antigravity/runs/fullsubnet_baseline/per_clip.csv")
GTCRN_P = Path("antigravity/runs/gtcrn_dns3_canonical_20261113/per_clip.csv")
GTCRN_INFER_P = Path("antigravity/runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv")

OUT_DIR = Path("antigravity/research")

def load_dict(p):
    with open(p, "r", encoding="utf-8") as f:
        return {int(r["val_index"]): r for r in csv.DictReader(f)}

def bootstrap_ci(deltas, n_resamples=2000, seed=26052, alpha=0.05):
    """Percentile bootstrap 95% CI."""
    rng = np.random.RandomState(seed)
    n = len(deltas)
    if n == 0:
        return (0.0, 0.0, 0.0)
    indices = rng.randint(0, n, size=(n_resamples, n))
    resampled_means = np.mean(deltas[indices], axis=1)
    low = np.percentile(resampled_means, 100 * (alpha / 2))
    high = np.percentile(resampled_means, 100 * (1 - alpha / 2))
    return float(np.mean(deltas)), float(low), float(high)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    manifest = load_dict(MANIFEST_P)
    s500 = load_dict(STEP500_P)
    fsn = load_dict(FULLSUBNET_P)
    gtcrn = load_dict(GTCRN_P)
    gtcrn_infer = load_dict(GTCRN_INFER_P)

    # Compile master records joined by clip ID
    records = []
    for i in range(590):
        m = manifest[i]
        s = s500[i]
        f = fsn[i]
        g = gtcrn[i]
        gi = gtcrn_infer[i]
        
        target_snr = float(m["target_snr"])
        rec = {
            "val_index": i,
            "origin": m["dataset_origin"],
            "target_snr_db": target_snr,
            "input_snr_db": float(s["input_snr_db"]),
            "input_si_sdr_db": float(s["input_si_sdr_db"]),
            "input_stoi": float(s["input_stoi"]),
            "input_pesq_wb": float(s["input_pesq_wb"]),
            # Step-500
            "s500_snr": float(s["output_snr_db"]),
            "s500_sisdr": float(s["output_si_sdr_db"]),
            "s500_stoi": float(s["output_stoi"]),
            "s500_pesq": float(s["output_pesq_wb"]),
            "s500_pass_snr": float(s["output_snr_db"]) > 15.0,
            "s500_pass_stoi": float(s["output_stoi"]) > 0.85,
            "s500_pass_pesq": float(s["output_pesq_wb"]) > 2.5,
            "s500_pass_joint": (float(s["output_snr_db"]) > 15.0 and float(s["output_stoi"]) > 0.85 and float(s["output_pesq_wb"]) > 2.5),
            # FullSubNet
            "fsn_snr": float(f["output_snr_db"]),
            "fsn_sisdr": float(f["output_si_sdr_db"]),
            "fsn_stoi": float(f["output_stoi"]),
            "fsn_pesq": float(f["output_pesq_wb"]),
            "fsn_pass_snr": float(f["output_snr_db"]) > 15.0,
            "fsn_pass_stoi": float(f["output_stoi"]) > 0.85,
            "fsn_pass_pesq": float(f["output_pesq_wb"]) > 2.5,
            "fsn_pass_joint": (float(f["output_snr_db"]) > 15.0 and float(f["output_stoi"]) > 0.85 and float(f["output_pesq_wb"]) > 2.5),
            # GTCRN
            "gtcrn_snr": float(g["output_snr_db"]),
            "gtcrn_sisdr": float(g["output_si_sdr_db"]),
            "gtcrn_stoi": float(g["output_stoi"]),
            "gtcrn_pesq": float(g["output_pesq_wb"]),
            "gtcrn_pass_snr": float(g["output_snr_db"]) > 15.0,
            "gtcrn_pass_stoi": float(g["output_stoi"]) > 0.85,
            "gtcrn_pass_pesq": float(g["output_pesq_wb"]) > 2.5,
            "gtcrn_pass_joint": (float(g["output_snr_db"]) > 15.0 and float(g["output_stoi"]) > 0.85 and float(g["output_pesq_wb"]) > 2.5),
            # GTCRN timing & hash
            "gtcrn_infer_sec": float(gi["inference_seconds_stft_model_istft"]),
            "gtcrn_sha256": gi["output_sha256"]
        }
        records.append(rec)

    # Define bins
    bins_def = [
        ("-10 dB", lambda r: r["target_snr_db"] == -10.0),
        ("-5 dB", lambda r: r["target_snr_db"] == -5.0),
        ("0 dB", lambda r: r["target_snr_db"] == 0.0),
        ("5 dB", lambda r: r["target_snr_db"] == 5.0),
        ("<= 0 dB (Low SNR)", lambda r: r["target_snr_db"] <= 0.0),
        ("Full 590-clip set", lambda r: True),
    ]

    # 1. Generate STAGE7_SNR_BIN_SUMMARY.csv
    bin_summary_rows = []
    models = [
        ("Step-500", "s500"),
        ("FullSubNet", "fsn"),
        ("GTCRN", "gtcrn")
    ]

    for bin_name, bin_fn in bins_def:
        sub = [r for r in records if bin_fn(r)]
        n = len(sub)
        for model_label, m_pfx in models:
            snr_vals = np.array([r[f"{m_pfx}_snr"] for r in sub])
            sisdr_vals = np.array([r[f"{m_pfx}_sisdr"] for r in sub])
            stoi_vals = np.array([r[f"{m_pfx}_stoi"] for r in sub])
            pesq_vals = np.array([r[f"{m_pfx}_pesq"] for r in sub])
            
            pass_snr = sum(1 for r in sub if r[f"{m_pfx}_pass_snr"])
            pass_stoi = sum(1 for r in sub if r[f"{m_pfx}_pass_stoi"])
            pass_pesq = sum(1 for r in sub if r[f"{m_pfx}_pass_pesq"])
            pass_joint = sum(1 for r in sub if r[f"{m_pfx}_pass_joint"])
            joint_pct = (pass_joint / n) * 100.0 if n > 0 else 0.0

            row = {
                "bin": bin_name,
                "model": model_label,
                "clip_count": n,
                "mean_output_snr_db": f"{np.mean(snr_vals):.4f}",
                "median_output_snr_db": f"{np.median(snr_vals):.4f}",
                "mean_si_sdr_db": f"{np.mean(sisdr_vals):.4f}",
                "median_si_sdr_db": f"{np.median(sisdr_vals):.4f}",
                "mean_stoi": f"{np.mean(stoi_vals):.4f}",
                "median_stoi": f"{np.median(stoi_vals):.4f}",
                "mean_pesq_wb": f"{np.mean(pesq_vals):.4f}",
                "median_pesq_wb": f"{np.median(pesq_vals):.4f}",
                "pass_snr_gt_15": pass_snr,
                "pass_stoi_gt_0_85": pass_stoi,
                "pass_pesq_gt_2_5": pass_pesq,
                "joint_pass_count": pass_joint,
                "joint_pass_pct": f"{joint_pct:.2f}%"
            }
            bin_summary_rows.append(row)

    bin_csv_path = OUT_DIR / "STAGE7_SNR_BIN_SUMMARY.csv"
    with open(bin_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(bin_summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(bin_summary_rows)
    print(f"Wrote {bin_csv_path}")

    # 2. Generate STAGE7_PAIRED_COMPARISONS.csv
    # Model pairs: (Candidate, Reference, Cand_Pfx, Ref_Pfx)
    pairs = [
        ("GTCRN vs Step-500", "GTCRN", "Step-500", "gtcrn", "s500"),
        ("FullSubNet vs Step-500", "FullSubNet", "Step-500", "fsn", "s500"),
        ("GTCRN vs FullSubNet", "GTCRN", "FullSubNet", "gtcrn", "fsn")
    ]

    paired_summary_rows = []
    for pair_label, cand_name, ref_name, cand_pfx, ref_pfx in pairs:
        for bin_name, bin_fn in bins_def:
            sub = [r for r in records if bin_fn(r)]
            n = len(sub)
            if n == 0:
                continue
            
            d_snr = np.array([r[f"{cand_pfx}_snr"] - r[f"{ref_pfx}_snr"] for r in sub])
            d_sisdr = np.array([r[f"{cand_pfx}_sisdr"] - r[f"{ref_pfx}_sisdr"] for r in sub])
            d_stoi = np.array([r[f"{cand_pfx}_stoi"] - r[f"{ref_pfx}_stoi"] for r in sub])
            d_pesq = np.array([r[f"{cand_pfx}_pesq"] - r[f"{ref_pfx}_pesq"] for r in sub])

            mean_snr, ci_lo_snr, ci_hi_snr = bootstrap_ci(d_snr)
            mean_sisdr, ci_lo_sisdr, ci_hi_sisdr = bootstrap_ci(d_sisdr)
            mean_stoi, ci_lo_stoi, ci_hi_stoi = bootstrap_ci(d_stoi)
            mean_pesq, ci_lo_pesq, ci_hi_pesq = bootstrap_ci(d_pesq)

            cand_joint = sum(1 for r in sub if r[f"{cand_pfx}_pass_joint"])
            ref_joint = sum(1 for r in sub if r[f"{ref_pfx}_pass_joint"])

            row = {
                "comparison": pair_label,
                "candidate": cand_name,
                "reference": ref_name,
                "bin": bin_name,
                "clip_count": n,
                "delta_snr_mean": f"{mean_snr:+.4f}",
                "delta_snr_ci95_low": f"{ci_lo_snr:+.4f}",
                "delta_snr_ci95_high": f"{ci_hi_snr:+.4f}",
                "delta_sisdr_mean": f"{mean_sisdr:+.4f}",
                "delta_sisdr_ci95_low": f"{ci_lo_sisdr:+.4f}",
                "delta_sisdr_ci95_high": f"{ci_hi_sisdr:+.4f}",
                "delta_stoi_mean": f"{mean_stoi:+.4f}",
                "delta_stoi_ci95_low": f"{ci_lo_stoi:+.4f}",
                "delta_stoi_ci95_high": f"{ci_hi_stoi:+.4f}",
                "delta_pesq_mean": f"{mean_pesq:+.4f}",
                "delta_pesq_ci95_low": f"{ci_lo_pesq:+.4f}",
                "delta_pesq_ci95_high": f"{ci_hi_pesq:+.4f}",
                "cand_joint_pass": cand_joint,
                "ref_joint_pass": ref_joint,
                "delta_joint_pass": cand_joint - ref_joint
            }
            paired_summary_rows.append(row)

    paired_csv_path = OUT_DIR / "STAGE7_PAIRED_COMPARISONS.csv"
    with open(paired_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired_summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(paired_summary_rows)
    print(f"Wrote {paired_csv_path}")

    # 3. Analyze Failures, Single-Model Wins, Tradeoffs, and Top Regressions/Improvements
    # Group A: All three models fail joint criteria
    all_fail_clips = [r for r in records if (not r["s500_pass_joint"] and not r["fsn_pass_joint"] and not r["gtcrn_pass_joint"])]
    print(f"Clips where ALL THREE models fail: {len(all_fail_clips)} / 590 ({len(all_fail_clips)/590*100:.2f}%)")

    # Group B: Only one model passes joint criteria
    only_s500_clips = [r for r in records if (r["s500_pass_joint"] and not r["fsn_pass_joint"] and not r["gtcrn_pass_joint"])]
    only_fsn_clips = [r for r in records if (not r["s500_pass_joint"] and r["fsn_pass_joint"] and not r["gtcrn_pass_joint"])]
    only_gtcrn_clips = [r for r in records if (not r["s500_pass_joint"] and not r["fsn_pass_joint"] and r["gtcrn_pass_joint"])]
    print(f"Single model passes: Step-500 only={len(only_s500_clips)}, FullSubNet only={len(only_fsn_clips)}, GTCRN only={len(only_gtcrn_clips)}")

    # Group C: Tradeoffs in GTCRN vs Step-500
    # e.g., SNR improves by > 0.5 dB while PESQ degrades by < -0.1
    tradeoff_snr_up_pesq_down = [r for r in records if (r["gtcrn_snr"] - r["s500_snr"] > 0.5 and r["gtcrn_pesq"] - r["s500_pesq"] < -0.1)]
    # e.g., PESQ improves by > 0.1 while SNR degrades by < -0.5 dB
    tradeoff_pesq_up_snr_down = [r for r in records if (r["gtcrn_pesq"] - r["s500_pesq"] > 0.1 and r["gtcrn_snr"] - r["s500_snr"] < -0.5)]
    print(f"GTCRN vs Step-500 Tradeoffs: SNR up & PESQ down={len(tradeoff_snr_up_pesq_down)}, PESQ up & SNR down={len(tradeoff_pesq_up_snr_down)}")

    # 4. Generate STAGE7_FAILURE_CLIP_TABLE.csv
    # Include all common failures, single-model wins, and top regression/improvement clips
    # To be fully comprehensive, let's categorize each clip in the table!
    failure_table_rows = []
    
    # Sort criteria for top regressions/improvements in low-SNR (target_snr <= 0)
    low_snr_records = [r for r in records if r["target_snr_db"] <= 0.0]
    
    # Identify top 10 GTCRN vs Step-500 regressions & improvements by SNR in low-SNR
    top_gtcrn_snr_improvements = sorted(low_snr_records, key=lambda r: r["gtcrn_snr"] - r["s500_snr"], reverse=True)[:10]
    top_gtcrn_snr_regressions = sorted(low_snr_records, key=lambda r: r["gtcrn_snr"] - r["s500_snr"])[:10]
    
    # Identify top 10 FullSubNet vs Step-500 improvements & regressions by PESQ in low-SNR
    top_fsn_pesq_improvements = sorted(low_snr_records, key=lambda r: r["fsn_pesq"] - r["s500_pesq"], reverse=True)[:10]
    top_fsn_pesq_regressions = sorted(low_snr_records, key=lambda r: r["fsn_pesq"] - r["s500_pesq"])[:10]

    special_clip_ids = set()
    clip_categories = {}

    def tag_clips(clip_list, category):
        for r in clip_list:
            cid = r["val_index"]
            special_clip_ids.add(cid)
            if cid not in clip_categories:
                clip_categories[cid] = []
            clip_categories[cid].append(category)

    tag_clips(only_gtcrn_clips, "ONLY_GTCRN_PASSES")
    tag_clips(only_s500_clips, "ONLY_STEP500_PASSES")
    tag_clips(only_fsn_clips, "ONLY_FULLSUBNET_PASSES")
    tag_clips(top_gtcrn_snr_improvements, "TOP_GTCRN_SNR_GAIN_LOW_SNR")
    tag_clips(top_gtcrn_snr_regressions, "TOP_GTCRN_SNR_LOSS_LOW_SNR")
    tag_clips(top_fsn_pesq_improvements, "TOP_FSN_PESQ_GAIN_LOW_SNR")
    tag_clips(top_fsn_pesq_regressions, "TOP_FSN_PESQ_LOSS_LOW_SNR")
    
    # Also add the top 20 worst common failures (lowest average PESQ across all 3 models in <= 0 dB)
    worst_common_failures = sorted(all_fail_clips, key=lambda r: (r["s500_pesq"] + r["fsn_pesq"] + r["gtcrn_pesq"]))[:20]
    tag_clips(worst_common_failures, "WORST_COMMON_FAILURES_LOW_SNR")

    # Order special clips by val_index
    for cid in sorted(special_clip_ids):
        r = records[cid]
        row = {
            "val_index": cid,
            "target_snr_db": f"{r['target_snr_db']:+.1f}",
            "origin": r["origin"],
            "categories": "; ".join(clip_categories[cid]),
            # Step-500
            "s500_snr_db": f"{r['s500_snr']:.4f}",
            "s500_sisdr_db": f"{r['s500_sisdr']:.4f}",
            "s500_stoi": f"{r['s500_stoi']:.4f}",
            "s500_pesq_wb": f"{r['s500_pesq']:.4f}",
            "s500_joint_pass": "PASS" if r["s500_pass_joint"] else "FAIL",
            # FullSubNet
            "fsn_snr_db": f"{r['fsn_snr']:.4f}",
            "fsn_sisdr_db": f"{r['fsn_sisdr']:.4f}",
            "fsn_stoi": f"{r['fsn_stoi']:.4f}",
            "fsn_pesq_wb": f"{r['fsn_pesq']:.4f}",
            "fsn_joint_pass": "PASS" if r["fsn_pass_joint"] else "FAIL",
            # GTCRN
            "gtcrn_snr_db": f"{r['gtcrn_snr']:.4f}",
            "gtcrn_sisdr_db": f"{r['gtcrn_sisdr']:.4f}",
            "gtcrn_stoi": f"{r['gtcrn_stoi']:.4f}",
            "gtcrn_pesq_wb": f"{r['gtcrn_pesq']:.4f}",
            "gtcrn_joint_pass": "PASS" if r["gtcrn_pass_joint"] else "FAIL",
            # Deltas vs Step-500
            "delta_gtcrn_minus_s500_snr": f"{r['gtcrn_snr'] - r['s500_snr']:+.4f}",
            "delta_gtcrn_minus_s500_pesq": f"{r['gtcrn_pesq'] - r['s500_pesq']:+.4f}",
            "delta_fsn_minus_s500_snr": f"{r['fsn_snr'] - r['s500_snr']:+.4f}",
            "delta_fsn_minus_s500_pesq": f"{r['fsn_pesq'] - r['s500_pesq']:+.4f}",
        }
        failure_table_rows.append(row)

    fail_csv_path = OUT_DIR / "STAGE7_FAILURE_CLIP_TABLE.csv"
    with open(fail_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(failure_table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(failure_table_rows)
    print(f"Wrote {fail_csv_path} with {len(failure_table_rows)} characterized failure/contrast clips.")

if __name__ == "__main__":
    main()

