# Frozen Gold Evaluation: V1 vs V2 Polar-D

## 1. Evaluation Integrity
Integrity verified: no NaN/Inf parameters, stateful determinism passed, unmodified dataset.
## 2. Checkpoint Identity
- V1: runs/sih26052_polar_gpu/checkpoint_25000.pt (1448962 params)
- V2: runs/sih26052_polar_v2_25k/best.pt (1448962 params)

## 3. Gold Dataset Identity
SHA256: 46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9
100 files verified. Impulsive: 9, Nonstationary: 83.

## 4. Metric Implementation
PROJECT_SNR uses `calculate_active_speech_level(clean)` as requested.

## 5. Overall Gold Results
- Input: SNR=4.4118, SDR=3.2536, STOI=0.8288, PESQ=1.2889
- V1: SNR=4.8895, SDR=2.7984, STOI=0.8290, PESQ=1.2975
- V2: SNR=4.6366, SDR=2.6741, STOI=0.8290, PESQ=1.2951

## 6. SIH Target Measurements
- V1 SNR > 15: 0% | V2: 0%
- V1 STOI > 0.85: 48% | V2: 48%
- V1 PESQ > 2.5: 1% | V2: 1%

## 7. Impulsive Results
- V1: SNR=4.0259 (Imp: -1.1496)
- V2: SNR=3.7903 (Imp: -1.3852)

## 8. Nonstationary Results
- V1: SNR=5.0751 (Imp: 0.5949)
- V2: SNR=4.8419 (Imp: 0.3617)

## 9. Paired V1 vs V2 Gold Comparison
V2 minus V1 SNR Overall Delta: -0.2529
Impulsive Delta: -0.2356
Nonstationary Delta: -0.2332

## 10. Comparison With Previous V1 Gold Evaluation
PREVIOUS_V1_GOLD_COMPARISON=NOT_VERIFIED (unable to reliably assert precise numerical match to prior untracked logs without a preserved artifact file)

## 11. Interpretation
This is a descriptive external validation on 100 immutable gold test examples. V2 demonstrates general external behavior across both subclasses.

## 12. Final Integrity Status
FINAL_STATUS=GOLD_EVALUATION_VALID
