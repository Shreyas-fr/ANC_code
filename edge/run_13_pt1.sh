echo "=== Boot start of the old PolarLSTM ==="
ssh shreyas@shreyas.local 'systemctl --user cat sih26052-edge.service ; systemctl --user is-enabled sih26052-edge.service ; systemctl --user is-active sih26052-edge.service'
ssh shreyas@shreyas.local 'loginctl show-user shreyas | grep -i linger ; ls -l ~/.config/systemd/user ~/.config/autostart ~/.config/labwc /etc/xdg/autostart 2>&1'
ssh shreyas@shreyas.local 'crontab -l ; sudo crontab -l ; grep -rn "anc_stream\|sih26052" ~/.bashrc ~/.profile ~/.config/labwc 2>/dev/null'

echo "=== Power / storage ==="
ssh shreyas@shreyas.local 'lsblk -o NAME,SIZE,TRAN,MODEL,MOUNTPOINT ; lsusb'
ssh shreyas@shreyas.local 'for f in /proc/device-tree/chosen/power/*; do echo $f; xxd $f; done 2>&1'
ssh shreyas@shreyas.local 'vcgencmd bootloader_config ; vcgencmd pmic_read_adc'
ssh shreyas@shreyas.local 'dmesg | grep -i -E "usb|sda|ext4|i/o error|reset|over-?current" | tail -40'

echo "=== Load and bloat ==="
ssh shreyas@shreyas.local 'systemctl get-default ; systemctl list-units --type=service --state=running --no-pager'
ssh shreyas@shreyas.local 'ls -la ~ ~/sih26052_edge ; du -h --max-depth=2 ~ 2>/dev/null | sort -rh | head -30 ; ls -la /tmp | head -40'
ssh shreyas@shreyas.local 'ls ~/sih26052_edge | grep -i anc_fix ; find ~ -name "__pycache__" -type d -prune | wc -l ; du -sh ~/.cache 2>/dev/null'
ssh shreyas@shreyas.local 'find ~ -maxdepth 4 \( -name "*.zip" -o -name "*.wav" -o -name "*.log" \) -size +1M 2>/dev/null'
