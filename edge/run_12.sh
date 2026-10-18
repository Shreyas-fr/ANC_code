echo "=== 12a ==="
ssh shreyas@shreyas.local 'uptime -s ; uptime'
ssh shreyas@shreyas.local 'ls /var/log/journal 2>&1 ; grep -i Storage /etc/systemd/journald.conf'
ssh shreyas@shreyas.local 'journalctl --list-boots --no-pager'
ssh shreyas@shreyas.local 'journalctl -b -1 --no-pager | tail -60'
ssh shreyas@shreyas.local 'journalctl -b -1 -k --no-pager | grep -i -E "volt|throttl|oom|panic|watchdog|thermal|hwmon" | tail -20'
ssh shreyas@shreyas.local 'dmesg | grep -i -E "under-?volt|throttl|hwmon" | tail -20'

echo "=== 12b ==="
ssh shreyas@shreyas.local 'vcgencmd get_throttled ; vcgencmd measure_temp ; vcgencmd measure_clock arm'
ssh shreyas@shreyas.local 'vcgencmd pmic_read_adc | grep -E "EXT5V_V|VDD_CORE_V|VDD_CORE_A"'
ssh shreyas@shreyas.local 'vcgencmd get_config usb_max_current_enable ; vcgencmd bootloader_config | grep -i -E "PSU_MAX_CURRENT|POWER_OFF"'
ssh shreyas@shreyas.local 'free -m ; df -h / ; ps -eo pid,etime,%cpu,%mem,cmd --sort=-%cpu | head -15'

echo "=== 12c ==="
ssh shreyas@shreyas.local 'find ~/sih26052_edge -name "*.hk" -exec sha256sum {} +'
ssh shreyas@shreyas.local 'sha256sum ~/sih26052_edge/anc_fix_v2/anc_fix/streaming_core.py ~/sih26052_edge/anc_fix_v2/anc_fix/dfn3_enhance.py || echo "Files not found"'
ssh shreyas@shreyas.local '/home/shreyas/env/bin/python -c "import hk; print(\"hk importable\")" || echo "hk import failed" ; /home/shreyas/env/bin/pip list | grep -i -E "hknt|torch|numpy|scipy|deepfilter"'

echo "=== 12d ==="
ssh shreyas@shreyas.local 'bluetoothctl devices'
ssh shreyas@shreyas.local 'pw-dump | jq -r ".[] | select(.info.props[\"media.class\"]==\"Audio/Source\") | .info.props[\"node.name\"]" || pw-dump | grep -A 20 "Audio/Source"'
