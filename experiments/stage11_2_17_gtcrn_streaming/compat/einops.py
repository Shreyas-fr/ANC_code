"""Narrow exact shim for the sole einops expression used by pinned GTCRN.

Equivalent to rearrange(x, 'b c g t f -> b (c g) t f') for contiguous tensors.
It avoids installing a package in the existing evaluation environment.
"""

def rearrange(x, pattern):
    if pattern != "b c g t f -> b (c g) t f" or x.ndim != 5:
        raise NotImplementedError(f"isolated GTCRN shim does not implement {pattern!r}")
    return x.reshape(x.shape[0], x.shape[1] * x.shape[2], x.shape[3], x.shape[4])
