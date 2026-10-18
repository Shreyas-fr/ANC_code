#!/usr/bin/env bash
# Stop PolarLSTM / duplicate live audio processes. Run on the Pi before DFN3 demo.
set -euo pipefail
echo "Disabling stale PolarLSTM unit (sih26052-edge.service)..."
systemctl --user stop sih26052-edge.service 2>/dev/null || true
systemctl --user disable sih26052-edge.service 2>/dev/null || true
systemctl --user stop sih26052-dfn3.service 2>/dev/null || true

echo "Sending SIGTERM to leftover live processors..."
pkill -f "/app/anc_stream.py" 2>/dev/null || true
pkill -f "pi_ai_network_sender.py" 2>/dev/null || true
pkill -f "vs102_ai_stream.py" 2>/dev/null || true
pkill -f "dfn3_live_sender.py" 2>/dev/null || true
sleep 1
echo "Remaining matching processes:"
ps -eo pid,args | grep -E "anc_stream|dfn3_live|pi_ai_network|deep-filter|vs102_ai" | grep -v grep || echo "(none)"
echo "Done. Start exactly one sender:"
echo "  python3 ~/sih26052_edge/app/dfn3_live_sender.py --mode raw|resample|dfn3 --pc-ip <MAC_IP> --replace"
