# DeepFilterNet3 V8 SIH26052 conservative-LR horizon study

V8 repeats the V7 `1e-6` AdamW configuration and source/data recipe, but extends the horizon from 250 to 500 steps. It preserves the V6 full-pool sampler, exclusions, target-aligned RIR, clipping, loss, and 25-step checkpoints. The goal is to determine whether canonical gains keep improving beyond the V7 endpoint.

Evaluate all 20 checkpoints against the frozen 590-clip benchmark, deployed Step-500, and pretrained DFN3. Do not use synthetic validation loss to promote a checkpoint. Keep `SIH_GOLD_TEST` unmounted. The notebook is prepared locally and has not been pushed or trained.
