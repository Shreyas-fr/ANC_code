# DeepFilterNet3 V7 SIH26052 conservative fine-tuning

V7 starts from the V6 audit notebook and preserves its random speech-row sampler, source-group exclusions, RIR/clipping policy, model, optimizer type, loss, and train/validation sets. The sole training hyperparameter change is AdamW learning rate `1e-6` instead of `1e-5`.

The 250-step cap with checkpoints every 25 steps is a diagnostic run: V6 canonical quality was already substantially worse by step 250. Evaluate every checkpoint on the frozen 590-clip set and compare paired metrics to the deployed and pretrained models. If a checkpoint does not materially improve the canonical comparison, do not extend or deploy it based only on synthetic validation loss. `SIH_GOLD_TEST` must remain unmounted and unread.

This notebook is prepared locally and has not been pushed or run.
