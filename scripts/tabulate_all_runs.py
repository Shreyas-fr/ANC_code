#!/usr/bin/env python3
import csv
from pathlib import Path

runs = [
    ("Deployed Step-500", Path("antigravity/runs/sih26052_dfn3_canonical_step500/per_clip.csv")),
    ("R0 s26052 ckpt300", Path("kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step300/per_clip.csv")),
    ("R0 s26052 ckpt500", Path("kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step500/per_clip.csv")),
    ("R0 s26052 ckpt550", Path("kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step550/per_clip.csv")),
    ("R0 s26052 ckpt800", Path("kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step800/per_clip.csv")),
    ("R0 s26053 ckpt300", Path("kaggle_output/dfn3_v10_r0_s26053/canonical_eval_step300/per_clip.csv")),
    ("R0 s26053 ckpt500", Path("kaggle_output/dfn3_v10_r0_s26053/canonical_eval_step500/per_clip.csv")),
    ("R0 s26053 ckpt550", Path("kaggle_output/dfn3_v10_r0_s26053/canonical_eval_step550/per_clip.csv")),
    ("R0 s26053 ckpt800", Path("kaggle_output/dfn3_v10_r0_s26053/canonical_eval_step800/per_clip.csv")),
    ("R0 s26054 ckpt300", Path("kaggle_output/dfn3_v10_r0_s26054/canonical_eval_step300/per_clip.csv")),
    ("R0 s26054 ckpt500", Path("kaggle_output/dfn3_v10_r0_s26054/canonical_eval_step500/per_clip.csv")),
    ("R0 s26054 ckpt550", Path("kaggle_output/dfn3_v10_r0_s26054/canonical_eval_step550/per_clip.csv")),
    ("R0 s26054 ckpt800", Path("kaggle_output/dfn3_v10_r0_s26054/canonical_eval_step800/per_clip.csv")),
    ("A1 s26052 ckpt300", Path("kaggle_output/dfn3_v10_a1_sisdr001/canonical_eval_step300/per_clip.csv")),
    ("A1 s26052 ckpt500", Path("kaggle_output/dfn3_v10_a1_sisdr001/canonical_eval_step500/per_clip.csv")),
    ("A1 s26052 ckpt550", Path("kaggle_output/dfn3_v10_a1_sisdr001/canonical_eval_step550/per_clip.csv")),
    ("A1 s26052 ckpt800", Path("kaggle_output/dfn3_v10_a1_sisdr001/canonical_eval_step800/per_clip.csv")),
]

def load_rows(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

for name, path in runs:
    if not path.exists():
        print(f"MISSING: {name} at {path}")
        continue
    rows = load_rows(path)
    for split_name in ["Even", "Odd", "All"]:
        if split_name == "Even":
            sub = [r for r in rows if int(r["val_index"]) % 2 == 0]
        elif split_name == "Odd":
            sub = [r for r in rows if int(r["val_index"]) % 2 == 1]
        else:
            sub = rows
        tot = len(sub)
        snr = sum(float(r["output_snr_db"]) for r in sub) / tot
        sisdr = sum(float(r["output_si_sdr_db"]) for r in sub) / tot
        stoi = sum(float(r["output_stoi"]) for r in sub) / tot
        pesq = sum(float(r["output_pesq_wb"]) for r in sub) / tot
        jp = sum(1 for r in sub if float(r["output_snr_db"]) > 15.0 and float(r["output_stoi"]) > 0.85 and float(r["output_pesq_wb"]) > 2.5)
        print(f"{name:18s} | {split_name:4s} | SNR: {snr:7.4f} | SI-SDR: {sisdr:7.4f} | STOI: {stoi:.4f} | PESQ: {pesq:.4f} | JP: {jp:3d}/{tot}")

