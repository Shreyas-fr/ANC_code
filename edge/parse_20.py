import os
import re
import numpy as np
import json
import soundfile as sf
import sys

def parse():
    log_file = os.path.expanduser("~/anc_tests/pi_live_E.log")
    if not os.path.exists(log_file):
        print("pi_live_E.log not found yet")
        return

    with open(log_file, "r") as f:
        content = f.read()

    # POWER: 1004.15 4.96872V 1.94674A 0x0 57.1C 2400000000Hz 383844kB
    power_matches = re.findall(r'POWER: ([\d\.]+) ([\d\.]+)V ([\d\.]+)A (0x[\da-fA-F]+) ([\d\.]+)C (\d+)Hz (\d+)kB', content)
    ext5v_list = [float(m[1]) for m in power_matches]
    vdd_list = [float(m[2]) for m in power_matches]
    throt_set = set([m[3] for m in power_matches])
    temp_list = [float(m[4]) for m in power_matches]
    clock_list = [int(m[5]) for m in power_matches]
    mem_list = [int(m[6]) for m in power_matches]

    udp_matches = re.findall(r'UDP: uptime=([\d\.]+) stage=[\w]+ bg=([\d\.]+)ms blk_ms=([\d\.]+) blk_done=(\d+) q=(\d+)', content)
    bg_list = [float(m[1]) for m in udp_matches]
    blk_ms_list = [float(m[2]) for m in udp_matches]
    uptime_list = [float(m[0]) for m in udp_matches]

    if "ABORTED" in content:
        abort_match = re.search(r'ABORTED (.*)', content)
        print(f"\n!!! ABORTED RECEIVED: {abort_match.group(1)} !!!\n")

    print(f"UDP lines found: {len(udp_matches)}")
    if len(ext5v_list) > 0:
        print(f"EXT5V_V min/mean/max: {min(ext5v_list):.2f}/{np.mean(ext5v_list):.2f}/{max(ext5v_list):.2f}")
        print(f"Number of samples < 4.80: {sum(x < 4.80 for x in ext5v_list)}")
        print(f"VDD_CORE_A max: {max(vdd_list):.2f}")
        print(f"Max temp: {max(temp_list):.2f}")
        print(f"Throttled seen: {throt_set}")
        print(f"Arm clock min/max: {min(clock_list)} / {max(clock_list)}")
        print(f"MemAvailable min: {min(mem_list)} kB")
        
    if len(bg_list) > 0:
        print(f"Backlog p50/p95/max: {np.percentile(bg_list, 50):.2f}/{np.percentile(bg_list, 95):.2f}/{max(bg_list):.2f}")
        print(f"Backlog > 300 ms: {sum(x > 300 for x in bg_list)}")
        print(f"Backlog > 1000 ms: {sum(x > 1000 for x in bg_list)}")
        
    if len(blk_ms_list) > 0:
        print(f"Block-call p50/p95/max: {np.percentile(blk_ms_list, 50):.2f}/{np.percentile(blk_ms_list, 95):.2f}/{max(blk_ms_list):.2f}")

    print("\nLast 20 UDP lines:")
    for m in udp_matches[-20:]:
        print(f"UDP: uptime={m[0]} bg={m[1]}ms blk_ms={m[2]} blk_done={m[3]} q={m[4]}")
        
    e_json_path = "E.json"
    if os.path.exists(e_json_path):
        try:
            with open(e_json_path, "r") as f:
                ej = json.load(f)
            print("\nSender Summary (E.json):")
            print(f"Frames sent: {ej.get('frames_sent')}")
            print(f"Frames dropped: {ej.get('frames_dropped')}")
            
            # calculate jitter from intervals if present
            intervals = ej.get('send_intervals_ms', [])
            if intervals:
                print(f"Send-interval jitter p95/p99/max: {np.percentile(intervals, 95):.2f} / {np.percentile(intervals, 99):.2f} / {max(intervals):.2f} ms")
        except Exception as e:
            print(f"Error reading E.json: {e}")
            
    wav_path = os.path.expanduser("~/anc_tests/E_raw.wav")
    if os.path.exists(wav_path):
        try:
            data, sr = sf.read(wav_path)
            duration = len(data) / sr
            peak = np.max(np.abs(data))
            rms = np.sqrt(np.mean(data**2))
            
            print("\nRecorder Stats (E_raw.wav):")
            print(f"Duration: {duration:.2f}s")
            print(f"Peak: {peak:.4f}")
            print(f"RMS: {rms:.4f}")
        except Exception as e:
            print(f"Error reading E_raw.wav: {e}")

if __name__ == "__main__":
    parse()
