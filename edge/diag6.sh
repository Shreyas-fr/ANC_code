#!/bin/bash
echo "=== STEP 1 - CURRENT STATE ==="
wpctl status
DEV_ID=$(wpctl status | grep 'realme narzo 60 5G' | grep bluez5 | awk -F'.' '{print $1}' | awk '{print $NF}')
echo "DEV_ID BEFORE: $DEV_ID"
wpctl inspect $DEV_ID
bluetoothctl info A8:EF:5F:FF:6E:82
cat ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf

echo "=== STEP 2 - REMOVE FILE ==="
rm -f ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf
test ! -e ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf && echo "REMOVED"

echo "=== STEP 3 - RESTART WIREPLUMBER ==="
systemctl --user restart wireplumber
sleep 5

echo "=== STEP 4 - RECONNECT PHONE ==="
bluetoothctl connect A8:EF:5F:FF:6E:82
sleep 3
bluetoothctl info A8:EF:5F:FF:6E:82

echo "=== STEP 5 - CHECK PIPEWIRE ==="
wpctl status
NEW_DEV_ID=$(wpctl status | grep 'realme narzo 60 5G' | grep bluez5 | awk -F'.' '{print $1}' | awk '{print $NF}')
echo "DEV_ID AFTER: $NEW_DEV_ID"
wpctl inspect $NEW_DEV_ID
pw-cli list-objects | grep -i -E 'bluez|bluetooth|realme|a2dp'

echo "=== STEP 6 - CHECK THE MEDIA TRANSPORT ==="
busctl tree org.bluez
TRANSPORT=$(busctl tree org.bluez | grep 'fd' | awk '{print $1}' | head -1 | sed 's/├─//g; s/└─//g; s/│//g; s/ //g')
if [ -n "$TRANSPORT" ]; then
    echo "Found Transport: $TRANSPORT"
    busctl introspect org.bluez $TRANSPORT
else
    echo "No MediaTransport found in tree"
fi

echo "=== STEP 7 - PLAY ACTUAL AUDIO FROM THE PHONE ==="
sleep 15  # wait up to 15 seconds for user to initiate playback manually
echo "Checking wpctl status again..."
wpctl status
if [ -n "$TRANSPORT" ]; then
    echo "Checking transport again..."
    busctl introspect org.bluez $TRANSPORT
fi

echo "=== STEP 8 & 9 - CAPTURE IF SOURCE EXISTS ==="
# Determine if a source node appeared
SOURCE_NODE=$(wpctl status | awk '/Sources:/,/Filters:/' | grep 'realme' | grep 'vol' | awk -F'.' '{print $1}' | tr -d ' *' | awk '{print $1}')

if [ -n "$SOURCE_NODE" ]; then
    echo "Source node found: $SOURCE_NODE. Capturing audio..."
    pw-record --target $SOURCE_NODE ~/bluetooth_test_capture.wav &
    PW_PID=$!
    sleep 5
    kill $PW_PID
    echo "Capture complete."
    ls -l ~/bluetooth_test_capture.wav
else
    echo "No source node found to capture."
fi
