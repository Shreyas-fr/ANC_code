#!/bin/bash
export MAC_IP="10.190.58.182"
rm -rf /dev/shm/anc_run
mkdir -p /dev/shm/anc_run

# Record get_throttled at start
vcgencmd get_throttled > /dev/shm/anc_run/throttle_start.txt

/home/shreyas/env/bin/python ~/anc_logs/dfn3_paced2.py 1 300 $MAC_IP >/dev/null 2>&1 &
PY_PID=$!

/home/shreyas/env/bin/python /home/shreyas/sih26052_edge/anc_fix_v2/anc_fix/pi_sender_v2.py \
    --mode raw --target-ip $MAC_IP --name-match Rockerz --duration 300 \
    --report /dev/shm/anc_run/E2.json >/dev/null 2>&1 &
SENDER_PID=$!

V_DROP_COUNT=0

while kill -0 $PY_PID 2>/dev/null && kill -0 $SENDER_PID 2>/dev/null; do
    PMIC=$(vcgencmd pmic_read_adc)
    EXT5V=$(echo "$PMIC" | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
    
    ABORT=0
    REASON=""
    
    if awk "BEGIN {exit !($EXT5V < 4.70)}"; then
        V_DROP_COUNT=$((V_DROP_COUNT + 1))
        if [ "$V_DROP_COUNT" -ge 2 ]; then
            ABORT=1; REASON="V_DROP($EXT5V)"
        fi
    else
        V_DROP_COUNT=0
    fi
    
    if awk "BEGIN {exit !($TEMP >= 82)}"; then ABORT=1; REASON="TEMP($TEMP)"; fi
    
    THROT_DEC=$(( THROT ))
    if [ $(( THROT_DEC & 1 )) -ne 0 ]; then ABORT=1; REASON="THROTTLE_BIT0"; fi
    
    if [ "$ABORT" -eq 1 ]; then
        ROW="ext5v=$EXT5V throt=$THROT temp=$TEMP"
        echo "ABORTED $REASON $ROW" | nc -u -w1 $MAC_IP 5099
        kill -15 $PY_PID 2>/dev/null || true
        kill -15 $SENDER_PID 2>/dev/null || true
        sleep 3
        if kill -0 $PY_PID 2>/dev/null; then kill -9 $PY_PID 2>/dev/null || true; fi
        if kill -0 $SENDER_PID 2>/dev/null; then kill -9 $SENDER_PID 2>/dev/null || true; fi
        exit 1
    fi
    sleep 1
done

wait $PY_PID
wait $SENDER_PID

vcgencmd get_throttled > /dev/shm/anc_run/throttle_end.txt
