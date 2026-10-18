#!/bin/bash

# Start logger
~/anc_logs/power_logger.sh paced &
LOGGER_PID=$!

trap "kill $LOGGER_PID 2>/dev/null; exit" EXIT INT TERM

function check_abort {
    PMIC=$(vcgencmd pmic_read_adc)
    EXT5V=$(echo "$PMIC" | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
    
    ABORT=0
    REASON=""
    
    if awk "BEGIN {exit !($EXT5V < 4.75)}"; then
        ABORT=1; REASON="V_DROP($EXT5V)"
    fi
    if awk "BEGIN {exit !($TEMP >= 82)}"; then
        ABORT=1; REASON="TEMP($TEMP)"
    fi
    
    THROT_DEC=$(( THROT ))
    if [ $(( THROT_DEC & 1 )) -ne 0 ]; then
        ABORT=1; REASON="THROTTLE_BIT0"
    fi
    
    if [ "$ABORT" -eq 1 ]; then
        STAGE=$(cat ~/anc_logs/stage.txt 2>/dev/null)
        echo "ABORTED $STAGE $REASON throt=$THROT ext5v=$EXT5V temp=$TEMP" > ~/anc_logs/stage.txt
        echo "ABORTED $STAGE $REASON"
        
        if [ -n "$PY_PID" ]; then
            kill -15 $PY_PID 2>/dev/null || true
            sleep 3
            kill -9 $PY_PID 2>/dev/null || true
        fi
        kill $LOGGER_PID 2>/dev/null || true
        exit 1
    fi
}

function check_gate {
    STAGE_NAME=$1
    if [ ! -f ~/anc_logs/power_paced.csv ]; then
        return 0
    fi
    MIN_V=$(awk -F, -v stg="$STAGE_NAME" 'NR>1 && $12==stg {if(min=="" || $3<min) min=$3} END {print min}' ~/anc_logs/power_paced.csv)
    if [ -n "$MIN_V" ] && awk "BEGIN {exit !($MIN_V < 4.80)}"; then
        echo "GATE FAILED for $STAGE_NAME, min V = $MIN_V"
        echo "ABORTED GATING $STAGE_NAME $MIN_V" > ~/anc_logs/stage.txt
        kill $LOGGER_PID 2>/dev/null || true
        exit 1
    fi
}

function rest_stage {
    PREV=$1
    echo "rest_after_$PREV" > ~/anc_logs/stage.txt
    
    for i in {1..180}; do
        check_abort
        TEMP=$(vcgencmd measure_temp | cut -d= -f2 | sed "s/.C//")
        if awk "BEGIN {exit !($TEMP < 60)}"; then
            break
        fi
        sleep 1
    done
}

function run_stage {
    THREADS=$1
    STAGE_NAME="p${THREADS}"
    echo "$STAGE_NAME" > ~/anc_logs/stage.txt
    echo "Starting $STAGE_NAME"
    
    /home/shreyas/env/bin/python ~/anc_logs/dfn3_paced.py $THREADS 300 &
    PY_PID=$!
    
    while kill -0 $PY_PID 2>/dev/null; do
        check_abort
        sleep 1
    done
}

run_stage 2
rest_stage "p2"
check_gate "p2"

run_stage 3
rest_stage "p3"

echo "DONE" > ~/anc_logs/stage.txt
kill $LOGGER_PID 2>/dev/null || true
