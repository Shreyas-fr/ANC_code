#!/usr/bin/env python3
"""
Phase 9: PC-side UDP packet statistics receiver.
Runs on the PC, listens on port 5005, records:
  - packets received
  - packets lost (sequence gaps)
  - duplicates
  - out-of-order
  - packet loss %

Does NOT run AI inference. Does NOT play audio (statistics only).
Run this in parallel with the frontend for stats capture,
OR use this standalone for network-only verification.

Usage:
  python3 pc_stats_receiver.py [duration_seconds]
  
Defaults to 70 seconds (covers 60s test + margin).
"""
import socket
import struct
import time
import sys
import json
import os

PORT = 5005
PACKET_SIZE = 1032
PACKET_SAMPLES = 256

def run(duration=70):
    print(f"=== PC Stats Receiver (port {PORT}) ===")
    print(f"  Listening for {duration}s...")
    print(f"  Expected packet size: {PACKET_SIZE} bytes")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    sock.settimeout(0.1)

    packets_received = 0
    packets_lost = 0
    duplicates = 0
    out_of_order = 0
    malformed = 0
    last_seq = None
    first_seq = None
    t_start = time.monotonic()
    t_first_packet = None

    try:
        while (time.monotonic() - t_start) < duration:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue

            now = time.monotonic()
            if t_first_packet is None:
                t_first_packet = now
                print(f"  First packet from {addr[0]} at t+{now-t_start:.2f}s")

            if len(data) < 8:
                malformed += 1
                continue

            seq = struct.unpack('<Q', data[:8])[0]

            if first_seq is None:
                first_seq = seq

            if last_seq is None:
                packets_received += 1
                last_seq = seq
            elif seq == last_seq + 1:
                packets_received += 1
                last_seq = seq
            elif seq == last_seq:
                duplicates += 1
            elif seq < last_seq:
                out_of_order += 1
            else:
                gap = seq - (last_seq + 1)
                packets_lost += gap
                packets_received += 1
                last_seq = seq

    except KeyboardInterrupt:
        pass

    sock.close()

    total_expected = packets_received + packets_lost
    loss_pct = 100.0 * packets_lost / total_expected if total_expected > 0 else 0.0
    actual_duration = time.monotonic() - t_start

    print(f"\n=== Network Statistics ===")
    print(f"  Duration:          {actual_duration:.2f}s")
    print(f"  Packets received:  {packets_received}")
    print(f"  Packets lost:      {packets_lost}")
    print(f"  Packet loss:       {loss_pct:.4f}%")
    print(f"  Duplicates:        {duplicates}")
    print(f"  Out-of-order:      {out_of_order}")
    print(f"  Malformed:         {malformed}")
    print(f"  First seq:         {first_seq}")
    print(f"  Last seq:          {last_seq}")

    stats = {
        'duration_s': actual_duration,
        'packets_received': packets_received,
        'packets_lost': packets_lost,
        'loss_pct': loss_pct,
        'duplicates': duplicates,
        'out_of_order': out_of_order,
        'malformed': malformed,
        'first_seq': first_seq,
        'last_seq': last_seq,
    }

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'network_pc_stats.json')
    with open(out, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Stats saved to: {out}")

    # Print pass/fail
    ok = loss_pct < 1.0 and duplicates == 0
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'} (loss={loss_pct:.2f}%, dup={duplicates})")

    return stats


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 70
    run(duration)
