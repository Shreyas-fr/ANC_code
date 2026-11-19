# Stage 11.2.35R: Remaining Blockers & Hardware Qualification Gaps

This document records the remaining architectural, hardware, and deployment boundaries for SIH 26052 following Stage 11.2.35R host remediation.

---

## 1. Gate 04 — Raspberry Pi 5 Target Hardware Execution (LOCKED)

* **Status:** LOCKED / NOT QUALIFIED ON HARDWARE.
* **Scope:** All work in Stage 11.2.35R was executed exclusively on the Apple Silicon development host (macOS 15.1 ARM64, Apple clang 21.0.0, Apple M4).
* **Constraints Observed:**
  * No physical Raspberry Pi 5 hardware was accessed, connected, or provisioned.
  * No cross-compilation toolchains (e.g., `aarch64-linux-gnu-gcc`) or Debian aarch64 environments were invoked.
  * No deployment packages (`.deb` or tarballs) were transferred to embedded targets.
* **Analytical Projections vs Measured Reality:**
  * Host multi-threaded RTF ($0.1160$, $538.6\text{ FPS}$) demonstrates extensive host-side computational headroom (8.6x realtime).
  * On a Raspberry Pi 5 (Broadcom BCM2712 quad-core Cortex-A76 at 2.4 GHz), FullSubNet inference was measured at $11.8\text{ ms}$ per 16 ms chunk in Stage 11.2.34.4, Tract DFN3 requires $\sim 2.5\text{ ms}$, and GTCRN requires $\sim 1.5\text{ ms}$.
  * Hardware execution must be formally benchmarked in a designated Raspberry Pi 5 stage before Gate 04 can be unlocked.

---

## 2. Gate 05 — End-to-End Live Audio & Acoustical ANC (LOCKED)

* **Status:** LOCKED / ARCHITECTURALLY SEGREGATED.
* **Scope:** No ALSA drivers, PortAudio streams, microphone input, or loudspeaker playback were activated.
* **Strict Architectural Separation (Dual-Tier Architecture):**
  * **Tier 1 — Ultra-Low-Latency Local ANC ($\le 10\text{ ms}$):**
    * **Current Status:** **UNIMPLEMENTED / PROPOSED ONLY**.
    * The three-model deep learning ensemble cannot run within a 10 ms budget due to FullSubNet's 48 ms algorithmic lookahead (2 future frames at 16 ms hop) and 16 ms chunk size ($48 + 16 = 64\text{ ms}$ algorithmic latency floor).
    * Tier 1 local acoustic noise cancellation must be implemented via separate low-latency hardware (e.g., dedicated analog/digital DSP, FIR/IIR filter, or direct hardware codec loopback) and is completely out of scope of the Tier 2 deep speech enhancement model.
  * **Tier 2 — Frozen Tri-Model Ensemble for Voice Communications ($\le 80\text{ ms}$):**
    * **Current Status:** **HOST PROTOTYPE QUALIFIED**.
    * The $15/70/15$ ensemble ($0.15\text{ DFN3} + 0.70\text{ FullSubNet} + 0.15\text{ GTCRN}$) operates within the approved $\le 80\text{ ms}$ capture-to-transmitted-output communications budget:
      $$\text{Total Latency} = \text{Chunk Buffering (16 ms)} + \text{Algorithmic Lookahead (48 ms)} + \text{Compute Latency (1.85 ms)} = 65.85\text{ ms} \le 80\text{ ms}$$
    * Live acoustic validation of Tier 2 requires a dedicated acoustical test fixture.

---

## 3. GTCRN Single-Step ONNX State I/O Invariant

* **Status:** DOCUMENTED TECHNICAL INVARIANT FOR EMBEDDED PACKAGING.
* **Technical Root Cause:**
  * The current frozen `gtcrn_model.onnx` artifact possesses an utterance-level input signature: `[1, 257, time_frames, 2]`.
  * The graph does not expose external recurrent state tensors (e.g., `gru_h_in`, `gru_h_out`) or causal convolutional history buffers.
  * When invoked with single-step inputs ($T=1$), ONNX Runtime reinitializes the internal GRU hidden state to zeros on every chunk call.
* **Resolution Path for Stage 11.2.36 Embedded Deployment:**
  * Re-export GTCRN to ONNX with explicit recurrent state inputs and outputs (`gru_h_in`, `gru_h_out`), identical to the FullSubNet single-step export (`fullband_step.onnx` / `subband_step.onnx`), allowing native C code to maintain persistent GRU state without utterance batching.
  * On host, the causal streaming adapter verifies that when states are preserved, GTCRN achieves $115.09\text{ dB}$ SDR and $<1.52 \times 10^{-6}$ error against the canonical DNS3 reference.

---

## 4. Protected Holdout Dataset Seal

* **Status:** STRICTLY SEALED (`gold_test_read: false`).
* **Compliance Record:**
  * `data/SIH_GOLD_TEST` has remained completely untouched throughout Stage 11.2.35 and Stage 11.2.35R.
  * No file in `data/SIH_GOLD_TEST` was read, hashed, enumerated, decoded, or evaluated.
  * The holdout seal remains intact for final third-party blind testing.

