#!/bin/bash
echo "--- HOSTNAME ---"
hostname
echo -e "\n--- UNAME ---"
uname -a
echo -e "\n--- OS RELEASE ---"
cat /etc/os-release
echo -e "\n--- BLUETOOTH CONTROLLER ---"
bluetoothctl show
echo -e "\n--- BLUETOOTH SERVICE STATUS ---"
systemctl status bluetooth --no-pager
echo -e "\n--- BLUETOOTH DEVICES ---"
bluetoothctl devices
echo -e "\n--- BLUETOOTH PAIRED DEVICES ---"
bluetoothctl paired-devices
echo -e "\n--- SIH EDGE SERVICE STATUS ---"
systemctl --user status sih26052-edge.service || systemctl status sih26052-edge.service
echo -e "\n--- WPCTL STATUS ---"
wpctl status || echo "wpctl not found or not running"
echo -e "\n--- PACTL INFO ---"
pactl info || echo "pactl not found"
echo -e "\n--- PACTL LIST SINKS ---"
pactl list short sinks || echo "pactl not found"
echo -e "\n--- PACTL LIST SOURCES ---"
pactl list short sources || echo "pactl not found"
echo -e "\n--- ALSA RECORD DEVICES ---"
arecord -l || echo "arecord not found"
echo -e "\n--- ALSA PLAYBACK DEVICES ---"
aplay -l || echo "aplay not found"
