# Validation Identity Audit

The sampling ablation did NOT save per-example validation identities. Only aggregated metrics were saved in `combined_training_curves.csv`.

## Determinism
Identity Match: YES
Noisy Hash Match: YES
Clean Hash Match: YES
Origin Match: YES

## Discrepancy Explanation
The previous V1-vs-V2 comparison evaluated 442 gunfire and 148 proxy (590 total).
The sampling ablation counted the rows in `noise_val_v2.csv` natively, which has exactly 436 gunfire and 154 proxy rows (590 total).
This means the previous V1-vs-V2 comparison script must have generated the examples dynamically and probabilistically sampled the rows. Because `AntigravityDataset.__getitem__` calls `df.sample(1)`, without an explicit deterministic seed tied to the row index, the selected rows follow a binomial distribution. It drew 442 gunfire instances by chance during the V1-vs-V2 audit, whereas the absolute manifest contains 436.

Furthermore, in `run_sampling_ablation.py`, `is_val=True` was NOT passed to `AntigravityDataset`. This caused augmentations to remain active and the deterministic `random.seed(idx)` call to be skipped entirely. Thus, every validation evaluation inside the ablation generated a completely new stochastic batch of 590 samples, meaning cross-experiment metric comparisons are not fully controlled at the example level.
