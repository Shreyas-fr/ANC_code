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

low_snr_ids = [i for i in range(590) if float(manifest[i]["target_snr"]) <= 0.0]

def print_clip(i, note):
    t_snr = float(manifest[i]["target_snr"])
    orig = manifest[i]["dataset_origin"]
    s_s = float(s500[i]["output_snr_db"])
    s_p = float(s500[i]["output_pesq_wb"])
    s_st = float(s500[i]["output_stoi"])
    f_s = float(fsn[i]["output_snr_db"])
    f_p = float(fsn[i]["output_pesq_wb"])
    f_st = float(fsn[i]["output_stoi"])
    g_s = float(gtcrn[i]["output_snr_db"])
    g_p = float(gtcrn[i]["output_pesq_wb"])
    g_st = float(gtcrn[i]["output_stoi"])
    print(f"Clip {i:3d} (bin {t_snr:+5.1f} dB, {orig:15s}) [{note}]:")
    print(f"  Step-500  : SNR={s_s:6.2f} dB, SI-SDR={float(s500[i]['output_si_sdr_db']):6.2f} dB, STOI={s_st:.4f}, PESQ={s_p:.4f}")
    print(f"  FullSubNet: SNR={f_s:6.2f} dB, SI-SDR={float(fsn[i]['output_si_sdr_db']):6.2f} dB, STOI={f_st:.4f}, PESQ={f_p:.4f}")
    print(f"  GTCRN     : SNR={g_s:6.2f} dB, SI-SDR={float(gtcrn[i]['output_si_sdr_db']):6.2f} dB, STOI={g_st:.4f}, PESQ={g_p:.4f}")

print("=== TOP 5 GTCRN SNR IMPROVEMENTS OVER STEP-500 IN LOW-SNR (<= 0 dB) ===")
by_gtcrn_gain = sorted(low_snr_ids, key=lambda i: float(gtcrn[i]["output_snr_db"]) - float(s500[i]["output_snr_db"]), reverse=True)[:5]
for i in by_gtcrn_gain:
    d = float(gtcrn[i]["output_snr_db"]) - float(s500[i]["output_snr_db"])
    print_clip(i, f"Delta_SNR = {d:+6.2f} dB")

print("\n=== TOP 5 GTCRN SNR REGRESSIONS VS STEP-500 IN LOW-SNR (<= 0 dB) ===")
by_gtcrn_loss = sorted(low_snr_ids, key=lambda i: float(gtcrn[i]["output_snr_db"]) - float(s500[i]["output_snr_db"]))[:5]
for i in by_gtcrn_loss:
    d = float(gtcrn[i]["output_snr_db"]) - float(s500[i]["output_snr_db"])
    print_clip(i, f"Delta_SNR = {d:+6.2f} dB")

print("\n=== TOP 5 FULLSUBNET PESQ IMPROVEMENTS OVER STEP-500 IN LOW-SNR (<= 0 dB) ===")
by_fsn_pesq_gain = sorted(low_snr_ids, key=lambda i: float(fsn[i]["output_pesq_wb"]) - float(s500[i]["output_pesq_wb"]), reverse=True)[:5]
for i in by_fsn_pesq_gain:
    d = float(fsn[i]["output_pesq_wb"]) - float(s500[i]["output_pesq_wb"])
    print_clip(i, f"Delta_PESQ = {d:+5.2f}")

print("\n=== TOP 5 FULLSUBNET PESQ REGRESSIONS VS STEP-500 IN LOW-SNR (<= 0 dB) ===")
by_fsn_pesq_loss = sorted(low_snr_ids, key=lambda i: float(fsn[i]["output_pesq_wb"]) - float(s500[i]["output_pesq_wb"]))[:5]
for i in by_fsn_pesq_loss:
    d = float(fsn[i]["output_pesq_wb"]) - float(s500[i]["output_pesq_wb"])
    print_clip(i, f"Delta_PESQ = {d:+5.2f}")

