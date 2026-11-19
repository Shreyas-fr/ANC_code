# SIH 26052 Step-500 Baseline Reproduction

**Date:** 2026-11-13  
**Purpose:** Phase 1 acceptance record for the frozen canonical evaluator and a diagnostic summary of low-input-SNR behavior.  
**Status:** Step-500 reproduction passed. The full-set quality targets remain unmet.

## Reproduction identity

| Field | Value |
|---|---|
| Candidate | Deployed DeepFilterNet3 Step-500 artifact copied from Pi |
| Checkpoint SHA-256 | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` |
| Frozen manifest SHA-256 | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` |
| Manifest size | 590 clips; mono 16 kHz clean/noisy pairs |
| Git commit | `242e24c6fd803729314a5636d63ae0be235ce2e4` |
| Evaluation entry point | `scripts/run_candidate_evaluation.py` |
| Metric implementation | `scripts/evaluate_dfn3_canonical.py` |
| Comparison implementation | `scripts/compare_dfn3_canonical_split.py` |
| Output directory | `runs/sih26052_candidate_step500_repro_20261113/` |
| Runtime | 56.71 s wall clock for 1,770 s of audio; wall-clock RTF 0.0320 (includes interpreter/model startup) |
| Exit code | 0 |

## Acceptance results

The new `per_clip.csv` is byte-identical to the previously saved Step-500 file: both SHA-256 values are `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f`. The new summary confirms 590 valid rows and the expected manifest/checkpoint hashes. Paired deltas against the saved reference are exactly zero for SNR, SI-SDR, STOI, and PESQ-WB on the full, even, and odd partitions; all corresponding bootstrap intervals are `[0, 0]` because the rows match exactly.

| Metric | Mean | Target | Status |
|---|---:|---:|---|
| Output SNR | 13.4670 dB | >15 dB | Not met |
| SI-SDR | 12.3629 dB | — | Reported |
| STOI | 0.8847 | >0.85 | Mean met |
| PESQ-WB | 2.2323 | >2.5 | Not met |
| Joint clip pass | 161/590 (27.29%) | all three criteria | Not met |

The evaluator keeps the existing metric conventions: SNR and SI-SDR use unnormalized waveforms; STOI and PESQ use independently peak-normalized waveforms. It resets libDF state per clip and does not change alignment or resampling behavior. The report records sample rate/channel contract, manifest and checkpoint hashes, Git commit, evaluator hash, elapsed wall time, and real-time factor. No separate inference configuration was supplied, so its config hash is explicitly null.

## Low-input-SNR diagnostic

The table groups clips by the benchmark's **target input SNR**. The “measured input SNR” column is recomputed by the evaluator from each saved noisy waveform and clean reference. Output SNR improves substantially on the difficult bins, but speech-intelligibility and perceptual-quality scores remain low:

| Target input SNR | n | Measured input SNR | Output SNR | SNR gain | Output STOI | Output PESQ-WB | Joint passes |
|---:|---:|---:|---:|---:|---:|---:|---:|
| -10 dB | 30 | -8.91 dB | 6.56 dB | +15.48 dB | 0.677 | 1.386 | 0/30 |
| -5 dB | 63 | -2.33 dB | 9.95 dB | +12.28 dB | 0.804 | 1.689 | 3/63 |
| 0 dB | 117 | 1.85 dB | 11.03 dB | +9.17 dB | 0.856 | 1.859 | 8/117 |
| 5 dB | 137 | 5.89 dB | 12.81 dB | +6.93 dB | 0.891 | 2.146 | 20/137 |
| 10 dB | 121 | 11.66 dB | 15.17 dB | +3.51 dB | 0.929 | 2.504 | 46/121 |
| 15 dB | 86 | 16.93 dB | 17.91 dB | +0.98 dB | 0.951 | 2.835 | 55/86 |
| 20 dB | 36 | 20.86 dB | 19.47 dB | -1.40 dB | 0.960 | 3.080 | 29/36 |

Source composition is uneven at the worst conditions: at -10 dB, 22/30 clips are IoBT gunfire and 8/30 are existing proxies; at -5 dB, 54/63 are IoBT gunfire and 9/63 are proxies. The low-bin quality collapse therefore cannot be attributed to one source class from these aggregates alone.

### What the evidence supports

The model is removing a large amount of estimated error/noise at low SNR, as reflected by the output-SNR gains. At the same time, low-energy speech details are difficult to distinguish from the noise in a single-channel mixture. Time-frequency masking can suppress both noise and speech components when their spectra overlap; residual impulsive/noise energy and speech attenuation or distortion can therefore coexist. SNR rewards reduction in waveform error power but does not by itself guarantee intelligibility or naturalness, which explains why SNR rises while STOI and PESQ remain poor on these bins.

This is a **data-supported working explanation, not a proven unique cause**. The present evaluation does not measure speech deletion, consonant preservation, transient handling, or model mask behavior directly, and the low-SNR bins contain only 30 and 63 clips. The per-bin statistics identify the failure region but do not establish whether the dominant cause is training-domain mismatch, limited low-SNR examples/content diversity, phase/mask behavior, mixtures that are intrinsically ambiguous, or a combination. Phase 3 should therefore log realized SNR and compare targeted low-SNR experiments against repeated R0 seeds; inspect aligned audio/spectrogram examples and per-source metrics before making a causal claim.

## Warnings and limits

- The run emitted a SciPy warning that the installed SciPy build expects NumPy >=2.0 and <2.8, while NumPy 1.26.4 is installed. Evaluation completed with exit code 0 and exactly reproduced the saved per-clip CSV; preserve this environment warning in future reproductions.
- DeepFilterNet initialization emitted `fatal: not a git repository` while probing its downloaded upstream model cache. The model loaded and the evaluator completed; this message did not indicate that the project evaluator ran outside the `antigravity/` repository.
- The wall-clock RTF includes Python startup, model loading, scoring, and file I/O; it is not a pure model-inference RTF.
- The 590-clip canonical benchmark has prior checkpoint-selection exposure. The odd-index subset is not an untouched test set. SIH gold remained unopened.
- No audio was uploaded, and no model or Pi service was changed.

## Reproduction command

Run from the `antigravity/` repository root with the existing project Python environment:

```bash
../pc_venv/bin/python scripts/run_candidate_evaluation.py \
  --checkpoint runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt \
  --canonical-dir runs/sih26052_canonical_validation \
  --output-dir runs/sih26052_candidate_step500_repro_YYYYMMDD \
  --reference-per-clip runs/sih26052_dfn3_canonical_step500/per_clip.csv \
  --bootstrap 2000 --seed 26052
```

The orchestration script refuses a non-empty output directory, refuses any canonical path containing `SIH_GOLD_TEST`, and checks the expected frozen-manifest hash before calling the existing evaluator.
