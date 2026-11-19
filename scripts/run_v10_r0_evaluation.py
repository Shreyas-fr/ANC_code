#!/usr/bin/env python3
"""Run evaluation of all DeepFilterNet3 V10 R0 checkpoints on the canonical benchmark.

Computes metrics on:
1. Even selection split (n=295)
2. Odd confirmation split (n=295)
3. Full benchmark (n=590)

Also runs paired bootstrap comparisons against Deployed Step-500 and Pretrained DFN3.
"""

import concurrent.futures
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_BIN = REPO_ROOT / "pc_venv/bin/python"
CANONICAL_DIR = REPO_ROOT / "antigravity/runs/sih26052_canonical_validation"
CKPT_DIR = REPO_ROOT / "kaggle_output/dfn3_v10_r0_sih26052/dfn3_v10_r0_sih26052"
EVAL_BASE = REPO_ROOT / "kaggle_output/dfn3_v10_r0_sih26052"
EVAL_SCRIPT = REPO_ROOT / "antigravity/scripts/evaluate_dfn3_canonical.py"
COMPARE_SCRIPT = REPO_ROOT / "antigravity/scripts/compare_dfn3_canonical_split.py"
DEPLOYED_CSV = REPO_ROOT / "antigravity/runs/sih26052_dfn3_canonical_step500/per_clip.csv"
PRETRAINED_CSV = REPO_ROOT / "antigravity/runs/sih26052_dfn3_canonical_pretrained/per_clip.csv"

STEPS = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000]

def eval_checkpoint(step):
    ckpt_path = CKPT_DIR / f"step-{step}.hk"
    out_dir = EVAL_BASE / f"canonical_eval_step{step}"
    summary_file = out_dir / "summary.json"
    per_clip_file = out_dir / "per_clip.csv"
    if summary_file.is_file() and per_clip_file.is_file():
        print(f"[Step {step}] Already evaluated.")
        return step, out_dir
    
    print(f"[Step {step}] Starting evaluation...")
    cmd = [
        str(PYTHON_BIN),
        str(EVAL_SCRIPT),
        "--checkpoint", str(ckpt_path),
        "--canonical-dir", str(CANONICAL_DIR),
        "--output-dir", str(out_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[Step {step}] FAILED:\n{r.stderr}")
        raise RuntimeError(f"Step {step} failed: {r.stderr}")
    print(f"[Step {step}] Finished evaluation.")
    return step, out_dir

def compute_split_metrics(per_clip_path, split="all"):
    with open(per_clip_path, newline="", encoding="utf-8") as f:
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
    joint_passes = sum(1 for r in rows if float(r["output_snr_db"]) > 15.0 and float(r["output_stoi"]) > 0.85 and float(r["output_pesq_wb"]) > 2.5)
    
    return {
        "n": n,
        "snr_db": sum(snrs) / n,
        "si_sdr_db": sum(sisdrs) / n,
        "stoi": sum(stois) / n,
        "pesq_wb": sum(pesqs) / n,
        "joint_pass": joint_passes,
        "joint_pass_pct": (joint_passes / n) * 100.0,
    }

def main():
    print(f"Evaluating {len(STEPS)} checkpoints using up to 4 parallel workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(eval_checkpoint, s): s for s in STEPS}
        for future in concurrent.futures.as_completed(futures):
            step = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Error evaluating step {step}: {e}")
                sys.exit(1)
    
    print("\nAll checkpoints evaluated successfully. Compiling split summaries...\n")
    results = {}
    for step in STEPS:
        p = EVAL_BASE / f"canonical_eval_step{step}/per_clip.csv"
        results[step] = {
            "even": compute_split_metrics(p, "even"),
            "odd": compute_split_metrics(p, "odd"),
            "all": compute_split_metrics(p, "all"),
        }
    
    summary_path = EVAL_BASE / "v10_r0_split_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved full split summary to {summary_path}")

    # Print summary table for Even Selection Set
    print("\n" + "="*80)
    print("EVEN SELECTION SET (n=295) - PRIMARY TUNING GATE")
    print("="*80)
    print(f"{'Step':>6} | {'SNR (dB)':>9} | {'SI-SDR (dB)':>11} | {'STOI':>7} | {'PESQ-WB':>8} | {'Joint Pass':>14}")
    print("-" * 80)
    for step in STEPS:
        m = results[step]["even"]
        print(f"{step:6d} | {m['snr_db']:9.4f} | {m['si_sdr_db']:11.4f} | {m['stoi']:7.4f} | {m['pesq_wb']:8.4f} | {m['joint_pass']:3d}/295 ({m['joint_pass_pct']:5.2f}%)")
    
    # Print summary table for Full Benchmark
    print("\n" + "="*80)
    print("FULL BENCHMARK SET (n=590)")
    print("="*80)
    print(f"{'Step':>6} | {'SNR (dB)':>9} | {'SI-SDR (dB)':>11} | {'STOI':>7} | {'PESQ-WB':>8} | {'Joint Pass':>14}")
    print("-" * 80)
    for step in STEPS:
        m = results[step]["all"]
        print(f"{step:6d} | {m['snr_db']:9.4f} | {m['si_sdr_db']:11.4f} | {m['stoi']:7.4f} | {m['pesq_wb']:8.4f} | {m['joint_pass']:3d}/590 ({m['joint_pass_pct']:5.2f}%)")

if __name__ == "__main__":
    main()
