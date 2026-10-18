# DeepFilterNet3 Canonical Evaluation Binned by MEASURED Input SNR

Clips are binned by their **actual physically measured input SNR** ($10\log_{10}\frac{\|clean\|^2}{\|noisy - clean\|^2}$) rather than manifest labels.
This isolates the 4 proxy clips (034, 106, 242, 569) where 0 noise power was injected from corrupting the low-SNR bins.

| Measured SNR Bin | n | In SNR | Out SNR | $\Delta$ SNR | In SI-SDR | Out SI-SDR | $\Delta$ SI-SDR | In STOI | Out STOI | $\Delta$ STOI | In PESQ | Out PESQ | $\Delta$ PESQ | PS Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **-10 dB (<= -7.5)** | 30 | -10.00 | **-2.92** | **+7.08 dB** | -10.14 | **-4.48** | **+5.66 dB** | 0.571 | **0.648** | +0.077 | 1.089 | **1.144** | +0.055 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| **-5 dB (-7.5 to -2.5)** | 62 | -5.00 | **1.33** | **+6.33 dB** | -5.04 | **2.08** | **+7.12 dB** | 0.689 | **0.771** | +0.082 | 1.173 | **1.340** | +0.166 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| **0 dB (-2.5 to 2.5)** | 116 | 0.00 | **3.87** | **+3.87 dB** | -0.30 | **5.33** | **+5.63 dB** | 0.755 | **0.825** | +0.069 | 1.207 | **1.410** | +0.203 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| **5 dB (2.5 to 7.5)** | 137 | 5.00 | **6.95** | **+1.95 dB** | 4.65 | **9.24** | **+4.60 dB** | 0.826 | **0.875** | +0.049 | 1.420 | **1.687** | +0.267 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| **10 dB (7.5 to 12.5)** | 120 | 10.00 | **8.45** | <span style='color:red;'>**-1.55 dB** ⚠️</span> | 9.88 | **11.34** | **+1.46 dB** | 0.890 | **0.912** | +0.023 | 1.782 | **2.002** | +0.220 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| **15 dB (12.5 to 17.5)** | 85 | 15.00 | **10.25** | <span style='color:red;'>**-4.75 dB** ⚠️</span> | 14.78 | **13.46** | <span style='color:red;'>**-1.32 dB** ⚠️</span> | 0.935 | **0.943** | +0.008 | 2.100 | **2.291** | +0.191 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| **20 dB (17.5 to 30.0)** | 36 | 20.00 | **10.64** | <span style='color:red;'>**-9.36 dB** ⚠️</span> | 19.80 | **14.75** | <span style='color:red;'>**-5.05 dB** ⚠️</span> | 0.958 | **0.959** | +0.001 | 2.580 | **2.708** | +0.128 | ✅ PASS (STOI, PESQ) / ❌ FAIL (SNR) |
| **Clean / Outlier (>30 dB)** | 4 | 99.00 | **14.18** | <span style='color:red;'>**-84.82 dB** ⚠️</span> | 104.21 | **17.00** | <span style='color:red;'>**-87.21 dB** ⚠️</span> | 1.000 | **0.966** | -0.034 | 4.644 | **4.121** | -0.522 | ✅ PASS (STOI, PESQ) / ❌ FAIL (SNR) |
