#!/bin/bash
MAX_TEMP=75000
MIN_TEMP=65000

echo "Starting thermal monitor. MAX: $MAX_TEMP, MIN: $MIN_TEMP"

STOPPED=0

while true; do
    TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
    if [ "$TEMP" -ge "$MAX_TEMP" ]; then
        if [ "$STOPPED" -eq 0 ]; then
            echo "$(date) - Temp $TEMP >= $MAX_TEMP. Pausing build..."
            pkill -STOP rustc
            pkill -STOP cargo
            pkill -STOP cc1
            pkill -STOP cc1plus
            STOPPED=1
        fi
    elif [ "$TEMP" -le "$MIN_TEMP" ]; then
        if [ "$STOPPED" -eq 1 ]; then
            echo "$(date) - Temp $TEMP <= $MIN_TEMP. Resuming build..."
            pkill -CONT rustc
            pkill -CONT cargo
            pkill -CONT cc1
            pkill -CONT cc1plus
            STOPPED=0
        fi
    fi
    sleep 2
done
