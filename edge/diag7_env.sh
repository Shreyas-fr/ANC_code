#!/bin/bash
echo "=== SYSTEM INFO ==="
cat /etc/os-release | grep PRETTY_NAME
uname -a
bluetoothctl -v
pipewire --version
wireplumber --version
wpctl status | grep -i server -A 2

echo "=== BLUETOOTH CONTROLLER ==="
bluetoothctl list

echo "=== BLUETOOTH DEVICES ==="
bluetoothctl devices

echo "=== PAIRED DEVICES ==="
bluetoothctl paired-devices

echo "=== WPCTL STATUS ==="
wpctl status
