"""Isolated frame-stateful streaming adapter for the pinned GTCRN implementation.

The upstream model is imported unchanged. This module carries the temporal
GRU and causal-convolution state in an adapter and maintains centered STFT /
ISTFT overlap state. It is an experimental host prototype, not a deployment
runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F


@dataclass
class SessionState:
    # The audio input ring contains only samples needed by the next STFT frame.
    input_ring: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    input_ring_start: int = 0
    input_samples: int = 0
    next_frame_center: int = 0
    frame_count: int = 0
    # OLA rings are indexed from ola_start and contain un-emitted samples only.
    ola_num: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))
    ola_den: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))
    ola_start: int = 0
    next_output_sample: int = 0
    conv_context: dict[int, torch.Tensor] = field(default_factory=dict)
    attention_hidden: dict[int, torch.Tensor] = field(default_factory=dict)
    inter_gru_hidden: dict[int, torch.Tensor] = field(default_factory=dict)
    closed: bool = False


class GTCRNStreamAdapter:
    sample_rate = 16000
    n_fft = 512
    hop = 256
    half = 256
    max_internal_push_samples = 64
    max_chunk_samples = 4096  # 256 ms at 16 kHz; larger calls are rejected.

    def __init__(self, model: torch.nn.Module, device: str = "cpu"):
        self.model = model.to(device).eval()
        self.device = torch.device(device)
        self.window = torch.hann_window(self.n_fft, device=self.device).sqrt()
        self.window_np = self.window.detach().cpu().numpy().astype(np.float64)
        self.window_sq_np = self.window_np * self.window_np
        self.state = SessionState()
        self.max_input_ring_samples = 0
        self.max_ola_ring_samples = 0
        self.chunks_seen = 0
        self.frames_seen = 0

    def reset_session(self) -> None:
        """Clear all temporal, spectral, OLA and sample-index state."""
        self.state = SessionState()
        self.max_input_ring_samples = 0
        self.max_ola_ring_samples = 0
        self.chunks_seen = 0
        self.frames_seen = 0

    @classmethod
    def _validate_audio(cls, audio: np.ndarray) -> np.ndarray:
        raw = np.asarray(audio)
        if raw.ndim != 1:
            raise ValueError(f"expected mono 1-D float audio, got shape {raw.shape}")
        if not np.issubdtype(raw.dtype, np.number) or np.issubdtype(
            raw.dtype, np.complexfloating
        ):
            raise ValueError(f"expected real numeric audio, got dtype {raw.dtype}")
        if raw.size > cls.max_chunk_samples:
            raise ValueError(
                f"audio chunk has {raw.size} samples; limit is {cls.max_chunk_samples}"
            )
        if not np.isfinite(raw).all():
            raise ValueError("audio chunk contains NaN or infinity")
        return np.ascontiguousarray(raw, dtype=np.float32)

    def process_chunk(self, audio: np.ndarray, *, final: bool = False) -> np.ndarray:
        """Consume one chunk; return newly finalized, time-aligned samples.

        Caller chunks are limited to 4096 samples and internally ingested in
        bounded 64-sample pushes. Set final=True on the last chunk (including
        an empty last chunk) to reflect-pad the right edge and flush the tail.
        """
        if self.state.closed:
            raise RuntimeError("session is closed; call reset_session before reuse")
        x = self._validate_audio(audio)
        self.chunks_seen += 1
        emitted: list[np.ndarray] = []

        # Bound adapter-owned input buffering even when a caller submits a
        # large irregular chunk. Only the last sub-block may use right-edge
        # reflection; earlier sub-blocks wait for actual future samples.
        offsets = range(0, max(int(x.size), 1), self.max_internal_push_samples)
        for start in offsets:
            piece = x[start : start + self.max_internal_push_samples]
            if piece.size:
                self.state.input_ring = np.concatenate((self.state.input_ring, piece))
                self.state.input_samples += int(piece.size)
                self.max_input_ring_samples = max(
                    self.max_input_ring_samples, int(self.state.input_ring.size)
                )
            piece_is_final = final and start + piece.size >= x.size
            self._process_ready_frames(piece_is_final, emitted)

        if final:
            if self.state.input_samples < self.n_fft // 2 + 1:
                raise ValueError("final audio is too short for the reference reflect-padded STFT")
            # A final call must have processed all centered STFT frames.
            expected_frames = self.state.input_samples // self.hop + 1
            if self.state.frame_count != expected_frames:
                raise RuntimeError(
                    f"incomplete STFT flush: frames={self.state.frame_count}, expected={expected_frames}"
                )
            block = self._emit_until(self.state.input_samples)
            if block.size:
                emitted.append(block)
            self.state.closed = True

        if emitted:
            return np.concatenate(emitted).astype(np.float32, copy=False)
        return np.zeros(0, dtype=np.float32)

    def _process_ready_frames(self, final: bool, emitted: list[np.ndarray]) -> None:
        while self._next_frame_ready(final):
            center = self.state.next_frame_center
            frame = self._read_analysis_frame(center, final=final)
            spec = torch.fft.rfft(
                torch.from_numpy(frame).to(self.device) * self.window,
                n=self.n_fft,
                dim=-1,
            )
            spec_ri = torch.view_as_real(spec).reshape(1, self.n_fft // 2 + 1, 1, 2)
            enhanced_ri = self._model_frame(spec_ri)
            enhanced = torch.view_as_complex(enhanced_ri.contiguous()).reshape(-1)
            time_frame = torch.fft.irfft(enhanced, n=self.n_fft).detach().cpu().numpy()
            self._accumulate_synthesis_frame(center, time_frame)
            self.state.next_frame_center += self.hop
            self.state.frame_count += 1
            self.frames_seen += 1
            self._trim_input_ring()
            # Only samples strictly before the next frame center are finalized;
            # the final right-reflected tail is released after every final frame.
            block = self._emit_until(center)
            if block.size:
                emitted.append(block)

    def _next_frame_ready(self, final: bool) -> bool:
        c = self.state.next_frame_center
        n = self.state.input_samples
        if final:
            return c <= (n // self.hop) * self.hop
        # Reflect padding for frame 0 refers to x[1:257], requiring sample 256.
        if c == 0:
            return n >= self.half + 1
        # Interior centered frame c uses samples [c-half, c+half-1].
        return n >= c + self.half

    @staticmethod
    def _reflect_index(index: int, length: int) -> int:
        if length < 2:
            raise ValueError("reflect padding requires at least two samples")
        period = 2 * (length - 1)
        folded = index % period
        return period - folded if folded >= length else folded

    def _sample_at(self, absolute_index: int, *, final: bool) -> float:
        n = self.state.input_samples
        idx = absolute_index
        if idx < 0 or idx >= n:
            if not final and idx < 0 and self.state.next_frame_center == 0:
                idx = self._reflect_index(idx, n)
            elif final:
                idx = self._reflect_index(idx, n)
            else:
                raise RuntimeError("requested future sample before it arrived")
        ring_idx = idx - self.state.input_ring_start
        if ring_idx < 0 or ring_idx >= self.state.input_ring.size:
            raise RuntimeError(
                f"input ring lost sample {idx}; ring starts at {self.state.input_ring_start}"
            )
        return float(self.state.input_ring[ring_idx])

    def _read_analysis_frame(self, center: int, *, final: bool) -> np.ndarray:
        start = center - self.half
        return np.fromiter(
            (self._sample_at(start + i, final=final) for i in range(self.n_fft)),
            dtype=np.float32,
            count=self.n_fft,
        )

    def _model_frame(self, spec: torch.Tensor) -> torch.Tensor:
        """One spectrogram frame through upstream layers with explicit state."""
        with torch.inference_mode():
            spec_real = spec[..., 0].permute(0, 2, 1)
            spec_imag = spec[..., 1].permute(0, 2, 1)
            mag = torch.sqrt(spec_real.square() + spec_imag.square() + 1e-12)
            feat = torch.stack((mag, spec_real, spec_imag), dim=1)
            feat = self.model.erb.bm(feat)
            feat = self.model.sfe(feat)

            en_outs = []
            for module in self.model.encoder.en_convs:
                if module.__class__.__name__ == "GTConvBlock":
                    feat = self._gtconv_step(module, feat)
                else:
                    feat = module(feat)
                en_outs.append(feat)

            feat = self._dpgrnn_step(self.model.dpgrnn1, feat)
            feat = self._dpgrnn_step(self.model.dpgrnn2, feat)

            for i, module in enumerate(self.model.decoder.de_convs):
                feat = feat + en_outs[len(self.model.decoder.de_convs) - 1 - i]
                if module.__class__.__name__ == "GTConvBlock":
                    feat = self._gtconv_step(module, feat)
                else:
                    feat = module(feat)

            mask = self.model.erb.bs(feat)
            enhanced = self.model.mask(mask, spec.permute(0, 3, 2, 1))
            return enhanced.permute(0, 3, 2, 1)

    def _gtconv_step(self, block: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
        x1, x2 = torch.chunk(x, chunks=2, dim=1)
        x1 = block.sfe(x1)
        hidden_input = block.point_act(block.point_bn1(block.point_conv1(x1)))
        cache_key = id(block)
        pad_size = int(block.pad_size)
        if cache_key not in self.state.conv_context:
            zeros = torch.zeros(
                hidden_input.shape[0], hidden_input.shape[1], pad_size,
                hidden_input.shape[3], dtype=hidden_input.dtype, device=hidden_input.device
            )
            self.state.conv_context[cache_key] = zeros
        context = torch.cat((self.state.conv_context[cache_key], hidden_input), dim=2)
        padded = F.pad(context, (0, 0, pad_size, 0)) if pad_size else context
        y = block.depth_act(block.depth_bn(block.depth_conv(padded)))
        y = y[..., -1:, :]
        y = block.point_bn2(block.point_conv2(y))

        if cache_key not in self.state.attention_hidden:
            self.state.attention_hidden[cache_key] = torch.zeros(
                1, y.shape[0], block.tra.att_gru.hidden_size,
                dtype=y.dtype, device=y.device
            )
        z = torch.mean(y.square(), dim=-1).transpose(1, 2)
        a, h = block.tra.att_gru(z, self.state.attention_hidden[cache_key])
        self.state.attention_hidden[cache_key] = h
        a = block.tra.att_act(block.tra.att_fc(a).transpose(1, 2))[..., None]
        y = y * a
        self.state.conv_context[cache_key] = context[:, :, -pad_size:, :].clone() if pad_size else context[:, :, :0, :]
        return block.shuffle(y, x2)

    def _dpgrnn_step(self, module: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
        # Intra-RNN is over frequency bins independently per frame; it has no
        # cross-frame state. Inter-RNN is over time and carries hidden state.
        y = x.permute(0, 2, 3, 1)
        intra = y.reshape(y.shape[0] * y.shape[1], y.shape[2], y.shape[3])
        intra = module.intra_rnn(intra)[0]
        intra = module.intra_fc(intra)
        intra = intra.reshape(y.shape[0], -1, module.width, module.hidden_size)
        intra = module.intra_ln(intra)
        intra_out = torch.add(y, intra)
        inter_input = intra_out.permute(0, 2, 1, 3)
        inter_input = inter_input.reshape(
            inter_input.shape[0] * inter_input.shape[1], inter_input.shape[2], inter_input.shape[3]
        )
        key = id(module)
        hidden = self.state.inter_gru_hidden.get(key)
        inter, hidden = module.inter_rnn(inter_input, hidden)
        self.state.inter_gru_hidden[key] = hidden
        inter = module.inter_fc(inter)
        inter = inter.reshape(x.shape[0], module.width, -1, module.hidden_size)
        inter = inter.permute(0, 2, 1, 3)
        inter = module.inter_ln(inter)
        return torch.add(intra_out, inter).permute(0, 3, 1, 2)

    def _accumulate_synthesis_frame(self, center: int, time_frame: np.ndarray) -> None:
        start = center - self.half
        frame = np.asarray(time_frame, dtype=np.float64) * self.window_np
        lo = max(start, 0)
        hi = start + self.n_fft
        if hi <= lo:
            return
        self._ensure_ola_capacity(hi)
        dst_lo = lo - self.state.ola_start
        dst_hi = hi - self.state.ola_start
        src_lo = lo - start
        src_hi = src_lo + (hi - lo)
        self.state.ola_num[dst_lo:dst_hi] += frame[src_lo:src_hi]
        self.state.ola_den[dst_lo:dst_hi] += self.window_sq_np[src_lo:src_hi]
        self.max_ola_ring_samples = max(self.max_ola_ring_samples, self.state.ola_num.size)

    def _ensure_ola_capacity(self, end_sample: int) -> None:
        needed = end_sample - self.state.ola_start
        if needed > self.state.ola_num.size:
            extra = needed - self.state.ola_num.size
            self.state.ola_num = np.pad(self.state.ola_num, (0, extra))
            self.state.ola_den = np.pad(self.state.ola_den, (0, extra))

    def _emit_until(self, end_sample: int) -> np.ndarray:
        start = self.state.next_output_sample
        end = max(start, int(end_sample))
        if end == start:
            return np.zeros(0, np.float32)
        self._ensure_ola_capacity(end)
        a = start - self.state.ola_start
        b = end - self.state.ola_start
        den = self.state.ola_den[a:b]
        if np.any(den <= 1e-12):
            raise RuntimeError("ISTFT synthesis produced uncovered output samples")
        out = (self.state.ola_num[a:b] / den).astype(np.float32)
        self.state.next_output_sample = end
        drop = end - self.state.ola_start
        self.state.ola_num = self.state.ola_num[drop:].copy()
        self.state.ola_den = self.state.ola_den[drop:].copy()
        self.state.ola_start = end
        return out

    def _trim_input_ring(self) -> None:
        # Retain one extra sample for the far edge of torch's reflect padding
        # when a later final frame lands exactly at the input length.
        keep_from = max(0, self.state.next_frame_center - self.half - 1)
        drop = keep_from - self.state.input_ring_start
        if drop > 0:
            self.state.input_ring = self.state.input_ring[drop:].copy()
            self.state.input_ring_start = keep_from
        self.max_input_ring_samples = max(self.max_input_ring_samples, self.state.input_ring.size)

    def state_summary(self) -> dict[str, Any]:
        return {
            "input_samples_seen": self.state.input_samples,
            "frames_seen": self.state.frame_count,
            "next_frame_center": self.state.next_frame_center,
            "next_output_sample": self.state.next_output_sample,
            "conv_cache_frames": {
                str(k): int(v.shape[2]) for k, v in self.state.conv_context.items()
            },
            "attention_gru_state_shapes": [list(v.shape) for v in self.state.attention_hidden.values()],
            "inter_gru_state_shapes": [list(v.shape) for v in self.state.inter_gru_hidden.values()],
            "input_ring_samples": int(self.state.input_ring.size),
            "ola_ring_samples": int(self.state.ola_num.size),
            "max_input_ring_samples": int(self.max_input_ring_samples),
            "max_ola_ring_samples": int(self.max_ola_ring_samples),
            "session_closed": bool(self.state.closed),
        }
