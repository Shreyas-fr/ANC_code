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

from df.enhance import init_df, df_features, ModelParams
from libdf import DF
model, state, _ = init_df("DeepFilterNet3", log_level="ERROR")
p = ModelParams()
chunk1 = torch.randn(1, 480)
spec, erb, spec_f = df_features(chunk1, state, p.nb_df, device="cpu")
spec, erb, spec_f = df_features(chunk1, state, p.nb_df, device="cpu")
_, m, _, coefs = model(spec, erb, spec_f)
print("m:", m.shape)
print("coefs:", coefs.shape)
