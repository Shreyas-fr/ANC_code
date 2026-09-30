#!/bin/bash
echo "=== 1. INSPECT THE BLUETOOTH DEVICE OBJECT ==="
wpctl status
DEV_ID=$(wpctl status | grep 'realme narzo 60 5G' | grep bluez5 | awk -F'.' '{print $1}' | awk '{print $NF}')
echo "DEV_ID: $DEV_ID"
wpctl inspect $DEV_ID
pw-cli info $DEV_ID

echo "=== 2. LIST ALL BLUEZ OBJECTS ==="
pw-cli list-objects | grep -i -E 'bluez|bluetooth|realme|a2dp'
wpctl status -n

echo "=== 3. INSPECT BLUEZ DEVICE PARAMETERS ==="
pw-cli enum-params $DEV_ID Profile
pw-cli enum-params $DEV_ID Props
pw-cli enum-params $DEV_ID EnumProfile

echo "=== 4. INSPECT WIREPLUMBER LOGS ==="
journalctl --user -u wireplumber --since "15 minutes ago" --no-pager

echo "=== 5. INSPECT PIPEWIRE LOGS ==="
journalctl --user -u pipewire --since "15 minutes ago" --no-pager

echo "=== 6. CHECK CURRENT CONFIGURATION ==="
cat ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf
grep -RniE 'bluez5.roles|bluez5.auto-connect|monitor.bluez' /usr/share/wireplumber /etc/wireplumber ~/.config/wireplumber 2>/dev/null

echo "=== 7. CHECK BLUEZ CONNECTION DETAILS ==="
bluetoothctl info A8:EF:5F:FF:6E:82
busctl introspect org.bluez /org/bluez/hci0/dev_A8_EF_5F_FF_6E_82 org.bluez.Device1

echo "=== 8. CHECK WHETHER THE PHONE IS ACTUALLY STREAMING A2DP ==="
busctl tree org.bluez
# Also introspect MediaTransport if it exists:
TRANSPORT=$(busctl tree org.bluez | grep MediaTransport | awk '{print $1}' | head -1 | sed 's/├─//g; s/└─//g; s/│//g; s/ //g')
if [ -n "$TRANSPORT" ]; then
    echo "Found Transport: $TRANSPORT"
    busctl introspect org.bluez $TRANSPORT
else
    echo "No MediaTransport found in tree"
fi
