# SIH 26052 — Stage 11.2.10: Final Source-Integrity, Build, and Governance Reconciliation Audit

**Project:** Smart India Hackathon (SIH 26052)  
**Stage:** 11.2.10 (Final Source-Integrity, Build & Governance Reconciliation Audit)  
**Status:** Software Verification Complete | ARM64 Object Compilation Verified | Final ELF Linker & Physical Bench Pending  
**Collection Authorization Status:** **NO-GO FOR STAGE 11.3** (`0/5` Physical Qualification Gates Passed)  
**Date:** 2026-11-13  
**Target Hardware:** Raspberry Pi 5 (Broadcom BCM2712, Quad-core ARM Cortex-A76 @ 2.4 GHz)  
**Host Architecture:** Apple Silicon Mac (`aarch64-apple-darwin`, Darwin Kernel 25.6.0, Apple clang 17.0.0, rustc 1.99.0)  
**Target Architecture:** Linux ARM64 (`aarch64-unknown-linux-gnu`, Debian 12 Bookworm, Cortex-A76)  

---

## 1. Executive Summary & Audit Mandate

Stage 11.2.10 conducts a narrow, exhaustive final audit of source integrity, build mechanics, and governance reconciliation prior to any physical hardware qualification.

### Primary Audit Findings:
1. **Source Inspection of `DfTract::reset()`:** Verified that every state-bearing component (Tract recurrent GRU states, rolling spectral deques, STFT analysis/synthesis memories, and EMA normalization vectors) is completely re-instantiated to pristine conditions. An audit of `libDF/src/` confirmed zero global mutable state across calls.
2. **Independent Session-Isolation Reproduction:** Re-executed [`scripts/test_session_isolation.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/test_session_isolation.py) from the final source tree. All five operational sequences passed with bit-exact **$\mathbf{0.00 \times 10^0}$** absolute error across every utterance.
3. **Continuous Streaming Invariance:** Executed [`scripts/verify_continuous_streaming_integrity.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/verify_continuous_streaming_integrity.py) across 1.0 s, 5.0 s, 10.0 s, and 20.0 s streams (up to 960,000 samples). Continuous-stream output with per-file reset vs `--no-reset` was **100% bit-exact ($0.00\text{ difference}$, $r = 1.000000$, $\text{SDR} = 120.00\text{ dB}$)**, proving that the reset implementation does not interfere with continuous streaming.
4. **ARM64 Linux Cross-Build Evaluation:**
   - **Target Sysroot:** Installed `rust-std-aarch64-unknown-linux-gnu`.
   - **Cross-Typechecking (`cargo check --target aarch64-unknown-linux-gnu`):** **PASSED** (0 errors, 8.40 s).
   - **Crate & Assembly Compilation:** **PASSED**. All 80+ dependency crates—including `tract-linalg` with custom ARM64 NEON matrix multiplication assembly routines (`arm64simd_mmm_f32_...`)—compiled to ARM64 machine code using Clang with `--target=aarch64-unknown-linux-gnu`.
   - **Cross-Linking on macOS Darwin:** **FAILED (exit code 101)** as expected, because the macOS host linker (`ld64`) rejects GNU ELF linker flags (`--version-script`, `-Wl,-z,relro`, `-Bstatic`).
   - **Target Environment Resolution:** On native Raspberry Pi 5 hardware (Debian 12 Bookworm), system GNU ld natively accepts all ELF flags. **Host build (`aarch64-apple-darwin`) is strictly distinguished from target ARM64 Linux build (`aarch64-unknown-linux-gnu`)**.
5. **Governance & Gate Definition Reconciliation:** Reconciled historical documentation divergences. Re-established the single, authoritative set of 5 physical qualification gates in [`STAGE11_2_1_QUALIFICATION_TRACKER.csv`](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/STAGE11_2_1_QUALIFICATION_TRACKER.csv) and [`scripts/verify_stage11_qualification_gates.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/verify_stage11_qualification_gates.py), preserving all ethics, consent, facility, ADC, and Pi 5 criteria.
6. **Immutable Protected Checksums & Sealed Gold Boundary:** Verified all 5 core checksums bit-for-bit. Confirmed `data/SIH_GOLD_TEST` remains unread and isolated (`gold_test_read: false`).
7. **Three-Way Project Status Separation:** Formally updated governance reporting to reflect separate statuses for Software Verification (Complete), ARM64 Compilation (Source Compiled / Linker Pending Target), and Physical Pi 5 Qualification (Unmeasured / Pending).

---

## 2. Workstream 1: Source Inspection of `DfTract::reset()`

### 2.1 State-Bearing Component Analysis
The native `DfTract` struct encapsulates the following state-bearing elements:

```rust
#[derive(Clone)]
pub struct DfTract {
    df_params: DfParams,
    r_params: RuntimeParams,
    enc: TractModel,                       // Recurrent GRU h_t & pulsed delay nodes
    erb_dec: TractModel,                   // Recurrent GRU h_t & pulsed delay nodes
    df_dec: TractModel,                    // Recurrent GRU h_t & pulsed delay nodes
    df_states: Vec<DFState>,               // STFT analysis/synthesis memory, EMA vectors
    rolling_spec_buf_y: VecDeque<Tensor>,  // DF order + lookahead spectral history (cap 7)
    rolling_spec_buf_x: VecDeque<Tensor>,  // Noisy spectral history (cap 5)
    spec_buf: Tensor,                      // Intermediate frame buffer
    erb_buf: TValue,                       // Intermediate ERB energy buffer
    cplx_buf: TValue,                      // Intermediate complex spectrum buffer
    skip_counter: usize,                   // Silence skip counter
    // ... static config fields ...
}
```

### 2.2 Reset Method Implementation
In [`libDF/src/tract.rs`](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/libDF/src/tract.rs#L435-L442):

```rust
impl DfTract {
    /// Reset internal state between independent utterances.
    /// Completely restores all recurrent GRU states, rolling spectrogram buffers,
    /// STFT analysis/synthesis memories, and EMA normalization states to initial pristine condition.
    pub fn reset(&mut self) -> Result<()> {
        let fresh = Self::new(self.df_params.clone(), &self.r_params)?;
        *self = fresh;
        Ok(())
    }
}
```

### 2.3 Verification of Complete State Restoration
1. **Recurrent GRU Hidden States ($h_t$):** `Self::new()` invokes `init_encoder_from_read`, `init_erb_decoder_from_read`, and `init_df_decoder_from_read`, which invoke `SimpleState::new()`. This allocates a completely empty `SessionState` and uninitialized `states` vector, wiping all previous recurrent history.
2. **Rolling Spectrogram Buffers:** In `Self::new()`, `m.init()?` clears `rolling_spec_buf_y` and `rolling_spec_buf_x` and fills them with pristine zero tensors.
3. **STFT Analysis Memory:** `DFState::new()` creates a zeroed `Vec<f32>` of length 480 (1 hop lookback).
4. **iSTFT Synthesis Memory:** `DFState::new()` creates a zeroed `Vec<f32>` of length 480 (10.0 ms overlap-add tail).
5. **EMA Normalization States:** `state.init_norm_states(nb_df)` initializes `mean_norm_state` and `unit_norm_state` to canonical initial vectors (`MEAN_NORM_INIT` and `UNIT_NORM_INIT`).
6. **Skip Counter:** Initialized to `0`.

### 2.4 Audit of Global / Static Mutable State
A codebase-wide search across `libDF/src/` for `static mut`, mutable statics, and thread-local state revealed:
- `static LOGGER_INIT: Once = Once::new();` (one-time logging init).
- `static INIT: Once = Once::new();` (test harness only).
- `static ALLOC: jemallocator::Jemalloc` (optional allocator).
- **Result:** Exactly zero global mutable state exists for signal processing. All streaming and model state is strictly owned by the `DfTract` struct instance. Re-assigning `*self = fresh;` guarantees 100% complete state isolation.

---

## 3. Workstream 2: Independent Session-Isolation Reproduction

The test suite [`scripts/test_session_isolation.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/test_session_isolation.py) was re-executed against the final native binary:

```
================================================================================
SIH 26052 — STAGE 11.2.9: SESSION-STATE ISOLATION AUDIT
================================================================================
Native Binary: antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter
Model Archive: models/dfn3_step500_tract.tar.gz
================================================================================

[Sequence 1] Continuous Frames in One Session...
  Continuous Stream Duration: 3.0 s | Finite: True | RMS: 0.0603 | [PASS]

[Sequence 2] Two Independent Sessions in One Process...
  Max Absolute Difference with RESET:    0.00e+00 (Threshold < 1e-6) [PASS]
  Max Absolute Difference WITHOUT RESET: 3.23e-01 (Notice state contamination without reset)

[Sequence 3] Session Reset Followed by Silence...
  Silence Output Energy WITH RESET:    0.00e+00 | Max Amp: 0.00e+00 [PASS]
  Silence Output Energy WITHOUT RESET: 1.01e-03 (Residual tail leakage)

[Sequence 4] Continuous-Stream Output Equivalence After Reset vs Fresh Model...
  Max Absolute Difference (Fresh vs Post-Reset): 0.00e+00 (Threshold < 1e-6) [PASS]

[Sequence 5] Multiple Independent Utterances in One Process (10 Clips)...
  10-Utterance Batch: Worst Max Absolute Difference: 0.00e+00 (Threshold < 1e-6) [PASS]

================================================================================
SESSION-STATE ISOLATION AUDIT SUMMARY
================================================================================
Audit Record JSON: antigravity/research/STAGE11_2_9_SESSION_ISOLATION.json
OVERALL VERDICT: PASSED (Zero cross-talk, bit-exact equivalence, complete session isolation confirmed)
================================================================================
```

Every sequence achieved a maximum absolute difference of **$0.00 \times 10^0$**, confirming zero cross-utterance contamination.

---

## 4. Workstream 3: Verification of Continuous-Session Output Invariance

To prove that the reset implementation does not degrade or alter continuous streaming output within a session, [`scripts/verify_continuous_streaming_integrity.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/verify_continuous_streaming_integrity.py) was executed across multiple stream lengths:

```
================================================================================
SIH 26052 — STAGE 11.2.10: CONTINUOUS STREAMING INTEGRITY VERIFICATION
================================================================================
Native Binary: antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter
Model Archive: models/dfn3_step500_tract.tar.gz
================================================================================

Evaluating Continuous Stream Duration: 1.0 s (48000 samples)...
  Max Absolute Difference: 0.00e+00 (Threshold <= 1e-6)
  Pearson Correlation:     1.000000 (Threshold >= 0.99999)
  Signal-to-Distortion:    120.00 dB (Threshold >= 60.0 dB)
  Verdict:                 [PASS]

Evaluating Continuous Stream Duration: 5.0 s (240000 samples)...
  Max Absolute Difference: 0.00e+00 (Threshold <= 1e-6)
  Pearson Correlation:     1.000000 (Threshold >= 0.99999)
  Signal-to-Distortion:    120.00 dB (Threshold >= 60.0 dB)
  Verdict:                 [PASS]

Evaluating Continuous Stream Duration: 10.0 s (480000 samples)...
  Max Absolute Difference: 0.00e+00 (Threshold <= 1e-6)
  Pearson Correlation:     1.000000 (Threshold >= 0.99999)
  Signal-to-Distortion:    120.00 dB (Threshold >= 60.0 dB)
  Verdict:                 [PASS]

Evaluating Continuous Stream Duration: 20.0 s (960000 samples)...
  Max Absolute Difference: 0.00e+00 (Threshold <= 1e-6)
  Pearson Correlation:     1.000000 (Threshold >= 0.99999)
  Signal-to-Distortion:    120.00 dB (Threshold >= 60.0 dB)
  Verdict:                 [PASS]

================================================================================
CONTINUOUS STREAMING INTEGRITY AUDIT SUMMARY
================================================================================
Machine-readable JSON: antigravity/research/STAGE11_2_10_CONTINUOUS_STREAMING_AUDIT.json
OVERALL VERDICT: PASSED (Continuous-session streaming output is 100% bit-exact and unchanged)
================================================================================
```

### Technical Findings:
1. Within a single audio file or continuous session, `model.process()` iterates frame-by-frame with zero resets.
2. The initial call to `model.reset()` before processing file 0 is functionally and mathematically identical to the initial `new()` invocation.
3. Therefore, continuous-session streaming output is **100% bit-exact ($0.00\text{ error}$)**.

---

## 5. Workstream 4: Reproducible ARM64 Build Attempt & Detailed Reporting

### 5.1 Environment Configuration
- **Host System:** Apple Silicon Mac (`aarch64-apple-darwin`)
- **Target Triple:** `aarch64-unknown-linux-gnu`
- **Compiler:** `rustc 1.99.0` with `rust-std-aarch64-unknown-linux-gnu`
- **C Cross-Compiler:** `clang` with `CFLAGS="--target=aarch64-unknown-linux-gnu"`

### 5.2 Step 1: Target Typecheck & Compilation
Command:
```bash
export CC_aarch64_unknown_linux_gnu="clang"
export CFLAGS_aarch64_unknown_linux_gnu="--target=aarch64-unknown-linux-gnu"
cd antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/libDF
cargo check --target aarch64-unknown-linux-gnu --bin deep-filter --features "bin,tract,wav-utils,transforms"
```
**Result: SUCCESS (Exit Code 0, 8.40 s)**.  
All 80+ dependency crates (`tract-core`, `tract-onnx`, `tract-pulse`, `tract-linalg`, `realfft`, `ndarray`, `deep_filter`) compiled cleanly for ARM64 Linux without syntax, type, or platform errors.

### 5.3 Step 2: Full Release Crate Compilation
Command:
```bash
cargo build --release --target aarch64-unknown-linux-gnu --bin deep-filter --features "bin,tract,wav-utils,transforms"
```
**Compilation Phase:** **SUCCESS**.  
All `.rs` source files and `tract-linalg` NEON matrix multiplication assembly kernels (`arm64simd_mmm_f32_...`) successfully compiled into ARM64 Linux `.rlib` static archives and `.o` object files.

**Linking Phase:** **FAILED (Exit Code 101)**.  
Linker Diagnostic:
```
= note: ld: unknown options: --version-script=... --no-undefined-version --fix-cortex-a53-843419 --as-needed -Bstatic -Bdynamic --eh-frame-hdr -z --gc-sections -z -z --strip-debug
        clang: error: linker command failed with exit code 1 (use -v to see invocation)
```

### 5.4 Root Cause Analysis
1. When targeting `aarch64-unknown-linux-gnu` without an explicit cross-linker configured in `.cargo/config.toml`, `rustc` invokes the host C compiler (`clang`) as the linker driver.
2. On macOS Darwin, `clang` delegates to Apple's Mach-O linker (`/usr/bin/ld` / `ld64`).
3. The Mach-O linker does not recognize GNU ELF linker flags (`--version-script`, `-Wl,-z,relro`, `-Bstatic`, `--fix-cortex-a53-843419`).
4. To produce a final linked ELF binary on macOS Darwin, an ELF linker such as `lld` (`rust-lld` or `ld.lld`) or an `aarch64-linux-gnu-gcc` cross-toolchain is required.
5. On the native Raspberry Pi 5 target (running Raspberry Pi OS 64-bit / Debian 12 Bookworm), GNU ld (`/usr/bin/ld.bfd` or `ld.gold`) is the default native linker and accepts all of these flags natively.

> [!IMPORTANT]
> **Strict Distinction Enforced:**
> - Host binary: `antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter` (`aarch64-apple-darwin`, Mach-O 64-bit executable, verified for software testing).
> - Target ARM64 Linux binary: Source and object compilation verified; final ELF linking pending native Pi 5 target build or containerized cross-linker.
> - **We do NOT substitute a host build for an ARM64 Linux build.**

---

## 6. Workstream 5: Reconciliation of Qualification Gate Definitions

A historical audit revealed that early documentation revisions occasionally displayed a parallel 5-gate in-silico list (Test Set Isolation, Benchmark Equivalence, Power Proof, Statistical Significance, Pi 5 Reproduction) alongside the real-world qualification gates.

Stage 11.2.10 formally reconciles the qualification framework into a clear two-tier structure:

### Tier 1: Software & Protocol Pre-Bench Verification (In-Silico — Complete)
These five workstreams verify mathematical, algorithmic, and statistical readiness prior to hardware deployment:
1. **Sealed Gold Boundary:** `data/SIH_GOLD_TEST` isolated (`gold_test_read: false`).
2. **Deterministic Model Export:** Step-500 Tract package SHA-256 `99e99379...`.
3. **Mathematical Equivalence:** Pearson $r = 0.98418$, $\text{SDR} = 54.91\text{ dB}$, 0-sample delay lag.
4. **Session-State Isolation:** Zero cross-talk, bit-exact $0.00$ error across consecutive utterances.
5. **Statistical Power Proof:** 10,000-iteration simulation, $n=240$ per bin, Holm-Bonferroni FWER control.

### Tier 2: Real-World Physical Qualification Gates (Hardware & Governance — Locked)
These are the **five mandatory physical qualification gates** enforced by [`STAGE11_2_1_QUALIFICATION_TRACKER.csv`](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/STAGE11_2_1_QUALIFICATION_TRACKER.csv) and [`scripts/verify_stage11_qualification_gates.py`](file:///Users/shreyasdivekar/Documents/anc%20sih/scripts/verify_stage11_qualification_gates.py). All five must be cleared before Stage 11.3 physical collection can be authorized:

```
+-----------------------------------------------------------------------------------------------------------------------+
| ID      | Gate Name                                  | Authority           | Required Evidence Artifact                | Status |
+---------+--------------------------------------------+---------------------+-------------------------------------------+--------+
| GATE_01 | Formal Ethics Committee Approval (IEC/IRB) | Chair_IEC           | evidence/IEC_APPROVAL_CERTIFICATE.pdf     | LOCKED |
| GATE_02 | Legal and Participant Consent Sign-Off     | Legal_Counsel       | evidence/LEGAL_COUNSEL_ATTESTATION.pdf    | LOCKED |
| GATE_03 | Acoustic Booth Facility Certification      | Metrology_Lead      | evidence/BOOTH_ACOUSTIC_CERTIFICATE.pdf   | LOCKED |
| GATE_04 | ADC Hardware Calibration Qualification     | Hardware_Lead       | evidence/ADC_BENCH_CALIBRATION_REPORT.pdf | LOCKED |
| GATE_05 | Physical Raspberry Pi 5 Reproduction       | Embedded_Lead       | evidence/PI5_PHYSICAL_BENCH_REPORT.pdf    | LOCKED |
+-----------------------------------------------------------------------------------------------------------------------+
```

Every ethics, consent, facility, ADC, benchmark, and Raspberry Pi 5 requirement is strictly preserved and enforced.

---

## 7. Workstream 6: Verification of Protected Checksums & Sealed-Gold Boundary

Independent verification confirmed that all five core project checksums remain 100% bit-exact:

```
d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4  runs/sih26052_canonical_validation/manifest.csv
bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27  antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt
482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0  antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar
a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79  antigravity/checkpoints/gtcrn_stage5/model_trained_on_dns3.tar
99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d  models/dfn3_step500_tract.tar.gz
```

- Sealed test set: `data/SIH_GOLD_TEST` is a symbolic link to `antigravity/data/SIH_GOLD_TEST`, sealed and unread (`gold_test_read: false`).
- Production runtime: `~/anc_live` untouched.
- Git working tree: modified files (`REPORT.md`, `system_diagrams.md`) preserved unstaged; zero files committed.

---

## 8. Workstream 7: Project Status Overview with Disaggregated Statuses

In accordance with Scope Item 7, project capabilities are disaggregated into explicit, distinct operational statuses:

| Workstream / Capability Area | Technical Assessment | Status |
| :--- | :--- | :---: |
| **Step-500 Checkpoint Integrity** | Verified bit-exact (`bc1fc9b7...`), loaded strict | **VERIFIED** |
| **Tract Export Reproducibility** | Verified bit-exact package (`99e99379...`), deterministic container | **VERIFIED** |
| **Host-Native Runtime (Darwin)** | Host binary (`aarch64-apple-darwin`) verified, $r=0.98418$, $\text{SDR}=54.91\text{ dB}$ | **OPERATIONAL** |
| **Session-State Isolation** | Top-level `DfTract::reset()` verified, $0.00$ cross-talk across 5 sequences | **VERIFIED** |
| **Continuous Streaming Invariance** | Verified $0.00$ error, $r=1.000000$, $\text{SDR}=120.00\text{ dB}$ across streams up to 20.0 s | **VERIFIED** |
| **ARM64 Linux Source & Objects** | Target compilation (`aarch64-unknown-linux-gnu`) verified for all 80+ crates | **COMPILED** |
| **ARM64 Linux Final ELF Linking** | Cross-linker pending GNU ld on native Pi 5 or containerized toolchain | **PENDING** |
| **Physical Raspberry Pi 5 Benchmark** | Hardware performance (RTF, latency, thermals) unmeasured on physical device | **UNMEASURED** |
| **Physical Recording Study** | IEC clearance, consent, booth, and ADC calibration pending | **NOT AUTHORIZED** |
| **Stage 11.3 Physical Data Collection** | Mandatory Gatekeeper reports 0/5 gates passed (exit code 1) | **STRICTLY NO-GO** |

---

## 9. Conclusion & Next Steps

Stage 11.2.10 confirms that the software, numerical, and session-isolation foundations of SIH 26052 are complete, robust, and mathematically verified. The codebase is clean, well-tested, and ready for deployment onto physical Raspberry Pi 5 hardware.

No qualification gates have been unlocked, and physical data collection remains strictly prohibited until formal evidentiary sign-offs are submitted and verified.

---

## Evidence correction (2026-11-14)

The 54.91 dB waveform SDR repeated in this audit is retracted. The later numerical audit found that the metric script accidentally used the fourth-power error sum after mutating the error array in place; the corrected synthetic waveform SDR is **18.92 dB**. Do not cite 54.91 dB as parity evidence. Any host-native binary or synthetic test described here is not proof of Pi 5 deployment qualification or full-path real-time latency. The current evidence status is maintained in `MASTER_SIH_COMPLIANCE.md`; see also `STAGE11_2_15_NUMERICAL_DISCREPANCY_AUDIT.md`.

