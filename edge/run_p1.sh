#!/bin/bash
export MAC_IP="${SIH_PC_IP:-${1:?Error: SIH_PC_IP environment variable or argument 1 required}}"
rm -rf /dev/shm/anc_run
/home/shreyas/env/bin/python ~/anc_logs/dfn3_paced2.py 1 300 $MAC_IP &
PY_PID=$!

while kill -0 $PY_PID 2>/dev/null; do
    PMIC=$(vcgencmd pmic_read_adc)
    EXT5V=$(echo "$PMIC" | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
    
    ABORT=0
    REASON=""
    
    if awk "BEGIN {exit !($EXT5V < 4.75)}"; then ABORT=1; REASON="V_DROP($EXT5V)"; fi
    if awk "BEGIN {exit !($TEMP >= 82)}"; then ABORT=1; REASON="TEMP($TEMP)"; fi
    
    THROT_DEC=$(( THROT ))
    if [ $(( THROT_DEC & 1 )) -ne 0 ]; then ABORT=1; REASON="THROTTLE_BIT0"; fi
    
    if [ "$ABORT" -eq 1 ]; then
        ROW="ext5v=$EXT5V throt=$THROT temp=$TEMP"
        echo "ABORTED $REASON $ROW" | nc -u -w1 $MAC_IP 5099
        kill -15 $PY_PID 2>/dev/null || true
        sleep 3
        if kill -0 $PY_PID 2>/dev/null; then
            kill -9 $PY_PID 2>/dev/null || true
        fi
        exit 1
    fi
    sleep 1
done
