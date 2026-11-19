# DeepFilterNet3 V9 SIH26052 clipping ablation

V9 repeats V8's 500-step, `lr=1e-6` training recipe and disables the 15% clipping operation that was applied to the noisy mixture without clipping the speech target. All other setup is retained: V6 full-pool speech sampling, canonical exclusions and source-group splits, V5 target-aligned RIR, objective, model initialization, optimizer, dataset sizes, and 25-step checkpoint cadence.

Evaluate all 20 checkpoints on the frozen 590-clip benchmark and paired baselines. Report the full SNR/STOI/PESQ tradeoff. Do not promote unless a checkpoint exceeds the deployed candidate and passes edge gates. Keep `SIH_GOLD_TEST` unmounted and unread. The notebook is prepared locally and has not been pushed or run.
