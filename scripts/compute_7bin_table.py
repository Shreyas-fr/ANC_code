#!/usr/bin/env python3
import csv
from pathlib import Path

def load_csv(p):
    with open(p, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

dep_rows = load_csv("antigravity/runs/sih26052_dfn3_canonical_step500/per_clip.csv")
r0_550_rows = load_csv("kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step550/per_clip.csv")

bins = [-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]

print(f"{'Target SNR Bin':15s} | {'N':4s} | {'Deployed SNR':12s} | {'R0-550 SNR':12s} | {'Delta SNR':10s} | {'Dep SI-SDR':10s} | {'R0 SI-SDR':10s} | {'Dep STOI':8s} | {'R0 STOI':8s} | {'Dep PESQ':8s} | {'R0 PESQ':8s} | {'Dep JP':6s} | {'R0 JP':6s}")
print("-" * 150)

for b in bins:
    d_sub = [r for r in dep_rows if float(r["target_snr_db"]) == b]
    r_sub = [r for r in r0_550_rows if float(r["target_snr_db"]) == b]
    n = len(d_sub)
    
    d_snr = sum(float(r["output_snr_db"]) for r in d_sub) / n
    r_snr = sum(float(r["output_snr_db"]) for r in r_sub) / n
    delta_snr = r_snr - d_snr
    
    d_sisdr = sum(float(r["output_si_sdr_db"]) for r in d_sub) / n
    r_sisdr = sum(float(r["output_si_sdr_db"]) for r in r_sub) / n
    
    d_stoi = sum(float(r["output_stoi"]) for r in d_sub) / n
    r_stoi = sum(float(r["output_stoi"]) for r in r_sub) / n
    
    d_pesq = sum(float(r["output_pesq_wb"]) for r in d_sub) / n
    r_pesq = sum(float(r["output_pesq_wb"]) for r in r_sub) / n
    
    d_jp = sum(1 for r in d_sub if float(r["output_snr_db"]) > 15.0 and float(r["output_stoi"]) > 0.85 and float(r["output_pesq_wb"]) > 2.5)
    r_jp = sum(1 for r in r_sub if float(r["output_snr_db"]) > 15.0 and float(r["output_stoi"]) > 0.85 and float(r["output_pesq_wb"]) > 2.5)
    
    print(f"{b:+5.1f} dB         | {n:4d} | {d_snr:10.4f} dB | {r_snr:10.4f} dB | {delta_snr:+9.4f} dB | {d_sisdr:9.4f} | {r_sisdr:9.4f} | {d_stoi:8.4f} | {r_stoi:8.4f} | {d_pesq:8.4f} | {r_pesq:8.4f} | {d_jp:3d}/{n:2d} | {r_jp:3d}/{n:2d}")

