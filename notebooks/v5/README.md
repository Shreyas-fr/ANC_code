# DeepFilterNet3 V5 SIH26052 target-aligned retraining

V5 is based on the completed V4 source-group / exclusion-safe Kaggle notebook. It changes one training target contract: if synthetic room response is applied to speech before mixing, the target now uses that same reverberant speech. V4 instead supplied the dry speech target for those reverberant inputs, encouraging dereverberation and likely contributing to the observed dry-benchmark regression. This is a testable hypothesis, not a proven sole cause.

The separate canonical 590-clip benchmark remains reserved for checkpoint/model selection. `SIH_GOLD_TEST` is not mounted or read. Preserve all three V4 dataset attachments in Kaggle and verify the preflight output before training. Evaluate all saved checkpoints against the frozen canonical manifest before choosing a deployment model.

Notebook: `deepfilternet3_v5_sih26052.ipynb`
