#!/usr/bin/env python3
import csv
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

def is_pass(row):
    return (float(row["output_snr_db"]) > 15.0 and float(row["output_stoi"]) > 0.85 and float(row["output_pesq_wb"]) > 2.5)

print("=== ONLY GTCRN PASSES ===")
for i in range(590):
    if is_pass(gtcrn[i]) and not is_pass(s500[i]) and not is_pass(fsn[i]):
        t_snr = float(manifest[i]["target_snr"])
        orig = manifest[i]["dataset_origin"]
        s_s = float(s500[i]["output_snr_db"])
        s_p = float(s500[i]["output_pesq_wb"])
        f_s = float(fsn[i]["output_snr_db"])
        f_p = float(fsn[i]["output_pesq_wb"])
        g_s = float(gtcrn[i]["output_snr_db"])
        g_p = float(gtcrn[i]["output_pesq_wb"])
        print(f"Clip {i:3d} (bin {t_snr:+5.1f} dB, {orig:15s}): S500=[SNR {s_s:5.2f}, PESQ {s_p:4.2f}] | FSN=[SNR {f_s:5.2f}, PESQ {f_p:4.2f}] | GTCRN=[SNR {g_s:5.2f}, PESQ {g_p:4.2f}]")

print("\n=== ONLY STEP-500 PASSES ===")
for i in range(590):
    if is_pass(s500[i]) and not is_pass(gtcrn[i]) and not is_pass(fsn[i]):
        t_snr = float(manifest[i]["target_snr"])
        orig = manifest[i]["dataset_origin"]
        s_s = float(s500[i]["output_snr_db"])
        s_p = float(s500[i]["output_pesq_wb"])
        f_s = float(fsn[i]["output_snr_db"])
        f_p = float(fsn[i]["output_pesq_wb"])
        g_s = float(gtcrn[i]["output_snr_db"])
        g_p = float(gtcrn[i]["output_pesq_wb"])
        print(f"Clip {i:3d} (bin {t_snr:+5.1f} dB, {orig:15s}): S500=[SNR {s_s:5.2f}, PESQ {s_p:4.2f}] | FSN=[SNR {f_s:5.2f}, PESQ {f_p:4.2f}] | GTCRN=[SNR {g_s:5.2f}, PESQ {g_p:4.2f}]")

print("\n=== ONLY FULLSUBNET PASSES (count summary by bin) ===")
fsn_only_bins = {}
for i in range(590):
    if is_pass(fsn[i]) and not is_pass(s500[i]) and not is_pass(gtcrn[i]):
        t_snr = float(manifest[i]["target_snr"])
        fsn_only_bins[t_snr] = fsn_only_bins.get(t_snr, 0) + 1
for b in sorted(fsn_only_bins.keys()):
    print(f"  {b:+5.1f} dB: {fsn_only_bins[b]} clips")

