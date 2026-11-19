# SIH 26052 — Stage 11.2.33: Candidate B Native Streaming Architecture, Mathematical Audit, and Raspberry Pi 5 Feasibility Investigation
## Rigorous Technical Audit, Causal Inference Contract, Latency Budgeting, Compute Modeling, and Embedded Feasibility Analysis

**Document Identifier:** `research/STAGE11_2_33_NATIVE_STREAMING_FEASIBILITY.md`  
**Date:** 2026-11-14  
**Author:** Antigravity Autonomous Technical Execution Agent (SIH 26052 Master Mission)  
**Status:** COMPLETED — SOFTWARE-ONLY ARCHITECTURAL & FEASIBILITY INVESTIGATION  
**Governance & Boundary:** Sealed Gold Test Dataset `data/SIH_GOLD_TEST` isolated (`gold_test_read: false`). Checkpoints ($D, F, G$), validation manifest, and 15/70/15 frozen reference predictions are immutable. Physical qualification gates remain 0/5 passed (Stage 11.3 NO-GO). Zero physical Raspberry Pi hardware access.

---

## 1. Stage 11.2.32 Output Verification and Forensic Mathematical Audit

In accordance with TASK 1, an independent forensic verification of all Stage 11.2.32 artifacts was executed. All 590 rows in `runs/stage11_2_32_full_590_causal/per_clip_results.csv`, `summary.json`, and `paired_statistical_comparison.json` were audited against the raw implementation in `experiments/stage11_2_32_full_590_causal/run_590_evaluation.py` and `experiments/stage11_2_31_fullsubnet_causal/causal_fullsubnet.py`.

### 1.1 Bit-Exact Reproduction of Saved Benchmark Outputs
1. **Per-Clip Metrics & Summary Means:** Recomputation of standalone FullSubNet and 15/70/15 ensemble metrics confirmed 100% bit-exact equivalence with `summary.json`:
   - Standalone Candidate B FullSubNet: Mean SNR $14.5741\text{ dB}$, Median SNR $14.5014\text{ dB}$, Population Std SNR $6.1400\text{ dB}$, Mean SI-SDR $13.3803\text{ dB}$, Mean STOI $0.9020$, Mean PESQ-WB $2.4421$.
   - 15/70/15 Candidate B Ensemble: Mean SNR $14.8473\text{ dB}$, Median SNR $14.8106\text{ dB}$, Population Std SNR $5.9961\text{ dB}$, Mean SI-SDR $13.7600\text{ dB}$, Mean STOI $0.9064$, Mean PESQ-WB $2.5424$.
   - Pass counts verified: SNR $> 15.0\text{ dB}$ (283 clips), STOI $> 0.85$ (482 clips), PESQ-WB $> 2.50$ (299 clips), Joint Pass (All 3) = **221 / 590 ($37.46\%$)**.
2. **Paired Statistical Bootstrap Distributions:** Re-executing $B = 2,000$ bootstrap iterations with seed `26052` reproduced all 95% confidence intervals bit-for-bit:
   - Candidate B Ensemble vs Frozen Offline Ensemble: Mean $\Delta\text{SNR} = -0.1939\text{ dB}$ ($95\%\text{ CI } [-0.3115, -0.0844]$), $\Delta\text{STOI} = -0.0005$ ($95\%\text{ CI } [-0.0014, +0.0004]$), $\Delta\text{PESQ-WB} = -0.0429$ ($95\%\text{ CI } [-0.0566, -0.0287]$).

---

### 1.2 Forensic Resolution of Specific Discrepancies

#### Discrepancy 1 & 2: Laplace Normalization vs Standardization / Variance Tracking
- **Reported Statement in Stage 11.2.32:** The Stage 11.2.32 report described Candidate B as tracking *"mean and variance accumulators"* and referred to *"causal variance $\sigma_t^2$ jumping abruptly"* in section 6 and section 7.
- **Forensic Code Audit:** Examination of `causal_fullsubnet.py` (lines 80–132) and the upstream vendor code in `audio_zen/model/base_model.py` (lines 203–218) reveals that **this description in the report text was factually inaccurate.**
- **True Mathematical Operation:**
  Upstream FullSubNet uses `offline_laplace_norm`:
  $$\mu = \frac{1}{C \cdot F \cdot T} \sum_{c, f, t} |X_{c, f, t}|, \quad X_{\text{normed}} = \frac{X}{\mu + 10^{-5}}$$
  In `causal_fullsubnet.py`, Candidate B (`config3_ema002`) replaces the offline global mean with a causal running mean $\mu_t$:
  $$\mu_t = (1 - \alpha) \mu_{t-1} + \alpha \bar{x}_t, \quad X_{\text{normed}}[t] = \frac{X[t]}{\mu_t + 10^{-5}}$$
  **There is NO variance accumulator, NO standard deviation, and NO subtraction of the mean.**
- **Technical Correction:** FullSubNet operates strictly on non-negative magnitude STFT spectra ($|X| \ge 0$). Laplace normalization is a **pure scale normalization** (where $\mu$ estimates the scale parameter $b$ of a zero-mean Laplace distribution). It is NOT a Gaussian standardization $(X - \mu)/\sigma$. Subtracting the mean would shift spectral magnitudes into negative values, destroying the input representation. The code correctly implemented pure scale division, but the Stage 11.2.32 report's prose erroneously analogized it to Welford Gaussian normalization.

#### Discrepancy 3: Verification of EMA Normalization State Size
- **Reported Size in Stage 11.2.32:** The report claimed "16 Bytes ($2 \times \text{float64}$)" based on two scalar accumulators ($\mu, \sigma^2$).
- **Actual Code Accounting:**
  FullSubNet applies normalization at **two separate structural locations**:
  1. `norm_fb`: Fullband input magnitude normalization.
  2. `norm_sb`: Subband concatenated feature normalization.
  Each location maintains:
  - `running_mu`: 1 scalar float value.
  - `step_idx`: 1 integer scalar value.
  Therefore, across both normalization stages:
  - Floating state: $2 \times \text{Float32} = 8\text{ Bytes}$ (or $2 \times \text{Float64} = 16\text{ Bytes}$).
  - Integer step state: $2 \times \text{Uint32} = 8\text{ Bytes}$.
  - Total normalization state footprint: **$16\text{ to }24\text{ Bytes}$**.
  The 16-byte figure is validated if stored as two float64 accumulators ($8\text{ B}$ each for fullband and subband), but the variables are $\mu_{\text{fb}}$ and $\mu_{\text{sb}}$, NOT mean and variance.

#### Discrepancy 4: Recurrent State Calculation vs Process Memory
- **Reported Recurrent State in Stage 11.2.32:** $1.56\text{ MB}$ to $1.587\text{ MB}$.
- **Precise Tensor Accounting:**
  1. Fullband LSTM (`fb_model`):
     - 2 layers, unidirectional, hidden size 512, batch size 1.
     - $h_{\text{fb}} \in \mathbb{R}^{2 \times 1 \times 512}$ (1,024 elements $\times$ 4 bytes = $4,096\text{ Bytes}$).
     - $c_{\text{fb}} \in \mathbb{R}^{2 \times 1 \times 512}$ (1,024 elements $\times$ 4 bytes = $4,096\text{ Bytes}$).
     - Subtotal: $8,192\text{ Bytes}$ ($8.0\text{ KiB}$).
  2. Subband LSTM (`sb_model`):
     - 2 layers, unidirectional, hidden size 384, evaluated over 257 frequency bins (effective batch size 257).
     - $h_{\text{sb}} \in \mathbb{R}^{2 \times 257 \times 384}$ (197,376 elements $\times$ 4 bytes = $789,504\text{ Bytes}$).
     - $c_{\text{sb}} \in \mathbb{R}^{2 \times 257 \times 384}$ (197,376 elements $\times$ 4 bytes = $789,504\text{ Bytes}$).
     - Subtotal: $1,579,008\text{ Bytes}$ ($1,542.0\text{ KiB}$).
  - **Total Dynamic Recurrent State:**
    $$396,800\text{ Float32 elements} \times 4\text{ Bytes} = \mathbf{1,587,200\text{ Bytes}} \quad (1,550.0\text{ KiB} \approx 1.5872\text{ MB}_{\text{dec}} = 1.5137\text{ MiB}_{\text{bin}})$$
- **Distinction from Total Process Memory and Rigorous Unit Disentanglement:**
  This $1,587,200\text{ bytes}$ is ONLY the dynamic recurrent hidden/cell state. To avoid confusing decimal ($10^6\text{ B}$) and binary ($2^{20}\text{ B}$) units, memory accounting is explicitly disaggregated:
  - **Static Model Weights:** $5,637,635\text{ Float32 parameters} \times 4\text{ Bytes} = 22,550,540\text{ Bytes} = \mathbf{22.55\text{ MB}}$ (decimal) or $\mathbf{21.51\text{ MiB}}$ (binary).
  - **Dynamic Recurrent State:** $396,800\text{ Float32 elements} \times 4\text{ Bytes} = 1,587,200\text{ Bytes} = \mathbf{1.59\text{ MB}}$ (decimal) or $\mathbf{1.51\text{ MiB}}$ (binary).
  - **Dynamic Audio FIFOs, Normalizer & Resampler State:** $\approx 100\text{ KB} = \mathbf{0.10\text{ MB}}$ (decimal) or $\mathbf{0.10\text{ MiB}}$ (binary).
  - **Total Static Weights + Working State Memory:** $\mathbf{24.24\text{ MB}}$ (decimal) or $\mathbf{23.12\text{ MiB}}$ (binary) (correcting the earlier conflated $23.2\text{ MB}$ figure).
  - **Peak Resident Memory (RSS):** In a native Rust/C/Tract runtime, peak RSS includes allocator heap fragmentation and thread stack allocations (budgeted at $< 35\text{ MB}$ RSS), compared to $50\text{--}150\text{ MB}$ in PyTorch/Python.

#### Discrepancy 5: Algorithmic Latency Floor Accounting (48 ms vs 64 ms)
- **Reported Floor in Stage 11.2.32:** $48.0\text{ ms}$ algorithmic latency floor.
- **Detailed Physical Signal Path Breakdown:**
  1. **STFT Hop Size:** $H = 256$ samples @ 16 kHz = **$16.0\text{ ms}$**.
  2. **STFT Analysis Window:** $N_{\text{fft}} = 512$ samples ($32.0\text{ ms}$). Centered STFT adds $N_{\text{fft}} // 2 = 256$ samples of lookahead = **$16.0\text{ ms}$**.
  3. **Model Lookahead:** Explicitly configured as `look_ahead = 2` frames ($2 \times 16.0\text{ ms}$) = **$32.0\text{ ms}$**.
  4. **Synthesis Overlap-Add (OLA) Buffer:** Standard inverse STFT with 50% Hann overlap requires accumulating the current frame and the subsequent frame before synthesizing time-domain PCM without window modulation distortion = **$16.0\text{ ms}$**.
- **Corrected Algorithmic Latency Calculation:**
  - If using standard overlap-add synthesis:
    $$\tau_{\text{algo}} = \tau_{\text{STFT\_center}} + \tau_{\text{lookahead}} + \tau_{\text{OLA}} = 16.0\text{ ms} + 32.0\text{ ms} + 16.0\text{ ms} = \mathbf{64.0\text{ ms}}$$
  - If using a causal zero-delay synthesis filter:
    $$\tau_{\text{algo}} = 16.0\text{ ms} + 32.0\text{ ms} = \mathbf{48.0\text{ ms}}$$
  The claimed $48.0\text{ ms}$ floor is the **absolute theoretical minimum** under ideal zero-delay synthesis; in a standard OLA streaming pipeline, the true algorithmic delay is **$64.0\text{ ms}$**.

#### Discrepancy 6: Host RTF vs Raspberry Pi 5 Capabilities
- Confirmed: The host RTF values ($0.1398$ for Candidate A, $0.1499$ for Candidate B) were measured on an Apple Silicon M-series host processor running multi-threaded PyTorch with Accelerate framework. They reflect host execution only. Section 5 provides the analytical Raspberry Pi 5 performance model.

#### Discrepancy 7: Reconciling Worst-Case Failure Claims with Objective Evidence
- **Reported Claim in Stage 11.2.32:** The report stated: *"These are not speech distortion or unintelligibility failures; they reflect an artifact of comparing a physically realizable causal estimator against a non-causal offline oracle..."*
- **Forensic Evidence Verification:**
  - In Clip 242 (Existing Proxy, $-5\text{ dB}$ target SNR), PESQ-WB was $4.59$ (pristine speech) and STOI was $0.9984$. The output SNR was $26.87\text{ dB}$. The claim held true here.
  - **HOWEVER, in Clip 536 (IoBT Gunfire, $+5\text{ dB}$ target SNR):**
    - FullSubNet standalone PESQ-WB dropped from $3.10$ down to **$1.73$** ($\Delta = -1.37$).
    - 15/70/15 Ensemble PESQ-WB dropped from $3.15$ down to **$1.77$** ($\Delta = -1.37$).
    - Ensemble SNR dropped from $21.06\text{ dB}$ down to $11.15\text{ dB}$ ($\Delta = -9.90\text{ dB}$).
  - **Correction:** The claim that failure cases exhibited *no speech distortion* was **overstated**. While STOI remained at $0.9697$ (speech remains intelligible), the perceptual quality collapsed by $-1.37$ PESQ points on Clip 536 due to intense transient energy from gunfire bursts shocking the EMA mean estimator. This objective evidence is now properly recorded.

---

## 2. Frozen Causal Inference Contract (Candidate B)

This section establishes the formal, immutable specification for Candidate B (`config3_ema002`).

### 2.1 Interface Contract
- **Input Sampling Rate:** $16,000\text{ Hz}$, single-channel (mono), 32-bit floating point (`float32`), range $[-1.0, 1.0]$.
- **Output Sampling Rate:** $16,000\text{ Hz}$, single-channel (mono), 32-bit floating point (`float32`), range $[-1.0, 1.0]$.
- **Streaming Chunk Size ($C_{\text{chunk}}$):** 256 samples ($16.0\text{ ms}$) per invocation.
- **Analysis STFT Parameters:**
  - $N_{\text{fft}} = 512$, $W = 512$ (Hann window), Hop $H = 256$.
  - Number of frequency bins: $F = 257$ ($f_k = k \cdot \frac{16000}{512} = k \cdot 31.25\text{ Hz}$, for $k \in [0, 256]$).
- **Hann Window Formula:**
  $$w[n] = 0.5 \left(1 - \cos\left(\frac{2\pi n}{512}\right)\right), \quad n \in [0, 511]$$

---

### 2.2 Mathematical Equations for Candidate B Normalization

FullSubNet employs two distinct normalization modules. Both execute Candidate B EMA with $\alpha = 0.02$.

```
                        CANDIDATE B NORMALIZATION LIFECYCLE
                        
  Frame t Arrival
         |
         v
  Compute Spatial Mean: x_bar[t] = (1 / N) * sum(X[t])
         |
         +--------------------------------+
         |                                |
         v                                v
  [Warmup: step < 99]           [Steady-State: step >= 99]
  alp = min((step-1)/(step+1), 0.02)       alp = 0.02
         |                                |
         +--------------------------------+
         |
         v
  Update EMA Mean:
  mu[t] = (1 - alp) * mu[t-1] + alp * x_bar[t]
         |
         v
  Normalize Magnitude Slice:
  X_normed[t] = X[t] / (mu[t] + 1e-5)
```

#### Location 1: Fullband Input Normalization (`norm_fb`)
- Input slice: Magnitude spectrum $X_{\text{fb}}[t] \in \mathbb{R}^{257}$.
- Spatial mean:
  $$\bar{x}_{\text{fb}}[t] = \frac{1}{257} \sum_{f=0}^{256} X_{\text{fb}}[f, t]$$

#### Location 2: Subband Input Normalization (`norm_sb`)
- Input tensor: Concatenated subband units $X_{\text{sb}}[t] \in \mathbb{R}^{257 \times 32}$.
- Spatial mean across all 257 subbands and 32 neighbor/prediction features:
  $$\bar{x}_{\text{sb}}[t] = \frac{1}{257 \times 32} \sum_{f=0}^{256} \sum_{k=0}^{31} X_{\text{sb}}[f, k, t]$$

#### EMA Update Equations (Both Locations)
- Parameter: $\alpha = 0.02$, warmup threshold $t_{\text{sample}} = \text{round}(2.0 / 0.02 - 1.0) = 99\text{ frames}$ ($1.584\text{ s}$).
- **Step 0 (Initialization):**
  $$\mu[0] = \bar{x}[0], \quad \text{step} = 0$$
- **Warmup Phase ($1 \le \text{step} < 99$):**
  $$\alpha_{\text{eff}} = \max\left(0.0, \, \min\left(\frac{\text{step} - 1.0}{\text{step} + 1.0}, \, 0.02\right)\right)$$
  $$\mu[\text{step}] = (1.0 - \alpha_{\text{eff}}) \cdot \mu[\text{step}-1] + \alpha_{\text{eff}} \cdot \bar{x}[\text{step}]$$
- **Steady-State Phase ($\text{step} \ge 99$):**
  $$\mu[\text{step}] = 0.98 \cdot \mu[\text{step}-1] + 0.02 \cdot \bar{x}[\text{step}]$$
- **Application:**
  $$X_{\text{normed}}[f, t] = \frac{X[f, t]}{\mu[t] + 10^{-5}}$$

---

### 2.3 Subband Unfolding & Neighbor Structure
For each frequency bin $f \in [0, 256]$:
1. Extract 31 noisy magnitude neighbors: $[f - 15, \dots, f, \dots, f + 15]$ with reflect padding at the boundary (bin 0 and bin 256).
2. Append the single corresponding fullband model output: $\hat{Y}_{\text{fb}}[f, t]$ ($1$ feature).
3. Resulting subband feature vector: $v_f[t] \in \mathbb{R}^{32}$.
4. All 257 vectors are evaluated in parallel by `sb_model`.

---

### 2.4 Model Architectures & State Shapes

```
+---------------------------------------------------------------------------------------------------+
|                                  CANDIDATE B PIPELINE ARCHITECTURE                                |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  Audio In (16 kHz, 256 samples)                                                                   |
|      |                                                                                            |
|      v                                                                                            |
|  [512-point STFT] ---> Magnitude [257] ------------------------+                                  |
|      |                                                         |                                  |
|      v                                                         v                                  |
|  [norm_fb (EMA)] (mu_fb: 8 B)                     [31-Neighbor Frequency Unfold]                  |
|      |                                                         |                                  |
|      v                                                         v                                  |
|  [Fullband LSTM (2x512)] (h_fb, c_fb: 8.19 KB)    Concat [31 noisy + 1 FB = 32]                   |
|      |                                                         |                                  |
|      v                                                         v                                  |
|  Linear(512->257) + ReLU                         [norm_sb (EMA)] (mu_sb: 8 B)                     |
|      |                                                         |                                  |
|      +-------------------------------------------------------->+                                  |
|                                                                |                                  |
|                                                                v                                  |
|                                                   [Subband LSTM (2x384 across 257 bins)]          |
|                                                   (h_sb, c_sb: 1,579.0 KB)                        |
|                                                                |                                  |
|                                                                v                                  |
|                                                   Linear(384->2) ---> cIRM Mask [257, 2]          |
|                                                                |                                  |
|                                                                v                                  |
|  Complex STFT Multiplication ----------------------------------+                                  |
|      |                                                                                            |
|      v                                                                                            |
|  [512-point iSTFT OLA] ---> Audio Out (16 kHz, 256 samples)                                       |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

1. **Fullband Model (`fb_model`):**
   - 2-layer LSTM: `input_size = 257`, `hidden_size = 512`, `num_layers = 2`, `bidirectional = False`.
   - Output projection: `Linear(512, 257)` + `ReLU()`.
   - State tensors: $h_{\text{fb}} \in \mathbb{R}^{2 \times 1 \times 512}$, $c_{\text{fb}} \in \mathbb{R}^{2 \times 1 \times 512}$.
2. **Subband Model (`sb_model`):**
   - 2-layer LSTM: `input_size = 32`, `hidden_size = 384`, `num_layers = 2`, `bidirectional = False`.
   - Output projection: `Linear(384, 2)`.
   - Evaluated across 257 bins: effective batch dimension is 257.
   - State tensors: $h_{\text{sb}} \in \mathbb{R}^{2 \times 257 \times 384}$, $c_{\text{sb}} \in \mathbb{R}^{2 \times 257 \times 384}$.
3. **cIRM Decompression & Masking:**
   - The 2 output channels represent real and imaginary compressed ratios: $[M_r, M_i]$.
   - Decompress via hyperbolic tangent transform ($K = 10, C = 0.1$):
     $$M_{\text{real}} = -\frac{1}{C} \log\left(\frac{K - M_r}{K + M_r}\right), \quad M_{\text{imag}} = -\frac{1}{C} \log\left(\frac{K - M_i}{K + M_i}\right)$$
   - Complex multiplication with noisy STFT:
     $$S_{\text{real}} = M_{\text{real}} Y_{\text{real}} - M_{\text{imag}} Y_{\text{imag}}, \quad S_{\text{imag}} = M_{\text{real}} Y_{\text{imag}} + M_{\text{imag}} Y_{\text{real}}$$

---

### 2.5 Lifecycle and Reset Semantics
- **Session Reset (`reset()`):**
  - Zero all LSTM recurrent states: $h_{\text{fb}} \leftarrow 0, c_{\text{fb}} \leftarrow 0, h_{\text{sb}} \leftarrow 0, c_{\text{sb}} \leftarrow 0$.
  - Reset EMA normalizers: `step_idx` $\leftarrow 0$, `running_mu` $\leftarrow \text{None}$ for both `norm_fb` and `norm_sb`.
  - Flush STFT analysis FIFO (512 samples) and synthesis OLA buffer (512 samples).
  - Reset lookahead frame FIFO (2 frames).
- **Deterministic Reproducibility:** Calling `reset()` and feeding an identical sequence of chunks must produce bit-for-bit identical output waveforms.

---

## 3. Native Streaming Architecture Investigation

This section evaluates the feasibility of executing Candidate B in a native C/Rust environment on ARM64 Linux (Raspberry Pi 5).

### 3.1 Tract / ONNX Graph Compatibility
- **Tract Compatibility:** Tract (`tract-onnx = 0.21.4`) is the deployment engine currently utilized for DFN3 Step-500.
- **Feasibility Evaluation:**
  - Standard ONNX export of `fb_model` and `sb_model` as standalone modules with explicit $(h, c)$ state inputs and outputs (`[x, h_in, c_in] -> [y, h_out, c_out]`) was validated using PyTorch's TorchScript-based exporter (`dynamo=False`).
  - `fb_model` exports cleanly: Single-step LSTM with shape `[1, 1, 257]` and hidden state `[2, 1, 512]`.
  - `sb_model` exports cleanly: Single-step LSTM with shape `[257, 1, 32]` and hidden state `[2, 257, 384]`.
  - **Graph Split Architecture:** Rather than attempting to export the full pipeline (including `freq_unfold` and EMA loops) into a single monolithic ONNX graph, the recommended native architecture decouples the neural graphs from the DSP pipeline:
    1. `fullband_step.onnx` ($14.54\text{ MB}$ weights).
    2. `subband_step.onnx` ($6.96\text{ MB}$ weights).
    3. Host/DSP code (in Rust/C) executes STFT, EMA normalization, subband neighbor extraction, and iSTFT.

---

### 3.2 Native DSP Components (STFT, Polyphase Resampling, OLA)
1. **Native STFT / iSTFT:**
   - DFN3 utilizes a native 960/480 STFT in Rust (`libDF`). FullSubNet requires a **512/256 STFT at 16 kHz**.
   - Rust crates `rustfft` or Tract's native FFT kernels provide zero-allocation 512-point real-to-complex FFT in $< 15\text{ }\mu\text{s}$ per frame on Cortex-A76.
2. **Native Polyphase Resampling:**
   - DFN3 Step-500 operates internally at $48\text{ kHz}$. FullSubNet and GTCRN operate at $16\text{ kHz}$.
   - The Stage 11.2.26 61-tap Kaiser polyphase filter must be instantiated as a stateful streaming resampler:
     - 48 kHz $\to$ 16 kHz (Decimation factor 3): Filter length 61 taps, decimation phase step 3.
     - 16 kHz $\to$ 48 kHz (Interpolation factor 3): Filter length 61 taps, polyphase phase step 1.
   - Streaming state: Ring buffer of 61 input samples ($244\text{ Bytes}$).

---

### 3.3 Zero-Allocation Execution Contract
In the native audio processing thread:
- **No dynamic allocations (`malloc` / `Box::new`) in the audio path.**
- All buffers (STFT circular buffers, lookahead queues, LSTM hidden states, GEMM scratchpads) are pre-allocated during pipeline initialization.
- State memory layout is contiguous to maximize L1/L2 cache locality.

---

## 4. Latency Feasibility and Component Budget

The provisional SIH project latency ceiling is **$\le 35.0\text{ ms}$** end-to-end physical latency.

### 4.1 Theoretical Latency Budget and Timestamp Audit Caveats

> [!WARNING]
> **Engineering Analytical Model Only:** The $\approx 97.1\text{ ms}$ figure below is a synthetic analytical estimate derived from configured buffer parameters and theoretical filter delays, NOT a physically measured hardware latency. Physical end-to-end latency cannot be verified without physical Pi 5 hardware and audio I/O instrumentation (which remains strictly locked under Gate 04).
> 
> Furthermore, a timestamp-level audit must be conducted during native prototyping to establish:
> 1. The exact sample timestamp when each input sample is captured.
> 2. The exact output sample index to which each enhanced frame corresponds.
> 3. The precise emission timestamp at the DAC.
> 4. Whether the synthesis window and frame convention incur a full 16 ms OLA hop delay in every native implementation or can be mitigated via causal synthesis windows.

```
+-------------------------------------------------------------------------------------------------------+
|                               THEORETICAL PHYSICAL LATENCY MODEL (ANALYTICAL)                         |
+-------------------------------------------------------------------------------------------------------+
|  Component                                Delay (ms)   Cumulative (ms)   Status / Nature              |
+-------------------------------------------------------------------------------------------------------+
|  1. ALSA Capture Ring Buffer (2 periods)     10.67 ms        10.67 ms    Hardware OS I/O (48 kHz)     |
|  2. Polyphase Resampler (48k -> 16k)          0.64 ms        11.31 ms    Group delay (30 taps @ 48k)  |
|  3. STFT Analysis Framing (Centered)         16.00 ms        27.31 ms    Algorithmic Window Center    |
|  4. FullSubNet Model Lookahead (2 frames)    32.00 ms        59.31 ms    Algorithmic Lookahead        |
|  5. FullSubNet Neural Compute Time           10.00 ms        69.31 ms    Pi 5 CPU Execution Budget    |
|  6. Synthesis Overlap-Add (OLA)              16.00 ms        85.31 ms    Algorithmic Synthesis Hop    |
|  7. Polyphase Upsampler (16k -> 48k)          0.64 ms        85.95 ms    Group delay (30 taps @ 48k)  |
|  8. ALSA Playback Ring Buffer (2 periods)    10.67 ms        96.62 ms    Hardware OS I/O (48 kHz)     |
|  9. Acoustic Propagation (Mic to Headset)     0.50 ms        97.12 ms    Physical distance (17 cm)    |
+-------------------------------------------------------------------------------------------------------+
|  TOTAL ESTIMATED PHYSICAL LATENCY:                          ~97.1 ms (ANALYTICAL ESTIMATE)            |
|  PROVISIONAL SIH LATENCY GATE:                              <= 35.0 ms                                |
|  VARIANCE (GATE DEFICIT):                                   +62.1 ms (FAILED)                         |
+-------------------------------------------------------------------------------------------------------+
```

---

### 4.2 Lookahead Reduction & Retraining Analysis
Can the $32.0\text{ ms}$ model lookahead be removed to satisfy the 35 ms gate?
1. **Mathematical Reality:** `look_ahead = 2` was fixed during supervised training on DNS Challenge datasets. The LSTM weights in `sb_model` were conditioned to expect 2 future frames of context to disambiguate speech onsets from noise.
2. **Zero-Lookahead Evaluation Without Retraining:**
   - Setting `look_ahead = 0` during inference shifts the temporal receptive field by 2 frames.
   - This causes acoustic degradation: consonants and explosive speech phonemes are clipped or distorted because the mask prediction lags behind the acoustic event.
3. **Governance Constraint:** The project instructions explicitly mandate:
   *"Do not change the selected model weights or normalization configuration. The checkpoints and offline reference predictions are frozen."*
4. **Architectural Conclusion:**
   - FullSubNet epoch 58 **CANNOT** satisfy the 35.0 ms latency gate under its frozen weights.
   - Its algorithmic floor alone ($48.0\text{ to }64.0\text{ ms}$) strictly exceeds the 35.0 ms threshold before hardware audio buffering is even added.
   - **Retained Exception 03 remains an architectural blocker for hardware qualification.**

---

## 5. Raspberry Pi 5 Computational Feasibility

This section presents the analytical performance model for FullSubNet on the Broadcom BCM2712 SoC (Raspberry Pi 5).

### 5.1 Exact Floating-Point Operations per 16 ms Frame

| Neural Sub-Module | Matrix Dimensions | MACs / Frame | FLOPs / Frame | % of Total Model Compute |
|---|---|:---:|:---:|:---:|
| **Fullband LSTM Layer 0** | $W_{\text{ih}} [2048, 257], W_{\text{hh}} [2048, 512]$ | $1,574,912$ | $3.15\text{ MFLOPs}$ | $0.33\%$ |
| **Fullband LSTM Layer 1** | $W_{\text{ih}} [2048, 512], W_{\text{hh}} [2048, 512]$ | $2,097,152$ | $4.19\text{ MFLOPs}$ | $0.44\%$ |
| **Fullband Linear + ReLU** | $W_{\text{out}} [257, 512]$ | $131,584$ | $0.26\text{ MFLOPs}$ | $0.03\%$ |
| *Fullband Total* | — | *3,803,648* | *7.61 MFLOPs* | *0.80%* |
| **Subband LSTM Layer 0** ($257\times$) | $257 \times (W_{\text{ih}} [1536, 32] + W_{\text{hh}} [1536, 384])$ | $164,216,832$ | $328.43\text{ MFLOPs}$ | $34.84\%$ |
| **Subband LSTM Layer 1** ($257\times$) | $257 \times (W_{\text{ih}} [1536, 384] + W_{\text{hh}} [1536, 384])$ | $303,169,536$ | $606.34\text{ MFLOPs}$ | $64.32\%$ |
| **Subband Linear** ($257\times$) | $257 \times W_{\text{out}} [2, 384]$ | $197,376$ | $0.39\text{ MFLOPs}$ | $0.04\%$ |
| *Subband Total* | — | *467,583,744* | *935.17 MFLOPs* | *99.20%* |
| **MODEL TOTAL PER FRAME** | — | **471,387,392** | **942.77 MFLOPs** | **100.00%** |

- **Frame Deadline:** $T_{\text{frame}} = 16.0\text{ ms} = 0.016\text{ s}$.
- **Sustained Compute Demand:**
  $$\text{Throughput}_{\text{req}} = \frac{942.77 \times 10^6\text{ FLOPs}}{0.016\text{ s}} = \mathbf{58.92\text{ GFLOPs/s}}$$

---

### 5.2 Raspberry Pi 5 Hardware Capacity & Theoretical Utilization
- **CPU:** 4x ARM Cortex-A76 cores @ 2.40 GHz.
- **NEON Pipelines:** 2x 128-bit vector execution units per core.
- **Theoretical Peak FP32 Throughput:**
  - Per core: $2\text{ units} \times 4\text{ lanes} \times 2\text{ (FMA)} \times 2.4\text{ GHz} = 38.4\text{ GFLOPs/s}$.
  - 4 Cores Combined (Peak): $4 \times 38.4 = \mathbf{153.6\text{ GFLOPs/s}}$.
  - Single-FMA / Non-Ideal Issue Peak: $4 \times 2.4 \times 8 = \mathbf{76.8\text{ GFLOPs/s}}$.
- **Theoretical Compute Utilization:**
  $$\text{Utilization}_{\text{peak}} = \frac{58.92}{153.6} = 38.36\%, \quad \text{Utilization}_{\text{conservative}} = \frac{58.92}{76.8} = 76.72\%$$

---

### 5.3 Real-World Real-Time Factor (RTF) Analytical Modeling

```
+-------------------------------------------------------------------------------------------------------+
|                    ANALYTICAL REAL-TIME FACTOR (RTF) PERFORMANCE MODEL ON RASPBERRY PI 5              |
+-------------------------------------------------------------------------------------------------------+
|  Runtime Engine & Precision         Expected Throughput   Execution Time / Frame   Projected RTF      |
+-------------------------------------------------------------------------------------------------------+
|  PyTorch ARM64 (Python, FP32)          23.0 GFLOPs/s              41.0 ms              2.56 (OVERFLOW)|
|  Native Tract / C++ (FP32, 4-thread)   48.0 GFLOPs/s              19.6 ms              1.23 (HIGH RISK)|
|  Highly Optimized NEON FP32 (GEMM)     65.0 GFLOPs/s              14.5 ms              0.91 (MARGINAL)|
|  INT8 Quantized (Hypothetical SDOT)   180.0 GOPs/s                 5.2 ms              0.33 (UNMEASURED)|
+-------------------------------------------------------------------------------------------------------+
|  REAL-TIME THRESHOLD: RTF < 1.0 (Target RTF <= 0.60 to leave headroom for OS & DFN3/GTCRN)           |
+-------------------------------------------------------------------------------------------------------+
```

1. **Unoptimized Python/PyTorch (FP32):** Achieves $\approx 20\text{--}25\text{ GFLOPs/s}$ on ARM64 Linux $\implies \text{RTF} \approx 2.56$. Buffer underruns occur continuously.
2. **Native Tract / C++ (FP32):** Even with multi-threaded matrix multiplication across all 4 cores, FP32 execution is estimated to require $14.5\text{--}19.6\text{ ms}$ per frame ($\text{RTF} \approx 0.91\text{--}1.23$). This represents **high risk with insufficient demonstrated real-time headroom** on Pi 5, leaving little to no CPU capacity for OS scheduling, audio I/O, or the remaining ensemble models (DFN3 and GTCRN).
3. **INT8 Quantization (Hypothetical NEON `SDOT` Mapping):**
   > [!IMPORTANT]
   > **Unmeasured Analytical Hypothesis:** The projected RTF of $\approx 0.33$ for INT8 is an analytical estimate based on theoretical NEON `SDOT` peak instructions, NOT a measured benchmark on hardware.
   > 
   > Treating INT8 as a proven solution is technically premature. Quantizing recursive LSTMs presents severe numerical drift risks in cell states $c_t$, and mapping the 257 parallel subbands efficiently to `SDOT` kernels requires experimental proof of accuracy and throughput.

---

## 6. Quantization and Numerical Parity Assessment

Because FP32 poses severe throughput risks on Pi 5, INT8 quantization is a prominent candidate optimization to investigate.

### 6.1 Quantization Feasibility & Analytical Hypothesis
- **Weights:** $5,637,635$ parameters. Quantizing weights to `int8` reduces model parameter storage from $22.55\text{ MB}$ ($21.51\text{ MiB}$) to **$5.64\text{ MB}$** ($5.38\text{ MiB}$), fitting comfortably within the Pi 5's memory hierarchy and significantly reducing memory bandwidth pressure.
- **Subband Matrix Dimensionality:** In `sb_model`, each subband LSTM step multiplies $W_{\text{hh}} \in \mathbb{R}^{1536 \times 384}$ by $h \in \mathbb{R}^{384 \times 257}$. This is a dense GEMM $(1536 \times 384) \times (384 \times 257)$, which could theoretically map onto NEON `SDOT` kernels if activations and weights can be stably quantized.

### 6.2 Critical Numerical Parity Risks (Experimental Proof Required)
1. **Recurrent State Quantization Drift:** Unlike feed-forward CNNs, LSTMs accumulate state recursively over thousands of frames:
   $$c_t = f_t \odot c_{t-1} + i_t \odot \tilde{c}_t$$
   Small rounding errors in INT8 activations compound over time, leading to state drift, saturation, or collapse.
2. **Dynamic Range Mismatch in Frequency Bins:** The 257 frequency bins exhibit vastly different dynamic ranges (low frequencies have $40\text{ dB}$ higher energy than high frequencies). A single global scale factor for all 257 subbands causes severe quantization noise in high frequencies. Per-channel or per-subband scaling is mandatory.
3. **Tract Operator Limitations:** Tract's native INT8 quantization pipeline has limited support for stateful recurrent ONNX `LSTM` operators, requiring either manual fixed-point decomposition or export as unrolled cell primitives.
4. **Current Status:** INT8 remains an **unverified candidate optimization requiring accuracy and performance proof**, not a qualified runtime.

---

## 7. Frozen Ensemble Integration Architecture

The immutable ensemble equation is:
$$\hat{y}[n] = 0.15 \, D[n] + 0.70 \, F[n] + 0.15 \, G[n]$$

```
+---------------------------------------------------------------------------------------------------+
|                        SYNCHRONIZED STREAMING ENSEMBLE DELAY-LINE ARCHITECTURE                    |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  Audio In (48 kHz PCM)                                                                            |
|      |                                                                                            |
|      +------------------------------------------+-----------------------+                         |
|      |                                          |                       |                         |
|      v                                          v                       v                         |
|  [DFN3 Step-500]                         [Resample 3:1]          [Resample 3:1]                   |
|  (48 kHz, 10 ms hop)                     (48k -> 16k)            (48k -> 16k)                     |
|  Algo Delay = 30.0 ms                           |                       |                         |
|      |                                          v                       v                         |
|      |                                   [FullSubNet B]          [GTCRN DNS3]                     |
|      |                                   (16 kHz, 16 ms hop)     (16 kHz, 16 ms hop)              |
|      |                                   Algo Delay = 48.0 ms    Algo Delay = 16.0 ms             |
|      |                                          |                       |                         |
|      v                                          v                       v                         |
|  [FIFO Delay: 18.0 ms]                   [FIFO Delay: 0.0 ms]    [FIFO Delay: 32.0 ms]            |
|  (864 samples @ 48k)                     (0 samples)             (512 samples @ 16k)              |
|      |                                          |                       |                         |
|      |                                          v                       v                         |
|      |                                   [Resample 1:3]          [Resample 1:3]                   |
|      |                                   (16k -> 48k)            (16k -> 48k)                     |
|      |                                          |                       |                         |
|      v                                          v                       v                         |
|  Gain: 0.15                              Gain: 0.70              Gain: 0.15                       |
|      \                                          |                      /                          |
|       +-----------------------------------------+---------------------+                           |
|                                                 |                                                 |
|                                                 v                                                 |
|                                        Aligned Audio Out (48 kHz)                                 |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 7.1 Delay Alignment Proposal and Verification Requirements
- **Architectural Proposal:**
  To prevent devastating comb-filtering and phase cancellation, all three model outputs must be aligned to the exact same sample index $n$:
  $$\tau_{\text{ensemble}} = \max(\tau_{\text{DFN3}}, \, \tau_{\text{FullSubNet}}, \, \tau_{\text{GTCRN}}) = \max(30.0, 48.0, 16.0) = \mathbf{48.0\text{ ms}}$$
- **Proposed Delay Compensation Lines:**
  - FullSubNet Delay Line: $\Delta = 48.0 - 48.0 = \mathbf{0.0\text{ ms}}$ (0 samples).
  - DFN3 Delay Line: $\Delta = 48.0 - 30.0 = \mathbf{18.0\text{ ms}}$ ($864\text{ samples}$ @ 48 kHz).
  - GTCRN Delay Line: $\Delta = 48.0 - 16.0 = \mathbf{32.0\text{ ms}}$ ($512\text{ samples}$ @ 16 kHz).

> [!WARNING]
> **Proposal Status — Experimental Verification Mandatory:** These delay values are an engineering proposal based on nominal algorithmic delays (30, 48, and 16 ms). Simply matching chunk sequence numbers does not guarantee sample-accurate phase alignment across disparate sample rates (48 kHz vs 16 kHz) and polyphase resamplers. Actual input/output sample correspondence must be experimentally measured for each component during prototype integration.

- **Synchronous Mixing Contract:**
  Every chunk emitted by the audio capture thread carries an incremental 64-bit sequence counter `chunk_seq`. Each model worker pushes into a thread-safe bounded FIFO tagged with `chunk_seq`. The ensemble summing thread reads matching tags, applies the linear blend ($0.15 D + 0.70 F + 0.15 G$), and writes to the playback FIFO. Zero samples are dropped or misaligned.

---

## 8. Minimal Native Prototype Implementation Plan

To establish technical feasibility without premature physical deployment, the following 10-step software engineering roadmap is defined:

| Step | Workstream | Description | Explicit Acceptance Criteria |
|:---:|---|---|---|
| **1** | **EMA Normalizer Unit Tests** | Implement Candidate B recursive EMA in pure C/Rust. | Numerical output matches PyTorch `causal_fullsubnet.py` within max absolute error $< 10^{-6}$ on synthetic vectors. |
| **2** | **Fullband State Persistence** | Implement single-step `FBStep` LSTM with persistent $(h, c)$. | Chunk-by-chunk output matches full-utterance forward pass bit-for-bit ($L_\infty < 10^{-6}$). |
| **3** | **Subband State Persistence** | Implement 257-band parallel single-step `SBStep` LSTM. | Hidden state transitions match PyTorch recurrent tensor state bit-for-bit across 100 consecutive frames. |
| **4** | **Chunk-Boundary Parity** | Stream 32 ms audio chunks through STFT + EMA + LSTM + iSTFT. | Reconstructed audio matches full-utterance causal PyTorch output with SDR $> 60\text{ dB}$. |
| **5** | **Tract Graph Compilation** | Compile `fullband_step.onnx` and `subband_step.onnx` into Tract plan. | Tract inference output matches PyTorch ONNX runtime output within max error $< 10^{-5}$. |
| **6** | **Polyphase Streaming Filter** | Implement stateful Kaiser 61-tap 3:1 decimation/interpolation. | Resampling SNR $> 80\text{ dB}$; zero memory allocations in process loop. |
| **7** | **End-to-End Canonical Waveform Parity** | Process 10 canonical validation clips through native prototype. | Paired SDR vs PyTorch Candidate B $> 40\text{ dB}$; $\Delta\text{SNR} < 0.05\text{ dB}$. |
| **8** | **Zero-Allocation Memory Audit** | Profile native pipeline using `valgrind` / `dhat`. | Zero `malloc` calls inside `process_chunk()`; heap footprint $< 25\text{ MB}$. |
| **9** | **Continuous Streaming Soak Test** | Run prototype continuously on 60 minutes of concatenated audio. | Zero memory growth; zero NaN/Inf occurrences; exact sample count preserved. |
| **10** | **Host CPU Profiling** | Benchmark execution time on ARM64 Linux container. | Profile FLOP throughput, cache misses, and multi-thread scaling. |

---

## 9. Comprehensive Risk Register and Open Questions

| Risk ID | Category | Description | Severity | Mitigation Strategy |
|:---:|---|---|:---:|---|
| **R-01** | **Physical Latency** | FullSubNet lookahead (32 ms) + STFT (16 ms) creates a 48 ms algorithmic floor, strictly exceeding the 35 ms project gate. | **CRITICAL** | Retain technical exception; require future explicit authorization for lookahead reduction or sub-band retraining. |
| **R-02** | **Pi 5 Compute Overload** | FullSubNet requires 58.9 GFLOPs/s (76.7% of Pi 5 peak). FP32 execution will cause buffer underruns (RTF > 1.0). | **CRITICAL** | INT8 post-training quantization and NEON `SDOT` vectorization are non-negotiable for embedded deployment. |
| **R-03** | **Quantization Drift** | Recursive LSTM hidden states may accumulate numerical drift under INT8 quantization over long audio streams. | **HIGH** | Evaluate per-subband scaling and EMA accumulator preservation in high-precision Float32. |
| **R-04** | **Ensemble Phase Alignment** | Disparate algorithmic delays (16 ms GTCRN, 30 ms DFN3, 48 ms FullSubNet) cause destructive interference if not delayed. | **HIGH** | Strict tagged-sequence FIFO delay lines (18 ms for DFN3, 32 ms for GTCRN) to ensure sample-accurate alignment. |
| **R-05** | **Transient Shock Distortion** | Gunfire bursts shock the causal EMA mean, causing temporary drop in PESQ (e.g. Clip 536 PESQ drops to 1.77). | **MEDIUM** | Bound maximum adaptation step or investigate asymmetrical attack/decay time constants in future iterations. |

---

## 10. Explicit Technical Recommendation

### Architectural Decision: **ACCEPT INVESTIGATION WITH TECHNICAL CORRECTIONS; CONDITIONAL GO FOR HOST SOFTWARE PROTOTYPE; STRICT NO-GO FOR HARDWARE DEPLOYMENT**

1. **Software Prototyping Viability (CONDITIONAL GO):**
   - Candidate B (`config3_ema002`) possesses a verified, deterministic scale normalization formulation ($X / (\mu_t + 10^{-5})$).
   - The architecture cleanly decouples into two standalone single-step ONNX LSTMs (`fullband_step.onnx` and `subband_step.onnx`) and native DSP kernels.
   - Working dynamic state is strictly bounded ($16\text{ B}$ normalizer state, $1.587\text{ MB}$ recurrent state, $22.55\text{ MB}$ weights).
   - Host software prototyping (Stage 11.2.34) to establish chunk-by-chunk numerical and waveform parity against Python is **TECHNICALLY CREDIBLE AND RECOMMENDED**.
2. **Raspberry Pi 5 Feasibility Assessment (CALIBRATED FINDINGS):**
   - **FP32 on Pi 5:** Represents **high risk with insufficient demonstrated real-time headroom** (sustained compute demands 76.7% of conservative 4-core SoC capacity, analytical $\text{RTF} \approx 0.91\text{--}1.23$).
   - **INT8 Optimization:** Represents a **promising candidate optimization requiring accuracy, drift, and performance proof**, not a proven solution (analytical $\text{RTF} \approx 0.33$ is an unmeasured hypothesis).
   - **Hardware Status:** Neither FP32 nor INT8 has yet demonstrated real-time execution on physical Pi 5.
   - **Latency Ceiling Conflict:** FullSubNet's frozen lookahead ($32.0\text{ ms}$) and framing ($16.0\text{ ms}$) enforce a minimum algorithmic floor of $48.0\text{ ms}$, strictly incompatible with the provisional $\le 35.0\text{ ms}$ physical latency gate.
   - Physical Gate 04 (Latency) and Gate 05 (Demonstration) remain **LOCKED**. Zero physical hardware testing or deployment is permitted.

---

### Mandatory Stop Condition
Stage 11.2.33 investigation is complete and formally updated with all technical corrections. The next step is Stage 11.2.34 (Native Candidate B Software Prototype — Host Only, No Hardware Deployment). I am halting here to await your explicit review and authorization.

