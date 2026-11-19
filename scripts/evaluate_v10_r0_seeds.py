#!/usr/bin/env python3
"""Evaluate checkpoints 300, 500, 550, and 800 for R0 seeds (26052, 26053, 26054).

Computes across-seed mean and sample standard deviation on:
- Even selection split (n=295)
- Odd confirmation split (n=295)
- Full benchmark set (n=590)

Defines the empirical noise floor as 2 * sample_std across the 3 runs.
"""

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

STEPS = [300, 500, 550, 800]
SEEDS = [26052, 26053, 26054]

def eval_ckpt_if_needed(seed, step):
    base_dir = REPO_ROOT / f"kaggle_output/dfn3_v10_r0_sih26052" if seed == 26052 else REPO_ROOT / f"kaggle_output/dfn3_v10_r0_s{seed}"
    out_dir = base_dir / f"canonical_eval_step{step}"
    per_clip_file = out_dir / "per_clip.csv"
    if per_clip_file.is_file():
        return per_clip_file
    
    matches = list(base_dir.glob(f"**/step-{step}.hk"))
    if not matches:
        raise FileNotFoundError(f"Missing checkpoint step-{step}.hk in {base_dir}")
    ckpt_path = matches[0]
    
    print(f"[Seed {seed} | Step {step}] Evaluating on canonical set ({ckpt_path.name})...")
    cmd = [
        str(PYTHON_BIN), str(EVAL_SCRIPT),
        "--checkpoint", str(ckpt_path),
        "--canonical-dir", str(CANONICAL_DIR),
        "--output-dir", str(out_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Eval failed for seed {seed} step {step}:\n{r.stderr}")
    return per_clip_file

def get_metrics_for_split(per_clip_path, split="all"):
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
        "n": n,
        "snr": sum(snrs) / n,
        "sisdr": sum(sisdrs) / n,
        "stoi": sum(stois) / n,
        "pesq": sum(pesqs) / n,
        "joint": joint,
    }

def mean_std(vals):
    n = len(vals)
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / (n - 1) if n > 1 else 0.0
    s = math.sqrt(var)
    return m, s

def main():
    print("Evaluating required seeds and checkpoints...")
    for seed in SEEDS:
        for step in STEPS:
            eval_ckpt_if_needed(seed, step)
    
    print("\nAll checkpoints evaluated. Calculating 3-seed statistics...\n")
    data = {}
    for step in STEPS:
        data[step] = {}
        for split in ["even", "odd", "all"]:
            metrics_list = []
            for seed in SEEDS:
                if seed == 26052:
                    p = REPO_ROOT / f"kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step{step}/per_clip.csv"
                else:
                    p = REPO_ROOT / f"kaggle_output/dfn3_v10_r0_s{seed}/canonical_eval_step{step}/per_clip.csv"
                metrics_list.append(get_metrics_for_split(p, split))
            
            snr_m, snr_s = mean_std([m["snr"] for m in metrics_list])
            sisdr_m, sisdr_s = mean_std([m["sisdr"] for m in metrics_list])
            stoi_m, stoi_s = mean_std([m["stoi"] for m in metrics_list])
            pesq_m, pesq_s = mean_std([m["pesq"] for m in metrics_list])
            joint_m, joint_s = mean_std([m["joint"] for m in metrics_list])
            
            data[step][split] = {
                "snr": (snr_m, snr_s),
                "sisdr": (sisdr_m, sisdr_s),
                "stoi": (stoi_m, stoi_s),
                "pesq": (pesq_m, pesq_s),
                "joint": (joint_m, joint_s),
            }

    out_file = REPO_ROOT / "kaggle_output/r0_three_seed_variance.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved variance data to {out_file}\n")

    for split in ["even", "odd", "all"]:
        print("="*90)
        print(f"R0 3-SEED MEAN ± SD ({split.upper()} SPLIT)")
        print("="*90)
        print(f"{'Step':>6} | {'SNR (dB)':>18} | {'SI-SDR (dB)':>18} | {'STOI':>16} | {'PESQ-WB':>16} | {'Joint Pass':>16}")
        print("-" * 90)
        for step in STEPS:
            d = data[step][split]
            print(f"{step:6d} | {d['snr'][0]:7.4f} ± {d['snr'][1]:6.4f} | {d['sisdr'][0]:7.4f} ± {d['sisdr'][1]:6.4f} | {d['stoi'][0]:6.4f} ± {d['stoi'][1]:6.4f} | {d['pesq'][0]:6.4f} ± {d['pesq'][1]:6.4f} | {d['joint'][0]:5.1f} ± {d['joint'][1]:4.1f}")
        print()

if __name__ == "__main__":
    main()

