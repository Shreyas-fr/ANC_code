# Stage 11.2.21 — Legacy Gold-Access Entry-Point Block

## Finding

Static source review found historical scripts that could read the sealed SIH gold manifest/audio, use gold hashes in training/audit workflows, regenerate the gold set, or mutate the gold manifest. Prior compliance wording called these tools “quarantined by policy,” but there was no executable quarantine.

## Change

Added `scripts/legacy_gold_access_guard.py` and inserted its unconditional fail-closed call before data operations in the following legacy entry points:

| Entry point | Historical behavior indicated by source |
|---|---|
| `scripts/create_dataset_v2.py` | Uses the gold manifest in dataset construction |
| `scripts/train_polar_gpu.py` | Reads gold manifest hash during training setup |
| `scripts/independent_snr_audit.py` | Reads gold manifest and gold audio |
| `scripts/audit_overlap.py` | Uses gold manifest in overlap audit |
| `scripts/test_mutation.py` | Writes to the gold manifest during mutation test |
| `scripts/run_v2_post_training_eval.py` | Reads gold manifest/audio during evaluation |
| `scripts/create_v2_deduplicated_manifest.py` | Reads gold corpus for deduplication |
| `scripts/final_gunfire_validation.py` | Reads gold manifest during validation |
| `scripts/evaluate_v1_v2_gold.py` | Reads gold audio during model evaluation |
| `scripts/train_baseline.py` | Reads gold manifest hash during training setup |
| `scripts/test_data_integrity.py` | Reads gold manifest in integrity checks |
| `scripts/run_sampling_ablation.py` | Reads gold manifest hash in ablation workflow |
| `scripts/test_determinism.sh` | Regenerates gold data and reads its hash |
| `scripts/train_polar_full.py` | Reads gold manifest hash during training setup |
| `scripts/test_v2_loader.py` | Includes gold manifest in loader checks |
| `scripts/evaluate_gold_test.py` | Reads gold manifest/audio during evaluation |
| `scripts/run_full_evaluation.py` | Reads gold manifest/audio during evaluation |
| `scripts/train_full.py` | Reads gold manifest hash during training setup |
| `scripts/audit_defence_noise.py` | Reads the gold manifest during auditing |
| `scripts/train_v2_25k.py` | Reads gold manifest hash during training setup |
| `scripts/freeze_gold_test.py` | Creates/writes the gold dataset and manifest hash |
| `scripts/evaluate_polar_gold.py` | Reads gold manifest/audio during evaluation |
| `scripts/dataset_final_audit.py` | Reads gold manifest during integrity audit |
| `scripts/audit_model_behavior.py` | Reads gold manifest/audio during model audit |
| `scripts/run_sisdr_ablation.py` | Reads the protected gold manifest during an ablation |

The original list covered 24 entry points; static follow-up found `run_sisdr_ablation.py` as an additional direct gold-manifest reader, bringing the guarded inventory to **25 entry points**. The guard has no environment-variable bypass. The maintained canonical evaluator, streamed evaluator, and `run_candidate_evaluation.py` are not blocked; they retain their non-gold path and manifest protections.

## Verification and limits

`tests/test_legacy_gold_access_guard.py` invokes all 25 listed scripts as subprocesses from an empty temporary working directory and requires exit code 2 with the guard message. The suite passes **2/2 tests** (the subprocess test covers all 25 entry points and a second test checks there is no environment override). All 24 Python files parse successfully after insertion, and `bash -n scripts/test_determinism.sh` passes. The tests use no project data or gold path. This is an accidental-use barrier at the listed entry points, not an operating-system access-control boundary: a user can still edit code or directly read files outside these entry points. Keep the gold directory excluded from training, selection and tuning; any eventual formal gold evaluation needs a separately reviewed process.

No gold file was opened, hashed, decoded, scored, or modified for this change. No checkpoint, canonical manifest, evaluator implementation, or training artifact was changed. No dependencies were installed, and nothing was staged or committed.
