#!/usr/bin/env python3
"""Export a separate zero-lookahead Step-500-weight DFN3 research candidate."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import shutil
import tarfile
import tempfile
import types
import sys
from pathlib import Path


EXPECTED_STEP500_SHA256 = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
EXPECTED_STEP500_ARCHIVE_SHA256 = "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d"
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


def extract_config(archive: Path) -> tuple[bytes, str]:
    with tarfile.open(archive, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name.endswith("config.ini")]
        if len(members) != 1:
            raise RuntimeError(f"Expected one config.ini in {archive}, got {len(members)}")
        raw = tf.extractfile(members[0]).read()
        return raw, members[0].name


def load_step500_state(path: Path):
    import torch

    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        state = state["model_state_dict"]
    if isinstance(state, dict) and state and all(k.startswith("model.") for k in list(state)[:3]):
        state = {k[len("model."):]: v for k, v in state.items()}
    if not isinstance(state, dict):
        raise TypeError("Step-500 artifact did not contain a state dictionary")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"),
    )
    parser.add_argument("--step500-archive", type=Path, default=Path("../models/dfn3_step500_tract.tar.gz"))
    parser.add_argument(
        "--canonical-manifest",
        type=Path,
        default=Path("runs/sih26052_canonical_validation/manifest.csv"),
    )
    parser.add_argument("--native-binary", type=Path, default=Path(
        "runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter"
    ))
    args = parser.parse_args()

    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing candidate output: {output}")
    checkpoint = args.checkpoint.expanduser().resolve()
    archive = args.step500_archive.expanduser().resolve()
    manifest = args.canonical_manifest.expanduser().resolve()
    binary = args.native_binary.expanduser().resolve()
    for p in (checkpoint, archive, manifest, binary):
        if not p.is_file():
            raise FileNotFoundError(p)

    hashes_before = {
        "step500_checkpoint": sha256(checkpoint),
        "step500_archive": sha256(archive),
        "canonical_manifest": sha256(manifest),
    }
    if hashes_before["step500_checkpoint"] != EXPECTED_STEP500_SHA256:
        raise RuntimeError("V10 R0 Step-500 checkpoint hash mismatch")
    if hashes_before["step500_archive"] != EXPECTED_STEP500_ARCHIVE_SHA256:
        raise RuntimeError("Protected Step-500 Tract archive hash mismatch")
    if hashes_before["canonical_manifest"] != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("Frozen canonical manifest hash mismatch")

    import torch
    install_torchaudio_shim()
    from df.config import DfParams
    from df.enhance import df_features, init_df

    raw_config, member_name = extract_config(archive)
    cfg = configparser.ConfigParser()
    cfg.read_string(raw_config.decode("utf-8"))
    original = {
        "conv_lookahead": cfg.get("deepfilternet", "conv_lookahead"),
        "df_lookahead": cfg.get("df", "df_lookahead"),
    }
    cfg.set("deepfilternet", "conv_lookahead", "0")
    cfg.set("df", "df_lookahead", "0")

    output.mkdir(parents=True)
    config_dir = output / "model_config"
    config_dir.mkdir()
    config_path = config_dir / "config.ini"
    with config_path.open("w", encoding="utf-8") as f:
        cfg.write(f)
    candidate_checkpoint = output / "causal_step500_weights.pt"
    shutil.copyfile(checkpoint, candidate_checkpoint)
    model, df_state, _ = init_df(
        str(config_dir), log_file=None, epoch="none", config_allow_defaults=True
    )
    model = model.cpu().eval()
    incompatible = model.load_state_dict(load_step500_state(candidate_checkpoint), strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError(f"Non-strict checkpoint load: {incompatible}")

    from df.deepfilternet3 import ModelParams
    p = ModelParams()
    if p.conv_lookahead != 0 or p.df_lookahead != 0:
        raise RuntimeError(
            f"Runtime config not causal: conv={p.conv_lookahead}, df={p.df_lookahead}"
        )

    onnx_dir = output / "onnx"
    onnx_dir.mkdir()
    sample = torch.zeros(1, p.hop_size, dtype=torch.float32)
    _, feat_erb, feat_spec = df_features(sample, df_state, p.nb_df, device="cpu")
    feat_spec_enc = feat_spec.transpose(1, 4).squeeze(4)
    with torch.no_grad():
        e0, e1, e2, e3, emb, c0, _ = model.enc(feat_erb, feat_spec_enc)

    def export(path, module, inputs, input_names, output_names, dynamic_axes):
        torch.onnx.export(
            module.eval(),
            inputs,
            str(path),
            input_names=input_names,
            output_names=output_names,
            dynamic_axes=dynamic_axes,
            opset_version=12,
            export_params=True,
            do_constant_folding=False,
            keep_initializers_as_inputs=False,
            dynamo=False,
        )

    export(
        onnx_dir / "enc.onnx",
        model.enc,
        (feat_erb, feat_spec_enc),
        ["feat_erb", "feat_spec"],
        ["e0", "e1", "e2", "e3", "emb", "c0", "lsnr"],
        {
            "feat_erb": {2: "S"}, "feat_spec": {2: "S"},
            "e0": {2: "S"}, "e1": {2: "S"}, "e2": {2: "S"}, "e3": {2: "S"},
            "emb": {1: "S"}, "c0": {2: "S"}, "lsnr": {1: "S"},
        },
    )
    with torch.no_grad():
        _ = model.erb_dec(emb, e3, e2, e1, e0)
    export(
        onnx_dir / "erb_dec.onnx",
        model.erb_dec,
        (emb.clone(), e3, e2, e1, e0),
        ["emb", "e3", "e2", "e1", "e0"],
        ["m"],
        {"emb": {1: "S"}, "e3": {2: "S"}, "e2": {2: "S"}, "e1": {2: "S"}, "e0": {2: "S"}, "m": {2: "S"}},
    )
    with torch.no_grad():
        _ = model.df_dec(emb, c0)
    export(
        onnx_dir / "df_dec.onnx",
        model.df_dec,
        (emb.clone(), c0),
        ["emb", "c0"],
        ["coefs"],
        {"emb": {1: "S"}, "c0": {2: "S"}, "coefs": {1: "S"}},
    )

    import onnx
    for name in ("enc.onnx", "erb_dec.onnx", "df_dec.onnx"):
        graph = onnx.load(onnx_dir / name)
        onnx.checker.check_model(graph)

    model_archive = output / "causal_step500_tract.tar.gz"
    with tarfile.open(model_archive, "w:gz") as tf:
        for pth in (onnx_dir / "enc.onnx", onnx_dir / "erb_dec.onnx", onnx_dir / "df_dec.onnx", config_path):
            arcname = f"tmp/export/{pth.name}"
            tf.add(pth, arcname=arcname)

    metadata = {
        "candidate": "DFN3 Step-500 weights with zero-lookahead configuration; research-only",
        "model_weights_changed": False,
        "training_performed": False,
        "lookahead_before": original,
        "lookahead_after": {"conv_lookahead": p.conv_lookahead, "df_lookahead": p.df_lookahead},
        "sampling_rate_hz": p.sr,
        "hop_size_samples": p.hop_size,
        "hop_duration_ms": 1000.0 * p.hop_size / p.sr,
        "fft_size_samples": p.fft_size,
        "parameter_count": sum(x.numel() for x in model.parameters()),
        "checkpoint_source": str(checkpoint),
        "checkpoint_source_sha256": hashes_before["step500_checkpoint"],
        "candidate_checkpoint_sha256": sha256(candidate_checkpoint),
        "step500_archive_source": str(archive),
        "step500_archive_sha256": hashes_before["step500_archive"],
        "source_config_member": member_name,
        "source_config_sha256": hashlib.sha256(raw_config).hexdigest(),
        "candidate_config_sha256": sha256(config_path),
        "candidate_tract_archive_sha256": sha256(model_archive),
        "canonical_manifest_sha256": hashes_before["canonical_manifest"],
        "native_binary_sha256": sha256(binary),
        "host_platform": sys.platform,
        "torch_version": torch.__version__,
        "onnx_version": onnx.__version__,
        "onnx_files": {n: sha256(onnx_dir / n) for n in ("enc.onnx", "erb_dec.onnx", "df_dec.onnx")},
        "strict_state_dict_load": "PASS",
        "onnx_checkers": "PASS",
        "physical_pi_measurement": False,
    }
    metadata_path = output / "export_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    hashes_after = {
        "step500_checkpoint": sha256(checkpoint),
        "step500_archive": sha256(archive),
        "canonical_manifest": sha256(manifest),
    }
    if hashes_after != hashes_before:
        raise RuntimeError(f"Protected hashes changed: before={hashes_before}, after={hashes_after}")
    print(json.dumps(metadata, indent=2))
    print("PROTECTED_HASHES_UNCHANGED=PASS")


if __name__ == "__main__":
    main()
