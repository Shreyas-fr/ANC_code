"""Training-only FullSubNet frequency-group helper.

The upstream model imports ``drop_band`` from a module that also imports
librosa. The canonical adapter runs batch size one, so upstream never calls
this training-time helper during inference. This local implementation keeps
the model import independent of librosa and matches the upstream helper for
batch sizes greater than one.
"""

import torch


def drop_band(input: torch.Tensor, num_groups: int = 2) -> torch.Tensor:
    """Partition frequency bands across samples as upstream FullSubNet does."""
    batch_size, _, num_freqs, _ = input.shape
    if batch_size <= num_groups:
        raise ValueError(
            f"batch_size={batch_size} must exceed num_groups={num_groups}"
        )
    if num_groups <= 1:
        return input
    if num_freqs % num_groups:
        input = input[..., : num_freqs - (num_freqs % num_groups), :]
        num_freqs = input.shape[2]
    groups = []
    for group_idx in range(num_groups):
        sample_indices = torch.arange(group_idx, batch_size, num_groups, device=input.device)
        freq_indices = torch.arange(group_idx, num_freqs, num_groups, device=input.device)
        selected_samples = torch.index_select(input, dim=0, index=sample_indices)
        groups.append(torch.index_select(selected_samples, dim=2, index=freq_indices))
    return torch.cat(groups, dim=0)
