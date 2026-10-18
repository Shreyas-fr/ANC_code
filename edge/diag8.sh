#!/bin/bash

export XDG_RUNTIME_DIR=/run/user/1000
echo "=== PHASE 1 - DISCOVER NOISE BUDS VS102 ==="
echo "Starting scan..."
bluetoothctl --timeout 15 scan on > scan_results.txt 2>&1
echo "Scan complete. Looking for Noise Buds or VS102..."

# Parse scan results to find the MAC address of "Noise Buds" or "VS102"
MAC=""
grep -i -E "Noise Buds|VS102" scan_results.txt | grep -E "Device [0-9A-F:]+" | head -n 1 > found_device.txt

if [ -s found_device.txt ]; then
    MAC=$(cat found_device.txt | grep -o -E "([0-9A-F]{2}:){5}[0-9A-F]{2}")
    NAME=$(cat found_device.txt | sed -E 's/.*Device ([0-9A-F:]+) //')
    echo "Found VS102 at MAC: $MAC with Name: $NAME"
else
    # Also check `bluetoothctl devices` in case it was already discovered but not in this scan
    bluetoothctl devices > current_devices.txt
    grep -i -E "Noise Buds|VS102" current_devices.txt > found_device.txt
    if [ -s found_device.txt ]; then
        MAC=$(cat found_device.txt | grep -o -E "([0-9A-F]{2}:){5}[0-9A-F]{2}" | head -n 1)
        NAME=$(cat found_device.txt | head -n 1 | sed -E 's/.*Device ([0-9A-F:]+) //')
        echo "Found VS102 in known devices at MAC: $MAC with Name: $NAME"
    else
        echo "VS102 not discovered."
        cat scan_results.txt
        echo "FAILURE_LAYER=A"
        exit 1
    fi
fi

echo "=== PHASE 2 - PAIR AND CONNECT ==="
echo "Pairing $MAC..."
bluetoothctl pair $MAC
sleep 3
echo "Trusting $MAC..."
bluetoothctl trust $MAC
sleep 1
echo "Connecting $MAC..."
bluetoothctl connect $MAC
sleep 5

INFO=$(bluetoothctl info $MAC)
echo "$INFO"

if echo "$INFO" | grep -q "Connected: yes"; then
    echo "Connection successful."
else
    echo "Connection failed."
    echo "FAILURE_LAYER=C"
    exit 1
fi

echo "=== PHASE 3 - DETERMINE AUDIO PROFILE CAPABILITY ==="
echo "$INFO" | grep -E "UUID|Alias|Name|Paired|Trusted|Connected"

echo "=== PHASE 4 - PIPEWIRE / WIREPLUMBER INSPECTION ==="
wpctl status > wp_status.txt
cat wp_status.txt
DEV_ID=$(wpctl status | grep -i "bluez5" | grep -i -E "Noise|VS102" | awk -F'.' '{print $1}' | tr -d ' *' | awk '{print $1}')
echo "VS102 PipeWire Device ID: $DEV_ID"
if [ -n "$DEV_ID" ]; then
    wpctl inspect $DEV_ID
fi

pw-cli list-objects | grep -i -E 'bluez|Noise|VS102|a2dp|hfp|hsp' > pw_objects.txt

echo "=== PHASE 5 - BLUEZ TRANSPORT DIAGNOSTICS ==="
MAC_UNDERSCORE=$(echo $MAC | sed 's/:/_/g')
busctl tree org.bluez | grep -A 10 "dev_$MAC_UNDERSCORE" > bluez_tree.txt
cat bluez_tree.txt

TRANSPORT=$(cat bluez_tree.txt | grep -o "fd[0-9]*" | head -n 1)
if [ -n "$TRANSPORT" ]; then
    TRANSPORT_PATH=$(busctl tree org.bluez | grep -o "/org/bluez/hci0/dev_$MAC_UNDERSCORE/sep[0-9]*/$TRANSPORT" | head -n 1)
    if [ -n "$TRANSPORT_PATH" ]; then
        echo "Transport path: $TRANSPORT_PATH"
        busctl introspect org.bluez $TRANSPORT_PATH
    fi
else
    echo "No transport found."
fi

echo "=== PHASE 6 - ACTIVATE MICROPHONE PROFILE IF AVAILABLE ==="
# Check if a source already exists
SOURCE_NODE=$(wpctl status | awk '/Sources:/,/Filters:/' | grep -i -E "Noise|VS102" | grep 'vol' | awk -F'.' '{print $1}' | tr -d ' *' | awk '{print $1}')

if [ -z "$SOURCE_NODE" ] && [ -n "$DEV_ID" ]; then
    echo "No source node found. Attempting to switch profile to HFP/HSP (headset-head-unit)..."
    # Find profile ID for headset-head-unit or similar
    # Typically HFP is index 2, or named 'headset-head-unit'
    # Use pw-cli to dump profiles
    pw-cli enum-params $DEV_ID EnumProfile > profiles.txt
    cat profiles.txt
    HFP_INDEX=$(cat profiles.txt | grep -B 1 "headset-head-unit" | grep "index" | grep -o "[0-9]*" | head -1)
    if [ -n "$HFP_INDEX" ]; then
        echo "Setting profile to $HFP_INDEX (headset-head-unit)"
        wpctl set-profile $DEV_ID $HFP_INDEX
        sleep 3
    else
        echo "Could not find HFP profile index."
    fi
fi

# Recheck source node
wpctl status > wp_status_new.txt
SOURCE_NODE=$(cat wp_status_new.txt | awk '/Sources:/,/Filters:/' | grep -i -E "Noise|VS102" | grep 'vol' | awk -F'.' '{print $1}' | tr -d ' *' | awk '{print $1}')

echo "=== PHASE 7 & 8 - VERIFY REAL MICROPHONE AUDIO ==="
if [ -n "$SOURCE_NODE" ]; then
    echo "Microphone source found! ID: $SOURCE_NODE"
    mkdir -p ~/sih26052-edge/audio
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FILE_PATH="$HOME/sih26052-edge/audio/vs102_mic_test_${TIMESTAMP}.wav"
    
    echo "Please speak a short test sentence into the earbuds now. Recording for 10 seconds..."
    pw-record --target $SOURCE_NODE -d 10 "$FILE_PATH"
    
    echo "Recording complete: $FILE_PATH"
    ls -l "$FILE_PATH"
    
    echo "Analyzing audio..."
    # Generate python script for analysis
    cat << 'EOF' > analyze_audio.py
import sys
import wave
import math

filepath = sys.argv[1]
try:
    with wave.open(filepath, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        duration = frames / float(rate)
        
        raw_data = wf.readframes(frames)
        
        # calculate RMS
        sum_sq = 0.0
        peak = 0
        if sampwidth == 2:
            import struct
            samples = struct.unpack(f"<{frames*channels}h", raw_data)
            for s in samples:
                sum_sq += s*s
                if abs(s) > peak:
                    peak = abs(s)
            rms = math.sqrt(sum_sq / len(samples)) if len(samples) > 0 else 0
        else:
            rms = -1
            peak = -1
            
        print(f"duration: {duration}s")
        print(f"sample_rate: {rate} Hz")
        print(f"channels: {channels}")
        print(f"sampwidth: {sampwidth} bytes")
        print(f"rms: {rms}")
        print(f"peak: {peak}")
        
        if peak == 0:
            print("speech_detected: NO (completely silent)")
        else:
            print("speech_detected: YES (non-zero audio)")
except Exception as e:
    print(f"Error analyzing audio: {e}")
EOF
    python3 analyze_audio.py "$FILE_PATH"
else
    echo "No microphone source found."
    echo "FAILURE_LAYER=G"
fi
