# Kaggle DeepFilterNet3 + HKNT fine-tuning

`deepfilternet3_hknt_kaggle.ipynb` is the local source for the Kaggle draft at:

https://www.kaggle.com/code/shreyasdivekar/deepfilternet3-hknt-anc

The draft is configured for Internet and GPU T4 x2. The full 18.83 GB archive is being uploaded to a **private** Kaggle dataset as `anc-sih-training-data-opaque/anc-sih-dfnet-training-data.bin`; this preserves the gzip tar bytes under an opaque extension so Kaggle need not index/extract 86,788 files on dataset creation. The notebook detects the archive by dataset path and content and extracts it in the cloud runtime, using `pigz` if available. It pins DeepFilterNet and HKNT package versions, imports the upstream DeepFilterNet3 checkpoint, stores the reference and fine-tuned weights in HK containers, requests three full epochs, and emits a strict-load report. Batch size 8 and four data-loader workers use both T4s more effectively than the original settings.

The active production checkpoints were copied with SHA-256 verification to `backups/before_deepfilternet_v3/`. Keep the current deployment paths unchanged until a trained `.hk` artifact has been downloaded and verified.

## V4 compliance retraining

`deepfilternet3_v4_sih26052.ipynb` and `kernel-metadata-v4.json` define a corrected retraining run. The V2 notebook split speech/noise sources between training and validation incorrectly, used a randomly changing validation mixture set, silently replaced failed audio reads with silence, and reused mutable libDF feature state across waveforms. V4 adds a deterministic, global source-group holdout across noise classes, strict file errors, deterministic synthetic validation mixtures, per-waveform libDF state resets, SI-SDR and multi-resolution STFT losses, synthetic room response and clipping augmentation, and checkpoints every 500 optimizer steps. It starts from the pretrained reference rather than the V2 checkpoint because the local canonical evaluation shows the V2 weights regress against that reference.

The self-contained upload folder is `notebooks/v4/`. After Kaggle CLI authentication and confirming the configured private datasets are available:

```bash
kaggle kernels push -p v4
kaggle kernels status shreyasdivekar/deepfilternet3-v4-sih26052
kaggle kernels output shreyasdivekar/deepfilternet3-v4-sih26052 -p ../kaggle_output_v4
```

The user-started V4 Kaggle run initialized upstream DeepFilterNet3 but failed before training because no processed-audio `metadata.csv` was mounted. The two V4 upload metadata files now both name the processed-audio, training-data, and canonical-exclusions datasets. Before retrying, attach all three in the Kaggle notebook Input panel and confirm the runtime preflight finds their metadata and exclusion files. Do not select a checkpoint from training loss alone; evaluate each saved checkpoint on the frozen 590-clip canonical benchmark with `../scripts/evaluate_dfn3_canonical.py`. Keep `data/SIH_GOLD_TEST` isolated until the model and operating point are frozen.

## Active repaired V3.4 run

The established V3.4 notebook includes canonical exclusions, a fixed SNR-stratified validation set, zip-streamed audio, SI-SDR loss, and checkpoint saves every 500 steps. Its Oct. 21 run stopped at step 50 because `gc.collect()` was called without importing `gc`; it also reused libDF normalization state across clips. The repaired source in `notebooks/v3_4_repaired/` adds the missing import and resets feature state before every training waveform and validation inference.

This source was submitted to the existing private kernel `shreyasdivekar/dfn3-v3-1-sih-training` as version 10 on Nov. 9, 2026. Its status was later observed as `Cancelling…`; no completed run or retrieved checkpoints are evidenced. The prior GPU benchmark projected 5.73 hours for 6,000 updates. The V4 Kaggle run was started by the user but failed before training due to missing mounted inputs.

## Current local evidence (2026-11-09)

The available V2 candidate and its saved pretrained reference were both evaluated with fresh libDF state per clip. Results and per-clip metrics are in `../runs/sih26052_dfn3_canonical_v2/` and `../runs/sih26052_dfn3_canonical_pretrained/`. The three-epoch V2 candidate regressed against the upstream reference on all four aggregate metrics, so it is not recommended for deployment. See the project compliance report for the measured values and remaining data/hardware gates.
