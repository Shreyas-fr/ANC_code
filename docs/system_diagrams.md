# Antigravity ANC System Diagrams

This document outlines the architecture, data pipeline, and deployment flows for the Polar-D neural noise suppression system.

## 1. Technical Flow (Polar-D Architecture)

The core neural engine operates strictly causally, processing incoming audio frame-by-frame suitable for real-time embedded streaming.

```mermaid
flowchart TD
    %% Inputs
    AudioIn[Noisy Audio Waveform] --> STFT
    
    %% Feature Extraction
    subgraph Signal Processing [Signal Processing]
        STFT[Causal STFT<br>center=False, n_fft=512, hop=256]
        Concat[Concat Real & Imaginary]
        iSTFT[Causal Inverse STFT<br>overlap-add fold]
    end
    
    %% Neural Network Core
    subgraph Polar-D [Polar-D Neural Core]
        LSTM[2-Layer Stateful LSTM<br>hidden_size=256]
        FC_Mag[Linear -> Sigmoid * 2.0<br>Magnitude Mask: 0 to 2.0]
        FC_Phase[Linear -> Tanh * π<br>Phase Mask: -π to π]
        ComplexConvert[Combine Mag & Phase<br>mag * exp(j * phase)]
    end
    
    %% Connections
    STFT -->|Complex Spectrogram| Concat
    STFT -->|Noisy Spectrogram| ComplexMult((x))
    
    Concat -->|Features: B x T x 514| LSTM
    LSTM --> FC_Mag
    LSTM --> FC_Phase
    
    FC_Mag --> ComplexConvert
    FC_Phase --> ComplexConvert
    
    ComplexConvert -->|Complex Ratio Mask| ComplexMult
    ComplexMult -->|Enhanced Spectrogram| iSTFT
    
    iSTFT --> AudioOut[Enhanced Audio Waveform]
```

## 2. Data Sources & Training Pipeline

The dynamic mixer aggressively augments clean audio with proxy noises, genuine gunfire, and impulse responses (RIRs) to create robust training mixtures on the fly.

```mermaid
flowchart LR
    %% Data Sources
    subgraph Data Sources [Raw Data Sources]
        Clean[Clean Speech<br>UrbanSound, AudioSet]
        ProxyNoise[Proxy Noise<br>ESC-50, etc.]
        Gunfire[IoBT Gunfire<br>Defence Domain]
        RIR[Impulse Responses<br>Reverb]
    end
    
    %% Mixer Logic
    subgraph Mixer [Dynamic DataLoader]
        Augment[Augmentations<br>TimeStretch, PitchShift]
        Convolve[Apply RIR]
        Mix[SNR Mixer<br>-10dB to +20dB]
    end
    
    %% Sinks
    Target[Target Clean Audio]
    Noisy[Noisy Audio Mixture]
    
    %% Flow
    Clean --> Augment
    Augment --> Convolve
    RIR -.-> Convolve
    
    ProxyNoise --> Mix
    Gunfire --> Mix
    Convolve --> Mix
    
    Convolve --> Target
    Mix --> Noisy
    
    Target --> Loss[EnhancementLoss<br>L1 + MRSTFT]
    Noisy --> Model[Polar-D Network]
    Model --> Pred[Enhanced Audio]
    Pred --> Loss
```

## 3. User Flow (Embedded Deployment)

The deployment flow demonstrates how a user interfaces with the embedded ONNX model running on a Raspberry Pi device in the field.

```mermaid
sequenceDiagram
    participant Mic as USB Microphone
    participant RPi as Raspberry Pi (ONNX)
    participant Out as Speaker/Headphones
    
    note over Mic,Out: Real-Time Stream Loop (16ms Algorithmic Latency)
    
    Mic->>RPi: Capture 256 samples (16kHz)
    activate RPi
    RPi->>RPi: Buffer into 512-sample window
    RPi->>RPi: Causal STFT Extraction
    RPi->>RPi: ONNX Runtime (Polar-D Inference)
    RPi->>RPi: State Update (LSTM hidden/cell)
    RPi->>RPi: Complex Multiplication & iSTFT
    RPi->>RPi: Overlap-Add Fold
    RPi->>Out: Output 256 clean samples
    deactivate RPi
    
    Out-->>Mic: Continuous loop...
```
