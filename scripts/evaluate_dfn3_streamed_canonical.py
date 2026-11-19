#!/usr/bin/env python3
"""Evaluate the deployed Pi block-streaming DSP path on frozen canonical clips.

This replays the Pi's exact deployed streaming_core.py and playout.py modules
offline. Inference results are made available immediately to the playout
scheduler, so this measures acoustic effects of framing, resampling, windows,
crossfades, and delay alignment, but not real-time deadline misses.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent / "runs" / "sih26052_rpi_deployment_audit" / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_dfn3_canonical import install_torchaudio_compat_shim, metrics, require_non_gold_canonical_dir, sha256  # noqa: E402
from playout import PlayoutScheduler  # noqa: E402
from streaming_core import AudioChain, BlockBackend  # noqa: E402


FRAME = 256


def make_enhance_fn(checkpoint: Path, threads: int):
    install_torchaudio_compat_shim()
    import scipy.signal  # noqa: F401 - required by DeepFilterNet DSP stack
    from df.enhance import enhance, init_df, maybe_download_model
    from df.model import ModelParams
    from libdf import DF

    torch.set_num_threads(threads)
    model_dir = maybe_download_model("DeepFilterNet3")
    model, _, _ = init_df(model_dir, log_file=None)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        state = state["model_state_dict"]
    model.load_state_dict(state, strict=True)
    model.eval()
    params = ModelParams()

    def run_window(window48: np.ndarray) -> np.ndarray:
        df_state = DF(
            sr=params.sr,
            fft_size=params.fft_size,
            hop_size=params.hop_size,
            nb_bands=params.nb_erb,
        )
        audio = torch.from_numpy(np.ascontiguousarray(window48, dtype=np.float32)).unsqueeze(0)
        with torch.inference_mode():
            output = enhance(model, df_state, audio)
        return output.squeeze(0).cpu().numpy().astype(np.float32)

    return run_window


def soft_limit(x: np.ndarray, knee: float = 0.8) -> tuple[np.ndarray, int]:
    a = np.abs(x)
    mask = a > knee
    if not mask.any():
        return x, 0
    y = x.copy()
    y[mask] = np.sign(x[mask]) * (knee + (1.0 - knee) * np.tanh((a[mask] - knee) / (1.0 - knee)))
    return y, int(mask.sum())


def stream_clip(noisy: np.ndarray, enhance_fn, config: dict[str, int]) -> tuple[np.ndarray, dict[str, int]]:
    n_samples = len(noisy)
    n_frames = (n_samples + FRAME - 1) // FRAME
    padded_len = n_frames * FRAME
    padded = np.pad(np.asarray(noisy, dtype=np.float32), (0, padded_len - n_samples))

    backend = BlockBackend(
        enhance_fn,
        block_ms=config["block_ms"],
        context_ms=config["context_ms"],
        guard_ms=config["guard_ms"],
        xfade_ms=config["xfade_ms"],
    )
    chain = AudioChain(backend, align_to=FRAME)
    delay_frames = chain.delay_samples_io // FRAME
    jitter_frames = int(round(config["jitter_ms"] / (FRAME / 16.0)))
    scheduler = PlayoutScheduler(delay_frames, jitter_frames, FRAME)
    zero = np.zeros(FRAME, dtype=np.float32)
    output_chunks: list[np.ndarray] = []
    limited_total = 0

    # Feed trailing zeros to flush the final delayed source frames through the
    # block backend and scheduler, preserving the Pi sender's source timeline.
    n_total_frames = n_frames + delay_frames + jitter_frames + 1
    for seq in range(n_total_frames):
        if seq < n_frames:
            chunk = padded[seq * FRAME : (seq + 1) * FRAME]
        else:
            chunk = zero
        enhanced = chain.process(chunk)
        scheduler.push_input(seq, chunk)
        scheduler.push_result(seq, enhanced)
        out = scheduler.next_output(seq)
        source_frame = seq - jitter_frames - delay_frames
        if 0 <= source_frame < n_frames:
            out, limited = soft_limit(out)
            limited_total += limited
            output_chunks.append(out)

    streamed = np.concatenate(output_chunks)[:n_samples]
    counts = {
        "frames": n_frames,
        "delay_frames": delay_frames,
        "jitter_frames": jitter_frames,
        "windows": backend.windows,
        "backend_errors": backend.errors,
        "chain_underruns": chain.underruns,
        "fallback_frames_simulated": scheduler.fallback_frames,
        "soft_limited_samples": limited_total,
    }
    return streamed, counts


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    fields = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    values = {name: np.asarray([float(row[f"output_{name}"]) for row in rows]) for name in fields}
    pass_masks = {
        "snr_gt_15_db": values["snr_db"] > 15.0,
        "stoi_gt_0_85": values["stoi"] > 0.85,
        "pesq_gt_2_5": values["pesq_wb"] > 2.5,
    }
    return {
        "count": len(rows),
        "means": {name: float(np.nanmean(value)) for name, value in values.items()},
        "pass_counts": {
            **{name: int(mask.sum()) for name, mask in pass_masks.items()},
            "all_three": int((pass_masks["snr_gt_15_db"] & pass_masks["stoi_gt_0_85"] & pass_masks["pesq_gt_2_5"]).sum()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--canonical-dir", type=Path, default=Path("runs/sih26052_canonical_validation"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/sih26052_dfn3_streamed_canonical"))
    parser.add_argument("--threads", type=int, default=3)
    parser.add_argument("--block-ms", type=int, default=500)
    parser.add_argument("--context-ms", type=int, default=300)
    parser.add_argument("--guard-ms", type=int, default=40)
    parser.add_argument("--xfade-ms", type=int, default=10)
    parser.add_argument("--jitter-ms", type=int, default=320)
    args = parser.parse_args()

    args.canonical_dir = require_non_gold_canonical_dir(args.canonical_dir)
    manifest_path = args.canonical_dir / "manifest.csv"
    manifest = list(csv.DictReader(manifest_path.open(newline="")))
    if len(manifest) != 590:
        raise SystemExit(f"Expected 590 canonical rows, found {len(manifest)}")
    config = {
        "block_ms": args.block_ms,
        "context_ms": args.context_ms,
        "guard_ms": args.guard_ms,
        "xfade_ms": args.xfade_ms,
        "jitter_ms": args.jitter_ms,
    }
    enhance_fn = make_enhance_fn(args.checkpoint, args.threads)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for position, row in enumerate(manifest, 1):
        index = int(row["val_index"])
        clean, clean_sr = sf.read(args.canonical_dir / "clean_audio" / f"{index:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(args.canonical_dir / "noisy_audio" / f"{index:04d}_noisy.wav", dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.ndim != 1 or noisy.ndim != 1 or len(clean) != len(noisy):
            raise ValueError(f"Canonical clip {index} violates the mono 16 kHz aligned-waveform contract")
        streamed, stream_counts = stream_clip(noisy, enhance_fn, config)
        input_metrics = metrics(clean, noisy)
        output_metrics = metrics(clean, streamed)
        results.append({
            "val_index": index,
            "dataset_origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_metrics["snr_db"],
            **{f"output_{k}": v for k, v in output_metrics.items()},
            **stream_counts,
        })
        if position % 25 == 0 or position == len(manifest):
            print(f"Stream-evaluated {position}/{len(manifest)}", flush=True)

    per_clip = args.output_dir / "per_clip.csv"
    with per_clip.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    strata: dict[str, list[dict[str, object]]] = {}
    for result in results:
        strata.setdefault(f"{float(result['target_snr_db']):g}", []).append(result)
    app_hashes = {
        name: sha256(APP_DIR / name)
        for name in ("streaming_core.py", "playout.py", "dfn3_enhance.py", "pi_sender_v5.py")
    }
    summary = {
        "checkpoint": str(args.checkpoint.resolve()),
        "checkpoint_sha256": sha256(args.checkpoint),
        "canonical_manifest_sha256": sha256(manifest_path),
        "count": len(results),
        "criteria": {"output_snr_db_gt": 15.0, "stoi_gt": 0.85, "pesq_wb_gt": 2.5},
        "stream_config": config,
        "deployed_module_sha256": app_hashes,
        "replay_limit": "offline synchronous replay; does not model wall-clock late fallbacks",
        "overall": aggregate(results),
        "strata": {key: aggregate(value) for key, value in sorted(strata.items(), key=lambda pair: float(pair[0]))},
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["overall"], indent=2))
    print(f"Wrote {per_clip} and {summary_path}")


if __name__ == "__main__":
    main()
