"""Edge-TF-GridNet: Causal Compact Neural Post-Filter for Dual-Microphone Speech Enhancement.

Architecture Specification (Stage 11.2.50D / 11.2.51B):
- 4-Channel Dual-Microphone Input: [B, 4, F, T] (Real & Imag of Mic 1 & Mic 2)
- Complex Ratio Mask (cRM) Output: [B, 2, F, T] (Applied to Reference Mic 1)
- Blocks: B=3 GridBlocks
- Embedding Dimension: D=24
- LSTM Hidden Units: H=48
- Total Parameter Count: Exactly 202,706 parameters
- Compute: 50,960,016 MACs/frame (101,920,032 FLOPs/frame) at 62.5 fps (3.1850 GMACs/s)
- Causal temporal padding (Kt - 1, 0) guaranteeing 0 frames algorithmic lookahead
"""

from typing import Dict, Optional, Tuple
import torch
import torch.nn as nn
import torch.nn.functional as F


class CausalConv2d(nn.Module):
    """2D Convolution with causal temporal padding and symmetric frequency padding.

    For kernel size (Kf, Kt), causal padding along time requires padding Kt - 1 past
    frames on the left and 0 frames on the right. Frequency padding is symmetric (Kf // 2).
    In streaming mode (T=1), it maintains a FIFO buffer of (Kt - 1) past frames.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: Tuple[int, int] = (3, 3),
        stride: int = 1,
        dilation: int = 1,
    ) -> None:
        super().__init__()
        self.kf, self.kt = kernel_size
        self.conv = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            dilation=dilation,
            padding=0,
            bias=True,
        )
        self.pad_f = self.kf // 2
        self.pad_t = self.kt - 1

    def forward(
        self, x: torch.Tensor, state: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """Forward pass for causal 2D convolution.

        Args:
            x: Input tensor of shape [B, C, F, T].
            state: Optional temporal buffer of shape [B, C, F, pad_t] for streaming mode.

        Returns:
            Tuple of (output tensor [B, C_out, F, T], updated state buffer).
        """
        if state is None:
            # Batch mode: zero-pad past frames along time (left=pad_t, right=0)
            # F.pad expects (left, right, top, bottom) -> (time_left, time_right, freq_top, freq_bottom)
            x_pad = F.pad(x, (self.pad_t, 0, self.pad_f, self.pad_f))
            out = self.conv(x_pad)
            return out, None
        else:
            # Streaming mode: concatenate persistent past frames along time axis
            x_cat = torch.cat([state, x], dim=-1)
            new_state = x_cat[..., -self.pad_t :]
            x_pad = F.pad(x_cat, (0, 0, self.pad_f, self.pad_f))
            out = self.conv(x_pad)
            return out, new_state


class GridBlock(nn.Module):
    """Single TF-GridNet block containing Intra-Frequency, Inter-Time, and Spatial modules."""

    def __init__(self, emb_dim: int = 24, hidden_dim: int = 48) -> None:
        super().__init__()
        self.emb_dim = emb_dim
        self.hidden_dim = hidden_dim

        # 1. Intra-Frequency BiLSTM module (sweeps frequency axis within current time frame)
        self.intra_bilstm = nn.LSTM(
            input_size=emb_dim,
            hidden_size=hidden_dim,
            bidirectional=True,
            batch_first=True,
        )
        self.intra_proj = nn.Linear(hidden_dim * 2, emb_dim)
        self.intra_ln = nn.LayerNorm(emb_dim)

        # 2. Inter-Time Unidirectional Causal LSTM module (sweeps time axis per frequency bin)
        self.inter_lstm = nn.LSTM(
            input_size=emb_dim,
            hidden_size=hidden_dim,
            bidirectional=False,
            batch_first=True,
        )
        self.inter_proj = nn.Linear(hidden_dim, emb_dim)
        self.inter_ln = nn.LayerNorm(emb_dim)

        # 3. Spatial Convolutional module
        self.conv1 = CausalConv2d(emb_dim, emb_dim * 2, (3, 3))
        self.prelu = nn.PReLU(emb_dim * 2)
        self.conv2 = CausalConv2d(emb_dim * 2, emb_dim, (3, 3))
        self.spatial_ln = nn.LayerNorm(emb_dim)

    def forward(
        self, x: torch.Tensor, state: Optional[Dict[str, torch.Tensor]] = None
    ) -> Tuple[torch.Tensor, Optional[Dict[str, torch.Tensor]]]:
        """Forward pass through a GridBlock.

        Args:
            x: Feature map tensor of shape [B, D, F, T].
            state: Optional dictionary containing persistent states for streaming.

        Returns:
            Tuple of (output tensor [B, D, F, T], next_state dictionary).
        """
        B, D, F, T = x.shape

        # 1. Intra-Frequency BiLSTM
        # Permute to [B * T, F, D] so each time frame is processed independently along F
        x_intra = x.permute(0, 3, 2, 1).contiguous().reshape(B * T, F, D)
        intra_out, _ = self.intra_bilstm(x_intra)
        intra_out = self.intra_proj(intra_out)
        intra_out = self.intra_ln(intra_out)
        x1 = intra_out.view(B, T, F, D).permute(0, 3, 2, 1).contiguous()
        x = x + x1  # Residual 1

        # 2. Inter-Time Causal LSTM
        # Permute to [B * F, T, D] so each frequency bin is processed independently along T
        x_inter = x.permute(0, 2, 3, 1).contiguous().reshape(B * F, T, D)
        if state is None:
            inter_out, _ = self.inter_lstm(x_inter)
            new_lstm_state = None
        else:
            h, c = state["inter_lstm"]
            inter_out, (new_h, new_c) = self.inter_lstm(x_inter, (h, c))
            new_lstm_state = (new_h, new_c)

        inter_out = self.inter_proj(inter_out)
        inter_out = self.inter_ln(inter_out)
        x2 = inter_out.view(B, F, T, D).permute(0, 3, 1, 2).contiguous()
        x = x + x2  # Residual 2

        # 3. Spatial Convolutional Module
        conv1_state = state["conv1"] if state is not None else None
        s1, new_conv1_state = self.conv1(x, conv1_state)
        s1 = self.prelu(s1)

        conv2_state = state["conv2"] if state is not None else None
        s2, new_conv2_state = self.conv2(s1, conv2_state)

        # LayerNorm applied over the channel dimension D
        s2_ln = self.spatial_ln(s2.permute(0, 3, 2, 1)).permute(0, 3, 2, 1).contiguous()
        x = x + s2_ln  # Residual 3

        if state is not None:
            next_state = {
                "inter_lstm": new_lstm_state,
                "conv1": new_conv1_state,
                "conv2": new_conv2_state,
            }
        else:
            next_state = None

        return x, next_state


class EdgeTFGridNet(nn.Module):
    """Compact Causal Edge-TF-GridNet Neural Post-Filter.

    Total parameters: 202,706.
    Input: [B, 4, F, T] where channels are [X1_real, X1_imag, X2_real, X2_imag].
    Output: [B, 2, F, T] where channels are [M_real, M_imag] (Complex Ratio Mask).
    """

    def __init__(
        self,
        in_channels: int = 4,
        out_channels: int = 2,
        emb_dim: int = 24,
        hidden_dim: int = 48,
        num_blocks: int = 3,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.emb_dim = emb_dim
        self.hidden_dim = hidden_dim
        self.num_blocks = num_blocks

        # Input projection 2D convolution
        self.in_conv = CausalConv2d(in_channels, emb_dim, (3, 3))

        # Stacked GridBlocks
        self.blocks = nn.ModuleList(
            [GridBlock(emb_dim, hidden_dim) for _ in range(num_blocks)]
        )

        # Output projection 2D convolution
        self.out_conv = CausalConv2d(emb_dim, out_channels, (3, 3))

    def init_state(
        self, batch_size: int = 1, num_freqs: int = 257, device: torch.device = torch.device("cpu")
    ) -> Dict[str, object]:
        """Initialize zero recurrent and convolutional state buffers for streaming.

        Memory footprint: ~289.13 KB for batch_size=1, num_freqs=257 in FP32.
        """
        state = {
            "in_conv": torch.zeros(
                batch_size, self.in_channels, num_freqs, 2, device=device
            ),
            "blocks": [
                {
                    "inter_lstm": (
                        torch.zeros(
                            1, batch_size * num_freqs, self.hidden_dim, device=device
                        ),
                        torch.zeros(
                            1, batch_size * num_freqs, self.hidden_dim, device=device
                        ),
                    ),
                    "conv1": torch.zeros(
                        batch_size, self.emb_dim, num_freqs, 2, device=device
                    ),
                    "conv2": torch.zeros(
                        batch_size, self.emb_dim * 2, num_freqs, 2, device=device
                    ),
                }
                for _ in range(self.num_blocks)
            ],
            "out_conv": torch.zeros(
                batch_size, self.emb_dim, num_freqs, 2, device=device
            ),
        }
        return state

    def forward(
        self, x: torch.Tensor, state: Optional[Dict[str, object]] = None
    ) -> Tuple[torch.Tensor, Optional[Dict[str, object]]]:
        """Forward pass supporting both batched and frame-by-frame streaming inference.

        Args:
            x: Input tensor [B, 4, F, T].
            state: Optional streaming state dictionary.

        Returns:
            Tuple of (mask tensor [B, 2, F, T], next_state dictionary).
        """
        if state is None:
            # Batch forward pass
            feat, _ = self.in_conv(x)
            for block in self.blocks:
                feat, _ = block(feat)
            mask, _ = self.out_conv(feat)
            return mask, None
        else:
            # Streaming forward pass
            feat, new_in_conv = self.in_conv(x, state["in_conv"])
            new_block_states = []
            for b_idx, block in enumerate(self.blocks):
                feat, b_state = block(feat, state["blocks"][b_idx])
                new_block_states.append(b_state)
            mask, new_out_conv = self.out_conv(feat, state["out_conv"])
            next_state = {
                "in_conv": new_in_conv,
                "blocks": new_block_states,
                "out_conv": new_out_conv,
            }
            return mask, next_state


class StreamingEdgeTFGridNet:
    """Stateful streaming wrapper for EdgeTFGridNet managing audio streaming lifecycle."""

    def __init__(
        self,
        model: EdgeTFGridNet,
        batch_size: int = 1,
        num_freqs: int = 257,
        device: torch.device = torch.device("cpu"),
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self.num_freqs = num_freqs
        self.device = device
        self.model.to(device)
        self.model.eval()
        self.state = self.model.init_state(batch_size, num_freqs, device)

    def reset(self) -> None:
        """Reset all internal recurrent and convolutional states to zero."""
        self.state = self.model.init_state(self.batch_size, self.num_freqs, self.device)

    @torch.no_grad()
    def step(self, x_frame: torch.Tensor) -> torch.Tensor:
        """Process a single 16 ms streaming frame.

        Args:
            x_frame: Tensor of shape [B, 4, F, 1] representing current frame's 4-ch STFT.

        Returns:
            cRM mask tensor of shape [B, 2, F, 1].
        """
        mask_frame, self.state = self.model(x_frame, self.state)
        return mask_frame


def apply_complex_ratio_mask(
    mask: torch.Tensor, mic1_stft: torch.Tensor
) -> torch.Tensor:
    """Apply estimated complex ratio mask to Channel 0 (Reference Microphone 1).

    Formulation:
        Let M = M_r + j M_i be the mask, and X_1 = X_{1,r} + j X_{1,i} be Mic 1.
        S_r = M_r * X_{1,r} - M_i * X_{1,i}
        S_i = M_r * X_{1,i} + M_i * X_{1,r}

    Args:
        mask: Tensor of shape [B, 2, F, T] with [M_r, M_i].
        mic1_stft: Tensor of shape [B, 2, F, T] with [X_{1,r}, X_{1,i}].

    Returns:
        Enhanced complex spectrum tensor of shape [B, 2, F, T].
    """
    m_r = mask[:, 0:1, :, :]
    m_i = mask[:, 1:2, :, :]
    x_r = mic1_stft[:, 0:1, :, :]
    x_i = mic1_stft[:, 1:2, :, :]

    s_r = m_r * x_r - m_i * x_i
    s_i = m_r * x_i + m_i * x_r

    return torch.cat([s_r, s_i], dim=1)

