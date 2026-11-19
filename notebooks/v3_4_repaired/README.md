# Repaired DeepFilterNet3 V3.4 Kaggle kernel

This is the locally versioned source for the existing private Kaggle kernel `shreyasdivekar/dfn3-v3-1-sih-training`. It retains the kernel's canonical exclusion dataset, zip-streamed defence audio, fixed SNR-stratified validation set, SI-SDR training loss, and checkpoints every 500 steps.

The previous run failed at step 50 because `gc` was referenced without import. This copy adds the missing import and resets libDF state before every clip in training, pretrained validation, candidate validation, and the SI-SDR diagnostic.

From this directory:

```bash
kaggle kernels push -p .
kaggle kernels status shreyasdivekar/dfn3-v3-1-sih-training
kaggle kernels output shreyasdivekar/dfn3-v3-1-sih-training -p ../../kaggle_output_v3_4
```

A push executes the notebook by default. It uses the configured GPU T4×2 accelerator and private datasets, including the canonical exclusion list. Evaluate retrieved checkpoints on the local frozen 590-clip benchmark before selecting or deploying one.
