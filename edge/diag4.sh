#!/bin/bash
echo "=== STEP 1 - CURRENT STATE ==="
wpctl status > state_wpctl_before.txt
wpctl inspect 76 > state_wpctl_inspect_before.txt
bluetoothctl info A8:EF:5F:FF:6E:82 > state_bt_info_before.txt
cat state_wpctl_before.txt
cat state_wpctl_inspect_before.txt
cat state_bt_info_before.txt

echo "=== STEP 2 & 3 - CREATE CONFIG ==="
mkdir -p ~/.config/wireplumber/wireplumber.conf.d/
cat << 'EOF' > ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink ]
}
EOF
cat ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf

echo "=== STEP 4 - RESTART WIREPLUMBER ==="
systemctl --user restart wireplumber
sleep 5

echo "=== STEP 5 - RECONNECT ==="
bluetoothctl connect A8:EF:5F:FF:6E:82
sleep 3
bluetoothctl info A8:EF:5F:FF:6E:82

echo "=== STEP 6 - CHECK PIPEWIRE ==="
wpctl status
# We need to find the new device ID since restarting wireplumber might have changed it!
# wpctl inspect 76 might be wrong now.
# Let's dynamically find it.
DEV_ID=$(wpctl status | grep 'realme narzo 60 5G' | grep bluez5 | awk -F'.' '{print $1}' | awk '{print $NF}')
if [ -z "$DEV_ID" ]; then
    echo "Could not find device in wpctl status"
else
    echo "Device ID: $DEV_ID"
    wpctl inspect "$DEV_ID"
fi

journalctl --user -u wireplumber -n 50 --no-pager
journalctl -u bluetooth -n 50 --no-pager
