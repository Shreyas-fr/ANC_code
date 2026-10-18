# SI-SDR Loss Ablation Report

## 1. Integrity Checks
- Parameter count: 1448962
- Architecture: StatefulPolarLSTM
- Canonical Hash: Verified
- Gold Hash: Verified (46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9)

## 2. Best Checkpoint
- Best validation step: 20000
- Best validation loss: 4.546
- The checkpoint has stable mask statistics: 0.95 mean mask, NaN count 0, very stable phase, and speech correlation of 0.789.

## 3. Statistical Comparison
When compared against the V2 Polar-D baseline on the canonical 590 validation examples, the SI-SDR loss model yielded:
- **ALL**: SI-SDR improved by +0.33 dB (p < 0.05). SNR improved by +0.13 dB (p < 0.05). PESQ and STOI had very minor positive deltas.
- **IoBT Gunfire**: SI-SDR improved by +0.27 dB (p < 0.05). SNR degraded marginally by -0.006 dB.
- **Existing Proxy**: SI-SDR improved by +0.51 dB (p < 0.05). SNR improved by +0.53 dB (p < 0.05).

## 4. Conclusion
While the improvement is numerically small (+0.33 dB SI-SDR), it is statistically significant across the entire canonical dataset and shows no catastrophic degradations. The addition of the SI-SDR term successfully optimized the time-domain metrics without destroying the frequency-domain stability (zero NaNs, safe mask bounds). It represents a defensible, incremental improvement.

STATUS: SI_SDR_ABLATION_IMPROVED
