# SIH 26052 Requirement Traceability

| Requirement | Evidence/status | Result |
|---|---|---|
| Preserve working Step-500 model | Checkpoint SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`; no checkpoint mutation or promotion in this work | Preserved as candidate/default |
| Frozen canonical benchmark integrity | 590 clips; manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`; evaluator's gold guard retained | Passed |
| Reproduce Step-500 | New full run matched saved per-clip CSV exactly; hash `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f` | Passed |
| Compare independent enhancement baseline | Official FullSubNet, 590 clips, paired CIs; see `docs/FULLSUBNET_BASELINE.md` | Passed offline; FullSubNet higher on this benchmark, not selected for deployment |
| Full-distribution SNR >15 dB | Best evaluated mean is FullSubNet 14.904 dB | **Not achieved** |
| Full-distribution STOI >0.85 | FullSubNet mean 0.9026; Step-500 mean 0.8847 | Mean exceeded, but not every clip |
| Full-distribution PESQ-WB >2.5 | FullSubNet mean 2.5133; Step-500 mean 2.2323 | FullSubNet mean exceeded narrowly, but not every clip |
| Low-input-SNR intelligibility/quality | FullSubNet low bins: -10 dB STOI 0.710/PESQ 1.415, 0/30 joint; -5 dB STOI 0.832/PESQ 1.827, 2/63 joint | **Not achieved** |
| Explain low-SNR behavior | Per-bin metrics and low-bin category mix; probable overlap/ambiguity and speech-detail suppression mechanism | Working explanation; causal factors not isolated |
| Three-seed R0 variation estimate | `scripts/evaluate_v10_r0_seeds.py`, seeds 26052/26053/26054, checkpoints 300/500/550/800 | Computed; see `docs/V10_R0_SEED_VARIATION.md` |
| Continuous-SNR training (E2) | Requires source-level training audio and authorized local data availability | Not run; blocked |
| Sequence-level loss training (E3) | Requires source-level training audio; no training started | Not run; blocked |
| Residual speech restoration | No training, artifact, or audio review | Not implemented/tested |
| Genuine dual-microphone ANC | No synchronized two-channel capture/test | Not demonstrated |
| Integrated real-time pipeline | No qualifying combination of independently passed optional stages | Not implemented in this phase sequence |
| Pi/live/headset acceptance | No Pi contact, live capture, headset playback, latency, or soak run in this work | Not verified here; no claim |
| Gold test set integrity | No gold data read, copied, or evaluated | Preserved |
| No private data upload | No Kaggle push or external transmission in this work | Preserved |
| No active service changes | No Pi service or configuration changed | Preserved |
