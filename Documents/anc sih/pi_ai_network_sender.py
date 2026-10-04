#!/usr/bin/env python3
"""Deprecated PolarLSTM sender. Forwards to the DFN3 live sender."""
import os
import sys

print("Root pi_ai_network_sender.py is retired. Forwarding to dfn3_live_sender.py")
target = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "runs",
    "final_model",
    "dfn3_live_sender.py",
)
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
