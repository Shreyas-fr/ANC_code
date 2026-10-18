#!/bin/bash
echo "=== 1. Bluetooth Info & Show ==="
bluetoothctl info A8:EF:5F:FF:6E:82
bluetoothctl show

echo "=== 2. BlueZ Capabilities & Permissions ==="
systemctl cat bluetooth
systemctl status bluetooth --no-pager
journalctl -u bluetooth --since "30 minutes ago" --no-pager

echo "=== 3. PipeWire/WirePlumber Bluetooth Support ==="
wpctl status
wpctl inspect 76
pw-cli list-objects | grep -i -E 'bluez|bluetooth|a2dp|hfp|hsp'
pw-cli list-objects | grep -i -E 'node|device' | head -100

echo "=== 4. Installed Packages ==="
dpkg -l | grep -iE 'bluez|pipewire|wireplumber|libspa.*bluez'
dpkg -L libspa-0.2-bluetooth 2>/dev/null | head -100

echo "=== 5. WirePlumber & PipeWire User Logs ==="
journalctl --user -u wireplumber --since "30 minutes ago" --no-pager
journalctl --user -u pipewire --since "30 minutes ago" --no-pager

echo "=== 6. Specific Log Search ==="
journalctl --since "30 minutes ago" | grep -iE 'A8:EF:5F:FF:6E:82|denied|reject|access|authorization|a2dp|hfp|hsp|bluez' | tail -n 200

echo "=== 7. SPA Plugin Files ==="
find /usr/lib /usr/lib/aarch64-linux-gnu -iname '*bluez*' -o -iname '*bluetooth*' 2>/dev/null | head -100
