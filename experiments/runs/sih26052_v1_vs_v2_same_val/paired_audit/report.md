# Paired V1 vs V2 Statistical Audit

## 1. Input Integrity
- INPUT_CSV=runs/sih26052_v1_vs_v2_same_val/per_example_metrics.csv
- INPUT_SHA256=da4ca3a92039d0e1cc94d586ea65eb21336508b0176134c96819104421df86a2
- ROW_COUNT=590
- GUNFIRE_ROWS=442
- PROXY_ROWS=148

## 2. Overall 590-Example Results
### PROJECT_SNR
- Mean Delta: -0.1021
- Median Delta: -0.1401
- Trimmed Mean (5%): -0.0861
- Std Dev: 1.8717
- Min: -14.3590, Max: 10.5630
- 25th Pct: -0.5580, 75th Pct: 0.4112
- Improved: 34.6%, Degraded: 54.2%, Tied: 11.2%
- Wilcoxon Stat: 74282.0, p-value: 1.8586e-03
- Effect Size (Cohen's d): -0.0545
- Distribution: mixed distribution

### SI-SDR
- Mean Delta: -0.0568
- Median Delta: -0.0113
- Trimmed Mean (5%): -0.0483
- Std Dev: 2.1457
- Min: -15.5713, Max: 10.9496
- 25th Pct: -0.5840, 75th Pct: 0.3815
- Improved: 39.7%, Degraded: 41.2%, Tied: 19.2%
- Wilcoxon Stat: 83338.0, p-value: 3.5460e-01
- Effect Size (Cohen's d): -0.0264
- Distribution: mixed distribution

### STOI
- Mean Delta: 0.0000
- Median Delta: 0.0000
- Trimmed Mean (5%): 0.0000
- Std Dev: 0.0001
- Min: -0.0004, Max: 0.0006
- 25th Pct: -0.0000, 75th Pct: 0.0001
- Improved: 0.0%, Degraded: 0.0%, Tied: 100.0%
- Wilcoxon Stat: 53284.0, p-value: 2.8120e-16
- Effect Size (Cohen's d): 0.3542
- Distribution: strong concentration around zero

### PESQ
- Mean Delta: 0.0028
- Median Delta: 0.0002
- Trimmed Mean (5%): 0.0009
- Std Dev: 0.0870
- Min: -0.5303, Max: 1.2033
- 25th Pct: -0.0056, 75th Pct: 0.0080
- Improved: 7.6%, Degraded: 6.3%, Tied: 86.1%
- Wilcoxon Stat: 82603.5, p-value: 2.7002e-01
- Effect Size (Cohen's d): 0.0326
- Distribution: strong concentration around zero

## 3. IoBT Gunfire Results
### PROJECT_SNR
- Mean Delta: -0.1429
- Median Delta: -0.1698
- Trimmed Mean (5%): -0.1335
- Std Dev: 1.7586
- Min: -14.3590, Max: 8.8648
- 25th Pct: -0.5107, 75th Pct: 0.3228
- Improved: 31.7%, Degraded: 55.9%, Tied: 12.4%
- Wilcoxon Stat: 38912.0, p-value: 1.8680e-04
- Effect Size (Cohen's d): -0.0813
- Distribution: mixed distribution

### SI-SDR
- Mean Delta: -0.1011
- Median Delta: -0.0309
- Trimmed Mean (5%): -0.0906
- Std Dev: 2.0038
- Min: -15.5713, Max: 10.1363
- 25th Pct: -0.5372, 75th Pct: 0.2780
- Improved: 37.8%, Degraded: 41.6%, Tied: 20.6%
- Wilcoxon Stat: 44991.0, p-value: 1.4051e-01
- Effect Size (Cohen's d): -0.0505
- Distribution: mixed distribution

### STOI
- Mean Delta: 0.0001
- Median Delta: 0.0000
- Trimmed Mean (5%): 0.0000
- Std Dev: 0.0001
- Min: -0.0003, Max: 0.0006
- 25th Pct: -0.0000, 75th Pct: 0.0001
- Improved: 0.0%, Degraded: 0.0%, Tied: 100.0%
- Wilcoxon Stat: 26033.0, p-value: 1.4739e-17
- Effect Size (Cohen's d): 0.4345
- Distribution: strong concentration around zero

### PESQ
- Mean Delta: 0.0005
- Median Delta: 0.0002
- Trimmed Mean (5%): 0.0010
- Std Dev: 0.0504
- Min: -0.5017, Max: 0.3911
- 25th Pct: -0.0052, 75th Pct: 0.0078
- Improved: 7.2%, Degraded: 5.9%, Tied: 86.9%
- Wilcoxon Stat: 46459.5, p-value: 3.5372e-01
- Effect Size (Cohen's d): 0.0092
- Distribution: strong concentration around zero

## 4. Existing Proxy Results
### PROJECT_SNR
- Mean Delta: 0.0200
- Median Delta: -0.0904
- Trimmed Mean (5%): 0.0660
- Std Dev: 2.1701
- Min: -13.6632, Max: 10.5630
- 25th Pct: -0.6571, 75th Pct: 0.6955
- Improved: 43.2%, Degraded: 49.3%, Tied: 7.4%
- Wilcoxon Stat: 5489.0, p-value: 9.6336e-01
- Effect Size (Cohen's d): 0.0092
- Distribution: mixed distribution

### SI-SDR
- Mean Delta: 0.0758
- Median Delta: 0.0454
- Trimmed Mean (5%): 0.0899
- Std Dev: 2.5176
- Min: -15.5179, Max: 10.9496
- 25th Pct: -0.6871, 75th Pct: 0.7430
- Improved: 45.3%, Degraded: 39.9%, Tied: 14.9%
- Wilcoxon Stat: 5190.0, p-value: 5.3637e-01
- Effect Size (Cohen's d): 0.0301
- Distribution: mixed distribution

### STOI
- Mean Delta: 0.0000
- Median Delta: 0.0000
- Trimmed Mean (5%): 0.0000
- Std Dev: 0.0001
- Min: -0.0004, Max: 0.0004
- 25th Pct: -0.0000, 75th Pct: 0.0001
- Improved: 0.0%, Degraded: 0.0%, Tied: 100.0%
- Wilcoxon Stat: 4689.0, p-value: 1.1471e-01
- Effect Size (Cohen's d): 0.1471
- Distribution: strong concentration around zero

### PESQ
- Mean Delta: 0.0099
- Median Delta: 0.0003
- Trimmed Mean (5%): 0.0011
- Std Dev: 0.1501
- Min: -0.5303, Max: 1.2033
- 25th Pct: -0.0072, 75th Pct: 0.0088
- Improved: 8.8%, Degraded: 7.4%, Tied: 83.8%
- Wilcoxon Stat: 5219.0, p-value: 5.7357e-01
- Effect Size (Cohen's d): 0.0661
- Distribution: strong concentration around zero

## 5. Wilcoxon Tests
Wilcoxon signed-rank tests were executed and their p-values are reported in the respective sections above. Scipy was successfully utilized. WILCOXON_STATUS=AVAILABLE.

## 6. Practical Effect Analysis
Effect sizes (Cohen's d) are included above. For most metrics, the effect sizes highlight whether the shifts are meaningful relative to the sample variance.

## 7. Trimmed-Mean / Outlier Analysis
By comparing the regular mean to the 5% trimmed mean, we can observe the impact of outliers. The top and bottom 10 outliers per key subgroup are saved in `outliers.csv`. In many metrics, the trimmed mean stays close to the regular mean and the median, indicating the shift is systemic rather than purely outlier-driven, though some outliers exhibit large swings (>10 dB).

## 8. Interpretation
On proxy data, the +0.0200 dB SNR mean delta is accompanied by a median of -0.0904, a trimmed mean of 0.0660, and 7.4% ties. The distribution is mixed distribution. This shows the effect on proxy data is effectively indistinguishable from zero or well within practical equivalence.
On gunfire data, the -0.1429 dB SNR mean delta has a median of -0.1698, a trimmed mean of -0.1335, and 55.9% degraded examples vs 31.7% improved. The distribution is mixed distribution. This indicates the degradation on gunfire is relatively consistent and not merely caused by a few extreme outliers.

## 9. Integrity Checks
MODEL_INFERENCE_RUN=NO
RETRAINING=NO
GOLD_LOADED=NO
GOLD_EVALUATED=NO
GOLD_MODIFIED=NO
