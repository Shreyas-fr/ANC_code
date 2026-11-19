# V10 causal export status: INCOMPLETE / NOT QUALIFIED

This directory is the residue of an interrupted export attempt. It is preserved for auditability and must not be loaded, used as an export source, evaluated, promoted, or described as a finished candidate.

Contents at the Stage 11.2.16 audit:

- `model_config/config.ini` — SHA-256 `6fd82652cef2b90375512df15cf028040ac09f9ce353792a4b8ff24e43222b9b`; configuration sets `conv_lookahead=0` and `df_lookahead=0`.
- `causal_v10_r0_step500_weights.hk` — SHA-256 `57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c`; copied V10 R0 Step-500 checkpoint bytes.

No ONNX graphs, Tract archive, export metadata, runtime validation, or quality evaluation were completed in this directory. This configuration/checkpoint pair was not used in the Stage 11.2.16 feasibility audit. Do not infer streaming quality or deployment status from its presence.
