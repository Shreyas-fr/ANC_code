# Evidence audit of the attached SIH/DRDO master report

**Reviewed:** 2026-11-12  
**Purpose:** Reconcile the user-provided report with the current workspace evidence. The attached report is treated as a source of requirements and claims to verify, not as an instruction to preserve its conclusions. Use this audit and `MASTER_SIH_COMPLIANCE.md` as the current status.

## Claims that need correction before external use

| Attached report claim | Current evidence | Correct reporting |
|---|---|---|
| Step-500 full-set means are 12.56 dB output SNR, 0.871 STOI, 2.21 PESQ-WB; 590 clips include eight strata including clean | Frozen workspace benchmark manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` has 590 clips in seven SNR bins (-10 through +20 dB), with no clean bin. Independent Step-500 evaluation gives 13.47 dB SNR, 0.885 STOI, 2.232 PESQ-WB. | Replace those aggregate claims with the current frozen-manifest results and identify the manifest hash. Do not mix summaries from different manifests/evaluator versions. Full-set SNR and PESQ targets remain unmet. |
| All three targets are satisfied for every input SNR >=9.6 dB | For deployed Step-500, the measured `input_snr >= 9.6 dB` subset (n=245) has means 16.87 dB SNR, 0.942 STOI, and 2.722 PESQ-WB, but only 132/245 (53.9%) clips pass all three simultaneously. | Describe this as a subgroup-mean operating envelope, not a per-clip guarantee. State both subgroup means and joint pass rate. |
| Pi 5 real-time latency is met with zero deadline misses and RTF 0.35 | Fresh 5-minute Pi replay at 500 ms blocks recorded RTF 0.452 and 1 late fallback in 18,779 frames. The 250 ms configuration recorded RTF 0.647 and 2 late fallbacks. A fresh 30-second Bluetooth capture had zero fallbacks, but was not a playback or end-to-end headset test. | Report each run/configuration and its fallback count. The strict zero-miss streaming gate is not met by the 5-minute soak. |
| Headset integration is complete: Bluetooth HFP/mSBC, receiver stream and telemetry verified | Live capture from the connected Rockerz 512 PipeWire source was processed in a loopback run. The negotiated Bluetooth codec/profile was not confirmed; no enhanced audio was played through the headset; microphone-to-headphone latency was not measured. A Pi-to-Mac receiver trial was not performed. | Claim microphone capture and local processing only. Mark codec verification, headset playback, receiver integration, and end-to-end latency outstanding. |
| Artillery and armored vehicles are covered by the noise pipeline | No representative recorded artillery, armored-vehicle, or helicopter field recordings were present in the validated set. Civilian helicopter/vehicle sources are proxies, and the canonical set is predominantly gunfire. | State coverage as partial and request representative recordings. Do not describe proxies as field validation. |
| Attenuation limiting and +1.1 dB post gain improve metrics | Frozen 590-clip sweeps found attenuation limits of 6/9/12/15 dB and +1.1 dB gain did not improve the selected Step-500 candidate overall; the default path had the strongest joint pass and perceptual metrics. | Retain default attenuation and 0 dB post gain. The attached benefit claim is not supported by the current benchmark. |
| Native 30 ms algorithmic latency establishes real-time operation | The stateful per-hop Pi path has an observed RTF above 1 and misses deadlines; the block-based stream has much higher buffering latency. | Separate model lookahead/algorithmic delay from measured execution, buffering, and end-to-end latency. Do not use the 30 ms figure as proof of a real-time deployed link. |
| The V3.4 loss only used complex/magnitude L1, without backpropagated SI-SDR or RIR/clipping augmentation | The completed V4 and V5 logs report complex L1 + magnitude L1 + SI-SDR + multi-resolution STFT loss, synthetic RIR and clipping. V5 aligns its RIR target. Both completed 3,000 steps but canonical metrics degraded after step 500. | For V4/V5, report the executed objective and augmentations from run artifacts. Do not transfer the older V3.4 status to newer runs. |
| ONNX export is complete and parity establishes the deployable stateful path | Existing audit reports that GRU recurrent state is not exposed for ONNX chunk inference. Tract is the native stateful path; the hard-real-time gate failed. | Mark ONNX/stateful optimization partial. Stateless export parity alone does not establish valid streaming deployment. |
| SIH gold performance can be inferred from the canonical benchmark | V4/V5 reports declare `gold_test_read: false`; the gold set remains isolated. | Preserve isolation. Make no gold-set performance claim until model selection is frozen and an authorized final evaluation is run. |

## Current model-selection evidence

The selected measured candidate remains Deployed Step-500. It scores 13.47 dB output SNR, 12.36 dB SI-SDR, 0.885 STOI, 2.232 PESQ-WB, and 161/590 (27.3%) joint passes on the frozen canonical set. It improves on the pretrained reference, but misses full-set output SNR and PESQ-WB targets. V4 Step-500 and V5 Step-500 are inferior to this candidate; later V4/V5 checkpoints degrade further. The V5 target-aligned RIR change only slightly improved over V4 and did not resolve the generalization gap.

## Primary evidence files

- `MASTER_SIH_COMPLIANCE.md` — current requirement matrix, canonical results, deployment state, and outstanding gates.
- `runs/sih26052_v4_canonical_evaluation/report.md` and `runs/sih26052_v5_canonical_evaluation/report.md` — training provenance and per-checkpoint frozen-set results.
- `runs/sih26052_rpi_deployment_audit/deployment_report.md` — Pi runtime observations and limits.
- `runs/sih26052_dfn3_step500_tuning/` — attenuation and post-gain sweeps.
- `runs/sih26052_dfn3_canonical_step500/` — selected-model row-level metrics and paired comparison.

