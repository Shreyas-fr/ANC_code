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
import df.multiframe as MF
spec = torch.randn(1, 1, 1, 481, 2)
coefs = torch.randn(1, 1, 1, 96, 5, 2)
out = MF.DF(96, 5, 0)(spec, coefs)
print(out.shape)
