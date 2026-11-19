#!/usr/bin/env python3
"""Read-only waveform compatibility audit for the three saved Stage 8 models.

Checks file/hash/ID/audio metadata and bounded pairwise cross-correlation. It
does not write to or alter any prediction, checkpoint, manifest, or baseline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
EXPECTED_IDS = list(range(590))
SAMPLE_RATE = 16000
SAMPLE_COUNT = 48000
MAX_LAG = 2048  # 128 ms either side
FFT_SIZE = 131072  # >= 2 * 48000 - 1, so the correlation is linear, not aliased


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def get_layouts():
    return {
        "step500": {
            "dir": ROOT / "runs/stage8_ensemble_20261113/step500_predictions",
            "ledger": ROOT / "runs/stage8_ensemble_20261113/step500_predictions/prediction_files.csv",
            "hash_field": "sha256",
            "audio_pattern": "{id:04d}_enhanced.wav",
        },
        "fullsubnet": {
            "dir": ROOT / "runs/stage8_ensemble_20261113/fullsubnet_predictions",
            "ledger": ROOT / "runs/stage8_ensemble_20261113/fullsubnet_predictions/prediction_files.csv",
            "hash_field": "sha256",
            "audio_pattern": "{id:04d}_enhanced.wav",
        },
        "gtcrn": {
            "dir": ROOT / "runs/gtcrn_dns3_canonical_20261113/predictions",
            "ledger": ROOT / "runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv",
            "hash_field": "output_sha256",
            "audio_pattern": "{id:04d}_enhanced.wav",
        },
        "noisy": {
            "dir": ROOT / "runs/sih26052_canonical_validation/noisy_audio",
            "ledger": None,
            "hash_field": None,
            "audio_pattern": "{id:04d}_noisy.wav",
        },
    }


def read_audio(name: str, clip_id: int, layouts: dict):
    spec = layouts[name]
    path = spec["dir"] / spec["audio_pattern"].format(id=clip_id)
    info = sf.info(path)
    audio, sample_rate = sf.read(path, dtype="float32")
    if sample_rate != SAMPLE_RATE or info.channels != 1 or len(audio) != SAMPLE_COUNT:
        raise ValueError(f"{name} clip {clip_id} audio contract mismatch: {info}")
    if audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError(f"{name} clip {clip_id} is not finite mono audio")
    return path, info, audio


def normalized_correlation(x: np.ndarray, y: np.ndarray):
    """Return bounded lag of x relative to y, best signed correlation, zero-lag correlation."""
    x = x.astype(np.float64, copy=False)
    y = y.astype(np.float64, copy=False)
    x = x - x.mean()
    y = y - y.mean()
    denominator = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denominator == 0:
        return 0, 0.0, 0.0
    corr = np.fft.irfft(np.fft.rfft(x, n=FFT_SIZE) * np.conj(np.fft.rfft(y, n=FFT_SIZE)), n=FFT_SIZE)
    # Negative lags are stored at the end of circular storage. FFT_SIZE is
    # long enough for the complete linear correlation, so these are not aliases.
    bounded = np.concatenate((corr[-MAX_LAG:], corr[: MAX_LAG + 1])) / denominator
    position = int(np.argmax(np.abs(bounded)))
    lag = position - MAX_LAG
    return lag, float(bounded[position]), float(bounded[MAX_LAG])


def quantiles(values):
    return [float(np.percentile(values, p)) for p in (1, 50, 99)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runs/stage8_ensemble_20261113/phase_b_alignment",
    )
    args = parser.parse_args()

    manifest = ROOT / "runs/sih26052_canonical_validation/manifest.csv"
    if sha256(manifest) != MANIFEST_SHA256:
        raise SystemExit("Frozen canonical manifest hash mismatch")
    manifest_rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    ids = [int(row["val_index"]) for row in manifest_rows]
    if ids != EXPECTED_IDS:
        raise SystemExit("Canonical manifest ID sequence mismatch")

    layouts = get_layouts()
    ledger_maps = {}
    for name, spec in layouts.items():
        ledger = spec["ledger"]
        if ledger is None:
            continue
        ledger_maps[name] = {
            int(row["val_index"]): row
            for row in csv.DictReader(ledger.open(newline="", encoding="utf-8"))
        }
        if set(ledger_maps[name]) != set(EXPECTED_IDS):
            raise SystemExit(f"{name} per-file ledger does not cover canonical IDs")

    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing audit output directory: {output_dir}")
    output_dir.mkdir(parents=True)

    models = ("step500", "fullsubnet", "gtcrn")
    model_rms = {name: [] for name in (*models, "noisy")}
    model_peaks = {name: [] for name in (*models, "noisy")}
    model_audio_info = {name: {"subtypes": {}, "hashes_verified": 0} for name in (*models, "noisy")}
    pair_rows = []
    pairs = [("step500", "fullsubnet"), ("step500", "gtcrn"), ("fullsubnet", "gtcrn"),
             ("step500", "noisy"), ("fullsubnet", "noisy"), ("gtcrn", "noisy")]

    for clip_id in EXPECTED_IDS:
        clip_audio = {}
        for name in (*models, "noisy"):
            path, info, audio = read_audio(name, clip_id, layouts)
            model_audio_info[name]["subtypes"][info.subtype] = model_audio_info[name]["subtypes"].get(info.subtype, 0) + 1
            model_rms[name].append(float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))))
            model_peaks[name].append(float(np.max(np.abs(audio))))
            if name in ledger_maps:
                record = ledger_maps[name][clip_id]
                actual = sha256(path)
                if actual != record[layouts[name]["hash_field"]]:
                    raise ValueError(f"{name} clip {clip_id} file hash differs from its inference ledger")
                model_audio_info[name]["hashes_verified"] += 1
            clip_audio[name] = audio

        for first, second in pairs:
            lag, corr_best, corr_zero = normalized_correlation(clip_audio[first], clip_audio[second])
            pair_rows.append({
                "val_index": clip_id,
                "first_signal": first,
                "second_signal": second,
                "best_lag_samples_first_relative_to_second": lag,
                "best_lag_ms": lag * 1000.0 / SAMPLE_RATE,
                "best_signed_normalized_correlation": corr_best,
                "zero_lag_normalized_correlation": corr_zero,
            })
        if (clip_id + 1) % 100 == 0 or clip_id == 589:
            print(f"Audited {clip_id + 1}/590 canonical clips", flush=True)

    metric_rows = output_dir / "pairwise_waveform_alignment.csv"
    with metric_rows.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pair_rows[0]))
        writer.writeheader()
        writer.writerows(pair_rows)

    summary = {
        "manifest_sha256": sha256(manifest),
        "manifest_count": len(ids),
        "canonical_ids": {"count": len(ids), "first": ids[0], "last": ids[-1], "sequence_exact": ids == EXPECTED_IDS},
        "audio_contract": {"sample_rate_hz": SAMPLE_RATE, "channels": 1, "sample_count": SAMPLE_COUNT, "duration_seconds": SAMPLE_COUNT / SAMPLE_RATE},
        "search": {"method": "zero-mean normalized full-signal linear cross-correlation via NumPy FFT", "fft_size": FFT_SIZE, "lag_bound_samples": MAX_LAG, "lag_bound_ms": MAX_LAG * 1000.0 / SAMPLE_RATE, "lag_sign": "positive lag means first signal is delayed relative to second"},
        "file_sets": {},
        "amplitude": {},
        "pairwise_correlations": {},
        "details_csv": str(metric_rows),
        "interpretation_limit": "A cross-correlation peak is a diagnostic, not proof that differently enhanced waveforms should be mixed. Weak or boundary peaks are marked ambiguous.",
    }
    for name, spec in layouts.items():
        if name == "noisy":
            actual_files = sorted(spec["dir"].glob("*_noisy.wav"))
        else:
            actual_files = sorted(spec["dir"].glob("*_enhanced.wav"))
        summary["file_sets"][name] = {
            "directory": str(spec["dir"]),
            "file_count": len(actual_files),
            "id_mapping_exact_0_to_589": len(actual_files) == 590,
            "format_subtype_counts": model_audio_info[name]["subtypes"],
            "verified_hash_count": model_audio_info[name]["hashes_verified"],
        }
    noisy_rms = np.asarray(model_rms["noisy"])
    for name, rms_values in model_rms.items():
        rms = np.asarray(rms_values)
        peaks = np.asarray(model_peaks[name])
        item = {
            "rms_p01_p50_p99": quantiles(rms),
            "peak_abs_p01_p50_p99": quantiles(peaks),
            "peak_abs_max": float(peaks.max()),
            "peak_abs_ge_0_999_count": int(np.count_nonzero(peaks >= 0.999)),
            "peak_abs_gt_1_count": int(np.count_nonzero(peaks > 1.0)),
        }
        if name != "noisy":
            ratios = rms / noisy_rms
            item["rms_ratio_to_noisy_p01_p50_p99"] = quantiles(ratios)
            item["rms_ratio_to_noisy_min_max"] = [float(ratios.min()), float(ratios.max())]
        summary["amplitude"][name] = item
    for first, second in pairs:
        selected = [row for row in pair_rows if row["first_signal"] == first and row["second_signal"] == second]
        lag = np.asarray([row["best_lag_samples_first_relative_to_second"] for row in selected], dtype=np.int64)
        best = np.asarray([row["best_signed_normalized_correlation"] for row in selected], dtype=np.float64)
        zero = np.asarray([row["zero_lag_normalized_correlation"] for row in selected], dtype=np.float64)
        summary["pairwise_correlations"][f"{first}_vs_{second}"] = {
            "count": len(selected),
            "best_lag_zero_count": int(np.count_nonzero(lag == 0)),
            "best_lag_within_1_sample_count": int(np.count_nonzero(np.abs(lag) <= 1)),
            "best_lag_within_16_samples_count": int(np.count_nonzero(np.abs(lag) <= 16)),
            "best_lag_samples_min_max": [int(lag.min()), int(lag.max())],
            "best_lag_samples_p01_p50_p99": quantiles(lag),
            "best_lag_ms_p01_p50_p99": quantiles(lag * (1000.0 / SAMPLE_RATE)),
            "best_abs_correlation_p01_p50_p99": quantiles(np.abs(best)),
            "zero_lag_correlation_p01_p50_p99": quantiles(zero),
            "negative_best_correlation_count": int(np.count_nonzero(best < 0)),
            "negative_zero_lag_correlation_count": int(np.count_nonzero(zero < 0)),
            "nonzero_lag_clip_ids": [int(row["val_index"]) for row in selected if row["best_lag_samples_first_relative_to_second"] != 0],
        }

    (output_dir / "alignment_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "file_sets": summary["file_sets"], "pairwise_correlations": summary["pairwise_correlations"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
