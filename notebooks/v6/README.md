# DeepFilterNet3 V6 SIH26052 speech-sampling audit

V6 isolates one suspected training-data defect while preserving the V5 objective and augmentation: training now draws clean speech rows from the full eligible source-group training pool on every sample access instead of cycling only through the first 7,200 rows. It logs the number of distinct speech rows actually sampled. The V5 held-out split, canonical exclusions, target-aligned RIR, clipping augmentation, model initialization, optimizer, and losses are retained.

The run is capped at 1,500 optimizer steps and writes checkpoints every 250 steps so model-selection evaluation can detect early canonical degradation. Compare all six checkpoints on the frozen 590-clip validation manifest. Do not mount/read `SIH_GOLD_TEST`. A successful synthetic validation loss is not enough to promote a checkpoint.

This is an experiment hypothesis, not an expected performance guarantee. Do not deploy V6 unless its checkpoint beats the current deployed candidate on the frozen benchmark and passes the required edge gates.

Notebook: `deepfilternet3_v6_sih26052.ipynb`
