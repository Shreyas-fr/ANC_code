import pandas as pd

# Last 30 rows of power CSV
df_power = pd.read_csv("power_paced.csv")
print("=== Last 30 rows of power CSV ===")
print(df_power[['uptime_s', 'EXT5V_V', 'VDD_CORE_A', 'throttled']].tail(30).to_string(index=False))

# Episodes in dfn3_paced_t2.csv
print("\n=== Backlog > 300 ms Episodes ===")
df_paced = pd.read_csv("dfn3_paced_t2.csv", names=['timestamp', 'duration_ms', 'backlog_ms'])
# compute seconds since stage start
start_ts = df_paced['timestamp'].iloc[0]
df_paced['sec'] = df_paced['timestamp'] - start_ts

in_episode = False
ep_start = 0
ep_peak = 0
episodes = []

for _, row in df_paced.iterrows():
    b = row['backlog_ms']
    t = row['sec']
    if b > 300:
        if not in_episode:
            in_episode = True
            ep_start = t
            ep_peak = b
        else:
            if b > ep_peak:
                ep_peak = b
    else:
        if in_episode:
            in_episode = False
            episodes.append((ep_start, t, ep_peak))

if in_episode:
    episodes.append((ep_start, df_paced['sec'].iloc[-1], ep_peak))

for (st, en, pk) in episodes:
    print(f"Start: {st:.2f}s, End: {en:.2f}s, Peak: {pk:.2f}ms")

if episodes:
    print("\nThey occur throughout the run (or cluster near the end).")

last_power_uptime = df_power['uptime_s'].iloc[-1]
last_power_epoch = df_power['epoch'].iloc[-1]
last_paced_epoch = df_paced['timestamp'].iloc[-1]
diff = last_power_epoch - last_paced_epoch
print(f"\nSeconds between last power CSV row and last paced CSV row: {diff:.2f}s")
