# V1 vs V2 Same-Validation Controlled Comparison

## Checkpoint Identity
- V1: runs/sih26052_polar_gpu/checkpoint_25000.pt (Params: 1448962)
- V2: runs/sih26052_polar_v2_25k/best.pt (Params: 1448962)

## Dataset Identity
Validated exactly 590 examples (Gunfire: 442, Proxy: 148).

## Metric Implementation Audit
PROJECT_SNR uses `calculate_active_speech_level(clean)` found in `scripts/evaluate_polar_gold.py`.
RESIDUAL_ERROR_SNR uses standard mean power as found in training scripts.

## Overall Results
**Input**:
- PROJECT_SNR: 6.5754
- RESIDUAL_SNR: 5.5390
- SI-SDR: 6.0243
- STOI: 0.8223
- PESQ: 1.6004

**V1 Output**:
- PROJECT_SNR: 5.8009 (Imp: -0.7746)
- RESIDUAL_SNR: 4.7511 (Imp: -0.7878)
- SI-SDR: 3.9363 (Imp: -2.0880)
- STOI: 0.8224
- PESQ: 1.5857

**V2 Output**:
- PROJECT_SNR: 5.6988 (Imp: -0.8766)
- RESIDUAL_SNR: 4.6491 (Imp: -0.8899)
- SI-SDR: 3.8796 (Imp: -2.1448)
- STOI: 0.8224
- PESQ: 1.5886

**Paired V2-vs-V1 Differences (V2 minus V1)**:
- **PROJ**: Mean=-0.1021, Median=-0.1401, Std=1.8717
  - Range: [-14.3590, 10.5630]
  - V2 > V1: 34.6% | V2 < V1: 54.2% | Tied: 11.2%
  - Wilcoxon p-value: 1.8586e-03
- **RES**: Mean=-0.1021, Median=-0.1401, Std=1.8717
  - Range: [-14.3590, 10.5630]
  - V2 > V1: 34.6% | V2 < V1: 54.2% | Tied: 11.2%
  - Wilcoxon p-value: 1.8586e-03
- **SDR**: Mean=-0.0568, Median=-0.0113, Std=2.1457
  - Range: [-15.5713, 10.9496]
  - V2 > V1: 39.7% | V2 < V1: 41.2% | Tied: 19.2%
  - Wilcoxon p-value: 3.5460e-01
- **STOI**: Mean=0.0000, Median=0.0000, Std=0.0001
  - Range: [-0.0004, 0.0006]
  - V2 > V1: 0.0% | V2 < V1: 0.0% | Tied: 100.0%
  - Wilcoxon p-value: 2.8120e-16
- **PESQ**: Mean=0.0028, Median=0.0002, Std=0.0870
  - Range: [-0.5303, 1.2033]
  - V2 > V1: 7.6% | V2 < V1: 6.3% | Tied: 86.1%
  - Wilcoxon p-value: 2.7002e-01

## IoBT Gunfire Results
**Input**:
- PROJECT_SNR: 6.3744
- RESIDUAL_SNR: 5.3007
- SI-SDR: 5.0119
- STOI: 0.8214
- PESQ: 1.5700

**V1 Output**:
- PROJECT_SNR: 5.7630 (Imp: -0.6114)
- RESIDUAL_SNR: 4.6893 (Imp: -0.6114)
- SI-SDR: 3.7685 (Imp: -1.2435)
- STOI: 0.8215
- PESQ: 1.5603

**V2 Output**:
- PROJECT_SNR: 5.6200 (Imp: -0.7544)
- RESIDUAL_SNR: 4.5464 (Imp: -0.7544)
- SI-SDR: 3.6673 (Imp: -1.3446)
- STOI: 0.8216
- PESQ: 1.5607

**Paired V2-vs-V1 Differences (V2 minus V1)**:
- **PROJ**: Mean=-0.1429, Median=-0.1698, Std=1.7586
  - Range: [-14.3590, 8.8648]
  - V2 > V1: 31.7% | V2 < V1: 55.9% | Tied: 12.4%
  - Wilcoxon p-value: 1.8680e-04
- **RES**: Mean=-0.1429, Median=-0.1698, Std=1.7586
  - Range: [-14.3590, 8.8648]
  - V2 > V1: 31.7% | V2 < V1: 55.9% | Tied: 12.4%
  - Wilcoxon p-value: 1.8680e-04
- **SDR**: Mean=-0.1011, Median=-0.0309, Std=2.0038
  - Range: [-15.5713, 10.1363]
  - V2 > V1: 37.8% | V2 < V1: 41.6% | Tied: 20.6%
  - Wilcoxon p-value: 1.4051e-01
- **STOI**: Mean=0.0001, Median=0.0000, Std=0.0001
  - Range: [-0.0003, 0.0006]
  - V2 > V1: 0.0% | V2 < V1: 0.0% | Tied: 100.0%
  - Wilcoxon p-value: 1.4739e-17
- **PESQ**: Mean=0.0005, Median=0.0002, Std=0.0504
  - Range: [-0.5017, 0.3911]
  - V2 > V1: 7.2% | V2 < V1: 5.9% | Tied: 86.9%
  - Wilcoxon p-value: 3.5372e-01

## Existing Proxy Results
**Input**:
- PROJECT_SNR: 7.1758
- RESIDUAL_SNR: 6.2504
- SI-SDR: 9.0479
- STOI: 0.8250
- PESQ: 1.6914

**V1 Output**:
- PROJECT_SNR: 5.9140 (Imp: -1.2618)
- RESIDUAL_SNR: 4.9357 (Imp: -1.3147)
- SI-SDR: 4.4377 (Imp: -4.6102)
- STOI: 0.8250
- PESQ: 1.6617

**V2 Output**:
- PROJECT_SNR: 5.9340 (Imp: -1.2418)
- RESIDUAL_SNR: 4.9557 (Imp: -1.2947)
- SI-SDR: 4.5135 (Imp: -4.5344)
- STOI: 0.8250
- PESQ: 1.6717

**Paired V2-vs-V1 Differences (V2 minus V1)**:
- **PROJ**: Mean=0.0200, Median=-0.0904, Std=2.1701
  - Range: [-13.6632, 10.5630]
  - V2 > V1: 43.2% | V2 < V1: 49.3% | Tied: 7.4%
  - Wilcoxon p-value: 9.6336e-01
- **RES**: Mean=0.0200, Median=-0.0904, Std=2.1701
  - Range: [-13.6632, 10.5630]
  - V2 > V1: 43.2% | V2 < V1: 49.3% | Tied: 7.4%
  - Wilcoxon p-value: 9.6336e-01
- **SDR**: Mean=0.0758, Median=0.0454, Std=2.5176
  - Range: [-15.5179, 10.9496]
  - V2 > V1: 45.3% | V2 < V1: 39.9% | Tied: 14.9%
  - Wilcoxon p-value: 5.3637e-01
- **STOI**: Mean=0.0000, Median=0.0000, Std=0.0001
  - Range: [-0.0004, 0.0004]
  - V2 > V1: 0.0% | V2 < V1: 0.0% | Tied: 100.0%
  - Wilcoxon p-value: 1.1471e-01
- **PESQ**: Mean=0.0099, Median=0.0003, Std=0.1501
  - Range: [-0.5303, 1.2033]
  - V2 > V1: 8.8% | V2 < V1: 7.4% | Tied: 83.8%
  - Wilcoxon p-value: 5.7357e-01

## Interpretation

## Integrity Checks
V1_RELOAD=PASS
V2_RELOAD=PASS
V1_DETERMINISM=PASS
V2_DETERMINISM=PASS
GOLD_LOADED=NO
GOLD_EVALUATED=NO
GOLD_MODIFIED=NO
V1_RETRAINED=NO
V2_RETRAINED=NO

