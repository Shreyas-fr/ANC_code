# PHASE-MASK FORENSIC FIX TEST

## OUTPUT METRICS

| Test | 16ms peak | tail energy | RMS | speech corr | SI-SDR | SNR |
|---|---|---|---|---|---|---|
| CURRENT | 99.25 | 0.289287 | 0.008539 | -0.0841 | -2.00 | -2.00 |
| PHASE_ZERO | 99.26 | 0.289291 | 0.008539 | -0.0846 | -2.01 | -2.01 |
| IDENTITY | 111.03 | 0.324512 | 0.009551 | -0.0839 | -2.35 | -2.35 |

## PHASE STATISTICS (Current Model)

- Mean: -0.001225 rad
- Std: 0.017705 rad
- Min: -0.044259 rad
- Max: 0.051428 rad
- Median Absolute: 0.011420 rad
- Bins > 0.1 rad: 0.00%
- Bins > 0.5 rad: 0.00%
- Bins > 1.0 rad: 0.00%

## CRITICAL INTERPRETATION

**PHASE_ZERO does NOT reduce the artifact.**

The 16 ms cross-correlation peak and tail energy remain virtually identical across all three tests (CURRENT, PHASE_ZERO, and IDENTITY). The `IDENTITY` reconstruction actually produces an even larger 16ms peak than the neural mask. Additionally, the phase statistics show that the model's predicted phase is incredibly small (standard deviation of only 0.017 rad, with 0% of bins exceeding 0.1 rad). 

Therefore, we conclude:
**PHASE MASK IS NOT SUFFICIENT TO EXPLAIN THE ARTIFACT.**

## INTEGRITY CHECK
- Checkpoint modified: NO
- Production service modified: NO
- LSTM state modified: NO
- Live server implemented: NO
