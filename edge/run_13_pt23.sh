#!/bin/bash
set -e

echo "=== PART 2.1 ==="
ssh shreyas@shreyas.local 'systemctl --user disable --now sih26052-edge.service ; systemctl --user is-enabled sih26052-edge.service ; systemctl --user is-active sih26052-edge.service ; sleep 30 ; ps -eo pid,cmd | grep -E "anc_stream|pi_sender" | grep -v grep || echo "PID 1294 is gone"'

echo "=== PART 2.2 ==="
ssh shreyas@shreyas.local 'mkdir -p ~/anc_logs ; cp /boot/firmware/config.txt ~/anc_logs/config.txt.bak'

echo "=== PART 2.3 ==="
ssh shreyas@shreyas.local 'sudo mkdir -p /var/log/journal ; sudo systemd-tmpfiles --create --prefix /var/log/journal ; sudo mkdir -p /etc/systemd/journald.conf.d ; printf "[Journal]\nStorage=persistent\nSystemMaxUse=100M\nSyncIntervalSec=1s\n" | sudo tee /etc/systemd/journald.conf.d/persist.conf ; sudo systemctl restart systemd-journald ; journalctl --list-boots'

echo "=== PART 2.4 (Write script) ==="
ssh shreyas@shreyas.local 'cat << '"'"'INNER_EOF'"'"' > ~/anc_logs/power_logger.sh
#!/bin/bash
TAG=$1
OUTFILE=~/anc_logs/power_${TAG}.csv
echo "epoch,uptime_s,EXT5V_V,VDD_CORE_V,VDD_CORE_A,arm_clock,temp,throttled,MemAvailable_MB,SwapUsed_MB,load1" > $OUTFILE
COUNT=0
while true; do
    EPOCH=$(date +%s)
    UPTIME=$(cat /proc/uptime | awk "{print \$1}")
    EXT5V=$(vcgencmd pmic_read_adc | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    VDD_V=$(vcgencmd pmic_read_adc | grep VDD_CORE_V | cut -d= -f2 | sed "s/V//")
    VDD_A=$(vcgencmd pmic_read_adc | grep VDD_CORE_A | cut -d= -f2 | sed "s/A//")
    CLK=$(vcgencmd measure_clock arm | cut -d= -f2)
    TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    MEM_AVAIL=$(awk "/MemAvailable/ {print \$2/1024}" /proc/meminfo)
    SWAP_TOTAL=$(awk "/SwapTotal/ {print \$2}" /proc/meminfo)
    SWAP_FREE=$(awk "/SwapFree/ {print \$2}" /proc/meminfo)
    SWAP_USED=$(awk "BEGIN {print ($SWAP_TOTAL-$SWAP_FREE)/1024}")
    LOAD1=$(cat /proc/loadavg | awk "{print \$1}")
    echo "$EPOCH,$UPTIME,$EXT5V,$VDD_V,$VDD_A,$CLK,$TEMP,$THROT,$MEM_AVAIL,$SWAP_USED,$LOAD1" >> $OUTFILE
    COUNT=$((COUNT+1))
    if [ $((COUNT % 5)) -eq 0 ]; then sync; fi
    sleep 1
done
INNER_EOF
chmod +x ~/anc_logs/power_logger.sh
cat ~/anc_logs/power_logger.sh
'

echo "=== PART 2.5 (Run & Stats) ==="
ssh shreyas@shreyas.local 'sleep 30 ; timeout 120 ~/anc_logs/power_logger.sh idle_clean || true'
scp shreyas@shreyas.local:~/anc_logs/power_idle_clean.csv .
awk -F, 'NR>1 {
  ext5v=$3; temp=$7; throt=$8; mem=$9
  if (min_ext5v=="" || ext5v<min_ext5v) min_ext5v=ext5v
  if (max_ext5v=="" || ext5v>max_ext5v) max_ext5v=ext5v
  sum_ext5v+=ext5v
  if (max_temp=="" || temp>max_temp) max_temp=temp
  if (min_mem=="" || mem<min_mem) min_mem=mem
  throt_vals[throt]++
  if (throt != "0x0") has_uv=1
} END {
  print "EXT5V min/mean/max: " min_ext5v " / " sum_ext5v/(NR-1) " / " max_ext5v
  print "Max temp: " max_temp
  printf "Throttled values seen: "
  for (t in throt_vals) printf t " "
  print ""
  print "MemAvailable min: " min_mem " MB"
  print "Any undervoltage row: " (has_uv?"YES":"NO")
}' power_idle_clean.csv
grep -v "0x0" power_idle_clean.csv || true

echo "=== PART 2.6 (Read-only dmesg/bootloader) ==="
ssh shreyas@shreyas.local 'dmesg | grep -i -E "power|supply|over-?current|under-?volt|i/o error|reset" | tail -40 ; vcgencmd bootloader_config | grep -i -E "PSU|POWER"'

echo "=== PART 3 (Verify) ==="
ssh shreyas@shreyas.local 'ps -eo pid,etime,%cpu,%mem,cmd --sort=-%cpu | head -10 ; free -m ; df -h / ; vcgencmd get_throttled ; vcgencmd measure_temp ; bluetoothctl devices ; pw-dump | jq -r ".[] | select(.info.props[\"media.class\"]==\"Audio/Source\") | .info.props[\"node.name\"]" || pw-dump | grep -A 20 "Audio/Source" ; ls ~/sih26052_edge/anc_fix_v2/anc_fix ; /home/shreyas/env/bin/python -c "import numpy, scipy, torch, hk; print(\"ok\")"'
