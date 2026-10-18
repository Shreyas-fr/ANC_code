import sys, types
import torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    cm.AudioMetaData = type("AudioMetaData", (), {})
    sys.modules["torchaudio.backend.common"] = cm
    if not hasattr(torchaudio, "backend"):
        bm = types.ModuleType("torchaudio.backend")
        bm.common = cm
        sys.modules["torchaudio.backend"] = bm
        torchaudio.backend = bm
    else:
        torchaudio.backend.common = cm
import torch
from df.enhance import init_df
model, state, _ = init_df("DeepFilterNet3", log_level="ERROR")

spec = torch.randn(1, 1, 2, 481, 2)
erb = torch.randn(1, 1, 2, 32)
spec_f = torch.randn(1, 1, 2, 96, 2)
# Since pad_feat needs T>=2 for lookahead=1!
_, m, _, coefs = model(spec, erb, spec_f)
print("coefs shape from model:", coefs.shape)
out = model.mask(spec, m, coefs)
print("enh_onnx native:", out.shape)
