#!/usr/bin/env python3
"""
Executes the automated evaluation suite using `anc-process` on the synthesized 30mm spatial benchmark clips.
Parses SI-SDR, SNR improvements, and RTF, and generates a formatted Markdown compliance report.
"""

import os
import glob
import re
import subprocess
import argparse
import numpy as np

def run_evaluation(aggressive: bool = False, model: str = "gtcrn"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bench_dir = os.path.join(base_dir, "data", "eval", "benchmarks")
    enhanced_dir = os.path.join(base_dir, "data", "eval", "enhanced")
    os.makedirs(enhanced_dir, exist_ok=True)

    # First compile release binary
    print("Building anc-process in release mode (LTO + O3)...")
    res = subprocess.run(["cargo", "build", "--release", "--bin", "anc-process"], cwd=base_dir)
    if res.returncode != 0:
        print("Build failed!")
        return

    bin_path = os.path.join(base_dir, "target", "release", "anc-process")

    stereo_files = sorted(glob.glob(os.path.join(bench_dir, "*_stereo.wav")))
    if not stereo_files:
        print("No benchmark clips found in", bench_dir)
        return

    mode_str = "Aggressive Max SNR Mode" if aggressive else f"Standard Intelligibility Mode (Neural: {model.upper()})"
    print(f"\nOptimization Mode: {mode_str}")
    print(f"Found {len(stereo_files)} benchmark clips. Beginning batch evaluation...\n")

    results = []

    for idx, s_path in enumerate(stereo_files):
        clip_name = os.path.basename(s_path).replace("_stereo.wav", "")
        ref_path = os.path.join(bench_dir, f"{clip_name}_clean_ref.wav")
        out_path = os.path.join(enhanced_dir, f"{clip_name}_enhanced.wav")

        if not os.path.exists(ref_path):
            continue

        cmd = [
            bin_path,
            "--input", s_path,
            "--clean-ref", ref_path,
            "--output", out_path,
            "--model", model,
            "--n-fft", "512",
            "--hop-size", "256",
        ]
        if aggressive:
            cmd.append("--aggressive-snr")

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = proc.stdout

        # Parse metrics from stdout
        # e.g.:
        # Processing complete in 0.02 s (RTF: 0.0034, 294.1x real-time)
        # Input SI-SDR:     -5.02 dB
        # Output SI-SDR:    12.45 dB (Delta: +17.47 dB)
        # Input SNR:        -4.98 dB
        # Output SNR:       14.12 dB (Delta: +19.10 dB)

        in_sisdr_match = re.search(r"Input SI-SDR:\s+([-\d\.]+)\s+dB", output)
        out_sisdr_match = re.search(r"Output SI-SDR:\s+([-\d\.]+)\s+dB", output)
        in_snr_match = re.search(r"Input SNR:\s+([-\d\.]+)\s+dB", output)
        out_snr_match = re.search(r"Output SNR:\s+([-\d\.]+)\s+dB", output)
        rtf_match = re.search(r"RTF:\s+([\d\.]+)", output)

        if in_sisdr_match and out_sisdr_match and in_snr_match and out_snr_match:
            in_sisdr = float(in_sisdr_match.group(1))
            out_sisdr = float(out_sisdr_match.group(1))
            in_snr = float(in_snr_match.group(1))
            out_snr = float(out_snr_match.group(1))
            rtf = float(rtf_match.group(1)) if rtf_match else 0.001

            delta_sisdr = out_sisdr - in_sisdr
            delta_snr = out_snr - in_snr

            # Parse noise name and target snr
            parts = clip_name.split("_")
            speech = parts[0]
            noise = parts[1]
            snr_tag = parts[2]

            results.append({
                "clip": clip_name,
                "speech": speech,
                "noise": noise,
                "snr_tag": snr_tag,
                "in_sisdr": in_sisdr,
                "out_sisdr": out_sisdr,
                "delta_sisdr": delta_sisdr,
                "in_snr": in_snr,
                "out_snr": out_snr,
                "delta_snr": delta_snr,
                "rtf": rtf,
            })

            print(f"[{idx+1:02d}/{len(stereo_files):02d}] {clip_name:<35} | SNR: {in_snr:>5.1f} -> {out_snr:>5.1f} dB ({delta_snr:>+5.1f} dB) | SI-SDR: {in_sisdr:>5.1f} -> {out_sisdr:>5.1f} dB ({delta_sisdr:>+5.1f} dB) | RTF: {rtf:.4f}")

    if not results:
        print("No valid results parsed.")
        return

    # Aggregate statistics
    mean_in_snr = np.mean([r["in_snr"] for r in results])
    mean_out_snr = np.mean([r["out_snr"] for r in results])
    mean_delta_snr = np.mean([r["delta_snr"] for r in results])

    mean_in_sisdr = np.mean([r["in_sisdr"] for r in results])
    mean_out_sisdr = np.mean([r["out_sisdr"] for r in results])
    mean_delta_sisdr = np.mean([r["delta_sisdr"] for r in results])

    mean_rtf = np.mean([r["rtf"] for r in results])

    print("\n" + "="*80)
    print("                     EVALUATION SUITE BENCHMARK SUMMARY")
    print("="*80)
    print(f"Total Evaluated Clips:        {len(results)}")
    print(f"Mean Input SNR:              {mean_in_snr:>6.2f} dB")
    print(f"Mean Enhanced Output SNR:    {mean_out_snr:>6.2f} dB")
    print(f"Mean Overall SNR Gain:       {mean_delta_snr:>+6.2f} dB")
    print(f"Mean Input SI-SDR:           {mean_in_sisdr:>6.2f} dB")
    print(f"Mean Enhanced Output SI-SDR: {mean_out_sisdr:>6.2f} dB")
    print(f"Mean Overall SI-SDR Gain:    {mean_delta_sisdr:>+6.2f} dB")
    print(f"Mean Edge Compute RTF:       {mean_rtf:>6.4f} ({1.0/mean_rtf:.1f}x real-time)")
    print("="*80)

    # Breakdown by Noise Type
    print("\n### Performance Breakdown by Noise Environment\n")
    print("| Noise Category | Clips | Input SNR | Output SNR | Δ SNR Gain | Input SI-SDR | Output SI-SDR | Δ SI-SDR Gain | RTF |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    noises = sorted(list(set(r["noise"] for r in results)))
    for n in noises:
        sub = [r for r in results if r["noise"] == n]
        m_in_snr = np.mean([r["in_snr"] for r in sub])
        m_out_snr = np.mean([r["out_snr"] for r in sub])
        m_d_snr = np.mean([r["delta_snr"] for r in sub])
        m_in_si = np.mean([r["in_sisdr"] for r in sub])
        m_out_si = np.mean([r["out_sisdr"] for r in sub])
        m_d_si = np.mean([r["delta_sisdr"] for r in sub])
        m_rtf = np.mean([r["rtf"] for r in sub])
        print(f"| {n:<14} | {len(sub):^5} | {m_in_snr:>7.2f} dB | {m_out_snr:>8.2f} dB | {m_d_snr:>+8.2f} dB | {m_in_si:>10.2f} dB | {m_out_si:>11.2f} dB | {m_d_si:>+11.2f} dB | {m_rtf:.4f} |")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate 30mm spatial ANC benchmark suite")
    parser.add_argument("--aggressive", action="store_true", help="Enable Aggressive Max SNR mode")
    parser.add_argument("--model", type=str, default="gtcrn", choices=["gtcrn", "fullsubnet", "dfn3", "ensemble", "spectral"], help="Neural enhancement model to evaluate")
    args = parser.parse_args()
    run_evaluation(aggressive=args.aggressive, model=args.model)
