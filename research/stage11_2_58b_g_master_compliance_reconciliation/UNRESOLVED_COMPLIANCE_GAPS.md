# Unresolved SIH 26052 Compliance Gaps & Risk Register

**Audit Date:** 2026-11-16  
**Project Milestone:** Stage 11.2.58B-G Master Compliance Reconciliation  
**Governing Architecture:** Track 1 (Mic 1 + Mic 2 → Corrected Causal MVDR → Frozen 15/70/15 Mono Ensemble)  

---

## 1. Executive Summary

This register formally documents the outstanding technical, acoustic, hardware, and legal compliance gaps identified across Stages 11.2.58B-A through 11.2.58B-H. In accordance with strict governance principles, no unfavorable finding is minimized, concealed, or marked as compliant without empirical proof.

---

## 2. Technical and Acoustic Compliance Gaps

### GAP-01: Absolute Output SNR > 15 dB Target Deficit
- **Target Specification:** SIH Problem Statement calls for enhanced output SNR $> 15.0\text{ dB}$.
- **Empirical Status:** **NOT MET (0 / 200 clips pass on Independent Evaluation Set).**
- **Measured Data (Stage 11.2.58B-E2):** Mean output SNR is **$-0.09\text{ dB}$** ($95\%\text{ CI: } [-0.68, +0.49]\text{ dB}$); maximum clip output SNR is **$+12.24\text{ dB}$**.
- **Root Cause (Stage 11.2.58B-H):** 
  1. *Severe Acoustic Stress:* Input SNR ranges from $-22.79\text{ dB}$ to $+4.92\text{ dB}$ (mean $-7.37\text{ dB}$). Achieving $>15\text{ dB}$ output would require an unprecedented $+22.37\text{ dB}$ average attenuation without speech distortion.
  2. *Reverberant Reference Mismatch:* Clean reference is anechoic direct-path; physical room reflections ($T_{60} \in [0.20, 0.45]\text{ s}$) create an inherent $-2.87\text{ dB}$ average error ceiling when evaluated against direct-path speech.
  3. *Waveform Scaling Deviation:* Deep learning models scale output amplitude by $\approx 0.85\text{--}0.95$, imposing an inherent $1.5\text{--}3.5\text{ dB}$ penalty in unscaled waveform difference $e[n] = y[n] - s[n]$.
- **Distinction:** Track 1 achieves consistent, significant **SNR improvement** ($\Delta\text{SNR} = \mathbf{+7.27\text{ dB}}$, up to $+15.88\text{ dB}$), but **Absolute Output SNR does NOT exceed 15 dB**.

### GAP-02: Perceptual Speech Quality (PESQ-WB > 2.50) Shortfall
- **Target Specification:** PESQ-WB $> 2.500$.
- **Empirical Status:** **NOT MET (3 / 200 clips pass on Independent Evaluation Set).**
- **Measured Data:** Mean PESQ-WB on the independent 200-clip benchmark is **$1.523$** ($95\%\text{ CI: } [1.474, 1.572]$).
- **Limitation:** In severe noise conditions ($-10\text{ to } -5\text{ dB}$ target, $-22.8\text{ dB}$ actual), wideband PESQ is heavily penalized by residual non-stationary artifacts and aggressive noise masking.

### GAP-03: FullSubNet Whole-Utterance Normalization Streaming Barrier
- **Target Specification:** Real-time bounded-latency streaming.
- **Architectural Barrier (Stage 11.2.58B-E):** FullSubNet Epoch58 uses utterance-wide offline normalization:
  $$\mu = \frac{1}{T \cdot F} \sum_{t=1}^T \sum_{f=1}^F |X(t, f)|, \quad \sigma = \sqrt{\frac{1}{T \cdot F} \sum_{t=1}^T \sum_{f=1}^F (|X(t, f)| - \mu)^2}$$
  In a live unbounded audio stream, computing whole-utterance normalization requires infinite future knowledge ($T \to \infty$).
- **Impact:** Exact bit-identical reproduction of FullSubNet in live streaming is mathematically impossible without introducing an online approximation (e.g., rolling exponential moving average) which inevitably alters inference behavior.

### GAP-04: Multi-Model Delay Equalization Requirement
- **Target Specification:** Synchronous fusion of DFN3 (15%), FullSubNet (70%), and GTCRN (15%).
- **Engineering Constraint (Stage 11.2.58B-E):**
  - FullSubNet uses 2 lookahead frames ($32\text{ ms} = 512\text{ samples}$ algorithmic delay).
  - DFN3 has an internal delay of $603\text{ samples}$ (combining lookahead and polyphase resampler FIR group delay).
  - GTCRN is strictly causal ($0\text{ samples}$ lookahead).
- **Impact:** In a stateful streaming implementation, ring-buffer delay compensation (padding DFN3 and GTCRN buffers) is required before combining branches to prevent catastrophic comb-filtering phase cancellation.

---

## 3. Hardware and Deployment Gaps

### GAP-05: Raspberry Pi 5 Physical Performance Unverified
- **Target Specification:** Real-time embedded execution on Raspberry Pi 5 (Quad-core Cortex-A76 @ 2.4 GHz).
- **Current Status:** **ESTIMATED / PROJECTED ONLY.**
- **Limitation:** No physical Raspberry Pi 5 hardware has been connected, benchmarked, or thermally profiled in recent milestones. All reported RTF values ($0.37\times$) and memory footprints ($312\text{ MB}$) were measured on a host Apple Silicon Mac.

### GAP-06: Physical Microphone Array and Headset Integration
- **Target Specification:** Dual-microphone physical array with 30 mm spacing, physical communication headset, and live audio I/O.
- **Current Status:** **PENDING PHYSICAL HARDWARE.**
- **Limitation:** All dual-microphone evaluations used synthetic room impulse response (ISM) simulations. No physical MEMS microphone array, I2S audio shield, or physical headset has been verified in an operational acoustic environment.

### GAP-07: Real-Time Demonstration & Low-Latency Compliance
- **Target Specification:** Live capture-to-headset processing with mouth-to-ear latency $\le 35\text{ ms}$ (project gate) / $\le 50\text{ ms}$ (SIH feasibility).
- **Current Status:** **NOT DEMONSTRATED.**
- **Projected Latency:** Stage 11.2.58B-E established an estimated mouth-to-ear budget of **$90.2\text{ ms}$** under a 16 ms chunk size (48 ms algorithmic delay + 36 ms compute + 6.2 ms ALSA/DAC I/O), which exceeds the strict 35 ms project gate.

---

## 4. Legal, Provenance, and Governance Gaps

### GAP-08: Dataset Commercial Clearance & Redistribution
- **Audit Findings (Stage 11.2.58B-D):**
  - ESC-50 noise assets carry **CC BY-NC 3.0** (strictly non-commercial).
  - DEMAND noise assets carry **CC BY-SA 4.0** (copyleft ShareAlike obligations).
  - OpenSLR 28 point noises carry Apache 2.0 packaging, but upstream web scraping provenance (Freesound/SoundBible) lacks individual contributor releases.
- **Compliance Status:** **Academic research ready ONLY; Commercial deployment NOT cleared.**

### GAP-09: Field Participant Data Collection Locked
- **Audit Findings:** Mandatory Qualification Tracker remains at **0/5 gates cleared**. Ethical, participant safety, and acoustic protocol gates remain locked. Physical data recording is strictly NO-GO.

