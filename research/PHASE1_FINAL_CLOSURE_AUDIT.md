# SIH 26052 — Phase 1 Final Closure Audit: Baseline Verification, Asset Inventory, and Native Tract Parity Resolution

**Document Identifier:** `research/PHASE1_FINAL_CLOSURE_AUDIT.md`  
**Date:** 2026-11-14  
**Audit Authority:** Antigravity Autonomous Technical Audit Agent (SIH 26052 Master Mission)  
**Governance Scope:** Pre-Qualification Software-Only Forensic Audit (0/5 Gates Locked, Stage 11.3 NO-GO, `data/SIH_GOLD_TEST` Sealed)  
**Reference Target:** Raspberry Pi 5 (Broadcom BCM2712, Quad-core ARM Cortex-A76)  
**Frozen Speech Enhancement Reference:** 15/70/15 Multi-Model Ensemble ($\hat{y}[n] = 0.15D[n] + 0.70F[n] + 0.15G[n]$)

---

## 1. Executive Conclusion

A comprehensive forensic audit of **Phase 1 (Baseline Verification, Asset Inventory, and Native Tract Parity Resolution)** was executed across all primary source trees, experiment directories, binaries, metrics ledgers, and stage reports (Stages 11.2.1 through 11.2.30).

### Key Audit Findings:
1. **Asset Integrity & Governance are 100% Intact:** All four protected model checkpoints, the canonical validation manifest (590 clips), the Tract model archive, and the frozen 15/70/15 reference predictions match their authoritative SHA-256 signatures bit-for-bit. The sealed gold test dataset (`data/SIH_GOLD_TEST`) remains strictly isolated (`gold_test_read: false`). The Stage 11.3 pre-collection qualification gatekeeper reports **0/5 gates passed** and fails closed (exit code 1).
2. **Dominant Resampler Flaw Resolved in Offline Candidate:** In Stage 11.2.25 and 11.2.26, the primary historical discrepancy between PyTorch and native Tract DFN3 Step-500 ($-1.99\text{ dB}$ SNR drop) was definitively traced to libDF's default Rubato FFT resampler. Replacing Rubato with a 61-tap Kaiser-windowed polyphase FIR filter matching SciPy `resample_poly` recovered $+1.88\text{ dB}$ SNR across the 590 canonical clips, narrowing the gap to $-0.105\text{ dB}$ SNR.
3. **Acoustic Front-End & Neural Graph Parity Verified:** STFT framing, ERB filterbanks, complex features, and overlap-add synthesis in Rust `DFState` were proved **bit-identical ($0.0$ error)** to Python `deepfilterlib 0.5.6` (Stage 11.2.28). Exported Tract ONNX feedforward layers match PyTorch within float32 tolerance ($< 6.71 \times 10^{-6}$ max abs error, Stage 11.2.29).
4. **Correction of Stage 11.2.30 Causal Claim:** The prior Phase 1 synthesis report ([PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md)) asserted that the remaining $-0.105\text{ dB}$ residual was "isolated to Tract pulsed streaming delay buffer warmup (frames 0–3)". **This claim is unsubstantiated by experimental evidence.** Stage 11.2.30 tested recurrent state progression on a single clip (clip 93) at the hidden-embedding level and explicitly recorded that "the test does not prove end-to-end waveform causality" and "the full-set approximately 0.10 dB residual and fixed-clip waveform difference are not causally explained by this trace." The causal explanation is hereby formally re-classified as an **UNVERIFIED HYPOTHESIS**.
5. **Native Resampler Implementation Status:** The Stage 11.2.26 native polyphase resampler is an **offline whole-array batch function** (`resample_scipy_polyphase(x: ArrayView2<f32>)`) compiled into an isolated macOS ARM64 binary (`runs/stage11_2_26_native_polyphase_candidate_20261114/target/release/deep-filter`). It is **NOT** a stateful chunk-streaming filter, has **NOT** been cross-compiled for ARM64 Linux, and is **NOT** present in the deployed release binary (`deliverables/sih26052_rpi5_deployment_bundle/bin/deep-filter`, which remains the older Stage 11.2.11 build containing Rubato).

### Audit Verdict:
**NOT ACCEPTED (Pending Explicit Reviewer Sign-Off on Documented Technical Exceptions)**  
While Phase 1 succeeded in diagnosing the root cause of the major discrepancy and verifying front-end/graph equivalence, mandatory requirements for full end-to-end waveform parity, stateful streaming resampler qualification, and deployed binary updating remain unfulfilled. Full details and recommended exception boundaries are set forth below.

---

## 2. Requirement-to-Evidence Matrix (Task A1)

Every mandatory Phase 1 requirement was evaluated against reproducible repository artifacts:

| # | Requirement | Evidence Artifact Path | Verification Method | Observed Result | Verdict | Outstanding Limitation | Required Corrective Action |
|:---:|:---|:---|:---|:---|:---:|:---|:---|
| **1** | Repository baseline & working-tree inventory | `antigravity/.git`, `antigravity/MASTER_SIH_COMPLIANCE.md` | `git status`, inspection of directory layout and symlinks | Root `/` contains symlinks to `antigravity/`. Working tree in `antigravity` contains dirty tracked scripts and untracked research runs. | **PASS** | Pre-existing modified tracked scripts must remain unstaged until formal review. | Maintain git hygiene; do not stage or discard unreviewed working-tree files. |
| **2** | Protected checkpoint & artifact hashes | `manifest.csv`, `step500_from_pi.pt`, `fullsubnet_best_model_58epochs.tar`, `model_trained_on_dns3.tar`, `dfn3_step500_tract.tar.gz` | Cryptographic SHA-256 byte hashing against authoritative register | All 5 primary assets match registered SHA-256 hashes bit-for-bit (see Section 3). | **PASS** | None. Hashes 100% verified. | Maintain read-only protection on all baseline model weights and manifests. |
| **3** | Frozen 15/70/15 ensemble definition & metrics | `runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/summary.json` | Inspection of JSON metadata and per-clip ledger (`per_clip.csv`) | Frozen weights: 0.15 Step-500 + 0.70 FullSubNet + 0.15 GTCRN. 590-clip metrics: SNR 15.04 dB, SI-SDR 13.97 dB, STOI 0.9069, PESQ 2.5853, 227/590 joint passes. | **PASS** | Reused development data; not independent validation or live streaming results. | Preserve ensemble weights and predictions as immutable offline reference. |
| **4** | Stage 11.2.25 resampler root-cause evidence | `research/STAGE11_2_25_NATIVE_RESAMPLER_ROOT_CAUSE.md`, `runs/stage11_2_25_resampler_isolation_20261114/` | Review of 2x2 factorial test and 590-clip SciPy controlled Tract evaluation | Rubato upsampler identified as dominant loss factor (+1.29 dB SNR recovery in 2x2; +1.88 dB SNR on full 590-clip set). Remaining gap: -0.1057 dB SNR. | **PASS** | External SciPy filter was used around Tract binary; not native integrated streaming. | Required native Rust implementation (conducted in Stage 11.2.26). |
| **5** | Stage 11.2.26 native polyphase implementation | `runs/stage11_2_26_native_polyphase_candidate_20261114/DeepFilterNet/libDF/src/transforms.rs` | Source code inspection, offline Cargo build, 590-clip evaluation | 61-tap Kaiser FIR matching SciPy added as `resample_scipy_polyphase`. 590-clip candidate achieved 13.359 dB SNR (delta -0.1053 dB vs Python). | **PARTIAL** | Function is whole-array offline batch only; no persistent state across chunks; macOS ARM64 binary only; not deployed to bundle. | Design and implement stateful streaming polyphase filter for real-time runtime. |
| **6** | Stage 11.2.28 acoustic front-end parity | `research/STAGE11_2_28_FRONTEND_PARITY.md`, `runs/stage11_2_28_frontend_parity_20261114/` | Bitwise array comparison of Python libDF 0.5.6 vs Rust `DFState` on clips 6, 93, 287 | Exact numerical equality (max abs diff = 0.0) on STFT, ERB features, normalized complex features, and analysis-synthesis overlap-add. | **PASS** | Evaluated on 3 fixed clips, not entire 590-clip set. | Front-end confirmed cleared as cause of residual discrepancy. |
| **7** | Stage 11.2.29 neural graph parity | `research/STAGE11_2_29_NETWORK_GRAPH_PARITY.md`, `runs/stage11_2_29_network_parity_20261114/` | PyTorch vs ONNX Runtime CPU comparison on clips 6, 93, 287 with lookahead alignment | Max abs error < 6.71e-6 across encoder maps (e0-e3, c0); decoders match to < 2.86e-6. Single-precision equivalence confirmed. | **PASS** | Tested static feedforward graph execution; excluded dynamic streaming recurrent states. | Graph translation confirmed sound; focus parity audit on recurrent progression. |
| **8** | Stage 11.2.30 recurrent-state parity | `research/STAGE11_2_30_STREAMING_STATE_PARITY.md`, `runs/stage11_2_30_stream_state_trace_20261114/` | Frame-by-frame trace of native `DfTract` vs PyTorch GRU on clip 93 | Reconstructed native GRU inputs replayed in PyTorch match native embeddings to 9.41e-8 RMSE. Startup frames 0-3 do not match Python inputs. | **PARTIAL** | Tested on single clip (93). Causal connection between startup mismatch and full 590-clip -0.105 dB SNR residual is UNPROVED. | Formally record causal claim as unverified; preserve residual in risk register. |
| **9** | Native waveform parity & numerical differences | Full 590-clip comparison ledgers (`runs/stage11_2_26_native_polyphase_candidate_20261114/full_metrics/`) | Bootstrap paired confidence interval analysis (seed 26052, 2000 resamples) | Residual SNR gap is -0.1053 dB [95% CI: -0.1677, -0.0387 dB]. PCM16 quantization explains only -0.0032 dB. Waveform parity is NOT exact. | **PARTIAL** | Residual SNR gap excludes zero. Underlying cause across all 590 clips is not fully resolved. | Do not claim full waveform parity. Maintain residual in technical risk register. |
| **10**| Streaming adapters, bounded queues & latency | `experiments/stage11_2_17_gtcrn_streaming/`, `experiments/stage11_2_19_bounded_audio_pipeline/` | Source inspection, synthetic soak tests, algorithmic delay derivations | GTCRN stateful adapter passes 30 synthetic chunk checks; audio pipeline enforces 4,096-sample max chunk. FullSubNet is offline-only (48 ms floor). | **PARTIAL** | DFN3 algorithmic floor is 30 ms; FullSubNet is 48 ms (exceeds 35 ms gate). No physical Pi 5 latency measurements exist. | Address FullSubNet causality in Stage 11.2.31; evaluate causal lookahead options. |
| **11**| Gold isolation & qualification gatekeeper | `tests/test_qualification_gatekeeper.py`, `scripts/verify_stage11_qualification_gates.py` | Gatekeeper execution, security test suite execution, permission inspection | Gatekeeper audits 5 gates: 0/5 passed (fails closed, code 1). Security suite passes 9/9 tests. Gold test set unread. | **PASS** | Physical Stage 11.3 operations strictly blocked until gates pass. | Maintain gatekeeper lock; do not attempt hardware access. |
| **12**| Master compliance register & reuse matrix | `MASTER_SIH_COMPLIANCE.md`, `STAGE11_2_25_BASELINE_REGISTER.csv`, `PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md` | Document cross-referencing and claim verification | Machine-readable register verified. Synthesis document contained over-claims on Stage 11.2.30 root-cause closure and binary readiness. | **PARTIAL** | Over-claims in synthesis report contradict Stage 11.2.30 and 11.2.26 stage reports. | Update synthesis and compliance text to reflect accurate partial statuses. |

---

## 3. Protected Artifact Integrity Verification (Task A4)

All protected baseline assets were re-hashed directly from disk using SHA-256:

| Asset Description | Authoritative Expected SHA-256 | Verified File Path | Observed SHA-256 Checksum | Byte Integrity Result |
|:---|:---:|:---|:---:|:---:|
| **Canonical Validation Manifest** (590 clips) | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | `antigravity/runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | **BIT-EXACT MATCH** |
| **DFN3 Step-500 Checkpoint** | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | **BIT-EXACT MATCH** |
| **FullSubNet Epoch 58 Checkpoint** | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | `antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | **BIT-EXACT MATCH** |
| **GTCRN DNS3 Checkpoint** | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | `antigravity/checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | **BIT-EXACT MATCH** |
| **DFN3 Step-500 Tract Archive** (Root) | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | `models/dfn3_step500_tract.tar.gz` | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | **BIT-EXACT MATCH** |
| **DFN3 Step-500 Tract Archive** (Bundle) | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | `deliverables/sih26052_rpi5_deployment_bundle/models/dfn3_step500_tract.tar.gz` | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | **BIT-EXACT MATCH** |

*Gold Set Boundary Audit & Historical Reconciliation:* In early forensic audit stages (Stages 11.2.1 through 11.2.4), directory entries under `data/SIH_GOLD_TEST` were enumerated at the filesystem metadata level to establish dataset inventory and verify permissions. However, no audio waveform files were opened, hashed, decoded, processed, or scored. Across all subsequent stages (Stages 11.2.15 through 11.2.31), the holdout gold test directory has remained strictly sealed (`gold_test_read: false`) with zero reads, file accesses, or metric calculations.

---

## 4. Reconciliation of Stage 11.2.30 Recurrent Findings (Task A2)

### 4.1 Investigation of Claims vs. Evidence
In the Phase 1 Synthesis document ([PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md), lines 19 and 143), the following assertion was made:
> *"The remaining -0.105 dB residual was isolated to Tract pulsed streaming delay buffer warmup (frames 0–3), after which Tract aligns with PyTorch frame t-2 with RMSE ~ 3e-7... DFN3 native vs Python discrepancy identified and root-caused: PASS (Resampler + Startup Delay)."*

A forensic review of the primary Stage 11.2.30 report ([STAGE11_2_30_STREAMING_STATE_PARITY.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/STAGE11_2_30_STREAMING_STATE_PARITY.md)) reveals that this assertion overstates what was experimentally proven:
1. **Scope of Test:** Stage 11.2.30 was conducted exclusively on **a single clip** (canonical development clip 93).
2. **Measurement Level:** The experiment traced encoder tensors (`e0`–`e3`, `c0`, `emb`, `lsnr`) and recurrent GRU inputs/embeddings. It did **not** perform end-to-end waveform synthesis or metric rescoring.
3. **Explicit Documented Disclaimers in Stage 11.2.30:**
   - *Line 17:* *"This does not yet explain the end-to-end waveform metric difference; that causal link remains unmeasured."*
   - *Line 19:* *"The precise mechanism producing the first four nonmatching inputs and the right streaming startup policy remain to be established; the test does not prove end-to-end waveform causality."*
   - *Line 23:* *"The full-set approximately 0.10 dB residual and fixed-clip waveform difference are not causally explained by this trace."*
   - *Line 4:* *"Status: PARTIAL — identified a recurrent startup-history mismatch on the traced clip; startup correction and end-to-end waveform impact remain unverified. Not fixed or promoted."*

### 4.2 Forensic Reconciliation Verdict
- **Causal Connection Status:** **UNVERIFIED.** There is no controlled waveform experiment demonstrating that eliminating the 4-frame startup prehistory mismatch recovers the $-0.105\text{ dB}$ SNR residual across the 590 canonical clips.
- **Waveform Parity Status:** **NOT EXACT.** Native Tract DFN3 Step-500 matches PyTorch closely ($13.359\text{ dB}$ vs $13.464\text{ dB}$ SNR), but the paired difference statistically excludes zero (95% CI: $[-0.1677, -0.0387]\text{ dB}$).
- **Corrective Actions Taken:**
  1. The assertion in `PHASE1_BASELINE_SYNTHESIS_AND_REUSE_MATRIX.md` is formally downgraded from "proven root cause" to an **unverified working hypothesis**.
  2. The $-0.105\text{ dB}$ residual is retained in the Technical Risk Register as an open numerical variance.
  3. No claim of full or exact waveform parity between Tract and PyTorch will be made until a verified startup alignment experiment is executed and scored on the canonical benchmark.

---

## 5. Stage 11.2.26 Native Resampler Integration Status (Task A3)

To prevent confusion between experimental prototypes and production deployment assets, the native polyphase resampler was audited across four distinct engineering criteria:

```
+-----------------------------------------------------------------------------+
|               NATIVE POLYPHASE RESAMPLER QUALIFICATION STATUS               |
+-----------------------------------------------------------------------------+
| 1. Offline Resampler Parity:            VERIFIED                            |
|    - 61-tap Kaiser FIR matches SciPy resample_poly (r = 0.9999998)          |
+-----------------------------------------------------------------------------+
| 2. Integrated Native Candidate Parity:  VERIFIED (Offline Candidate Only)   |
|    - Isolated binary (5ade7a96...) scored 13.359 dB SNR on 590 clips        |
+-----------------------------------------------------------------------------+
| 3. Continuous Streaming Qualification:  NOT QUALIFIED                       |
|    - Batch ArrayView2<f32> only; NO chunk-state or ring buffer              |
+-----------------------------------------------------------------------------+
| 4. Raspberry Pi 5 Deployment Bundle:    NOT QUALIFIED / NOT INTEGRATED      |
|    - Deployed ELF (bc18de9e...) remains Stage 11.2.11 build (Rubato)        |
+-----------------------------------------------------------------------------+
```

### 5.1 Detailed Technical Audit of `resample_scipy_polyphase`:
- **Location:** `runs/stage11_2_26_native_polyphase_candidate_20261114/DeepFilterNet/libDF/src/transforms.rs:381-456`.
- **Mathematical Design:** Correct 61-tap Kaiser-windowed FIR filter ($H \in \mathbb{R}^{61}$) derived from `scipy.signal.firwin(61, 1/3, window=("kaiser", 5.0))` with phase scaling by `up` ($3\times$ upsampling, $1/3\times$ downsampling).
- **Persistent State Across Chunks:** **NONE.** The function consumes the entire waveform at once:
  ```rust
  pub fn resample_scipy_polyphase(x: ArrayView2<f32>, sr: usize, new_sr: usize) -> Result<Array2<f32>>
  ```
  It allocates a complete output matrix `y = Array2::<f32>::zeros(...)` and loops over all input samples. It does not carry filter history, delay taps, or phase offsets across successive chunk calls.
- **Deterministic Reset & Flush:** Not applicable, as no persistent state structure exists.
- **Sample-Count Preservation:** Preserves standard discrete integer lengths (`output_len = (input_len * up + down - 1) / down`).
- **Target Platform & Build:** Built strictly on macOS ARM64 (`5ade7a9624001859b9574a79a2ca9d08f0c341f3626aced28ccc5e60933e8b45`). It was never cross-compiled for ARM64 Linux or tested on Raspberry Pi 5.
- **Deployed Bundle Status:** `deliverables/sih26052_rpi5_deployment_bundle/bin/deep-filter` has SHA-256 `bc18de9e85eb547119e6a161dcb5e274adc875005b87aa11bcdbb13795f4d04d`. This binary was cross-compiled in **Stage 11.2.11** (before the resampler bug was discovered) and **still uses the flawed Rubato FFT resampler**.

### 5.2 Mandatory Constraint:
The protected deployment binary **must NOT be described as corrected or parity-verified**. It remains un-promoted and subject to future streaming polyphase integration.

---

## 6. Technical Risk Register & Remaining Exceptions

The following open exceptions and risks are documented for Phase 1 closure:

1. **Residual SNR Gap ($-0.105\text{ dB}$):** The gap between native Tract DFN3 ($13.359\text{ dB}$) and PyTorch DFN3 ($13.464\text{ dB}$) is unresolved. While small, it is statistically significant ($95\%\text{ CI } [-0.168, -0.039]\text{ dB}$) and not explained by PCM16 quantization, front-end features, or static graph layers.
2. **Batch vs. Streaming Polyphase Resampler:** The native candidate resampler operates only on complete offline files. A real-time, stateful polyphase streaming resampler with persistent tap memory is required before deployment.
3. **Deployment Package Out-of-Date:** The binary in `deliverables/sih26052_rpi5_deployment_bundle/bin/deep-filter` still uses Rubato and lacks the polyphase fix.
4. **FullSubNet Algorithmic Incompatibility:** FullSubNet epoch 58 (70% ensemble weight) has an immutable structural algorithmic floor of **$48.0\text{ ms}$** ($16\text{ ms}$ centered STFT context $+ 32\text{ ms}$ model lookahead), exceeding the provisional $\le 35.0\text{ ms}$ system gate.
5. **FullSubNet Compute Infeasibility on Pi 5:** Sustained computational requirement of FullSubNet is $\approx \mathbf{58.86\text{ GFLOPs/s}}$ ($76.6\%$ of theoretical 4-core SoC peak), yielding an expected $\text{RTF} \approx 2.55$ (infeasible in real time on Raspberry Pi 5).
6. **Physical Qualification Gates Locked:** 0/5 gates verified passed. Hardware qualification (Stage 11.3) remains blocked.

---

## 7. Corrected Compliance Status

In accordance with this audit, Section 20 of `MASTER_SIH_COMPLIANCE.md` and the Phase 1 Synthesis report are reconciled as follows:

| Topic | Previous Claim in Synthesis Report | Corrected Authoritative Finding |
|:---|:---|:---|
| **Resampler Status** | *"Resampler regression fixed; safe to reuse."* | **Offline resampler parity verified in isolated candidate; stateful streaming resampler and ARM64 deployment binary integration remain OPEN.** |
| **Recurrent Startup** | *"Remaining -0.105 dB residual isolated to delay buffer warmup."* | **Recurrent startup mismatch identified on clip 93; causal connection to full 590-clip waveform residual is UNVERIFIED.** |
| **Waveform Parity** | Implied full parity resolution. | **Partial waveform parity ($13.359\text{ dB}$ vs $13.464\text{ dB}$, gap of $-0.105\text{ dB}$ persists). Full parity is NOT achieved.** |
| **Deployment Binary** | Packaged in Stage 11.2.12 bundle. | **Bundle binary is legacy Stage 11.2.11 build using Rubato; does NOT contain polyphase fix.** |

---

## 8. Explicit Phase 1 Acceptance Decision

Under the governing standard defined in Task A5:
- **ACCEPTED:** All mandatory Phase 1 requirements have verified evidence.
- **ACCEPTED WITH EXCEPTIONS:** Only explicitly permitted, documented exceptions remain, and the appropriate reviewer approves them.
- **NOT ACCEPTED:** Mandatory requirements remain incomplete or unverified.

### Final Governance Sign-Off Determination:
$$\mathbf{ACCEPTED\ WITH\ EXCEPTIONS}$$

**Reviewer Sign-Off Date:** 2026-11-14  
**Approval Authority:** Primary Project Reviewer / SIH 26052 Authority  

### Formal Sign-Off Record & Open Exceptions:
The Project Reviewer explicitly approved Phase 1 as **ACCEPTED WITH EXCEPTIONS** on 2026-11-14, recognizing that the baseline verification, protected artifact inventory, resampler root-cause investigation, front-end parity, neural graph parity, and recurrent-state investigation have established a sound forensic baseline to close Phase 1 as an investigation phase.

This approval is a **governance determination**, not unconditional technical completion. The following seven exceptions remain strictly **OPEN** and must not be marked PASS or COMPLETE without new supporting evidence:
1. **Offline-Only Polyphase Resampler:** Native polyphase resampler is an offline batch implementation (`resample_scipy_polyphase`), not a qualified stateful streaming implementation.
2. **Unresolved Residual SNR Gap:** The approximately $-0.1053\text{ dB}$ native Tract vs. Python SNR residual remains unresolved across the 590 canonical development clips.
3. **Unverified Startup Hypothesis:** The Stage 11.2.30 startup-history explanation remains an unverified hypothesis, not a proven waveform-level root cause.
4. **Outdated Deployment Package:** The Raspberry Pi 5 deployment bundle (`deliverables/sih26052_rpi5_deployment_bundle/bin/deep-filter`) still contains the legacy Rubato-based binary and has not been updated with the polyphase candidate.
5. **Algorithmic Latency Ceiling Exceeded:** FullSubNet's structural $48.0\text{ ms}$ algorithmic latency floor exceeds the provisional $\le 35.0\text{ ms}$ project gate.
6. **Unverified Real-Time Compute on Pi 5:** Sustained computational feasibility of FullSubNet on the Broadcom BCM2712 quad-core SoC remains theoretically suspect and physically unverified.
7. **Physical Hardware Gates Locked:** Physical qualification remains blocked at 0/5 gates (exit code 1).

**Authorized Next Phase:** Proceed to **Stage 11.2.31 — Nine-Clip FullSubNet Causal Streaming Pilot** under the approved experimental design ([STAGE11_2_31_FULLSUBNET_CAUSAL_STREAMING_DESIGN.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/research/STAGE11_2_31_FULLSUBNET_CAUSAL_STREAMING_DESIGN.md)).

