#!/usr/bin/env python3
"""
Custom DFN3 ONNX export for Tract streaming inference.
- Forces torch.onnx old tracing path (dynamo=False / opset_version=12)
- Exports with T=1 single-frame inputs (streaming mode)
- Preserves dynamic S axis so Tract can build a pulse model
- Loads fine-tuned checkpoint
"""
import sys, types, os, tarfile, shutil
from copy import deepcopy
from pathlib import Path

# ── torchaudio shim ──────────────────────────────────────────────────
import torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        def __init__(self, sr, nf, nc, bps, enc):
            self.sample_rate=sr; self.num_frames=nf
            self.num_channels=nc; self.bits_per_sample=bps; self.encoding=enc
    cm.AudioMetaData = AudioMetaData
    sys.modules["torchaudio.backend.common"] = cm
    if not hasattr(torchaudio, "backend"):
        bm = types.ModuleType("torchaudio.backend")
        bm.common = cm
        sys.modules["torchaudio.backend"] = bm
        torchaudio.backend = bm
    else:
        torchaudio.backend.common = cm

import torch
import numpy as np
from df.enhance import init_df, df_features
from df.config import DfParams as ModelParams

CKPT = os.path.expanduser("~/.cache/DeepFilterNet/DeepFilterNet3/checkpoints/model_120.ckpt.best")
EXPORT_DIR = os.path.expanduser("~/sih26052_edge/models/onnx_tract/")
TAR_OUT    = os.path.expanduser("~/sih26052_edge/models/dfn3_finetuned_tract.tar.gz")
CONFIG_SRC = os.path.expanduser("~/.cache/DeepFilterNet/DeepFilterNet3/config.ini")

os.makedirs(EXPORT_DIR, exist_ok=True)

# ── Load fine-tuned model ────────────────────────────────────────────
print("Loading model + fine-tuned checkpoint...")
model, df_state, _ = init_df("DeepFilterNet3", log_level="WARNING")
ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
state_dict = ckpt.get("model_state_dict", ckpt)
if all(k.startswith("model.") for k in list(state_dict.keys())[:3]):
    state_dict = {k[len("model."):]: v for k, v in state_dict.items()}
model.load_state_dict(state_dict, strict=True)
model.eval()
print("Checkpoint loaded.")

p = ModelParams()
OPSET = 12   # Use opset 12 — forces old tracing path in torch 2.x

def export_onnx(path, module, inputs, input_names, output_names, dynamic_axes):
    """Export using old tracing path (dynamo=False where supported, opset<=16)."""
    module = deepcopy(module).eval()
    kw = dict(
        model=module,
        args=inputs,
        f=path,
        input_names=input_names,
        output_names=output_names,
        dynamic_axes=dynamic_axes,
        opset_version=OPSET,
        export_params=True,
        do_constant_folding=False,   # CRITICAL: don't fold constants so dynamic dims survive
        keep_initializers_as_inputs=False,
    )
    # Try dynamo=False first (available from torch 2.1+)
    try:
        torch.onnx.export(**kw, dynamo=False)
    except TypeError:
        torch.onnx.export(**kw)
    print(f"  Exported: {path}")

# ── Build T=1 example inputs ─────────────────────────────────────────
# audio is 1 frame = 480 samples
audio_1frame = torch.randn(1, p.hop_size)
spec_1frame, feat_erb_1, feat_spec_1 = df_features(audio_1frame, df_state, p.nb_df, device="cpu")
# feat_erb_1:  [1, 1, 1, nb_erb]  (B, C, T=1, E)
# feat_spec_1: [1, 1, 1, nb_df, 2] (B, C, T=1, F, ri)
print(f"feat_erb shape: {feat_erb_1.shape}")
print(f"feat_spec shape: {feat_spec_1.shape}")

# Encoder input needs feat_spec transposed: [B, ri, T, F] → [B, 2, T, nb_df]
feat_spec_enc = feat_spec_1.transpose(1, 4).squeeze(4)  # [1, 2, 1, 96]

# ── Export encoder ───────────────────────────────────────────────────
print("\n[1/3] Exporting enc.onnx...")
with torch.no_grad():
    e0, e1, e2, e3, emb, c0, lsnr = model.enc(feat_erb_1, feat_spec_enc)

print(f"  e0={e0.shape} e1={e1.shape} e2={e2.shape} e3={e3.shape}")
print(f"  emb={emb.shape} c0={c0.shape} lsnr={lsnr.shape}")

export_onnx(
    path=os.path.join(EXPORT_DIR, "enc.onnx"),
    module=model.enc,
    inputs=(feat_erb_1, feat_spec_enc),
    input_names=["feat_erb", "feat_spec"],
    output_names=["e0", "e1", "e2", "e3", "emb", "c0", "lsnr"],
    dynamic_axes={
        "feat_erb":  {2: "S"},
        "feat_spec": {2: "S"},
        "e0":  {2: "S"},
        "e1":  {2: "S"},
        "e2":  {2: "S"},
        "e3":  {2: "S"},
        "emb": {1: "S"},
        "c0":  {2: "S"},
        "lsnr":{1: "S"},
    },
)

# ── Export ERB decoder ───────────────────────────────────────────────
print("\n[2/3] Exporting erb_dec.onnx...")
with torch.no_grad():
    m_mask = model.erb_dec(emb, e3, e2, e1, e0)
print(f"  m_mask={m_mask.shape}")

export_onnx(
    path=os.path.join(EXPORT_DIR, "erb_dec.onnx"),
    module=model.erb_dec,
    inputs=(emb.clone(), e3, e2, e1, e0),
    input_names=["emb", "e3", "e2", "e1", "e0"],
    output_names=["m"],
    dynamic_axes={
        "emb": {1: "S"},
        "e3":  {2: "S"},
        "e2":  {2: "S"},
        "e1":  {2: "S"},
        "e0":  {2: "S"},
        "m":   {2: "S"},
    },
)

# ── Export DF decoder ────────────────────────────────────────────────
print("\n[3/3] Exporting df_dec.onnx...")
with torch.no_grad():
    coefs = model.df_dec(emb, c0)
print(f"  coefs={coefs.shape}")

export_onnx(
    path=os.path.join(EXPORT_DIR, "df_dec.onnx"),
    module=model.df_dec,
    inputs=(emb.clone(), c0),
    input_names=["emb", "c0"],
    output_names=["coefs"],
    dynamic_axes={
        "emb":   {1: "S"},
        "c0":    {2: "S"},
        "coefs": {1: "S"},
    },
)

# ── Copy config.ini ──────────────────────────────────────────────────
shutil.copy(CONFIG_SRC, os.path.join(EXPORT_DIR, "config.ini"))
print(f"\nCopied: {CONFIG_SRC}")

# ── Verify dynamic axes in exported files ────────────────────────────
import onnx
print("\n── Shape verification ──")
for fname in ["enc.onnx", "erb_dec.onnx", "df_dec.onnx"]:
    fpath = os.path.join(EXPORT_DIR, fname)
    m_onnx = onnx.load(fpath)
    print(f"{fname}:")
    for inp in m_onnx.graph.input:
        dims = [d.dim_value if d.HasField("dim_value") else d.dim_param
                for d in inp.type.tensor_type.shape.dim]
        print(f"  {inp.name}: {dims}")

# ── Pack tar.gz with tmp/export/ prefix (Tract path convention) ──────
print(f"\nPacking: {TAR_OUT}")
with tarfile.open(TAR_OUT, "w:gz") as tf:
    for fname in ["enc.onnx", "erb_dec.onnx", "df_dec.onnx", "config.ini"]:
        fpath = os.path.join(EXPORT_DIR, fname)
        tf.add(fpath, arcname=f"tmp/export/{fname}")

import hashlib
sha256 = hashlib.sha256(open(TAR_OUT, "rb").read()).hexdigest()
print(f"SHA256: {sha256}")
print(f"Size:   {os.path.getsize(TAR_OUT) / 1024 / 1024:.2f} MB")
print(f"\nDone. Use:")
print(f"  deep-filter --model {TAR_OUT} ...")
