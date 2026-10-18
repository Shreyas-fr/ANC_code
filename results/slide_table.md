| Input SNR | STOI (T>0.85) | PESQ (T>2.5) | Out SNR (T>15dB) | Compliance |
|:---:|:---:|:---:|:---:|:---:|
| -10 dB | 0.65 ❌ | 1.14 ❌ | -2.9 dB ❌ | FAIL |
| -5 dB | 0.77 ❌ | 1.39 ❌ | 1.5 dB ❌ | FAIL |
| 0 dB | 0.83 ❌ | 1.43 ❌ | 4.0 dB ❌ | FAIL |
| 5 dB | **0.88** ✅ | 1.69 ❌ | 7.0 dB ❌ | FAIL (PESQ, Out SNR) |
| 10 dB | **0.91** ✅ | 2.02 ❌ | 8.5 dB ❌ | FAIL (PESQ, Out SNR) |
| 15 dB | **0.94** ✅ | 2.31 ❌ | 10.3 dB ❌ | FAIL (PESQ, Out SNR) |
| 20 dB | **0.96** ✅ | **2.71** ✅ | 10.6 dB ❌ | FAIL (Out SNR) |

*Source: Measured directly on canonical fine-tuned DeepFilterNet3 (`final_model/model.hk`, SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`) over 590 canonical validation clips via `scripts/evaluate_dfn3_per_snr.py`. Output SNR defined as $10\log_{10}(\|\text{clean}\|^2 / \|\text{enh} - \text{clean}\|^2)$ after delay alignment.*
