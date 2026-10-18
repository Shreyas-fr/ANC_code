import torch
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

from df.enhance import init_df
model, state, _ = init_df("DeepFilterNet3", log_level="ERROR")

spec = torch.randn(1, 1, 1, 481, 2)
coefs = torch.randn(1, 1, 1, 96, 10)
out = model.df(spec, coefs)
print("out shape:", out.shape)
