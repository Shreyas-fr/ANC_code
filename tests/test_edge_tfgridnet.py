"""Comprehensive Unit and Consistency Test Suite for Compact Edge-TF-GridNet.

Fulfills all mandatory tests for Stage 11.2.51B:
1. Exact 202,706 parameter count verification
2. Causal temporal padding verification (zero lookahead)
3. Streaming state persistence vs batch equivalence
4. State reset between independent utterances (zero state bleed)
5. STFT/ISTFT reconstruction fidelity (COLA condition, SNR > 60 dB)
6. Numerical stability under silence, near-zero amplitude, and clipping
7. Complex ratio mask equations and Mic 1 reference channel convention
"""

import math
import sys
import os
import unittest
import torch
import torch.nn.functional as F

# Add repository and antigravity roots to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
antigravity_root = os.path.join(repo_root, "antigravity")
src_root = os.path.join(antigravity_root, "src")

for p in [repo_root, antigravity_root, src_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from models.edge_tfgridnet import (
        EdgeTFGridNet,
        StreamingEdgeTFGridNet,
        apply_complex_ratio_mask,
    )
except ImportError:
    from antigravity.src.models.edge_tfgridnet import (
        EdgeTFGridNet,
        StreamingEdgeTFGridNet,
        apply_complex_ratio_mask,
    )


class TestEdgeTFGridNet(unittest.TestCase):
    """Test suite for EdgeTFGridNet implementation."""

    def setUp(self):
        torch.manual_seed(42)
        self.device = torch.device("cpu")
        self.model = EdgeTFGridNet(
            in_channels=4,
            out_channels=2,
            emb_dim=24,
            hidden_dim=48,
            num_blocks=3,
        ).to(self.device)
        self.model.eval()

    def test_01_exact_parameter_count(self):
        """Test 1: Verify exact 202,706 parameter count and layer breakdown."""
        total_params = sum(p.numel() for p in self.model.parameters())
        self.assertEqual(
            total_params,
            202706,
            f"Total parameter count mismatch: expected 202,706, got {total_params}",
        )

        # Layer-by-layer breakdown verification
        in_conv_params = sum(p.numel() for p in self.model.in_conv.parameters())
        self.assertEqual(in_conv_params, 888, f"in_conv expected 888, got {in_conv_params}")

        block_params = [
            sum(p.numel() for p in block.parameters()) for block in self.model.blocks
        ]
        for idx, bp in enumerate(block_params):
            self.assertEqual(
                bp, 67128, f"Block {idx} params expected 67,128, got {bp}"
            )
        self.assertEqual(
            sum(block_params),
            201384,
            f"3 blocks expected 201,384, got {sum(block_params)}",
        )

        out_conv_params = sum(p.numel() for p in self.model.out_conv.parameters())
        self.assertEqual(
            out_conv_params, 434, f"out_conv expected 434, got {out_conv_params}"
        )

    def test_02_causal_padding_temporal_direction(self):
        """Test 2: Verify causal padding is along time dimension (zero forward lookahead)."""
        # Inject an impulse at frame t=30 in a sequence of 60 frames
        x = torch.zeros(1, 4, 257, 60, device=self.device)
        x[..., 30] = 5.0

        with torch.no_grad():
            mask, _ = self.model(x)

        # In a strictly causal model, output at all past frames t < 30 MUST be identical
        # to the zero-input response (which is strictly zero before non-linear bias shifts)
        x_zero = torch.zeros(1, 4, 257, 60, device=self.device)
        with torch.no_grad():
            mask_zero, _ = self.model(x_zero)

        past_diff = (mask[..., :30] - mask_zero[..., :30]).abs().max().item()
        self.assertEqual(
            past_diff,
            0.0,
            f"Causality violation: impulse at t=30 affected past frames t < 30! Max diff: {past_diff}",
        )

    def test_03_streaming_state_persistence_vs_batch(self):
        """Test 3: Verify streaming state persistence matches batch execution bit-identically."""
        num_frames = 40
        x = torch.randn(1, 4, 257, num_frames, device=self.device)

        with torch.no_grad():
            # Batch forward pass
            batch_mask, _ = self.model(x)

            # Streaming forward pass with state passing
            streamer = StreamingEdgeTFGridNet(self.model, batch_size=1, num_freqs=257)
            stream_masks = []
            for t in range(num_frames):
                xt = x[..., t : t + 1]
                mt = streamer.step(xt)
                stream_masks.append(mt)
            stream_mask = torch.cat(stream_masks, dim=-1)

        max_abs_diff = (batch_mask - stream_mask).abs().max().item()
        self.assertLess(
            max_abs_diff,
            1e-5,
            f"Streaming state persistence diverged from batch! Max diff: {max_abs_diff}",
        )

    def test_04_state_reset_between_utterances(self):
        """Test 4: Verify state reset between independent utterances prevents state bleed."""
        u1 = torch.randn(1, 4, 257, 25, device=self.device)
        u2 = torch.randn(1, 4, 257, 25, device=self.device)

        streamer = StreamingEdgeTFGridNet(self.model, batch_size=1, num_freqs=257)

        with torch.no_grad():
            # Process Utterance 1
            for t in range(25):
                streamer.step(u1[..., t : t + 1])

            # Reset state
            streamer.reset()

            # Process Utterance 2 after reset
            u2_stream_masks = []
            for t in range(25):
                u2_stream_masks.append(streamer.step(u2[..., t : t + 1]))
            u2_stream_result = torch.cat(u2_stream_masks, dim=-1)

            # Process Utterance 2 from fresh cold start
            cold_streamer = StreamingEdgeTFGridNet(self.model, batch_size=1, num_freqs=257)
            cold_masks = []
            for t in range(25):
                cold_masks.append(cold_streamer.step(u2[..., t : t + 1]))
            cold_result = torch.cat(cold_masks, dim=-1)

        reset_diff = (u2_stream_result - cold_result).abs().max().item()
        self.assertEqual(
            reset_diff,
            0.0,
            f"State bleed detected! Reset state did not match cold start. Diff: {reset_diff}",
        )

    def test_05_stft_istft_reconstruction(self):
        """Test 5: Verify STFT and ISTFT reconstruction fidelity with Hann window and 50% overlap."""
        fs = 16000
        duration = 1.0  # 1 second
        t_axis = torch.linspace(0, duration, int(fs * duration))
        # Synthetic clean speech test signal: sum of harmonic sinusoids
        clean_audio = (
            0.5 * torch.sin(2 * math.pi * 300 * t_axis)
            + 0.3 * torch.sin(2 * math.pi * 700 * t_axis)
            + 0.2 * torch.sin(2 * math.pi * 1500 * t_axis)
        ).unsqueeze(0)  # [1, N]

        n_fft = 512
        hop_length = 256
        window = torch.hann_window(n_fft)

        # Forward STFT
        stft_complex = torch.stft(
            clean_audio,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=n_fft,
            window=window,
            center=True,
            pad_mode="reflect",
            normalized=False,
            onesided=True,
            return_complex=True,
        )  # [1, 257, T]

        # Apply identity complex ratio mask (M_r = 1, M_i = 0)
        mask = torch.zeros(1, 2, stft_complex.shape[1], stft_complex.shape[2])
        mask[:, 0, :, :] = 1.0  # Real = 1.0
        mask[:, 1, :, :] = 0.0  # Imag = 0.0

        mic1_stft = torch.stack(
            [stft_complex.real, stft_complex.imag], dim=1
        )  # [1, 2, 257, T]
        enhanced_stft_2ch = apply_complex_ratio_mask(mask, mic1_stft)
        enhanced_complex = torch.complex(
            enhanced_stft_2ch[:, 0, :, :], enhanced_stft_2ch[:, 1, :, :]
        )

        # Inverse STFT
        reconstructed_audio = torch.istft(
            enhanced_complex,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=n_fft,
            window=window,
            center=True,
            normalized=False,
            onesided=True,
            length=clean_audio.shape[-1],
        )

        # Compute Reconstruction Error & SNR
        error = clean_audio - reconstructed_audio
        signal_power = torch.mean(clean_audio ** 2)
        error_power = torch.mean(error ** 2)
        reconstruction_snr = 10 * torch.log10(signal_power / (error_power + 1e-12)).item()
        max_error = error.abs().max().item()

        self.assertGreater(
            reconstruction_snr,
            60.0,
            f"STFT/ISTFT reconstruction SNR too low: {reconstruction_snr:.2f} dB (expected > 60 dB)",
        )
        self.assertLess(
            max_error,
            1e-3,
            f"STFT/ISTFT max absolute reconstruction error too high: {max_error}",
        )

    def test_06_numerical_stability_edge_cases(self):
        """Test 6: Verify numerical stability under silence, near-zero, and clipped inputs."""
        with torch.no_grad():
            # A. Pure silence input
            x_silence = torch.zeros(1, 4, 257, 10, device=self.device)
            m_silence, _ = self.model(x_silence)
            self.assertTrue(
                torch.isfinite(m_silence).all().item(),
                "Silence input produced non-finite mask!",
            )

            # B. Near-zero amplitude input (1e-7)
            x_near_zero = torch.full((1, 4, 257, 10), 1e-7, device=self.device)
            m_near_zero, _ = self.model(x_near_zero)
            self.assertTrue(
                torch.isfinite(m_near_zero).all().item(),
                "Near-zero input produced non-finite mask!",
            )

            # C. Clipped / extreme amplitude input (+20 dB / magnitude 10.0)
            x_clipped = torch.full((1, 4, 257, 10), 10.0, device=self.device)
            m_clipped, _ = self.model(x_clipped)
            self.assertTrue(
                torch.isfinite(m_clipped).all().item(),
                "Clipped input produced non-finite mask!",
            )
            # Ensure mask values remain bounded
            self.assertLess(
                m_clipped.abs().max().item(),
                100.0,
                "Mask values exploded under clipped input!",
            )

    def test_07_complex_ratio_mask_and_reference_channel(self):
        """Test 7: Verify cRM equations and Mic 1 reference-channel convention."""
        # Create arbitrary Mic 1 STFT
        x1_r = torch.tensor([[[[2.0, 3.0], [1.0, -2.0]]]])
        x1_i = torch.tensor([[[[1.0, -1.0], [4.0, 0.5]]]])
        mic1 = torch.cat([x1_r, x1_i], dim=1)  # [1, 2, 2, 2]

        # Case A: Unity mask (M_r = 1, M_i = 0) -> Output must be exact replica of Mic 1
        m_unity = torch.zeros_like(mic1)
        m_unity[:, 0:1, :, :] = 1.0
        out_unity = apply_complex_ratio_mask(m_unity, mic1)
        self.assertTrue(
            torch.allclose(out_unity, mic1),
            "Unity mask failed to reproduce Mic 1 spectrum!",
        )

        # Case B: Zero mask (M_r = 0, M_i = 0) -> Output must be zero
        m_zero = torch.zeros_like(mic1)
        out_zero = apply_complex_ratio_mask(m_zero, mic1)
        self.assertTrue(
            torch.allclose(out_zero, torch.zeros_like(mic1)),
            "Zero mask failed to attenuate Mic 1 to zero!",
        )

        # Case C: 90-degree phase rotation mask (M_r = 0, M_i = 1)
        # S_r = -X_i, S_i = X_r
        m_rot = torch.zeros_like(mic1)
        m_rot[:, 1:2, :, :] = 1.0
        out_rot = apply_complex_ratio_mask(m_rot, mic1)
        expected_s_r = -x1_i
        expected_s_i = x1_r
        expected_rot = torch.cat([expected_s_r, expected_s_i], dim=1)
        self.assertTrue(
            torch.allclose(out_rot, expected_rot),
            "Phase rotation mask equation verification failed!",
        )


if __name__ == "__main__":
    unittest.main()
