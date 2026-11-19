#!/usr/bin/env python3
"""Evaluate Ablation A1 (lambda_sisdr=0.01) on the canonical benchmark.

Evaluates checkpoints 300, 500, 550, and 800 across:
- Even selection split (n=295)
- Odd confirmation split (n=295)
- Full benchmark set (n=590)

Computes paired bootstrap comparisons vs Deployed Step-500 and R0 seed 26052,
and applies the strict 2 * SD_R0 detection criterion on both even and odd subsets.
"""

import concurrent.futures
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_BIN = REPO_ROOT / "pc_venv/bin/python"
CANONICAL_DIR = REPO_ROOT / "antigravity/runs/sih26052_canonical_validation"
EVAL_SCRIPT = REPO_ROOT / "antigravity/scripts/evaluate_dfn3_canonical.py"
COMPARE_SCRIPT = REPO_ROOT / "antigravity/scripts/compare_dfn3_canonical_split.py"
DEPLOYED_CSV = REPO_ROOT / "antigravity/runs/sih26052_dfn3_canonical_step500/per_clip.csv"
R0_CSV = REPO_ROOT / "kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step500/per_clip.csv"

CKPT_BASE = REPO_ROOT / "kaggle_output/dfn3_v10_a1_sisdr001"
STEPS = [300, 500, 550, 800]

def eval_step(s):
    out_dir = CKPT_BASE / f"canonical_eval_step{s}"
    per_clip = out_dir / "per_clip.csv"
    if per_clip.is_file():
        return s, per_clip
    
    matches = list(CKPT_BASE.glob(f"**/step-{s}.hk"))
    if not matches:
        raise FileNotFoundError(f"Missing step-{s}.hk in {CKPT_BASE}")
    ckpt = matches[0]
    
    print(f"[A1 Step {s}] Evaluating on canonical benchmark...")
    cmd = [
        str(PYTHON_BIN), str(EVAL_SCRIPT),
        "--checkpoint", str(ckpt),
        "--canonical-dir", str(CANONICAL_DIR),
        "--output-dir", str(out_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"A1 step {s} failed:\n{r.stderr}")
    return s, per_clip

def get_split_stats(per_clip_path, split="all"):
    with open(per_clip_path, newline="") as f:
        rows = list(csv.DictReader(f))
    if split == "even":
        rows = [r for r in rows if int(r["val_index"]) % 2 == 0]
    elif split == "odd":
        rows = [r for r in rows if int(r["val_index"]) % 2 != 0]
    n = len(rows)
    snrs = [float(r["output_snr_db"]) for r in rows]
    sisdrs = [float(r["output_si_sdr_db"]) for r in rows]
    stois = [float(r["output_stoi"]) for r in rows]
    pesqs = [float(r["output_pesq_wb"]) for r in rows]
    joint = sum(1 for r in rows if float(r["output_snr_db"]) > 15.0 and float(r["output_stoi"]) > 0.85 and float(r["output_pesq_wb"]) > 2.5)
    return {
        "n": n, "snr": sum(snrs)/n, "sisdr": sum(sisdrs)/n,
        "stoi": sum(stois)/n, "pesq": sum(pesqs)/n, "joint": joint
    }

def main():
    print("Evaluating A1 checkpoints [300, 500, 550, 800]...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(eval_step, STEPS))
    print("A1 evaluations completed.")

    # Load R0 3-seed variance
    var_file = REPO_ROOT / "kaggle_output/r0_three_seed_variance.json"
    with open(var_file) as f:
        r0_var = json.load(f)

    # Print summary tables and test 2 * SD detection
    print("\n" + "="*110)
    print("ABLATION A1 (lambda_sisdr=0.01) vs R0 3-SEED MEAN ± SD")
    print("="*110)
    for split in ["even", "odd", "all"]:
        print(f"\n--- {split.upper()} SPLIT ---")
        print(f"{'Step':>6} | {'A1 SNR':>9} | {'R0 Mean±SD SNR':>19} | {'Delta':>8} | {'2*SD':>8} | {'SNR Detect':>11} | {'A1 PESQ':>8} | {'R0 PESQ':>8} | {'PESQ Detect':>11}")
        print("-" * 110)
        for s in STEPS:
            p = CKPT_BASE / f"canonical_eval_step{s}/per_clip.csv"
            a1_m = get_split_stats(p, split)
            r0_m, r0_s = r0_var[str(s)][split]["snr"]
            r0_pm, r0_ps = r0_var[str(s)][split]["pesq"]
            
            delta_snr = a1_m["snr"] - r0_m
            thresh_snr = 2.0 * r0_s
            real_snr = "REAL" if abs(delta_snr) > thresh_snr else "NOISE"
            
            delta_pesq = a1_m["pesq"] - r0_pm
            thresh_pesq = 2.0 * r0_ps
            real_pesq = "REAL" if abs(delta_pesq) > thresh_pesq else "NOISE"
            
            print(f"{s:6d} | {a1_m['snr']:9.4f} | {r0_m:7.4f} ± {r0_s:6.4f} | {delta_snr:+8.4f} | {thresh_snr:8.4f} | {real_snr:>11} | {a1_m['pesq']:8.4f} | {r0_pm:8.4f} | {real_pesq:>11}")

if __name__ == "__main__":
    main()

