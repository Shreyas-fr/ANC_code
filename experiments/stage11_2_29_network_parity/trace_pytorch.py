#!/usr/bin/env python3
"""Run protected Step-500 PyTorch network on frozen Stage 11.2.28 features."""
from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
STAGE28 = ROOT / "runs/stage11_2_28_frontend_parity_20261114"
OUT = ROOT / "runs/stage11_2_29_network_parity_20261114/pytorch"
SRC = STAGE28 / "DeepFilterNet/DeepFilterNet"
CKPT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"

# The Python 3.14 libdf extension is known to segfault on construction. Model
# graph construction only needs libdf's initialization helper and ERB widths;
# all runtime input features below came from the independently verified 0.5.6
# binding and are passed through unchanged.
libdf_stub = types.ModuleType("libdf")
def unit_norm_init(n):
    return np.ones(n, dtype=np.float32)
class DF:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("libdf DF constructor intentionally unavailable in this trace")
libdf_stub.unit_norm_init = unit_norm_init
libdf_stub.DF = DF
sys.modules["libdf"] = libdf_stub
sys.path.insert(0, str(SRC))
df_pkg = types.ModuleType("df")
df_pkg.__path__ = [str(SRC / "df")]
sys.modules["df"] = df_pkg

from df.config import config
from df.deepfilternet3 import DfNet
from df.modules import erb_fb
from df.utils import as_real

config.load(str(STAGE28 / "config.ini"), config_must_exist=True)
device = torch.device("cpu")
widths = np.array([1,1,1,1,1,1,2,2,2,3,3,4,4,5,5,7,7,8,10,12,13,15,18,20,24,28,31,37,42,50,56,67], dtype=np.int64)
erb = erb_fb(widths, 48000, inverse=False)
erb_inverse = erb_fb(widths, 48000, inverse=True)
model = DfNet(erb, erb_inverse).to(device)
state = torch.load(CKPT, map_location="cpu", weights_only=True)
missing, unexpected = model.load_state_dict(state, strict=True)
assert not missing and not unexpected
model.eval()

OUT.mkdir(parents=True, exist_ok=True)
inputs = STAGE28 / "python_features_py310"
records = []
for idx in (6, 93, 287):
    spec_np = np.fromfile(inputs / f"{idx:04d}_stft.f32", dtype=np.complex64).reshape(1,300,481)
    erb_np = np.fromfile(inputs / f"{idx:04d}_erb_features.f32", dtype="<f4").reshape(1,300,32)
    cplx_np = np.fromfile(inputs / f"{idx:04d}_complex_features.f32", dtype=np.complex64).reshape(1,300,96)
    spec = as_real(torch.from_numpy(spec_np).unsqueeze(1)).to(device)
    feat_erb = torch.from_numpy(erb_np).unsqueeze(1).to(device)
    feat_spec = as_real(torch.from_numpy(cplx_np).unsqueeze(1)).to(device)
    hooked = {}
    def capture(name):
        def hook(module, args, output):
            hooked[name] = output
        return hook
    handles = [model.enc.register_forward_hook(capture("enc")),
               model.erb_dec.register_forward_hook(capture("erb_dec")),
               model.df_dec.register_forward_hook(capture("df_dec"))]
    with torch.inference_mode():
        spec_e, mask, lsnr, coefs = model(spec, feat_erb, feat_spec)
    for h in handles: h.remove()
    arrays = {"spec_e": spec_e.cpu().numpy(), "mask": mask.cpu().numpy(),
              "lsnr": lsnr.cpu().numpy(), "coefs": coefs.cpu().numpy()}
    for name, arr in arrays.items():
        path = OUT / f"{idx:04d}_{name}.npy"
        np.save(path, arr)
        if not np.isfinite(arr).all():
            raise ValueError(f"non-finite {idx}/{name}")
    for module_name, output in hooked.items():
        values = output if isinstance(output, (tuple, list)) else (output,)
        for j, value in enumerate(values):
            arr=value.detach().cpu().numpy()
            np.save(OUT / f"{idx:04d}_{module_name}_{j}.npy", arr)
    records.append({"id":idx, "outputs": {k:{"shape":list(v.shape),"dtype":str(v.dtype),"sha256":hashlib.sha256((OUT/f"{idx:04d}_{k}.npy").read_bytes()).hexdigest()} for k,v in arrays.items()}})
    print(idx, {k: (v.shape, float(np.max(np.abs(v)))) for k,v in arrays.items()})

manifest = {"checkpoint":str(CKPT.relative_to(ROOT)), "checkpoint_sha256":hashlib.sha256(CKPT.read_bytes()).hexdigest(),
            "config":"Stage 11.2.28 pinned config.ini", "pytorch":torch.__version__, "device":"cpu",
            "strict_state_dict_load":True, "libdf_runtime":"not called; reused verified 0.5.6 feature arrays",
            "ids":records, "gold_accessed":False}
(OUT / "metadata.json").write_text(json.dumps(manifest,indent=2)+"\n")
