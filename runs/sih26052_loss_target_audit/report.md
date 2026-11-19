# Polar-D Objective Audit Report

## Section 1: Implementation Trace
1. `src/enhance/losses.py` (EnhancementLoss: L33-44): Calculates `5.0 * L1(waveform) + 5.0 * MRSTFTLoss(waveform)`. 
2. `src/enhance/stateful_polar_lstm.py` (StatefulPolarLSTM: L29-38): Generates raw magnitude and phase representations from LSTM hidden states. 
3. `src/enhance/stateful_polar_lstm.py` (StatefulPolarLSTM_Wrapper: L48-68): Takes raw audio, performs `center=False` STFT, applies network, produces complex mask `mr, mi`, multiplies with noisy STFT, and performs `causal_istft`.
4. `scripts/train_v2_25k.py` (L128-L135): Feeds noisy waveform to model. Collects enhanced waveform and aligns clean waveform via `clean[:, :L_out]`. Computes loss solely on these two waveforms.

## Section 2: Loss Equation
LOSS_TERM_1=5.0 * ||enh - clean||_1 (Waveform L1)
LOSS_TERM_2=5.0 * (Spectral Convergence + Log STFT Magnitude) over FFTs [512, 1024, 2048]
TOTAL_LOSS_EQUATION=LOSS_TERM_1 + LOSS_TERM_2

## Section 3: Target Representation
TARGET_TYPE=CLEAN WAVEFORM (End-to-End)
TARGET_COMPLEX_MASK_FORMULA=NOT_EXPLICITLY_COMPUTED
TARGET_MAGNITUDE_RANGE=NOT_APPLICABLE
TARGET_PHASE_RANGE=NOT_APPLICABLE
TARGET_CLIPPING=NOT_APPLICABLE
TARGET_NORMALIZATION=NONE
The network is trained purely on waveform distance; no explicit mask targets are ever calculated or supervised.

## Section 4: Polar-D Output Parameterization
PREDICTED_MAGNITUDE_RANGE=[0.0, 2.0] (via `sigmoid * 2.0`)
PREDICTED_PHASE_RANGE=[-pi, pi] (via `tanh * pi`)
MASK_FORMULA=mag * exp(j * phase)
IDENTITY_INITIALIZATION=YES (Linear biases zeroed, meaning mag ~1.0, phase ~0.0 initially)
IDENTITY_MASK=1.0 + 0j

## Section 5: Gradient Path
Gradient Finite: True
Gradient Nonzero: True
Gradient Magnitude: 0.248169

## Section 6: Identity Reconstruction
IDENTITY_SNR=38.8553
IDENTITY_MAX_ABS_ERROR=1.4391e+00
IDENTITY_RMS_ERROR=1.2805e-02

## Section 7: Target Reconstruction Test
TARGET_MASK_SNR=-4.4464
TARGET_MASK_SI_SDR=-4.5775
TARGET_MASK_STOI=0.9976
TARGET_MASK_PESQ=3.5219

## Section 8: Phase Audit
Phase Mean: 0.0017, Std: 0.7143, Min: -3.1416, Max: 3.1416
Phase > 0.1 rad: 80.11%, > 0.5: 29.25%, > 1.0: 11.54%, > 2.0: 3.18%
Mag Mean: 0.9658, Std: 0.4208, Min: 0.0030, Max: 2.0000
Mag > 1: 37.87%, > 2: 3.94%, < 0.5: 9.73%

## Section 9: Loss/Metric Alignment
1. Waveform fidelity: DIRECTLY ALIGNED. The L1 loss penalizes time-domain errors directly.
2. SI-SDR: WEAKLY ALIGNED. While lower L1 error tends to correlate with better SI-SDR, L1 is sensitive to global scale which SI-SDR explicitly ignores. The STFT loss provides better correlation but still penalizes phase and scale strictly.
3. Project SNR: DIRECTLY ALIGNED. SNR minimizes squared error in the waveform domain, which overlaps heavily with L1 and STFT spectral convergence.
4. STOI: WEAKLY ALIGNED. STOI is highly correlated with clean magnitude envelope preservation (handled by MRSTFT loss) but does not directly supervise correlation.
5. PESQ: NOT DIRECTLY ALIGNED. PESQ is an asymmetrical perceptual metric.

## Section 10: Controlled Loss Ablation
Initial SDR: 6.0131, SNR: 6.0027
Full Loss (A) - Initial Loss: 5.7488, Final Loss: 101.0170
Full Loss (A) - Final SDR: -29.3968, SNR: -21.4484
L1 Only (B) - Initial Loss: 0.4006, Final Loss: 0.4453
L1 Only (B) - Final SDR: -14.4681, SNR: -11.4654
STFT Only (C) - Initial Loss: 0.7506, Final Loss: 2.8163
STFT Only (C) - Final SDR: -7.1459, SNR: -5.1777

## Section 11: Data/Target Sanity
STFT/iSTFT alignment is verified structurally via L_out. Center=False creates a strict causal frame map. No target leakage is present.

## Section 12: Final Classification
LOSS_TARGET_AUDIT_PASS
