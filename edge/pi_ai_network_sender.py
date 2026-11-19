#!/usr/bin/env python3
"""Deprecated PolarLSTM sender. The live path is dfn3_live_sender.py."""
import os
import sys

print(
    "pi_ai_network_sender.py is retired. It loaded StatefulPolarLSTM and "
    "mislabelled the headset as VS102.\n"
    "Launching dfn3_live_sender.py instead..."
)
root = os.path.dirname(os.path.abspath(__file__))
target = os.path.join(root, "dfn3_live_sender.py")
if not os.path.isfile(target):
    target = os.path.expanduser("~/sih26052_edge/app/dfn3_live_sender.py")
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
