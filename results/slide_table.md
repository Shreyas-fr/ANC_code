| Input SNR | n | STOI (T>0.85) | PESQ (T>2.5) | Out SNR (T>15dB) | $\Delta$ SNR | Compliance |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **-10 dB** | 30 | 0.65 ❌ | 1.14 ❌ | -2.9 dB ❌ | +7.1 dB | FAIL |
| **-5 dB** * | 63 | 0.77 ❌ | 1.39 ❌ | 1.5 dB ❌ | +4.8 dB | FAIL |
| **0 dB** * | 117 | 0.83 ❌ | 1.43 ❌ | 4.0 dB ❌ | +3.1 dB | FAIL |
| **5 dB** | 137 | **0.88** ✅ | 1.69 ❌ | 7.0 dB ❌ | +2.0 dB | FAIL (PESQ, Out SNR) |
| **10 dB** * | 121 | **0.91** ✅ | 2.02 ❌ | 8.5 dB ❌ | -2.2 dB ⚠️ | FAIL (PESQ, Out SNR) |
| **15 dB** * | 86 | **0.94** ✅ | 2.31 ❌ | 10.3 dB ❌ | -5.7 dB ⚠️ | FAIL (PESQ, Out SNR) |
| **20 dB** | 36 | **0.96** ✅ | **2.71** ✅ | 10.6 dB ❌ | -9.4 dB ⚠️ | FAIL (Out SNR) |

*\* Note on Label Integrity: Rows -5, 0, 10, 15 dB include 4 proxy clips with 0 injected noise (~145 dB true SNR). See `results/dfn3/per_snr_measured_bins.md`.*

### Defense Gunfire Only (`IoBT_GUNFIRE`, 100% Exact Labels)

| Input SNR | n | STOI (T>0.85) | PESQ (T>2.5) | Out SNR (T>15dB) | $\Delta$ SNR | Compliance |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **5 dB (Gunfire)** | 104 | **0.87** ✅ | 1.68 ❌ | 7.1 dB ❌ | +2.1 dB | FAIL (PESQ, Out SNR) |
| **10 dB (Gunfire)** | 93 | **0.91** ✅ | 1.99 ❌ | 8.6 dB ❌ | -1.4 dB ⚠️ | FAIL (PESQ, Out SNR) |
| **15 dB (Gunfire)** | 63 | **0.94** ✅ | 2.24 ❌ | 10.3 dB ❌ | -4.7 dB ⚠️ | FAIL (PESQ, Out SNR) |

*Source: Measured directly on canonical fine-tuned DeepFilterNet3 (`final_model/model.hk`, SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`) via `scripts/evaluate_dfn3_deep_audit.py`. Output SNR defined as $10\log_{10}(\|\text{clean}\|^2 / \|\text{enh} - \text{clean}\|^2)$ after delay alignment.*
