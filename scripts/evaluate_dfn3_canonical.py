#!/usr/bin/env python3
"""Evaluate a DeepFilterNet3 checkpoint on the frozen SIH 590-clip benchmark.

Each clip gets a fresh libDF feature-extractor state. This avoids cross-clip
state leakage and keeps model selection away from the separate SIH gold set.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import scipy.signal
import soundfile as sf
import torch


def install_torchaudio_compat_shim() -> None:
    """Support torchaudio builds where df.io imports the removed backend path."""
    try:
        import torchaudio
    except ImportError:
        return
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_non_gold_canonical_dir(path: Path) -> Path:
    """Resolve a validation directory and refuse the held-out gold tree."""
    resolved = path.expanduser().resolve()
    if any(part.casefold() == "sih_gold_test" for part in resolved.parts):
        raise SystemExit(
            f"Refusing to evaluate on SIH gold holdout: {resolved}. "
            "Use the frozen 590-clip canonical validation directory."
        )
    return resolved


def active_speech_power(clean: np.ndarray, sample_rate: int = 16000) -> float:
    frame = sample_rate * 30 // 1000
    usable = len(clean) // frame * frame
    if usable == 0:
        return float(np.mean(clean.astype(np.float64) ** 2))
    frames = clean[:usable].astype(np.float64).reshape(-1, frame)
    powers = np.mean(frames**2, axis=1)
    threshold = float(np.max(powers)) * 0.001
    active = powers[powers > threshold]
    return float(np.mean(active)) if active.size else float(np.mean(powers))


def metrics(clean: np.ndarray, estimate: np.ndarray) -> dict[str, float]:
    from pesq import pesq
    from pystoi import stoi

    n = min(len(clean), len(estimate))
    clean = np.asarray(clean[:n], dtype=np.float32)
    estimate = np.asarray(estimate[:n], dtype=np.float32)
    error = estimate.astype(np.float64) - clean.astype(np.float64)
    speech_power = active_speech_power(clean)
    err_power = float(np.mean(error**2))
    centered_ref = clean.astype(np.float64) - float(np.mean(clean))
    centered_est = estimate.astype(np.float64) - float(np.mean(estimate))
    scale = float(np.dot(centered_est, centered_ref) / (np.dot(centered_ref, centered_ref) + 1e-12))
    target = scale * centered_ref
    residual = centered_est - target
    sisdr = 10.0 * np.log10((np.dot(target, target) + 1e-12) / (np.dot(residual, residual) + 1e-12))
    clean_peak = float(np.max(np.abs(clean)))
    estimate_peak = float(np.max(np.abs(estimate)))
    clean_norm = clean / max(clean_peak, 1e-8)
    estimate_norm = estimate / max(estimate_peak, 1e-8)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            stoi_value = float(stoi(clean_norm, estimate_norm, 16000, extended=False))
    except Exception:
        stoi_value = float("nan")
    try:
        pesq_value = float(pesq(16000, clean_norm, estimate_norm, "wb"))
    except Exception:
        pesq_value = float("nan")
    return {
        "snr_db": float(10.0 * np.log10((speech_power + 1e-12) / (err_power + 1e-12))),
        "si_sdr_db": float(sisdr),
        "stoi": stoi_value,
        "pesq_wb": pesq_value,
    }


def load_checkpoint(path: Path):
    install_torchaudio_compat_shim()
    import hk
    from df.enhance import init_df, maybe_download_model

    base = maybe_download_model("DeepFilterNet3")
    model, df_state, _ = init_df(base, log_file=None)
    model = model.cpu().eval()
    # The Kaggle artifact uses the ``.hk`` suffix but is serialized as a
    # PyTorch zip checkpoint (``PK\x03\x04``), not the unrelated HK container
    # handled by the similarly named Hugging Face package installed in some
    # environments. Accept a true HK mapping when available, then fall back to
    # PyTorch's weights-only loader for the project artifact format.
    try:
        state = hk.load_file(str(path))
    except (ValueError, OSError, EOFError):
        state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        state = state["model_state_dict"]
    model.load_state_dict(state, strict=True)
    return model, df_state


def enhance_one(
    model,
    df_state,
    noisy_16k: np.ndarray,
    atten_lim_db: float | None = None,
    post_gain_db: float = 0.0,
) -> np.ndarray:
    from df.enhance import enhance

    # Explicit reset is supported by libDF and gives each clip independent
    # running normalization statistics.
    df_state.reset()
    noisy_48k = scipy.signal.resample_poly(noisy_16k, 3, 1).astype(np.float32)
    with torch.inference_mode():
        output_48k = enhance(
            model,
            df_state,
            torch.from_numpy(noisy_48k).unsqueeze(0),
            atten_lim_db=atten_lim_db,
        )
    output_16k = scipy.signal.resample_poly(output_48k.squeeze(0).cpu().numpy(), 1, 3).astype(np.float32)
    output_16k *= np.float32(10.0 ** (post_gain_db / 20.0))
    if len(output_16k) < len(noisy_16k):
        output_16k = np.pad(output_16k, (0, len(noisy_16k) - len(output_16k)))
    return output_16k[: len(noisy_16k)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True, help="Strict-loadable DeepFilterNet3 .hk checkpoint")
    parser.add_argument("--canonical-dir", type=Path, default=Path("runs/sih26052_canonical_validation"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/sih26052_dfn3_canonical"))
    parser.add_argument(
        "--atten-lim-db",
        type=float,
        default=None,
        help="Optional DeepFilterNet attenuation limit; report the value in the output summary.",
    )
    parser.add_argument(
        "--post-gain-db",
        type=float,
        default=0.0,
        help="Optional constant output gain in dB, applied before metric calculation.",
    )
    args = parser.parse_args()

    args.canonical_dir = require_non_gold_canonical_dir(args.canonical_dir)
    manifest = args.canonical_dir / "manifest.csv"
    rows = list(csv.DictReader(manifest.open(newline="")))
    if len(rows) != 590:
        raise SystemExit(f"Expected frozen 590-clip canonical manifest, found {len(rows)}")
    model, df_state = load_checkpoint(args.checkpoint)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    output_rows: list[dict[str, object]] = []
    for i, row in enumerate(rows, 1):
        index = int(row["val_index"])
        clean, clean_sr = sf.read(args.canonical_dir / "clean_audio" / f"{index:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(args.canonical_dir / "noisy_audio" / f"{index:04d}_noisy.wav", dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.ndim != 1 or noisy.ndim != 1:
            raise ValueError(f"Clip {index} violates canonical mono 16 kHz waveform contract")
        if len(clean) != len(noisy) or not np.isfinite(clean).all() or not np.isfinite(noisy).all():
            raise ValueError(f"Clip {index} has invalid or misaligned audio")

        input_metrics = metrics(clean, noisy)
        enhanced = enhance_one(
            model,
            df_state,
            noisy,
            atten_lim_db=args.atten_lim_db,
            post_gain_db=args.post_gain_db,
        )
        output_metrics = metrics(clean, enhanced)
        output_rows.append({
            "val_index": index,
            "origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_metrics["snr_db"],
            **{f"input_{k}": v for k, v in input_metrics.items() if k != "snr_db"},
            **{f"output_{k}": v for k, v in output_metrics.items()},
        })
        if i % 25 == 0 or i == len(rows):
            print(f"Evaluated {i}/{len(rows)}", flush=True)

    per_clip = args.output_dir / "per_clip.csv"
    with per_clip.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    strata: dict[str, list[dict[str, object]]] = {}
    for result in output_rows:
        key = f"{float(result['target_snr_db']):g}"
        strata.setdefault(key, []).append(result)
    summary: dict[str, object] = {
        "checkpoint": str(args.checkpoint.resolve()),
        "checkpoint_sha256": sha256(args.checkpoint),
        "canonical_manifest_sha256": sha256(manifest),
        "atten_lim_db": args.atten_lim_db,
        "post_gain_db": args.post_gain_db,
        "count": len(output_rows),
        "criteria": {"output_snr_db_gt": 15.0, "stoi_gt": 0.85, "pesq_wb_gt": 2.5},
        "overall": {},
        "strata": {},
    }
    metric_names = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    for label, selected in [("all", output_rows), *sorted(strata.items(), key=lambda item: float(item[0]))]:
        data = {name: np.asarray([r[f"output_{name}"] for r in selected], dtype=float) for name in metric_names}
        summary_block = {
            name: float(np.nanmean(values)) if np.isfinite(values).any() else float("nan")
            for name, values in data.items()
        }
        summary_block["count"] = len(selected)
        valid_snr = np.isfinite(data["snr_db"])
        valid_stoi = np.isfinite(data["stoi"])
        valid_pesq = np.isfinite(data["pesq_wb"])
        valid_all = valid_snr & valid_stoi & valid_pesq
        summary_block["pass_rate"] = {
            "snr_gt_15_db": float(np.mean(data["snr_db"][valid_snr] > 15.0)) if valid_snr.any() else float("nan"),
            "stoi_gt_0_85": float(np.mean(data["stoi"][valid_stoi] > 0.85)) if valid_stoi.any() else float("nan"),
            "pesq_gt_2_5": float(np.mean(data["pesq_wb"][valid_pesq] > 2.5)) if valid_pesq.any() else float("nan"),
            "all_three": float(np.mean((data["snr_db"][valid_all] > 15.0) & (data["stoi"][valid_all] > 0.85) & (data["pesq_wb"][valid_all] > 2.5))) if valid_all.any() else float("nan"),
            "valid_counts": {"snr": int(valid_snr.sum()), "stoi": int(valid_stoi.sum()), "pesq": int(valid_pesq.sum()), "all_three": int(valid_all.sum())},
        }
        summary["overall" if label == "all" else "strata"][label if label != "all" else "mean"] = summary_block

    output_json = args.output_dir / "summary.json"
    output_json.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {per_clip} and {output_json}")


if __name__ == "__main__":
    main()
