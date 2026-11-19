# FullSubNet Independent Baseline

**Status:** Phase 2 passed for offline canonical evaluation. This is a research comparison, not a deployment promotion.

## Reproducibility record

- Evaluator: `scripts/evaluate_fullsubnet_canonical.py`, reusing metric definitions from `scripts/evaluate_dfn3_canonical.py`.
- Comparison: `scripts/compare_dfn3_canonical.py`, paired bootstrap (`2,000` resamples, seed `26052`).
- Frozen set: 590 mono 16 kHz clean/noisy pairs; manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`.
- FullSubNet checkpoint: official pretrained epoch 58; 5,637,635 parameters; SHA-256 `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0`.
- Upstream source: Audio-WestlakeU/FullSubNet, MIT License, pinned local checkout `e97448375cd1e883276ad583317b1828318910dc`.
- Inference configuration: mono 16 kHz, 512-point Hann STFT, 256-sample hop, 257 frequency bins, LSTM, two-frame lookahead, offline Laplace normalization, compressed complex ratio mask with mixture-phase reconstruction. Per-clip call starts with fresh model state.
- Local runtime: CPU, 590 clips / 1,770 seconds audio in 231.13 seconds (wall-clock RTF `0.131`). This does not establish Raspberry Pi runtime.
- Results: `runs/fullsubnet_baseline/per_clip.csv`, `summary.json`, and `paired_vs_deployed_step500.json`.
- Current source hashes: adapter `e0aca3fc2aa95723f730dd01c1a993638f380ee464b75a5dcb9837c96c480502`; evaluator `167be032e9380e3f78f4c165f9856a9bfa0eb238c495fda9386a8212e1df85f0`.
- Per-clip CSV SHA-256: `56207ad4325b9c91a71188cf2edecf063b1385f118c29579acd604d8a4dd7e62`.
- Repository Git HEAD at execution: `242e24c6fd803729314a5636d63ae0be235ce2e4`; local working tree was dirty and was not modified by checkout/reset operations.

## Canonical results

| Model | SNR (dB) | SI-SDR (dB) | STOI | PESQ-WB | All-three pass |
|---|---:|---:|---:|---:|---:|
| Deployed DFN3 Step-500 | 13.467 | 12.363 | 0.8847 | 2.2323 | 161/590 (27.3%) |
| Official FullSubNet epoch 58 | 14.904 | 13.700 | 0.9026 | 2.5133 | 218/590 (36.9%) |

FullSubNet minus Step-500 paired mean difference (95% bootstrap CI): SNR `+1.437 dB [1.181, 1.705]`; SI-SDR `+1.337 dB [1.059, 1.625]`; STOI `+0.0179 [0.0144, 0.0217]`; PESQ-WB `+0.2811 [0.2487, 0.3162]`. All four intervals are above zero for this fixed benchmark. The full-set mean SNR remains below the SIH `>15 dB` target. The higher per-clip joint pass rate is not universal compliance.

## Input-SNR strata

Means by target input-SNR bin, with the difference from deployed Step-500 in parentheses:

| Target SNR | n | Output SNR dB | SI-SDR dB | STOI | PESQ-WB | Joint pass |
|---:|---:|---:|---:|---:|---:|---:|
| -10 | 30 | 7.115 (+0.553) | 4.409 (+1.850) | 0.710 (+0.032) | 1.415 (+0.030) | 0/30 |
| -5 | 63 | 10.706 (+0.761) | 9.129 (+1.009) | 0.832 (+0.028) | 1.827 (+0.138) | 2/63 |
| 0 | 117 | 11.937 (+0.910) | 10.556 (+0.791) | 0.876 (+0.020) | 2.052 (+0.193) | 15/117 |
| 5 | 137 | 14.493 (+1.680) | 13.304 (+1.562) | 0.910 (+0.019) | 2.411 (+0.266) | 34/137 |
| 10 | 121 | 16.781 (+1.608) | 15.895 (+1.452) | 0.939 (+0.010) | 2.887 (+0.383) | 67/121 |
| 15 | 86 | 19.648 (+1.742) | 18.746 (+1.326) | 0.963 (+0.012) | 3.236 (+0.401) | 67/86 |
| 20 | 36 | 22.303 (+2.838) | 21.735 (+2.042) | 0.976 (+0.016) | 3.537 (+0.457) | 33/36 |

The low-SNR deficit remains visible even in this stronger baseline: zero joint passes in the `-10 dB` bin and only two in `-5 dB`. The low bins contain mostly gunfire-labeled examples in the manifest (22/30 at `-10 dB`, 54/63 at `-5 dB`).

## Source-label breakdown

Descriptive paired results grouped by the two `origin` values in the saved canonical per-clip files (`EXISTING_PROXY`, n=148; `IoBT_GUNFIRE`, n=442). Differences are FullSubNet minus Step-500; bootstrap uses 2,000 paired clip resamples with seed 26052 using `scripts/compare_dfn3_canonical.py`'s percentile-mean procedure. These groups are not balanced across SNR, and `IoBT_GUNFIRE` is a data-origin label rather than an acoustic event annotation.

| Origin | SNR Δ dB (95% CI) | SI-SDR Δ dB (95% CI) | STOI Δ (95% CI) | PESQ-WB Δ (95% CI) | Joint passes Step-500 → FullSubNet |
|---|---:|---:|---:|---:|---:|
| EXISTING_PROXY (n=148) | +1.277 [0.839, 1.752] | +0.847 [0.332, 1.365] | +0.0153 [0.0105, 0.0205] | +0.309 [0.242, 0.382] | 41 → 53 |
| IoBT_GUNFIRE (n=442) | +1.490 [1.184, 1.804] | +1.501 [1.175, 1.857] | +0.0188 [0.0143, 0.0239] | +0.272 [0.231, 0.311] | 120 → 165 |

This shows aggregate gains in both source groups, but it does not isolate SNR from source type or explain individual failures. In particular, FullSubNet still has only 0/30 and 2/63 joint passes in the -10 and -5 dB target-SNR bins. The project has no event-level labels here for transient duration, overlap with speech, or speech deletion, so those mechanisms remain hypotheses requiring separate annotation/listening analysis.

## Interpretation and limits

At low input SNR, noise energy overwhelms speech energy and may overlap speech in time and frequency. A single-channel estimator sees only their sum. Masking can reduce total error power and improve SNR while also attenuating weak consonants, altering speech harmonics, or leaving impulsive interference; STOI/PESQ therefore remain poor. The low-bin source mix also concentrates these cases in the gunfire-labeled category, so source/domain mismatch and transient overlap are plausible contributors. These are evidence-informed mechanisms, not isolated causal findings: this evaluation did not quantify speech deletion, inspect a blinded listening panel, or separate noise class from SNR.

FullSubNet is an offline, look-ahead model using offline normalization. No streaming implementation, bounded-latency behavior, Pi benchmark, microphone capture, headset playback, or deployment validation was established. Its results do not justify replacing the deployed Step-500 path. Preserve Step-500 as the production/default candidate until a separately authorized selection and hardware gate.

## Files and execution

- Adapter: `src/models/fullsubnet_adapter.py`.
- Evaluator: `scripts/evaluate_fullsubnet_canonical.py`.
- Canonical evaluation command: `../pc_venv/bin/python scripts/evaluate_fullsubnet_canonical.py --output-dir runs/fullsubnet_baseline --device cpu` (exit 0; all 590 clips).
- Paired comparison command: `../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/sih26052_candidate_step500_repro_20261113/per_clip.csv --candidate runs/fullsubnet_baseline/per_clip.csv --output runs/fullsubnet_baseline/paired_vs_deployed_step500.json --bootstrap 2000 --seed 26052` (exit 0).
- A nonempty output directory is intentionally not overwritten by the evaluator.
- The evaluator emitted the environment's existing SciPy/NumPy compatibility warning (`SciPy` expects NumPy >=2 while NumPy 1.26.4 is installed). Evaluation completed; dependency mismatch remains a reproducibility risk to resolve before broader use.
