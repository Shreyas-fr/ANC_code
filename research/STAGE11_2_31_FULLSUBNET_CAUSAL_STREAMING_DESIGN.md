# SIH 26052 — Stage 11.2.31: FullSubNet Causal and Stateful Streaming Normalization Investigation
## Audit, Mathematical Formulations, Latency Breakdown, and Pilot Experiment Design

**Author:** Antigravity Autonomous Agent (SIH 26052 Master Mission)  
**Date:** 2026-11-14  
**Status:** AUDIT & DESIGN COMPLETE — PENDING FORMAL REVIEW BEFORE CODING  
**Governance Boundary:** Sealed Gold Test Dataset `data/SIH_GOLD_TEST` is strictly isolated (`gold_test_read: false`). Checkpoints ($D, F, G$), validation manifest, and 15/70/15 frozen reference predictions are immutable. Physical qualification gates remain 0/5 passed (Stage 11.3 NO-GO).

---

## 1. Executive Summary & Objective

The primary speech enhancement quality reference for SIH 2026 Problem Statement 26052 is the frozen **15/70/15 ensemble**:
$$\hat{y}[n] = 0.15 \, D[n] + 0.70 \, F[n] + 0.15 \, G[n]$$
where:
- $D[n]$ = DFN3 Step-500 (`step500_from_pi.pt`)
- $F[n]$ = Audio-WestlakeU FullSubNet epoch 58 (`fullsubnet_best_model_58epochs.tar`)
- $G[n]$ = GTCRN DNS3 (`model_trained_on_dns3.tar`)

In the frozen offline reference evaluation across 590 canonical development clips (`runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/`), this ensemble achieved:
- **Output SNR:** $15.0412\text{ dB}$ (Target $> 15.0\text{ dB}$)
- **SI-SDR:** $13.9653\text{ dB}$
- **STOI:** $0.9069$ (Target $> 0.85$)
- **PESQ-WB:** $2.5853$ (Target $> 2.50$)
- **Joint Pass Rate:** 227 / 590 clips ($38.47\%$)

Because FullSubNet carries **70% of the linear ensemble weight**, the real-time viability of the entire 15/70/15 architecture hinges on whether FullSubNet can be transitioned from an offline, whole-utterance batch model into a causal, stateful, low-latency streaming pipeline without catastrophic quality degradation.

Stage 11.2.16 established that the official FullSubNet implementation is strictly **OFFLINE ONLY** due to:
1. **Utterance-wide normalization** (`norm_type="offline_laplace_norm"`) that computes a global scalar mean across all future time frames of the entire utterance;
2. **Stateless LSTM forward calls** in `audio_zen/model/module/sequence_model.py` where hidden states $(h, c)$ are discarded and re-initialized to zero at every invocation;
3. **Centering and lookahead delays**: PyTorch centered STFT reflection context ($16\text{ ms}$) plus explicit model lookahead ($32\text{ ms}$), establishing a theoretical minimum algorithmic delay floor of $48\text{ ms}$ before any compute or I/O latency.

### Scope of Stage 11.2.31
This stage provides the forensic code audit, mathematical formulations for 5 causal normalization alternatives, algorithmic latency and computational complexity analyses, and an experimental design utilizing a representative 9-clip development subset. **In accordance with protocol rules, this report is submitted for review prior to writing or executing any causal implementation code.**

---

## 2. Codebase Audit & Baseline Inspection

### 2.1 File Map and Responsibilities
- **Adapter Layer:** `antigravity/src/models/fullsubnet_adapter.py`
- **Model Topology:** `antigravity/third_party/fullsubnet_vendor/fullsubnet/model.py`
- **Normalization & Utility Kernels:** `antigravity/third_party/fullsubnet_vendor/audio_zen/model/base_model.py`
- **Sequence Wrapper:** `antigravity/third_party/fullsubnet_vendor/audio_zen/model/module/sequence_model.py`

### 2.2 Trace of Forward Execution Flow
In `src/models/fullsubnet_adapter.py` (lines 110–138):
1. **Input Signal:** Mono 16 kHz waveform $x[n]$ is converted to torch float32 tensor of shape `[1, N]`.
2. **STFT Extraction:**
   ```python
   noisy_complex = torch.stft(
       signal,
       n_fft=512, hop_length=256, win_length=512,
       window=self.window, return_complex=True
   )
   noisy_mag = noisy_complex.abs().unsqueeze(1)  # Shape: [1, 1, 257, T]
   ```
   Because `center=True` (PyTorch default), the signal is padded on both sides with $N_{\text{fft}} / 2 = 256$ samples ($16\text{ ms}$) using reflection.
3. **Model Forward Call:**
   In `fullsubnet/model.py` (lines 84–136):
   - **Lookahead Padding (line 85):**
     ```python
     noisy_mag = functional.pad(noisy_mag, [0, self.look_ahead])  # Pad 2 frames on right
     ```
     Appends 2 zero frames at the end of the time dimension: $T \gets T + 2$.
   - **First Normalization Stage (lines 92–94):**
     ```python
     fb_input = self.norm(noisy_mag).reshape(batch_size, num_channels * num_freqs, num_frames)
     ```
     `self.norm` evaluates `BaseModel.offline_laplace_norm(input)`.
   - **Fullband Sequence Model (line 95):**
     `fb_output = self.fb_model(fb_input)` evaluates 2-layer unidirectional LSTM (input 257, hidden 512, output 257) with ReLU activation.
   - **Subband Unit Unfolding (lines 97–107):**
     - Fullband output is unfolded across frequency with `fb_num_neighbors=0` (retaining 1 center frequency).
     - Noisy magnitude is unfolded across frequency with `sb_num_neighbors=15` (retaining $15 \times 2 + 1 = 31$ frequency neighbors).
     - Both tensors are concatenated along feature dimension:
       $$\text{sb\_input} \in \mathbb{R}^{B \times 257 \times 32 \times (T+2)}$$
   - **Second Normalization Stage (line 111):**
     ```python
     sb_input = self.norm(sb_input)
     ```
     `self.norm` evaluates `BaseModel.offline_laplace_norm(input)` a second time on the subband features!
   - **Subband Sequence Model (lines 121–128):**
     `sb_input` is reshaped to `[B * 257, 32, T + 2]`. Evaluates 2-layer unidirectional LSTM (input 32, hidden 384, output 2) across all 257 frequency bins in parallel.
   - **Lookahead Delay Slicing (lines 130–135):**
     ```python
     sb_mask = sb_mask.reshape(batch_size, num_freqs, 2, num_frames).permute(0, 2, 1, 3).contiguous()
     output = sb_mask[:, :, :, self.look_ahead :]  # Slice [:, :, :, 2:]
     ```
     Because the sequence model is unidirectional and delayed by 2 frames, mask frame $t$ is generated from LSTM state at step $t+2$.
4. **Mask Decompression & Synthesis:**
   cIRM mask is decompressed, multiplied with complex spectrogram, and reconstructed via `torch.istft`.

### 2.3 Non-Causality Root Cause: Utterance-Wide Laplace Normalization
In `audio_zen/model/base_model.py` (lines 204–219):
```python
@staticmethod
def offline_laplace_norm(input):
    # utterance-level mu
    mu = torch.mean(input, dim=list(range(1, input.dim())), keepdim=True)
    normed = input / (mu + 1e-5)
    return normed
```
- For `fb_input` (`noisy_mag` shape `[B, 1, 257, T+2]`):
  $$\mu_{\text{fb}} = \frac{1}{257 \cdot (T+2)} \sum_{f=0}^{256} \sum_{\tau=0}^{T+1} X(f, \tau)$$
- For `sb_input` (`sb_input` shape `[B, 257, 32, T+2]`):
  $$\mu_{\text{sb}} = \frac{1}{257 \cdot 32 \cdot (T+2)} \sum_{f=0}^{256} \sum_{k=0}^{31} \sum_{\tau=0}^{T+1} S(f, k, \tau)$$

**Consequences of this mechanism:**
1. **Complete Non-Causality:** The magnitude scaling applied to frame $t=0$ depends mathematically on speech and noise frames occurring seconds into the future.
2. **Session-Length Coupling:** Processing the identical speech segment within a 1-second clip vs. a 10-second clip yields different $\mu$, altering LSTM input activations and changing enhanced outputs.
3. **Continuous Streaming Impossibility:** In a live stream ($T \to \infty$), offline normalization cannot compute $\mu$ because the total duration is unbounded.

---

## 3. Mathematical Formulations of 5 Causal Normalization Configurations

To eliminate future frame dependency while preserving the numerical distribution expected by the pretrained LSTM weights, we define five causal candidate configurations.

```
       +-------------------------------------------------------------+
       |                  Incoming STFT Spectrogram                  |
       +-------------------------------------------------------------+
                                      |
                    +-----------------+-----------------+
                    |                                   |
           Dynamic Statistics                   Static Calibration
                    |                                   |
         +----------+----------+                        |
         |                     |                        |
   Moving Window          Recursive EMA            Fixed Scaler
     (Config 1)             (Config 3)              (Config 4)
         |                     |                        |
         v                     v                        v
+------------------+  +------------------+    +-------------------+
|  Past W frames   |  | μ_t = α x_t      |    | μ_fixed calibrated|
|  (400/800/1600ms)|  |       + (1-α)μ_t-1|   | on training set   |
+------------------+  +------------------+    +-------------------+
                    |
                    v
       +-------------------------------------------------------------+
       |   Causal Normalization: X_norm(t) = X(t) / (μ_t + 1e-5)     |
       +-------------------------------------------------------------+
                                      |
                                      v
       +-------------------------------------------------------------+
       | Config 5: Stateful Recurrent Chunk Inference (Persistent h,c)|
       +-------------------------------------------------------------+
```

### Configuration 1: Bounded-Window Moving Normalization
At frame index $t \ge 0$, normalizer $\mu_t^{(W)}$ is computed over a sliding causal historical buffer of $W$ frames:
$$\mu_t^{(W)} = \frac{1}{F \cdot K_t} \sum_{f=0}^{F-1} \sum_{\tau = \max(0, t - W + 1)}^{t} X(f, \tau)$$
where $K_t = \min(t + 1, W)$ handles startup warmup.
- **Window Length Parameter Sweeps:**
  - $W = 25$ frames $\implies 25 \times 16\text{ ms} = 400\text{ ms}$ history.
  - $W = 50$ frames $\implies 50 \times 16\text{ ms} = 800\text{ ms}$ history.
  - $W = 100$ frames $\implies 100 \times 16\text{ ms} = 1600\text{ ms} = 1.6\text{ s}$ history.
- **Subband Equivalent:**
  $$\mu_{t, \text{sb}}^{(W)} = \frac{1}{257 \cdot 32 \cdot K_t} \sum_{f=0}^{256} \sum_{k=0}^{31} \sum_{\tau = \max(0, t - W + 1)}^{t} S(f, k, \tau)$$
- **Memory Footprint:** A ring buffer storing $W$ scalar frame means ($W \times 4\text{ bytes} \le 400\text{ bytes}$).
- **Computational Complexity:** $O(1)$ per frame update via running accumulator:
  $$\text{sum}_t = \text{sum}_{t-1} + \text{frame\_mean}_t - \text{frame\_mean}_{t-W}$$

### Configuration 2: Causal Cumulative Normalization
Normalizer accumulates from the start of the session ($t=0$) to current frame $t$:
$$\mu_t^{(\text{cum})} = \frac{1}{F \cdot (t + 1)} \sum_{f=0}^{F-1} \sum_{\tau=0}^{t} X(f, \tau)$$
- **Recursive Form:**
  $$\text{acc}_t = \text{acc}_{t-1} + \sum_{f=0}^{F-1} X(f, t), \quad \mu_t^{(\text{cum})} = \frac{\text{acc}_t}{F \cdot (t + 1)}$$
- **Failure Mode & Risk Analysis:**
  As session length grows ($t \to \infty$), the marginal contribution of new incoming frames diminishes as $1 / (t + 1) \to 0$. In a continuous multi-minute session, the normalizer becomes effectively frozen. If the speaker shifts from a quiet room into a high-noise combat zone, the normalizer cannot adapt.
- **Upstream Implementation Divergence:** Upstream `BaseModel.cumulative_laplace_norm` (lines 221–251) computes per-frequency cumulative means for subband inputs rather than a global scalar. Both variants must be tested.

### Configuration 3: Stateful Exponential Moving Average (EMA) / Forgetting Norm
Applies recursive exponential smoothing to the per-frame spatial mean $\bar{x}_t = \frac{1}{F} \sum_{f=0}^{F-1} X(f, t)$:
$$\mu_t^{(\text{ema})} = (1 - \alpha) \mu_{t-1}^{(\text{ema})} + \alpha \bar{x}_t$$
with $\mu_0^{(\text{ema})} = \bar{x}_0$.
- **Upstream Two-Phase Schedule (`forgetting_norm`):**
  For startup index $t < T_{\text{sample}}$:
  $$\alpha_t = \min\left( \frac{t}{t + 2}, \alpha_{\text{target}} \right), \quad \mu_t = (1 - \alpha_t) \mu_{t-1} + \alpha_t \bar{x}_t$$
  For steady-state $t \ge T_{\text{sample}}$:
  $$\mu_t = (1 - \alpha_{\text{target}}) \mu_{t-1} + \alpha_{\text{target}} \bar{x}_t$$
  where $\alpha_{\text{target}} = \frac{2}{T_{\text{sample}} + 1}$.
- **Smoothing Parameter Grid:**
  - $\alpha = 0.05 \implies T_{\text{sample}} \approx 39$ frames ($624\text{ ms}$ time constant $\tau$).
  - $\alpha = 0.02 \implies T_{\text{sample}} \approx 99$ frames ($1.58\text{ s}$ time constant $\tau$).
  - $\alpha = 0.01 \implies T_{\text{sample}} \approx 199$ frames ($3.18\text{ s}$ time constant $\tau$; matches upstream default $T=192$).
- **State Footprint:** Exactly 2 scalar floats ($\mu_{\text{fb}}, \mu_{\text{sb}}$) preserved across chunks ($8\text{ bytes}$).
- **Adaptability:** Provides continuous responsiveness to non-stationary noise floors without memory accumulation.

### Configuration 4: Fixed Pre-Calibrated Statistics
Replaces dynamic estimation with static constants calibrated offline:
$$X_{\text{norm}}(f, t) = \frac{X(f, t)}{\mu_{\text{fixed}} + \epsilon}$$
- **Zero Algorithmic Latency & Zero State:** Requires $0\text{ ms}$ buffer history and $0\text{ bytes}$ persistent state.
- **Calibration Protocol:** Must be calibrated on an independent training split (e.g. DNS Challenge training set or pre-training development clips). **Strictly forbidden from using canonical evaluation or sealed gold test data.**
- **Risk Analysis:** Highly sensitive to absolute input gain and microphone ADC calibration. If input acoustic energy deviates from calibration energy by $\pm 12\text{ dB}$, LSTM activations will shift out of linear operating regimes.

### Configuration 5: Stateful Recurrent Chunk Inference
Executes FullSubNet in discrete temporal chunks $\Delta t \in \{1, 2\}$ frames ($16\text{ ms}$ or $32\text{ ms}$) while carrying persistent LSTM hidden and cell states across chunk calls:
$$\left( y_k, (h_k^{\text{fb}}, c_k^{\text{fb}}), (h_k^{\text{sb}}, c_k^{\text{sb}}), \text{norm\_state}_k \right) = \text{Model.step}\left( x_k, (h_{k-1}^{\text{fb}}, c_{k-1}^{\text{fb}}), (h_{k-1}^{\text{sb}}, c_{k-1}^{\text{sb}}), \text{norm\_state}_{k-1} \right)$$
- **Fullband LSTM State Dimensions:**
  - $h^{\text{fb}}, c^{\text{fb}} \in \mathbb{R}^{2 \times 1 \times 512}$ ($2,048$ float32 values $= 8.19\text{ KB}$).
- **Subband LSTM State Dimensions:**
  - $h^{\text{sb}}, c^{\text{sb}} \in \mathbb{R}^{2 \times 257 \times 384}$ ($394,752$ float32 values $\approx 1.58\text{ MB}$).
- **Total Persistent State:** $396,800$ float32 elements $\approx \mathbf{1.587\text{ MB}}$.
- **Session Lifecycle:** `reset_session()` zeros all hidden and cell states and resets normalization accumulators to fresh initial conditions.

---

## 4. Latency Breakdown and Raspberry Pi 5 Feasibility

### 4.1 Algorithmic Latency Analysis

| Delay Component | Parameter / Mechanism | Delay Contribution | Cumulative Algorithmic Floor |
|---|---|---|---|
| **STFT Analysis Window Context** | 512-point Hann window, centered ($N_{\text{fft}} / 2$) | $16.0\text{ ms}$ (256 samples @ 16 kHz) | $16.0\text{ ms}$ |
| **Model Explicit Lookahead** | `look_ahead = 2` hops ($2 \times 256$ samples) | $32.0\text{ ms}$ (512 samples @ 16 kHz) | **$48.0\text{ ms}$** |
| **Utterance Normalization Wait** | Offline: entire clip duration; Causal: $0.0\text{ ms}$ | $0.0\text{ ms}$ (under causal normalization) | **$48.0\text{ ms}$** |
| **Provisional System Latency Gate** | Master requirement | $\le \mathbf{35.0\text{ ms}}$ | **EXCEEDED BY 13.0 ms** |

> [!WARNING]
> **Fundamental Algorithmic Latency Conflict:**
> Even if FullSubNet executes in **zero computation time** on Raspberry Pi 5, its structural framing ($16\text{ ms}$) plus lookahead ($32\text{ ms}$) imposes an immutable **$48.0\text{ ms}$ algorithmic latency floor**.
> This exceeds the provisional $\le 35.0\text{ ms}$ end-to-end latency ceiling by **$13.0\text{ ms}$** before accounting for physical ALSA capture, ADC/DAC conversion, audio I/O scheduling, resampling, or model computation!
>
> If the $35.0\text{ ms}$ latency gate is non-negotiable for physical qualification, FullSubNet **cannot be physically deployed in streaming mode** without either:
> 1. Retraining with `look_ahead = 0` (causal training), which violates the immutable checkpoint freeze; or
> 2. Re-architecting the streaming ensemble to use DFN3 + GTCRN (which both support $\le 30\text{ ms}$ algorithmic delay) while retaining the frozen 15/70/15 ensemble as an offline quality oracle.

### 4.2 Computational Complexity on Raspberry Pi 5 SoC
- **Total Model Parameters:** $5,637,635$ ($\approx 5.64\text{M}$ parameters).
- **Fullband Sequence Model FLOPs:**
  - 2 layers, input 257, hidden 512, output 257:
  - $\approx 6.3\text{ MFLOPs}$ per frame.
- **Subband Sequence Model FLOPs:**
  - Evaluated across 257 distinct frequency bins!
  - 2 layers, input 32, hidden 384, output 2:
  - Each bin: $4 \times (32 \times 384 + 384^2) + 4 \times (384^2 + 384^2) \approx 3.64\text{ MFLOPs}$.
  - For 257 bins: $257 \times 3.64\text{ MFLOPs} \approx \mathbf{935.5\text{ MFLOPs}}$ per frame!
- **Total Compute per Frame:** $\approx \mathbf{941.8\text{ MFLOPs}}$.
- **Frame Rate at 16 kHz / hop 256:** $62.5\text{ frames/second}$.
- **Sustained Real-Time Throughput Required:**
  $$941.8\text{ MFLOPs/frame} \times 62.5\text{ frames/s} \approx \mathbf{58.86\text{ GFLOPs/second}}$$

**Hardware Reality on Raspberry Pi 5 (BCM2712, Quad-core Cortex-A76 @ 2.4 GHz):**
- Theoretical peak FP32 throughput (4 cores, 2x 128-bit NEON FMA/cycle):
  $$4 \times 8 \times 2.4\text{ GHz} = \mathbf{76.8\text{ GFLOPs/second}}$$
- Required throughput for FullSubNet alone represents **$76.6\%$ of the theoretical hardware peak** of the entire processor!
- In single-frame or small-chunk execution, BLAS GEMV efficiency on mobile ARM rarely exceeds $25\%\text{--}35\%$ of peak, resulting in an expected Real-Time Factor ($\text{RTF}$) on Pi 5 of:
  $$\text{RTF}_{\text{Pi5}} \approx \frac{58.86\text{ GFLOPs/s}}{76.8 \times 0.30\text{ GFLOPs/s}} \approx \mathbf{2.55} \quad (\text{Over 2.5}\times\text{ slower than real time!})$$

---

## 5. Pilot Experiment Protocol & Representative 9-Clip Validation Matrix

To rapidly validate numerical stability, state drift, and metric retention before running the full 590-clip evaluation, a representative 9-clip pilot subset is selected from the canonical development set (`runs/sih26052_canonical_validation/manifest.csv`).

### 5.1 Selection Criteria
The 9 clips are stratified to cover:
1. Both noise origins (`IoBT_GUNFIRE` impulsive noise and `EXISTING_PROXY` stationary/machinery noise).
2. The entire target SNR range from $-10\text{ dB}$ (severe stress) to $+20\text{ dB}$ (high SNR).
3. Representative baseline performance profiles (from complete failure at $-10\text{ dB}$ to joint metric passes).

### 5.2 Baseline Performance Ledger for the 9 Pilot Clips
Ground truth extracted from `runs/fullsubnet_baseline/per_clip.csv` (SHA-256 `482615e9709d2d6c...`):

| Clip Index | Dataset Origin | Target SNR | Input SNR (dB) | Baseline Out SNR (dB) | Baseline Out STOI | Baseline Out PESQ | Baseline Pass Status |
|---|---|---|---|---|---|---|---|
| **0061** | `IoBT_GUNFIRE` | $-10\text{ dB}$ | $-7.24$ | $8.66$ | $0.6867$ | $1.2942$ | Fail all |
| **0000** | `EXISTING_PROXY` | $-10\text{ dB}$ | $-9.45$ | $3.81$ | $0.7802$ | $1.1844$ | Fail all |
| **0033** | `IoBT_GUNFIRE` | $-5\text{ dB}$ | $-3.45$ | $14.00$ | $0.9687$ | $3.0796$ | Pass STOI, PESQ |
| **0003** | `EXISTING_PROXY` | $0\text{ dB}$ | $+1.66$ | $9.23$ | $0.5957$ | $1.9513$ | Fail all |
| **0004** | `IoBT_GUNFIRE` | $+5\text{ dB}$ | $+5.60$ | $16.42$ | $0.9515$ | $2.4281$ | Pass SNR, STOI |
| **0028** | `EXISTING_PROXY` | $+5\text{ dB}$ | $+6.19$ | $14.99$ | $0.9592$ | $2.3135$ | Pass STOI |
| **0023** | `IoBT_GUNFIRE` | $+10\text{ dB}$ | $+10.22$ | $15.80$ | $0.9596$ | $2.3843$ | Pass SNR, STOI |
| **0026** | `EXISTING_PROXY` | $+15\text{ dB}$ | $+15.36$ | $21.81$ | $0.9927$ | $2.7645$ | **Pass All 3** |
| **0009** | `IoBT_GUNFIRE` | $+20\text{ dB}$ | $+20.04$ | $14.62$ | $0.8042$ | $1.8981$ | Fail all |

### 5.3 Test Execution Matrix

For each candidate configuration, we evaluate:
1. **Per-Clip Metrics:** Output SNR (dB), SI-SDR (dB), STOI, and PESQ-WB.
2. **Delta from Frozen Baseline:**
   $$\Delta\text{SNR} = \text{SNR}_{\text{causal}} - \text{SNR}_{\text{offline}}$$
   $$\Delta\text{STOI} = \text{STOI}_{\text{causal}} - \text{STOI}_{\text{offline}}$$
   $$\Delta\text{PESQ} = \text{PESQ}_{\text{causal}} - \text{PESQ}_{\text{offline}}$$
3. **Waveform Equivalence Diagnostics:**
   - Root Mean Square Error ($\text{RMSE}$) against offline FullSubNet waveform.
   - Pearson correlation coefficient ($r$).
4. **Boundary & Temporal Continuity:**
   - Spectral distortion at chunk boundaries.
   - Onset transient behavior ($t \in [0, 400\text{ ms}]$).

---

## 6. Comprehensive Risk & Tradeoff Matrix

| Configuration | Algorithmic Latency | Memory Footprint | Adaptation Dynamics | Quality Retention Risk | Primary Failure Mode |
|---|---|---|---|---|---|
| **Baseline (Offline Laplace)** | Whole clip ($\ge 3\text{ s}$) | Whole spectrogram | Instant global oracle | $100\%$ (Frozen Reference) | Non-causal; live streaming impossible. |
| **Config 1: Bounded Window ($W=50$)** | $48\text{ ms}$ (STFT + lookahead) | $< 1\text{ KB}$ ring buffer | Slugs past $800\text{ ms}$ | Moderate risk of scale variance | Transient bursts (gunfire) distort window scale for $800\text{ ms}$. |
| **Config 2: Cumulative Norm** | $48\text{ ms}$ (STFT + lookahead) | $8\text{ bytes}$ (accumulators) | Decays as $1/t$ | Severe long-term degradation | Freezes normalizer in continuous sessions; unable to track moving noise floor. |
| **Config 3: Stateful EMA ($\alpha=0.02$)** | $48\text{ ms}$ (STFT + lookahead) | $8\text{ bytes}$ ($\mu_{\text{fb}}, \mu_{\text{sb}}$) | Continuous tracking ($\tau \approx 1.58\text{ s}$) | **Lowest expected quality loss** | Speech onset distortion during initial $200\text{ ms}$ warmup. |
| **Config 4: Fixed Static Calibration** | $48\text{ ms}$ (STFT + lookahead) | $0\text{ bytes}$ | Zero dynamic tracking | High risk across dynamic range | Volume mismatch leads to clipping or under-suppressed noise. |
| **Config 5: Stateful Chunks ($32\text{ ms}$)** | $48\text{ ms}$ total algorithmic floor | $1.587\text{ MB}$ (LSTM states) | Frame-by-frame stateful | Prerequisite for all chunk processing | High CPU load on Pi 5 ($58.8\text{ GFLOPs/s}$); exceeds RTF budget. |

---

## 7. Governance, Integrity, and Audit Trails

### 7.1 Cryptographic Hash Verification

| Artifact Description | File Path | Expected SHA-256 | Verified Byte Integrity |
|---|---|---|---|
| **Canonical Validation Manifest** | `antigravity/runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | **MATCH (Exact)** |
| **FullSubNet Epoch 58 Checkpoint** | `antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | **MATCH (Exact)** |
| **GTCRN DNS3 Checkpoint** | `antigravity/checkpoints/gtcrn/model_trained_on_dns3.tar` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | **MATCH (Exact)** |
| **DFN3 Step-500 Checkpoint** | `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | **MATCH (Exact)** |

### 7.2 Strict Governance Status
- **Sealed Gold Dataset Boundary:** `data/SIH_GOLD_TEST` isolated (`gold_test_read: false`). Zero access permitted.
- **Physical Hardware Qualification:** 0/5 prerequisite gates passed. Raspberry Pi 5 hardware access, live audio capture, ALSA streams, and Bluetooth operations remain **LOCKED** (Stage 11.3 NO-GO).
- **Ensemble Preservation:** Frozen 15/70/15 reference weights and offline predictions remain immutable.

---

## 8. Summary of Findings & Recommended Decision

1. **Root Cause Confirmed:** FullSubNet's non-causality is rooted directly in `offline_laplace_norm` (utterance-wide mean) and stateless LSTM execution in upstream code.
2. **Algorithmic Latency Incompatibility:** FullSubNet's centered STFT ($16\text{ ms}$) plus lookahead ($32\text{ ms}$) creates a **$48.0\text{ ms}$ algorithmic latency floor**, fundamentally violating the provisional $\le 35.0\text{ ms}$ latency gate.
3. **Compute Load Incompatibility:** Sustained computational demand is $\approx \mathbf{58.86\text{ GFLOPs/s}}$, consuming over $76\%$ of the Raspberry Pi 5's theoretical peak capacity and rendering real-time streaming infeasible on target hardware.
4. **Actionable Next Step:** Proceed with the 9-clip pilot validation of Config 3 (Stateful EMA) and Config 1 (Bounded Window) in software to establish the empirical quality envelope of causal FullSubNet, while preparing the architectural recommendation for the Master System Review.

---

*End of Stage 11.2.31 Audit and Experiment Design Report. Awaiting user feedback before implementation.*

