"""Adapter for the official pretrained Audio-WestlakeU FullSubNet model.

FullSubNet consumes mono 16 kHz audio, predicts a compressed complex ratio
mask, and reconstructs audio with the input mixture phase. This adapter uses
the upstream model/checkpoint parameterization and the official 512/256 STFT
settings without changing the canonical DeepFilterNet evaluator.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
VENDOR = REPO / "third_party/fullsubnet_vendor"
CHECKPOINT_DEFAULT = REPO / "checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_model_class():
    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from fullsubnet.model import Model
    from audio_zen.acoustics.mask import decompress_cIRM

    return Model, decompress_cIRM


class FullSubNetAdapter:
    """Inference adapter with strict checkpoint loading and aligned output."""

    sample_rate = 16000
    n_fft = 512
    win_length = 512
    hop_length = 256

    def __init__(self, checkpoint: str | Path = CHECKPOINT_DEFAULT, device: str = "cpu"):
        self.checkpoint = Path(checkpoint).expanduser().resolve()
        if not self.checkpoint.is_file():
            raise FileNotFoundError(f"FullSubNet checkpoint not found: {self.checkpoint}")
        self.checkpoint_sha256 = sha256(self.checkpoint)
        self.device = torch.device(device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is not available")

        Model, self._decompress_cirm = _load_model_class()
        self.model = Model(
            num_freqs=257,
            look_ahead=2,
            sequence_model="LSTM",
            fb_num_neighbors=0,
            sb_num_neighbors=15,
            fb_output_activate_function="ReLU",
            sb_output_activate_function=False,
            fb_model_hidden_size=512,
            sb_model_hidden_size=384,
            norm_type="offline_laplace_norm",
            num_groups_in_drop_band=2,
            weight_init=False,
        )

        # This is a public upstream checkpoint pinned by filename and digest in
        # the accompanying evaluation report. weights_only=False is required
        # for the legacy training metadata container; the source is trusted.
        checkpoint_obj = torch.load(
            self.checkpoint, map_location="cpu", weights_only=False
        )
        state = checkpoint_obj.get("model") or checkpoint_obj.get("model_state_dict")
        if not isinstance(state, dict):
            raise ValueError("FullSubNet checkpoint lacks a model state dictionary")
        state = {key.removeprefix("module."): value for key, value in state.items()}
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device).eval()
        self.epoch = int(checkpoint_obj.get("epoch", -1))
        self.parameter_count = sum(param.numel() for param in self.model.parameters())
        self.window = torch.hann_window(self.n_fft, device=self.device)

    @torch.inference_mode()
    def enhance(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """Enhance a finite, mono 16 kHz waveform, preserving its sample count."""
        if sample_rate != self.sample_rate:
            raise ValueError(f"FullSubNet expects {self.sample_rate} Hz, got {sample_rate}")
        waveform = np.asarray(audio, dtype=np.float32)
        if waveform.ndim != 1:
            raise ValueError(f"FullSubNet expects mono 1-D audio, got shape {waveform.shape}")
        if not np.isfinite(waveform).all():
            raise ValueError("Input waveform contains NaN or infinity")
        original_length = waveform.size
        if original_length == 0:
            raise ValueError("Input waveform is empty")

        # torch.stft's centered reflect padding requires more than n_fft/2
        # samples. Pad tiny clips safely and trim the reconstructed signal.
        minimum_length = self.n_fft // 2 + 1
        padded = waveform
        if len(padded) < minimum_length:
            padded = np.pad(padded, (0, minimum_length - len(padded)))
        signal = torch.from_numpy(np.ascontiguousarray(padded)).to(self.device).unsqueeze(0)
        noisy_complex = torch.stft(
            signal,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.win_length,
            window=self.window,
            return_complex=True,
        )
        noisy_mag = noisy_complex.abs().unsqueeze(1)
        compressed_mask = self.model(noisy_mag).permute(0, 2, 3, 1)
        complex_mask = self._decompress_cirm(compressed_mask)

        noisy_real = noisy_complex.real
        noisy_imag = noisy_complex.imag
        mask_real = complex_mask[..., 0]
        mask_imag = complex_mask[..., 1]
        enhanced_real = mask_real * noisy_real - mask_imag * noisy_imag
        enhanced_imag = mask_real * noisy_imag + mask_imag * noisy_real
        enhanced_complex = torch.complex(enhanced_real, enhanced_imag)
        enhanced = torch.istft(
            enhanced_complex,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.win_length,
            window=self.window,
            length=len(padded),
        ).squeeze(0)
        result = enhanced[:original_length].detach().cpu().numpy().astype(np.float32, copy=False)
        if result.shape != waveform.shape or not np.isfinite(result).all():
            raise RuntimeError("FullSubNet returned invalid or misaligned audio")
        return result
