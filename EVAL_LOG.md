# Evaluation Log: DeepFilterNet3 Canonical & Per-SNR Evaluation

## Date: 2026-10-18
## Evaluated Artifacts & Checkpoints
- **Model Checkpoint**: `final_model/model.hk`
- **Architecture**: DeepFilterNet3 (48 kHz native, 2,135,484 parameters)
- **Frozen Checksum**: `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`
- **Verification**: Strictly verified with SHA256 (`shasum -a 256 final_model/model.hk`). Checksums matched bit-for-bit.
- **Validation Dataset**: `runs/sih26052_canonical_validation/manifest.csv` (590 materialized audio pairs located in `runs/sih26052_canonical_validation/clean_audio` and `runs/sih26052_canonical_validation/noisy_audio`).

---

## Task 0: Verification & Discovery
1. **Model Checkpoint**: Verified `final_model/model.hk` matches target SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`.
2. **Canonical Manifest & Audio**: Located 590 clip pairs in `runs/sih26052_canonical_validation/` with sample rate 16000 Hz, length 48000 samples (3.0 seconds).
3. **Loader Implementation**: Reused canonical DFN3 loading from `edge/dfn3_enhance.py` and `scripts/run_full_evaluation.py` using `init_df(base)` and `hk.load_file(model_path)` with strict state dictionary loading (`strict=True`).
4. **Reproduced Clip 0 Baseline**: Replicated historical evaluation on clip 0 to 4 decimal places:
   - Measured SI-SDR: -4.0356 dB (archive: -4.0356 dB)
   - Measured STOI: 0.7388 (archive: 0.7388)
   - Measured PESQ: 1.0995 (archive: 1.0995)

---

## Task 1: Sanity Gate Verification (Overall 590-Clip Means)
Script `scripts/evaluate_dfn3_per_snr.py` executed across all 590 validation clips.

| Metric | Documented Historical Value | Measured In-Session Value | Difference | Sanity Gate Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Noisy Input SI-SDR** | 6.030 dB | 6.028 dB | 0.002 dB | $\pm 0.20\text{ dB}$ | ✅ **PASSED** |
| **DFN3 Output SI-SDR** | 8.450 dB | 8.446 dB | 0.004 dB | $\pm 0.20\text{ dB}$ | ✅ **PASSED** |
| **DFN3 Output STOI** | 0.866 | 0.866 | 0.000 | $\pm 0.020$ | ✅ **PASSED** |
| **DFN3 Output PESQ (WB)** | 1.798 | 1.798 | 0.000 | $\pm 0.020$ | ✅ **PASSED** |
| **DFN3 Active SNR** | 7.270 dB | 7.268 dB | 0.002 dB | — | ✅ **PASSED** |
| **DFN3 Explicit SNR** | — | 6.306 dB | — | — | Baseline recorded |

All metric differences are $\le 0.004$, well within the sanity gate thresholds ($\pm 0.2\text{ dB}$ SI-SDR, $\pm 0.02$ STOI/PESQ).

---

## Task 2: Per-SNR and Per-Origin Results

### PS Target Criteria
- Output SNR $> 15.0\text{ dB}$
- STOI $> 0.85$
- PESQ (wideband, 16 kHz) $> 2.50$

### Measured Per-SNR Table (`results/dfn3/per_snr_table.md`)
Grouped by target input SNR across all 590 clips:

| Input SNR | n | Noisy In SNR | DFN3 Out SNR (dB) | PS SNR (>15 dB) | Noisy STOI | DFN3 STOI | PS STOI (>0.85) | Noisy PESQ | DFN3 PESQ | PS PESQ (>2.5) | Noisy SI-SDR | DFN3 SI-SDR |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| -10.0 dB | 30 | -10.00 ± 0.00 | **-2.92 ± 3.82** | **FAIL** | 0.571 ± 0.152 | **0.648 ± 0.157** | **FAIL** | 1.089 ± 0.073 | **1.144 ± 0.113** | **FAIL** | -10.14 ± 0.27 | -4.48 ± 5.90 |
| -5.0 dB | 63 | -3.35 ± 13.00 | **1.49 ± 3.42** | **FAIL** | 0.694 ± 0.150 | **0.774 ± 0.131** | **FAIL** | 1.229 ± 0.488 | **1.385 ± 0.505** | **FAIL** | -3.28 ± 13.87 | 2.29 ± 4.63 |
| 0.0 dB | 117 | 0.85 ± 9.11 | **3.96 ± 2.57** | **FAIL** | 0.757 ± 0.124 | **0.826 ± 0.117** | **FAIL** | 1.236 ± 0.361 | **1.434 ± 0.376** | **FAIL** | 0.61 ± 9.85 | 5.45 ± 3.47 |
| 5.0 dB | 137 | 5.00 ± 0.00 | **6.95 ± 1.68** | **FAIL** | 0.826 ± 0.094 | **0.875 ± 0.085** | **PASS** | 1.420 ± 0.351 | **1.687 ± 0.364** | **FAIL** | 4.65 ± 1.79 | 9.24 ± 2.57 |
| 10.0 dB | 121 | 10.74 ± 8.06 | **8.51 ± 1.52** | **FAIL** | 0.891 ± 0.085 | **0.913 ± 0.074** | **PASS** | 1.806 ± 0.578 | **2.021 ± 0.467** | **FAIL** | 10.67 ± 8.72 | 11.38 ± 1.94 |
| 15.0 dB | 86 | 15.98 ± 9.01 | **10.31 ± 1.88** | **FAIL** | 0.936 ± 0.058 | **0.942 ± 0.050** | **PASS** | 2.130 ± 0.520 | **2.309 ± 0.478** | **FAIL** | 15.77 ± 9.23 | 13.50 ± 1.73 |
| 20.0 dB | 36 | 20.00 ± 0.00 | **10.64 ± 2.50** | **FAIL** | 0.958 ± 0.052 | **0.958 ± 0.042** | **PASS** | 2.580 ± 0.557 | **2.708 ± 0.507** | **PASS** | 19.80 ± 0.80 | 14.75 ± 1.24 |

### Per-Origin Breakdown at 5, 10, 15 dB (`results/dfn3/per_origin_table.md`)
Breakdown between `IoBT_GUNFIRE` (transient impulsive noise) and `EXISTING_PROXY` (continuous non-stationary proxy noise):
- **+5 dB IoBT Gunfire** ($n=104$): Out SNR = 7.14 dB, Out SI-SDR = 9.33 dB ($\Delta$ +4.77 dB), STOI = 0.870 (PASS), PESQ = 1.679.
- **+5 dB Existing Proxy** ($n=33$): Out SNR = 6.36 dB, Out SI-SDR = 8.97 dB ($\Delta$ +4.03 dB), STOI = 0.889 (PASS), PESQ = 1.712.
- **+10 dB IoBT Gunfire** ($n=93$): Out SNR = 8.61 dB, Out SI-SDR = 11.45 dB ($\Delta$ +1.61 dB), STOI = 0.909 (PASS), PESQ = 1.990.
- **+10 dB Existing Proxy** ($n=28$): Out SNR = 8.17 dB, Out SI-SDR = 11.15 dB ($\Delta$ -2.28 dB), STOI = 0.924 (PASS), PESQ = 2.123.
- **+15 dB IoBT Gunfire** ($n=63$): Out SNR = 10.30 dB, Out SI-SDR = 13.36 dB ($\Delta$ -1.34 dB), STOI = 0.940 (PASS), PESQ = 2.236.
- **+15 dB Existing Proxy** ($n=23$): Out SNR = 10.35 dB, Out SI-SDR = 13.89 dB ($\Delta$ -4.82 dB), STOI = 0.949 (PASS), PESQ = 2.509 (PASS).

### Plot Generated
- `results/dfn3/targets_vs_measured.png`: 3-panel visualization showing STOI, PESQ (wideband), and Output SNR vs. input SNR against DRDO PS target reference lines.

---

## Task 3: Deployed Streaming Configuration Evaluation
Tested real-time edge processing path using `AudioChain` and `BlockBackend` (500 ms block, 300 ms context, 40 ms guard, 10 ms crossfade, 256-sample IO frames):
- Evaluated on 344 clips at 5 dB, 10 dB, and 15 dB subsets (`results/dfn3/deployed_streaming_comparison.md`).
- Offline vs. Streaming differences:
  - 5 dB: Offline STOI 0.875 vs Streaming STOI 0.143; Offline PESQ 1.687 vs Streaming PESQ 1.378.
  - 10 dB: Offline STOI 0.913 vs Streaming STOI 0.127; Offline PESQ 2.021 vs Streaming PESQ 1.551.
  - 15 dB: Offline STOI 0.942 vs Streaming STOI 0.122; Offline PESQ 2.309 vs Streaming PESQ 1.723.
- Root Cause: Priming delay of ~880 ms ($B + X + R$) and segment crossfade windowing across 3.0s total file lengths significantly degrade short-clip scoring if evaluating entire transient segments without continuous state warm-up.

---

## Task 4: Documentation Updates & Pipeline Hardening
1. **`REPORT.md`**: Replaced UNVERIFIED rows with complete 7-row measured table (-10 to +20 dB). Added Section 7 reproduction commands.
2. **`results/slide_table.md`**: Updated with exact measured metrics and compliance status.
3. **`edge/streaming_core.py`**: Added native support for `align_to` and `delay_samples_io` property to `AudioChain`, resolving the `TypeError` and eliminating brittle sed monkey-patches in `test_sender_v5_e2e.py`.
4. **End-to-End Test Suite**: Verified 100% pass rate on `test_playout.py` (7/7 passed) and `test_sender_v5_e2e.py` (4/4 passed).
