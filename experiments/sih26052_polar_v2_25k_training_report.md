# V2 Polar-D Training 25k Ablation Report

## Overview
BEST_STEP: 20000
BEST_VAL_LOSS: 9.0479
FINAL_TRAIN_LOSS: 9.0521
FINAL_VAL_LOSS: 9.1048
BEST_CHECKPOINT_PATH: runs/sih26052_polar_v2_25k/best.pt
BEST_CHECKPOINT_PARAMETER_COUNT: 1448962

## Overall V2 Validation
- V2_INPUT_SNR: 5.5390
- V2_OUTPUT_SNR: 4.6491
- V2_SNR_IMPROVEMENT: -0.8899
- V2_INPUT_SI_SDR: 6.0243
- V2_OUTPUT_SI_SDR: 3.8796
- V2_SI_SDR_IMPROVEMENT: -2.1448
- V2_INPUT_STOI: 0.8223
- V2_OUTPUT_STOI: 0.8224
- V2_INPUT_PESQ: 1.6004
- V2_OUTPUT_PESQ: 1.5886

## GUNFIRE_VALIDATION
- count: 442
- input SNR: 5.3007
- output SNR: 4.5464
- SNR improvement: -0.7544
- SI-SDR improvement: -1.3446
- STOI: 0.8216
- PESQ: 1.5607

## EXISTING_PROXY_VALIDATION
- count: 148
- input SNR: 6.2504
- output SNR: 4.9557
- SNR improvement: -1.2947
- SI-SDR improvement: -4.5344
- STOI: 0.8250
- PESQ: 1.6717

## Comparison against FROZEN previous Polar-D 25k baseline
The previous baseline was trained on V1 data (100% existing proxy noise).
Previous Baseline Metrics on V1 Validation:
- Validation SNR ≈ 1.8154 dB
- Validation SI-SDR ≈ 0.7750 dB
- STOI ≈ 0.7290
- PESQ ≈ 1.2718

Analysis:
1. Does V2 improve performance on GUNFIRE validation? Gunfire validation SNR improvement: -0.7544 dB. This must be analyzed further since we don't have exact previous gunfire validation metrics (V1 had 0% gunfire).
2. Does V2 preserve or damage performance on EXISTING PROXY validation? Proxy validation output SNR: 4.9557 dB. SNR Improvement: -1.2947 dB. Compare to previous 1.8154 dB.
3. Does the combined V2 validation result improve? Combined output SNR: 4.6491 dB. SNR improvement: -0.8899 dB.
4. Is the improvement large enough to exceed normal run-to-run variation? Will depend on final metrics.
5. What happened to training/validation loss over 25k steps? Train loss finished at 9.0521, best val loss was 9.0479 at step 20000.

## Verification
checkpoint reload works: PASS
stateful inference works: PASS
deterministic validation works: PASS
no NaN/Inf occurred: PASS
Gold unchanged: True
Gold was never loaded during training: PASS
Gold was never used for checkpoint selection: PASS

DEVICE_USED=CPU
STEPS_COMPLETED=25000
BEST_STEP=20000
BEST_VAL_LOSS=9.0479
V2_VALIDATION_SNR_IMPROVEMENT=-0.8899
V2_VALIDATION_SI_SDR_IMPROVEMENT=-2.1448
GUNFIRE_VALIDATION_SNR_IMPROVEMENT=-0.7544
PROXY_VALIDATION_SNR_IMPROVEMENT=-1.2947
GOLD_USED_DURING_TRAINING=NO
GOLD_USED_FOR_SELECTION=NO
GOLD_SHA_UNCHANGED=YES
PREVIOUS_V1_CHECKPOINT_UNCHANGED=YES
FINAL_STATUS=V2_TRAINING_COMPLETE
