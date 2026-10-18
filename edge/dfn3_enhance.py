"""
dfn3_enhance.py - loads the fine-tuned DeepFilterNet3 and exposes enhance_fn(window48) -> window48.

Loading follows the same path your Pi already ran successfully (init_df + hk.load_file +
strict load_state_dict). Each call gets a FRESH libdf STFT state because df.enhance() is
an offline whole-signal routine: it resets the GRU state itself and compensates STFT delay
for the signal it is given, so it must not share STFT state between unrelated windows.
"""
import hashlib
import sys
import types

import numpy as np

FROZEN_SHA256 = "522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe"  # final_model/model.sha256


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _torchaudio_shim():
    import torchaudio
    if not hasattr(getattr(torchaudio, "backend", None), "common"):
        cm = types.ModuleType("torchaudio.backend.common")

        class AudioMetaData:
            def __init__(self, sr, nf, nc, bps, enc):
                self.sample_rate, self.num_frames, self.num_channels = sr, nf, nc
                self.bits_per_sample, self.encoding = bps, enc

        cm.AudioMetaData = AudioMetaData
        sys.modules["torchaudio.backend.common"] = cm
        if not hasattr(torchaudio, "backend"):
            bm = types.ModuleType("torchaudio.backend")
            bm.common = cm
            sys.modules["torchaudio.backend"] = bm
            torchaudio.backend = bm
        else:
            torchaudio.backend.common = cm


def make_dfn3_enhance_fn(model_path: str, threads: int = 3):
    import torch
    _torchaudio_shim()
    from df.enhance import enhance, init_df, maybe_download_model
    from df.model import ModelParams
    from libdf import DF

    torch.set_num_threads(threads)
    base = maybe_download_model("DeepFilterNet3")
    model, _, _ = init_df(base, log_file=None)
    import hk  # same loader as the existing dfn3_stream.py
    ckpt = hk.load_file(model_path)
    state = ckpt["model_state_dict"] if "model_state_dict" in ckpt else ckpt
    model.load_state_dict(state, strict=True)
    model.eval()
    p = ModelParams()

    def enhance_fn(win: np.ndarray) -> np.ndarray:
        df_state = DF(sr=p.sr, fft_size=p.fft_size, hop_size=p.hop_size, nb_bands=p.nb_erb)
        t = torch.from_numpy(np.ascontiguousarray(win, dtype=np.float32)).unsqueeze(0)
        with torch.no_grad():
            out = enhance(model, df_state, t)
        return out.squeeze(0).cpu().numpy().astype(np.float32)

    return enhance_fn
