# Polar-D Small-Set Overfit Diagnostic

## 1. Fixed Dataset
Fixed subset of exactly 8 examples constructed (4 IoBT_GUNFIRE, 4 EXISTING_PROXY).
Noisy/clean tensors are frozen in memory.

## 2. Model Identity
Using StatefulPolarLSTM_Wrapper (1,448,962 parameters).

## 3. Loss Identity
Using exactly EnhancementLoss: 5.0 * L1 waveform + 5.0 * MRSTFT.

## 4. Input Baseline
- SNR: 3.7003
- SI-SDR: 3.0995
- STOI: 0.7314
- PESQ: 1.4007

## 5. Random Initialization Results
- Loss reduction: 11.7594
- SNR improvement: 8.6626 (Best: 13.3161 at 950)
- SI-SDR improvement: 8.3488 (Best: 12.4059 at 950)
- Classification: OVERFIT_CAPABLE

## 6. Identity Initialization Results
- Loss reduction: 5.8604
- SNR improvement: 10.5850 (Best: 14.2853 at 1000)
- SI-SDR improvement: 10.3280 (Best: 13.4274 at 1000)
- Classification: OVERFIT_CAPABLE

## 7. Gradient Audit
Identity Step 1: norm=92.0592, zero=0.0014, NaN_grad=0.0000, NaN_out=False
Identity Step 10: norm=396.5133, zero=0.0014, NaN_grad=0.0000, NaN_out=False
Identity Step 100: norm=208.3516, zero=0.0014, NaN_grad=0.0000, NaN_out=False
Identity Step 1000: norm=193.0097, zero=0.0014, NaN_grad=0.0000, NaN_out=False

## 8. Learning Curves
Saved to overfit_log.csv.

## 9. Interpretation
1. Can the model fit the fixed examples? Yes
2. Does lower loss correspond to improved SI-SDR/SNR? Yes
3. Does identity initialization materially change learning behavior? No
4. Is there evidence of a gradient failure? No
5. Does this experiment support a local optimization/representation limitation? No

## 10. Integrity Checks
GOLD_ACCESSED=NO
GOLD_MODIFIED=NO
V1_CHECKPOINT_MODIFIED=NO
V2_CHECKPOINT_MODIFIED=NO
MANIFESTS_MODIFIED=NO
PRODUCTION_MODEL_MODIFIED=NO
