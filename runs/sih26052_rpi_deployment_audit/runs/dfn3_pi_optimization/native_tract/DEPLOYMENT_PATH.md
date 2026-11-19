# Deployment Path

- DeepFilterNet uses a native Rust inference implementation located in `libDF` and its `deep-filter` binary crates.
- The core streaming inference logic is encapsulated in the `DfTract` struct (from `df::tract`).
- `DfTract::new` loads the model from a `.tar.gz` model package containing the ONNX graphs and configuration.
- Streaming audio is processed using `model.process(chunk_in, chunk_out)` which acts on frames exactly equal to `model.hop_size` (typically 480 samples = 10 ms at 48 kHz).
- Statefulness (GRU/LSTM hidden states) is natively and implicitly maintained by the `Tract` inference engine which handles stateful ONNX operators internally across `process` calls.
- The official evaluation path for benchmarking and audio evaluation is to compile the `enhance_wav` binary in Rust (`libDF/src/bin/enhance_wav.rs`).

## Strategy
We will compile the `enhance_wav` binary natively on the Raspberry Pi 5 using Cargo and run our equivalence and latency benchmarks against it.
