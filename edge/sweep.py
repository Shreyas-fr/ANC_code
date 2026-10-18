import json
from test_sender_v5_e2e import run_v5, decode

configs = [
    ("base",         0.0,  ["--block-ms", "500", "--context-ms", "300", "--jitter-ms", "320", "--threads", "1"]),
    ("expensive",    0.45, ["--block-ms", "500", "--context-ms", "300", "--jitter-ms", "320", "--threads", "1"]),
    ("cheap",        0.1,  ["--block-ms", "500", "--context-ms", "300", "--jitter-ms", "320", "--threads", "1"]),
    ("tight budget", 0.45, ["--block-ms", "500", "--context-ms", "300", "--jitter-ms", "120", "--threads", "1"])
]

print(f"{'Config':<15} | {'Fallback %':<10} | {'Fallback Fr':<12} | {'Resets':<6} | {'Max Backlog':<11} | {'Lat P50':<7} | {'Lat Max':<7}")
print("-" * 85)

for name, sleep_s, extra in configs:
    try:
        a, t, i = run_v5("dfn3", sleep_s, extra=extra, duration=7)
        if not t:
            print(f"{name:<15} | ERROR: NO TELEMETRY")
            continue
        last = json.loads(t[-1])
        pct = last.get("fallback_pct", 0)
        frames = last.get("fallback_frames", 0)
        resets = last.get("chain_resets", 0)
        backlog = last.get("backlog_max", 0)
        p50 = last.get("latency_median_ms", 0)
        mx = last.get("max_ms", 0)
        print(f"{name:<15} | {pct:<10} | {frames:<12} | {resets:<6} | {backlog:<11} | {p50:<7} | {mx:<7}")
    except Exception as e:
        print(f"{name:<15} | ERROR: {e}")
