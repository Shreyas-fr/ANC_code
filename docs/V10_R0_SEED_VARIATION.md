# V10 R0 Three-Seed Variation and Plateau

**Seeds:** 26052, 26053, 26054. **Checkpoints:** 300, 500, 550, 800. **Split:** canonical val_index even (n=295), odd (n=295), and full (n=590). Standard deviation is sample SD across only three independent training seeds; it is a small-sample estimate, not a confidence interval. Outputs were computed by `scripts/evaluate_v10_r0_seeds.py`; source rows are the per-clip canonical CSVs under workspace `kaggle_output/dfn3_v10_r0_*`.

## Mean ± sample SD by split

### Even

| Step | SNR (dB) | SI-SDR (dB) | STOI | PESQ-WB | joint pass clips |
|---:|---:|---:|---:|---:|---:|
| 300 | 13.5538 ± 0.0613 | 12.4451 ± 0.0778 | 0.8903 ± 0.0012 | 2.2534 ± 0.0055 | 82.3 ± 0.6 |
| 500 | 13.6100 ± 0.0937 | 12.5141 ± 0.0721 | 0.8900 ± 0.0009 | 2.2456 ± 0.0089 | 85.7 ± 1.5 |
| 550 | 13.5527 ± 0.1117 | 12.4379 ± 0.1318 | 0.8878 ± 0.0022 | 2.2343 ± 0.0264 | 87.7 ± 2.9 |
| 800 | 13.5797 ± 0.0385 | 12.4732 ± 0.0642 | 0.8881 ± 0.0016 | 2.2372 ± 0.0233 | 86.0 ± 2.0 |

### Odd

| Step | SNR (dB) | SI-SDR (dB) | STOI | PESQ-WB | joint pass clips |
|---:|---:|---:|---:|---:|---:|
| 300 | 13.6035 ± 0.0660 | 12.3869 ± 0.1183 | 0.8853 ± 0.0016 | 2.2049 ± 0.0097 | 68.3 ± 0.6 |
| 500 | 13.7621 ± 0.1038 | 12.6112 ± 0.1042 | 0.8853 ± 0.0010 | 2.2136 ± 0.0059 | 74.7 ± 1.5 |
| 550 | 13.6995 ± 0.1173 | 12.5160 ± 0.1387 | 0.8834 ± 0.0018 | 2.2076 ± 0.0135 | 75.0 ± 1.0 |
| 800 | 13.7429 ± 0.0061 | 12.5910 ± 0.0166 | 0.8837 ± 0.0011 | 2.2109 ± 0.0159 | 77.3 ± 2.1 |

### Full

| Step | SNR (dB) | SI-SDR (dB) | STOI | PESQ-WB | joint pass clips |
|---:|---:|---:|---:|---:|---:|
| 300 | 13.5787 ± 0.0603 | 12.4160 ± 0.0965 | 0.8878 ± 0.0014 | 2.2292 ± 0.0072 | 150.7 ± 1.2 |
| 500 | 13.6860 ± 0.0987 | 12.5627 ± 0.0865 | 0.8877 ± 0.0009 | 2.2296 ± 0.0074 | 160.3 ± 1.5 |
| 550 | 13.6261 ± 0.1143 | 12.4769 ± 0.1352 | 0.8856 ± 0.0020 | 2.2210 ± 0.0199 | 162.7 ± 3.8 |
| 800 | 13.6613 ± 0.0221 | 12.5321 ± 0.0403 | 0.8859 ± 0.0013 | 2.2241 ± 0.0195 | 163.3 ± 2.5 |

## Interpretation

At the full-set level, Step 550 relative to Step 500 in the three-seed mean is not consistently better: mean SNR changes from 13.686 to 13.626 dB and PESQ from 2.230 to 2.221. The higher single-run R0 seed-26052 Step-550 result should therefore be treated as within the observed seed variation, not as a robust gain. From step 550 to 800, mean SNR, SI-SDR, STOI, and PESQ stay close to a broad plateau; there is no sustained post-550 collapse. PESQ is slightly higher at step 800 than at 550 in the even and full splits, while SI-SDR varies modestly.

This estimates across-run training variation at selected fixed checkpoints only. Three seeds are too few to characterize rare outcomes, and the 590-clip set is development data already used in prior selection. The empirical 2×SD thresholds are a practical screening rule, not a formal significance test.

The seed-run logs state `gold_test_read: false`. No gold audio was opened for this analysis.
