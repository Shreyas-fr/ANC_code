#!/usr/bin/env python3
"""Development-regression evaluation of the separate causal Step-500 candidate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

# The existing SciPy 1.18/NumPy 1.26 environment uses the pre-NumPy-2
# RankWarning location. Add an import-compatibility alias only; no metric or
# resampling behavior is changed.
try:
    import numpy.exceptions as np_exceptions
    if not hasattr(np_exceptions, "RankWarning") and hasattr(np, "RankWarning"):
        np_exceptions.RankWarning = np.RankWarning
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluate_dfn3_canonical import (  # noqa: E402
    enhance_one,
    metrics,
    require_non_gold_canonical_dir,
)

EXPECTED_STEP500_SHA256 = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
EXPECTED_CANONICAL_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def install_torchaudio_shim() -> None:
    import torchaudio

    if getattr(getattr(torchaudio, "backend", None), "common", None) is not None:
        return
    common = types.ModuleType("torchaudio.backend.common")

    class AudioMetaData:
        def __init__(self, sample_rate, num_frames, num_channels, bits_per_sample, encoding):
            self.sample_rate = sample_rate
            self.num_frames = num_frames
            self.num_channels = num_channels
            self.bits_per_sample = bits_per_sample
            self.encoding = encoding

    common.AudioMetaData = AudioMetaData
    backend = types.ModuleType("torchaudio.backend")
    backend.common = common
    sys.modules["torchaudio.backend"] = backend
    sys.modules["torchaudio.backend.common"] = common
    torchaudio.backend = backend


def load_model(config_dir: Path, checkpoint: Path):
    install_torchaudio_shim()
    from df.enhance import init_df

    model, df_state, _ = init_df(
        str(config_dir), log_file=None, epoch="none", config_allow_defaults=True
    )
    model = model.cpu().eval()
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        state = state["model_state_dict"]
    if isinstance(state, dict) and state and all(k.startswith("model.") for k in list(state)[:3]):
        state = {k[len("model."):]: v for k, v in state.items()}
    result = model.load_state_dict(state, strict=True)
    if result.missing_keys or result.unexpected_keys:
        raise RuntimeError(f"Non-strict weight load: {result}")
    return model, df_state


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    metric_names = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    block: dict[str, object] = {"count": len(rows), "means": {}}
    for name in metric_names:
        vals = np.asarray([float(r[f"output_{name}"]) for r in rows], dtype=np.float64)
        block["means"][name] = float(np.nanmean(vals))
    passed = [
        float(r["output_snr_db"]) > 15.0
        and float(r["output_stoi"]) > 0.85
        and float(r["output_pesq_wb"]) > 2.5
        for r in rows
    ]
    block["individual_pass_counts"] = {
        "snr_gt_15_db": sum(float(r["output_snr_db"]) > 15.0 for r in rows),
        "stoi_gt_0_85": sum(float(r["output_stoi"]) > 0.85 for r in rows),
        "pesq_wb_gt_2_5": sum(float(r["output_pesq_wb"]) > 2.5 for r in rows),
    }
    block["joint_pass_count"] = sum(passed)
    block["joint_pass_percent"] = 100.0 * sum(passed) / len(rows) if rows else float("nan")
    return block


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--canonical-dir", type=Path, default=Path("runs/sih26052_canonical_validation")
    )
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    out = run_dir / "canonical_development_regression"
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing evaluation output: {out}")
    canonical_dir = require_non_gold_canonical_dir(args.canonical_dir)
    manifest = canonical_dir / "manifest.csv"
    manifest_hash = sha256(manifest)
    if manifest_hash != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("Frozen canonical manifest hash mismatch")
    checkpoint = run_dir / "causal_step500_weights.pt"
    config_dir = run_dir / "model_config"
    checkpoint_hash = sha256(checkpoint)
    if checkpoint_hash != EXPECTED_STEP500_SHA256:
        raise RuntimeError("Causal candidate weights are not the protected Step-500 bytes")

    model, df_state = load_model(config_dir, checkpoint)
    rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if len(rows) != 590:
        raise RuntimeError(f"Expected 590 development clips, got {len(rows)}")
    out.mkdir(parents=True)
    pred_dir = out / "float_predictions"
    pred_dir.mkdir()
    result_rows: list[dict[str, object]] = []
    for i, row in enumerate(rows, 1):
        index = int(row["val_index"])
        clean_path = canonical_dir / "clean_audio" / f"{index:04d}_clean.wav"
        noisy_path = canonical_dir / "noisy_audio" / f"{index:04d}_noisy.wav"
        clean, clean_sr = sf.read(clean_path, dtype="float32")
        noisy, noisy_sr = sf.read(noisy_path, dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.ndim != 1 or noisy.ndim != 1:
            raise ValueError(f"Canonical clip {index} violates mono 16 kHz contract")
        if clean.shape != noisy.shape or not np.isfinite(clean).all() or not np.isfinite(noisy).all():
            raise ValueError(f"Canonical clip {index} is invalid or unaligned")
        input_result = metrics(clean, noisy)
        estimate = enhance_one(model, df_state, noisy)
        if estimate.shape != noisy.shape or not np.isfinite(estimate).all():
            raise ValueError(f"Non-finite or misaligned causal output on clip {index}")
        np.save(pred_dir / f"{index:04d}.npy", estimate.astype(np.float32), allow_pickle=False)
        output_result = metrics(clean, estimate)
        result_rows.append({
            "val_index": index,
            "origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_result["snr_db"],
            "input_si_sdr_db": input_result["si_sdr_db"],
            "input_stoi": input_result["stoi"],
            "input_pesq_wb": input_result["pesq_wb"],
            "output_snr_db": output_result["snr_db"],
            "output_si_sdr_db": output_result["si_sdr_db"],
            "output_stoi": output_result["stoi"],
            "output_pesq_wb": output_result["pesq_wb"],
        })
        if i % 25 == 0 or i == len(rows):
            print(f"Evaluated {i}/{len(rows)}", flush=True)

    per_clip = out / "per_clip.csv"
    with per_clip.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)

    target_groups: dict[str, list[dict[str, object]]] = {}
    origin_groups: dict[str, list[dict[str, object]]] = {}
    input_snr_groups: dict[str, list[dict[str, object]]] = {}
    centers = [-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]
    edges = [-float("inf"), -7.5, -2.5, 2.5, 7.5, 12.5, 17.5, float("inf")]
    bin_labels = ["< -7.5", "[-7.5,-2.5)", "[-2.5,2.5)", "[2.5,7.5)", "[7.5,12.5)", "[12.5,17.5)", ">=17.5"]
    for row in result_rows:
        target_groups.setdefault(f"{float(row['target_snr_db']):g}", []).append(row)
        origin_groups.setdefault(str(row["origin"]), []).append(row)
        x = float(row["input_snr_db"])
        idx = min(max(int(np.searchsorted(edges, x, side="right") - 1), 0), 6)
        input_snr_groups.setdefault(bin_labels[idx], []).append(row)
    summary = {
        "status": "DEVELOPMENT_BENCHMARK_ONLY; not independent validation",
        "candidate": "DFN3 Step-500 checkpoint bytes with conv_lookahead=0 and df_lookahead=0",
        "checkpoint_sha256": checkpoint_hash,
        "canonical_manifest_sha256": manifest_hash,
        "clip_count": len(result_rows),
        "model_weights_changed": False,
        "training_performed": False,
        "metric_implementation": "unchanged scripts/evaluate_dfn3_canonical.py metrics/active_speech_power/enhance_one",
        "criteria": {"output_snr_db_gt": 15.0, "output_stoi_gt": 0.85, "output_pesq_wb_gt": 2.5},
        "overall": summarize(result_rows),
        "by_target_snr_db": {k: summarize(v) for k, v in sorted(target_groups.items(), key=lambda kv: float(kv[0]))},
        "by_measured_input_snr_db": {k: summarize(v) for k, v in input_snr_groups.items()},
        "input_snr_bin_edges_db": ["-inf", -7.5, -2.5, 2.5, 7.5, 12.5, 17.5, "+inf"],
        "by_manifest_origin": {k: summarize(v) for k, v in sorted(origin_groups.items())},
        "noise_type_limit": "Manifest provides EXISTING_PROXY and IoBT_GUNFIRE origin labels, not finer noise/event labels.",
        "float_prediction_files": len(list(pred_dir.glob("*.npy"))),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"WROTE={per_clip} {out / 'summary.json'}")


if __name__ == "__main__":
    main()
