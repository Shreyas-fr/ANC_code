"""Canonical UDP 5006 telemetry field names and aliases from older senders."""

ALIASES = {
    "latency_ms": ("latency_ms", "processing_ms"),
    "latency_median_ms": ("latency_median_ms", "median_ms"),
    "latency_p95_ms": ("latency_p95_ms", "p95_ms"),
    "latency_p99_ms": ("latency_p99_ms", "p99_ms"),
    "latency_max_ms": ("latency_max_ms", "max_ms"),
    "nan_inf_events": ("nan_inf_events", "nans"),
    "state_resets": ("state_resets", "resets"),
    "buffer_underruns": ("buffer_underruns", "underruns", "capture_short_reads"),
}


def first_present(data: dict, keys: tuple):
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return None


def normalize_telemetry(data: dict) -> dict:
    if not data:
        return {}
    out = dict(data)
    for canonical, keys in ALIASES.items():
        val = first_present(data, keys)
        if val is not None:
            out[canonical] = val
    if "model" in out and isinstance(out["model"], str):
        low = out["model"].lower()
        if "polar" in low:
            # Do not silently rewrite history, but the live UI should not look like PolarLSTM
            # is the deployed engine when the operator froze DFN3. Keep the payload, flag it.
            out["model_is_stale"] = True
    return out
