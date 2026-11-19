#!/usr/bin/env python3
import csv
import numpy as np
from pathlib import Path

MANIFEST_P = Path("antigravity/runs/sih26052_canonical_validation/manifest.csv")
STEP500_P = Path("antigravity/runs/sih26052_candidate_step500_repro_20261113/per_clip.csv")
FULLSUBNET_P = Path("antigravity/runs/fullsubnet_baseline/per_clip.csv")
GTCRN_P = Path("antigravity/runs/gtcrn_dns3_canonical_20261113/per_clip.csv")

def load_dict(p):
    with open(p, "r", encoding="utf-8") as f:
        return {int(r["val_index"]): r for r in csv.DictReader(f)}

manifest = load_dict(MANIFEST_P)
s500 = load_dict(STEP500_P)
fsn = load_dict(FULLSUBNET_P)
gtcrn = load_dict(GTCRN_P)

records = []
for i in range(590):
    m = manifest[i]
    records.append({
        "val_index": i,
        "origin": m["dataset_origin"],
        "target_snr": float(m["target_snr"]),
        "s500_snr": float(s500[i]["output_snr_db"]),
        "s500_pesq": float(s500[i]["output_pesq_wb"]),
        "s500_joint": (float(s500[i]["output_snr_db"]) > 15.0 and float(s500[i]["output_stoi"]) > 0.85 and float(s500[i]["output_pesq_wb"]) > 2.5),
        "fsn_snr": float(fsn[i]["output_snr_db"]),
        "fsn_pesq": float(fsn[i]["output_pesq_wb"]),
        "fsn_joint": (float(fsn[i]["output_snr_db"]) > 15.0 and float(fsn[i]["output_stoi"]) > 0.85 and float(fsn[i]["output_pesq_wb"]) > 2.5),
        "gtcrn_snr": float(gtcrn[i]["output_snr_db"]),
        "gtcrn_pesq": float(gtcrn[i]["output_pesq_wb"]),
        "gtcrn_joint": (float(gtcrn[i]["output_snr_db"]) > 15.0 and float(gtcrn[i]["output_stoi"]) > 0.85 and float(gtcrn[i]["output_pesq_wb"]) > 2.5),
    })

hdr = f"{'Target SNR':12s} | {'Origin':15s} | {'N':3s} | {'S500 SNR':10s} | {'FSN SNR':10s} | {'GTCRN SNR':10s} | {'S500 PESQ':10s} | {'FSN PESQ':10s} | {'GTCRN PESQ':10s} | {'S500 JP':13s} | {'FSN JP':13s} | {'GTCRN JP':13s}"
print(hdr)
print("-" * len(hdr))

for snr in [-10.0, -5.0, 0.0, 5.0]:
    for orig in ["EXISTING_PROXY", "IoBT_GUNFIRE"]:
        sub = [r for r in records if r["target_snr"] == snr and r["origin"] == orig]
        n = len(sub)
        if n == 0: continue
        s_snr = np.mean([r["s500_snr"] for r in sub])
        f_snr = np.mean([r["fsn_snr"] for r in sub])
        g_snr = np.mean([r["gtcrn_snr"] for r in sub])
        s_pesq = np.mean([r["s500_pesq"] for r in sub])
        f_pesq = np.mean([r["fsn_pesq"] for r in sub])
        g_pesq = np.mean([r["gtcrn_pesq"] for r in sub])
        s_jp = sum(1 for r in sub if r["s500_joint"])
        f_jp = sum(1 for r in sub if r["fsn_joint"])
        g_jp = sum(1 for r in sub if r["gtcrn_joint"])
        print(f"{snr:+5.1f} dB     | {orig:15s} | {n:3d} | {s_snr:8.4f} dB | {f_snr:8.4f} dB | {g_snr:8.4f} dB | {s_pesq:8.4f} | {f_pesq:8.4f} | {g_pesq:8.4f} | {s_jp:2d}/{n:2d} ({s_jp/n*100:4.1f}%) | {f_jp:2d}/{n:2d} ({f_jp/n*100:4.1f}%) | {g_jp:2d}/{n:2d} ({g_jp/n*100:4.1f}%)")

print("-" * len(hdr))
for orig in ["EXISTING_PROXY", "IoBT_GUNFIRE"]:
    sub = [r for r in records if r["target_snr"] <= 0.0 and r["origin"] == orig]
    n = len(sub)
    s_snr = np.mean([r["s500_snr"] for r in sub])
    f_snr = np.mean([r["fsn_snr"] for r in sub])
    g_snr = np.mean([r["gtcrn_snr"] for r in sub])
    s_pesq = np.mean([r["s500_pesq"] for r in sub])
    f_pesq = np.mean([r["fsn_pesq"] for r in sub])
    g_pesq = np.mean([r["gtcrn_pesq"] for r in sub])
    s_jp = sum(1 for r in sub if r["s500_joint"])
    f_jp = sum(1 for r in sub if r["fsn_joint"])
    g_jp = sum(1 for r in sub if r["gtcrn_joint"])
    print(f"<= 0 dB total| {orig:15s} | {n:3d} | {s_snr:8.4f} dB | {f_snr:8.4f} dB | {g_snr:8.4f} dB | {s_pesq:8.4f} | {f_pesq:8.4f} | {g_pesq:8.4f} | {s_jp:2d}/{n:2d} ({s_jp/n*100:4.1f}%) | {f_jp:2d}/{n:2d} ({f_jp/n*100:4.1f}%) | {g_jp:2d}/{n:2d} ({g_jp/n*100:4.1f}%)")

