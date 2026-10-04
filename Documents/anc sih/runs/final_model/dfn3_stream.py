"""Stateful DeepFilterNet3 streaming wrapper.

CRITICAL: never call df.enhance() per live chunk. enhance() calls model.reset_h0()
on every invocation, which tears speech into robotic frames. This module keeps
STFT overlap (libdf DF state) and recurrent hidden state across hops.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import types

import numpy as np
import torch

from stream_resample import StatefulLinearResampler

# torchaudio backend shim used on the Pi Python build
try:
    import torchaudio
    if not hasattr(getattr(torchaudio, "backend", None), "common"):
        cm = types.ModuleType("torchaudio.backend.common")

        class AudioMetaData:
            def __init__(self, sr, nf, nc, bps, enc):
                self.sample_rate = sr
                self.num_frames = nf
                self.num_channels = nc
                self.bits_per_sample = bps
                self.encoding = enc

        cm.AudioMetaData = AudioMetaData
        sys.modules["torchaudio.backend.common"] = cm
        if not hasattr(torchaudio, "backend"):
            bm = types.ModuleType("torchaudio.backend")
            bm.common = cm
            sys.modules["torchaudio.backend"] = bm
            torchaudio.backend = bm
        else:
            torchaudio.backend.common = cm
except Exception:
    pass

from df.enhance import df_features, init_df, maybe_download_model
from df.utils import as_complex, get_device


FROZEN_SHA256 = "522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe"
PARAM_COUNT_CLAIM = 2167969


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_state_dict(path: str):
    if path.endswith(".hk"):
        import hk
        ckpt = hk.load_file(path)
    else:
        ckpt = torch.load(path, map_location="cpu")
    if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
        return ckpt["model_state_dict"]
    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        return ckpt["state_dict"]
    return ckpt


class DFN3Stream:
    """Hop-aligned streaming enhancer. Input/output default to 16 kHz PCM."""

    def __init__(self, config_dict):
        self.config = config_dict
        self.device = torch.device("cpu")
        try:
            torch.set_num_threads(max(1, int(os.environ.get("SIH_TORCH_THREADS", "2"))))
        except Exception:
            pass

        print("Initializing DeepFilterNet3 (stateful streaming, no per-chunk reset)...")
        base = maybe_download_model("DeepFilterNet3")
        self.model, self.df_state, _, _ = init_df(base, log_file=None)

        self.model_path = os.path.expanduser(
            self.config.get("model_path")
            or os.path.expanduser("~/sih26052_edge/models/model.hk")
        )
        self.model_sha = "unknown"
        self.weights_loaded = False
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(
                f"Frozen DFN3 weights missing at {self.model_path}. "
                "Refusing to silently fall back to pretrained."
            )
        self.model_sha = sha256_file(self.model_path)
        print(f"Loading weights from {self.model_path}")
        print(f"Model SHA256: {self.model_sha}")
        if self.model_sha != FROZEN_SHA256:
            print(
                "WARNING: live file SHA does not match frozen SHA "
                f"{FROZEN_SHA256}. Offline==live is NOT proven."
            )
        state_dict = _load_state_dict(self.model_path)
        self.model.load_state_dict(state_dict, strict=True)
        self.weights_loaded = True

        self.model.to(self.device)
        self.model.eval()
        self.nb_df = getattr(self.model, "nb_df", getattr(self.model, "df_bins", 96))

        self.sr_native = int(self.df_state.sr())
        self.hop_native = int(self.df_state.hop_size())
        self.fft_native = int(self.df_state.fft_size())
        self.sr_io = int(self.config.get("sample_rate", 16000))

        self.up = StatefulLinearResampler(self.sr_io, self.sr_native)
        self.down = StatefulLinearResampler(self.sr_native, self.sr_io)
        self._buf_48k = np.zeros(0, dtype=np.float32)

        self.nan_inf_count = 0
        self.state_resets = 0
        self.clip_count = 0
        self.dc_events = 0
        self.rms_events = 0
        self.deadline_misses = 0
        self.frames_processed = 0
        self.last_rms = 0.0
        self.last_dc = 0.0
        self.last_hop_ms = 0.0

        self._reset_hidden()
        n_params = sum(p.numel() for p in self.model.parameters())
        print(
            f"DFN3 Stream Ready. sr_native={self.sr_native} hop={self.hop_native} "
            f"fft={self.fft_native} params={n_params} io={self.sr_io} Hz"
        )

    def _reset_hidden(self):
        if hasattr(self.model, "reset_h0"):
            self.model.reset_h0(batch_size=1, device=get_device())
        self.state_resets += 1

    def reset_state(self):
        base = maybe_download_model("DeepFilterNet3")
        _, self.df_state, _, _ = init_df(base, log_file=None)
        self.up.reset()
        self.down.reset()
        self._buf_48k = np.zeros(0, dtype=np.float32)
        self._reset_hidden()

    def _health_check(self, x: np.ndarray, where: str) -> bool:
        if x is None or len(x) == 0:
            return False
        if np.isnan(x).any() or np.isinf(x).any():
            self.nan_inf_count += 1
            print(f"NaN/Inf in {where}")
            return False
        peak = float(np.max(np.abs(x)))
        if peak >= 0.99:
            self.clip_count += 1
        dc = float(np.mean(x))
        rms = float(np.sqrt(np.mean(x * x)))
        self.last_dc = dc
        self.last_rms = rms
        if abs(dc) > 0.05:
            self.dc_events += 1
        if rms > 0.9 or (rms < 1e-6 and peak > 0):
            self.rms_events += 1
        return True

    def _process_hop_48k(self, hop: np.ndarray) -> np.ndarray:
        """Process exactly one native hop. Does NOT reset recurrent state."""
        start = time.perf_counter()
        if not self._health_check(hop, "hop_in"):
            self.reset_state()
            return hop.astype(np.float32)

        audio = torch.from_numpy(np.ascontiguousarray(hop, dtype=np.float32)).unsqueeze(0)
        spec, erb_feat, spec_feat = df_features(audio, self.df_state, self.nb_df, device=self.device)
        with torch.no_grad():
            enhanced = self.model(spec.clone(), erb_feat, spec_feat)[0].cpu()
        enhanced = as_complex(enhanced.squeeze(1))
        out = torch.as_tensor(self.df_state.synthesis(enhanced.numpy()))
        y = out.squeeze(0).numpy().astype(np.float32)
        if y.shape[0] != hop.shape[0]:
            if y.shape[0] > hop.shape[0]:
                y = y[: hop.shape[0]]
            else:
                y = np.pad(y, (0, hop.shape[0] - y.shape[0]))

        if not self._health_check(y, "hop_out"):
            self.reset_state()
            return hop.astype(np.float32)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.last_hop_ms = elapsed_ms
        # Native hop is 10 ms at 48 kHz; 16 kHz UDP frames are 16 ms.
        if elapsed_ms > 10.0:
            self.deadline_misses += 1
        self.frames_processed += 1
        return y

    def process_pcm16k(self, chunk_16k: np.ndarray) -> np.ndarray:
        """Push 16 kHz samples, return any 16 kHz samples that are ready."""
        x = np.asarray(chunk_16k, dtype=np.float32).reshape(-1)
        up = self.up.process(x)
        if len(up):
            self._buf_48k = np.concatenate([self._buf_48k, up]) if len(self._buf_48k) else up
        out_48 = []
        hop = self.hop_native
        while len(self._buf_48k) >= hop:
            frame = self._buf_48k[:hop]
            self._buf_48k = self._buf_48k[hop:]
            out_48.append(self._process_hop_48k(frame))
        if not out_48:
            return np.zeros(0, dtype=np.float32)
        y48 = np.concatenate(out_48)
        return self.down.process(y48)

    def resample_only_16k(self, chunk_16k: np.ndarray) -> np.ndarray:
        """A/B mode B: 16k -> 48k -> 16k without the network."""
        x = np.asarray(chunk_16k, dtype=np.float32).reshape(-1)
        up = self.up.process(x)
        return self.down.process(up) if len(up) else np.zeros(0, dtype=np.float32)


if __name__ == "__main__":
    print("dfn3_stream.py is a library. Run dfn3_live_sender.py for the live path.")
