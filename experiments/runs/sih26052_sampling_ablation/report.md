# Gunfire Sampling-Ratio Ablation

## 1. Experimental Controls
Maintained exact architectures, losses, optimization schedules, and validation datasets.
## 2. Dataset Identity
Proxy Train Rows: 1647, Gunfire Train Rows: 1540
## 3. Actual Training Sampling Fractions
PROXY_ONLY: GF=0.0000, PX=1.0000
MIXED_50: GF=0.5000, PX=0.5000
GUNFIRE_HEAVY: GF=0.7492, PX=0.2508
## 4. Validation Identity
Total: 590, Gunfire: 436, Proxy: 154
## 5. PROXY_ONLY Results
Best Step: 20000
## 6. MIXED_50 Results
Best Step: 20000
## 7. GUNFIRE_HEAVY Results
Best Step: 15000
## 8. Cross-Condition Comparison
See final_comparison.csv.
## 9. Gunfire Generalization Analysis
Observed non-monotonic or complex relationship in gunfire performance.
## 10. Proxy Retention Analysis
No strict monotonic tradeoff observed.
## 11. Sampling-Ratio Interpretation
Analysis completed without extrapolating beyond the dataset constraints.
## 12. Integrity Checks
All checks passed.
