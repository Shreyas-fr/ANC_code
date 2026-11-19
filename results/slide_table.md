| Input SNR | n | STOI (T>0.85) | PESQ (T>2.5) | Out SNR (T>15 dB) | SI-SDR gain | Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| -10 dB | 30 | 0.648 ❌ | 1.144 ❌ | -2.92 dB ❌ | +5.66 dB | FAIL |
| -5 dB | 62 | 0.771 ❌ | 1.340 ❌ | 1.33 dB ❌ | +7.12 dB | FAIL |
| 0 dB | 116 | 0.825 ❌ | 1.410 ❌ | 3.87 dB ❌ | +5.63 dB | FAIL |
| 5 dB | 137 | 0.875 ✅ | 1.687 ❌ | 6.95 dB ❌ | +4.60 dB | STOI only |
| 10 dB | 120 | 0.912 ✅ | 2.002 ❌ | 8.45 dB ❌ | +1.46 dB | STOI only |
| 15 dB | 85 | 0.943 ✅ | 2.291 ❌ | 10.25 dB ❌ | -1.32 dB | STOI only |
| 20 dB | 36 | 0.959 ✅ | 2.708 ✅ | 10.64 dB ❌ | -5.05 dB | STOI + PESQ |

Source: results/dfn3/per_snr_measured_bins.md (binned by measured input SNR; 4 clips with no injected noise excluded). Model: final_model/model.hk, SHA256 522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe. Output SNR = 10*log10(||clean||^2 / ||enhanced - clean||^2).
