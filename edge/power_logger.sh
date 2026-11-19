#!/bin/bash
TAG=$1
OUTFILE=~/anc_logs/power_${TAG}.csv
echo "epoch,uptime_s,EXT5V_V,VDD_CORE_V,VDD_CORE_A,arm_clock,temp,throttled,MemAvailable_MB,SwapUsed_MB,load1,stage" > $OUTFILE
COUNT=0
while true; do
    EPOCH=$(date +%s)
    UPTIME=$(cat /proc/uptime | awk "{print \$1}")
    
    PMIC=$(vcgencmd pmic_read_adc)
    EXT5V=$(echo "$PMIC" | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    VDD_V=$(echo "$PMIC" | grep VDD_CORE_V | cut -d= -f2 | sed "s/V//")
    VDD_A=$(echo "$PMIC" | grep VDD_CORE_A | cut -d= -f2 | sed "s/A//")
    
    CLK=$(vcgencmd measure_clock arm | cut -d= -f2)
    TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    MEM_AVAIL=$(awk "/MemAvailable/ {print \$2/1024}" /proc/meminfo)
    SWAP_TOTAL=$(awk "/SwapTotal/ {print \$2}" /proc/meminfo)
    SWAP_FREE=$(awk "/SwapFree/ {print \$2}" /proc/meminfo)
    SWAP_USED=$(awk "BEGIN {print (\$SWAP_TOTAL-\$SWAP_FREE)/1024}")
    LOAD1=$(cat /proc/loadavg | awk "{print \$1}")
    
    STAGE=""
    if [ -f ~/anc_logs/stage.txt ]; then
        STAGE=$(cat ~/anc_logs/stage.txt)
    fi
    
    echo "$EPOCH,$UPTIME,$EXT5V,$VDD_V,$VDD_A,$CLK,$TEMP,$THROT,$MEM_AVAIL,$SWAP_USED,$LOAD1,$STAGE" >> $OUTFILE
    
    COUNT=$((COUNT+1))
    if [ $((COUNT % 5)) -eq 0 ]; then sync; fi
    sleep 1
done
