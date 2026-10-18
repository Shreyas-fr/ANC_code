import os
import re
import numpy as np

log_file = os.path.expanduser("~/anc_tests/pi_live.log")

with open(log_file, "r") as f:
    content = f.read()

power_matches = re.findall(r'POWER: ([\d\.]+) ([\d\.]+)V ([\d\.]+)A (0x[\da-fA-F]+) ([\d\.]+)C', content)
ext5v_list = [float(m[1]) for m in power_matches]
vdd_list = [float(m[2]) for m in power_matches]
throt_set = set([m[3] for m in power_matches])
temp_list = [float(m[4]) for m in power_matches]

udp_matches = re.findall(r'UDP: uptime=([\d\.]+) stage=[\w]+ bg=([\d\.]+)ms blk_ms=([\d\.]+) blk_done=(\d+) q=(\d+)', content)
bg_list = [float(m[1]) for m in udp_matches]
blk_ms_list = [float(m[2]) for m in udp_matches]
uptime_list = [float(m[0]) for m in udp_matches]

print(f"UDP lines found: {len(udp_matches)}")
if len(ext5v_list) > 0:
    print(f"EXT5V_V min/mean/max: {min(ext5v_list):.2f}/{np.mean(ext5v_list):.2f}/{max(ext5v_list):.2f}")
    print(f"VDD_CORE_A max: {max(vdd_list):.2f}")
    print(f"Max temp: {max(temp_list):.2f}")
    print(f"Throttled seen: {throt_set}")
    
if len(bg_list) > 0:
    print(f"Backlog p50/p95/max: {np.percentile(bg_list, 50):.2f}/{np.percentile(bg_list, 95):.2f}/{max(bg_list):.2f}")
    print(f"Backlog > 300 ms: {sum(x > 300 for x in bg_list)}")
    print(f"Backlog > 1000 ms: {sum(x > 1000 for x in bg_list)}")
    
if len(blk_ms_list) > 0:
    print(f"Block-call p50/p95/max: {np.percentile(blk_ms_list, 50):.2f}/{np.percentile(blk_ms_list, 95):.2f}/{max(blk_ms_list):.2f}")

print("\nLast 20 UDP lines:")
for m in udp_matches[-20:]:
    print(f"UDP: uptime={m[0]} bg={m[1]}ms blk_ms={m[2]} blk_done={m[3]} q={m[4]}")
