#!/usr/bin/env python3
"""Consolidate R0 3-seed baseline variance and ablation results.

Applies the strict detection rule:
An ablation effect is marked 'REAL' only if its magnitude exceeds 2 * SD_R0
on BOTH even and odd development subsets. Otherwise it is marked 'INCONCLUSIVE'.
"""

import csv
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VAR_JSON = REPO_ROOT / "kaggle_output/r0_three_seed_variance.json"
STEPS = [300, 500, 550, 800]

def get_split_metrics(per_clip_path, split="all"):
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
    if not VAR_JSON.is_file():
        print("Waiting for r0_three_seed_variance.json...")
        return
    
    with open(VAR_JSON) as f:
        r0_var = json.load(f)
    
    print("="*100)
    print("R0 3-SEED NOISE FLOOR (2 * SD) AND ABLATION COMPARISON")
    print("="*100)

if __name__ == "__main__":
    main()

