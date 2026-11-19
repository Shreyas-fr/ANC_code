# Evidence Note: Audio Enhancement Spectrogram Example

## 1. Source Artifacts & Evaluation Suite
- **Presentation Graph Artifact:** [results/ppt_spectrogram_comparison.png](file:///d:/ANC_code/results/ppt_spectrogram_comparison.png) (Exported from high-resolution validation run [results/spectrogram_10dB.png](file:///d:/ANC_code/results/spectrogram_10dB.png))
- **Secondary Scenario Artifact:** [results/spectrogram_-5dB.png](file:///d:/ANC_code/results/spectrogram_-5dB.png)
- **Evaluation Dataset Log:** [results/metrics.csv](file:///d:/ANC_code/results/metrics.csv) (1,194 test evaluations across 6 SNR tiers)
- **Summary Table:** [results/results_table.md](file:///d:/ANC_code/results/results_table.md)
- **Problem Statement Targets Report:** [REPORT.md](file:///d:/ANC_code/REPORT.md)

## 2. Spectrogram Comparison Structure
The visual artifact [ppt_spectrogram_comparison.png](file:///d:/ANC_code/results/ppt_spectrogram_comparison.png) provides a 3-panel time-frequency STOI/PESQ validation comparison:
1. **Top Panel:** Clean Reference Speech (Harmonic speech formants clearly preserved up to 8 kHz).
2. **Middle Panel:** Noisy Input (10 dB SNR condition with background noise interference spanning 0–8000 Hz).
3. **Bottom Panel:** Neural Enhanced Output (Substantial reduction of stationary and non-stationary background noise floor while reconstructing speech harmonics).

## 3. Measured Aggregate Metrics for Test Condition (10 dB SNR, N=199 Utterances)
- **Input SNR -> Output SNR:** **10.0 dB -> 12.69 dB** (Mean Improvement: **+2.69 dB**)
- **Input STOI -> Output STOI:** **0.90 -> 0.9049** (**PASS**, exceeds PS Target of > 0.85)
- **Input PESQ -> Output PESQ:** **1.73 -> 2.0360** (Mean Improvement: **+0.30**)
- **SI-SDR Improvement:** **+2.47 dB**

### Supplementary Scenario (-5 dB SNR Challenging Condition, N=199 Utterances)
- **Input SNR -> Output SNR:** **-5.0 dB -> 2.32 dB** (Mean Improvement: **+7.32 dB**)
- **Input STOI -> Output STOI:** **0.69 -> 0.7070**
- **Input PESQ -> Output PESQ:** **1.13 -> 1.2281**
- **SI-SDR Improvement:** **+5.61 dB**

## 4. Scientific Disclaimer & Assessment
- **Nature of Evidence:** This spectrogram example is an **illustrative validation pair** selected directly from the project's standardized evaluation suite.
- **Limitation:** A single spectrogram comparison illustrates qualitative frequency-bin attenuation and formant preservation; it **does not** prove global generalization across all acoustic environments. Full statistical metrics across the complete 1,194-sample benchmark in [results/metrics.csv](file:///d:/ANC_code/results/metrics.csv) should be referenced for overall system capabilities.
