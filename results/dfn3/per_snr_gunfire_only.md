# DeepFilterNet3 Evaluation: IoBT Gunfire Subset Only (Exact Labels)

- **Dataset Origin**: `IoBT_GUNFIRE` exclusively ($n=442$)
- **Label Integrity**: 100% exact (0 / 442 clips have SNR label deviation > 0.01 dB)
- **Evaluated Model**: Canonical DFN3 (`final_model/model.hk`, SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`)

## Problem Statement (PS) Targets
- Output SNR > 15.0 dB | STOI > 0.85 | PESQ > 2.50

| Target SNR | n | In SNR | Out SNR | $\Delta$ SNR | In SI-SDR | Out SI-SDR | $\Delta$ SI-SDR | In STOI | Out STOI | $\Delta$ STOI | In PESQ | Out PESQ | $\Delta$ PESQ | PS Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| -10 dB | 22 | -10.00 | **-2.89** | **+7.11 dB** | -10.16 | **-4.30** | **+5.86 dB** | 0.612 | **0.680** | +0.069 | 1.075 | **1.154** | +0.079 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| -5 dB | 54 | -5.00 | **1.54** | **+6.54 dB** | -5.06 | **2.38** | **+7.44 dB** | 0.705 | **0.779** | +0.073 | 1.181 | **1.364** | +0.183 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| +0 dB | 84 | 0.00 | **3.82** | **+3.82 dB** | -0.40 | **5.26** | **+5.66 dB** | 0.756 | **0.826** | +0.070 | 1.211 | **1.416** | +0.206 | ❌ FAIL / ❌ FAIL (SNR, STOI, PESQ) |
| +5 dB | 104 | 5.00 | **7.14** | **+2.14 dB** | 4.55 | **9.33** | **+4.77 dB** | 0.824 | **0.870** | +0.047 | 1.433 | **1.679** | +0.246 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| +10 dB | 93 | 10.00 | **8.61** | <span style='color:red;'>**-1.39 dB** ⚠️</span> | 9.84 | **11.45** | **+1.61 dB** | 0.890 | **0.909** | +0.019 | 1.772 | **1.990** | +0.218 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| +15 dB | 63 | 15.00 | **10.30** | <span style='color:red;'>**-4.70 dB** ⚠️</span> | 14.70 | **13.36** | <span style='color:red;'>**-1.34 dB** ⚠️</span> | 0.932 | **0.940** | +0.008 | 2.107 | **2.236** | +0.129 | ✅ PASS (STOI) / ❌ FAIL (SNR, PESQ) |
| +20 dB | 22 | 20.00 | **11.18** | <span style='color:red;'>**-8.82 dB** ⚠️</span> | 19.68 | **15.06** | <span style='color:red;'>**-4.62 dB** ⚠️</span> | 0.954 | **0.954** | -0.000 | 2.629 | **2.695** | +0.066 | ✅ PASS (STOI, PESQ) / ❌ FAIL (SNR) |
