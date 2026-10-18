#!/bin/bash
echo "=== 1. WirePlumber Version ==="
wireplumber --version
wpctl --version

echo "=== 2. Existing Config Locations ==="
find /usr/share/wireplumber /etc/wireplumber ~/.config/wireplumber -maxdepth 4 -type f 2>/dev/null | sort

echo "=== 3. Search Installed Config ==="
grep -RniE 'bluez|a2dp|hfp|hsp|auto-connect|profile' /usr/share/wireplumber /etc/wireplumber ~/.config/wireplumber 2>/dev/null | head -300

echo "=== 6. User/System Overrides ==="
grep -RniE 'bluez5|bluez|monitor.bluez|a2dp|hfp|hsp' ~/.config/wireplumber /etc/wireplumber 2>/dev/null

echo "=== 7. Environment ==="
wpctl status
wpctl inspect 76
