#!/bin/bash


echo "=== 14a. Verify ==="
ssh shreyas@shreyas.local 'systemctl --user is-enabled sih26052-edge.service ; systemctl --user is-active sih26052-edge.service'
ssh shreyas@shreyas.local 'ps -eo pid,cmd | grep -E "anc_stream|pi_sender" | grep -v grep || echo "Clean"'
ssh shreyas@shreyas.local 'journalctl --list-boots ; ls /var/log/journal'
ssh shreyas@shreyas.local 'uptime -s ; vcgencmd get_throttled'

echo "=== 14b. Fix logger ==="
ssh shreyas@shreyas.local 'cat << '"'"'INNER_EOF'"'"' > ~/anc_logs/power_logger.sh
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
INNER_EOF
chmod +x ~/anc_logs/power_logger.sh
cat ~/anc_logs/power_logger.sh
'

echo "=== 14c. Load test script ==="
ssh shreyas@shreyas.local 'cat << '"'"'INNER_EOF'"'"' > ~/anc_logs/loadtest.sh
#!/bin/bash

~/anc_logs/power_logger.sh load1 &
LOGGER_PID=$!

trap "kill $LOGGER_PID 2>/dev/null; exit" EXIT INT TERM

function check_abort {
    PMIC=$(vcgencmd pmic_read_adc)
    EXT5V=$(echo "$PMIC" | grep EXT5V_V | cut -d= -f2 | sed "s/V//")
    THROT=$(vcgencmd get_throttled | cut -d= -f2)
    
    ABORT=0
    if awk "BEGIN {exit !($EXT5V < 4.75)}"; then
        ABORT=1
    fi
    
    THROT_DEC=$(( THROT ))
    if [ $(( THROT_DEC & 1 )) -ne 0 ]; then
        ABORT=1
    fi
    
    if [ "$ABORT" -eq 1 ]; then
        STAGE=$(cat ~/anc_logs/stage.txt 2>/dev/null)
        echo "ABORTED $STAGE EXT5V=$EXT5V THROT=$THROT" > ~/anc_logs/stage.txt
        echo "ABORTED $STAGE EXT5V=$EXT5V THROT=$THROT"
        
        if [ -n "$PIDS" ]; then
            kill $PIDS 2>/dev/null || true
        fi
        kill $LOGGER_PID 2>/dev/null || true
        exit 1
    fi
}

function rest_stage {
    echo "rest" > ~/anc_logs/stage.txt
    for i in {1..30}; do
        check_abort
        sleep 1
    done
}

function run_stage {
    STAGE_NAME=$1
    echo "$STAGE_NAME" > ~/anc_logs/stage.txt
    echo "Starting $STAGE_NAME"
    
    PIDS=""
    if [[ "$STAGE_NAME" == *"cpu"* ]]; then
        CORES=$(echo "$STAGE_NAME" | grep -o -E "[0-9]+" | head -1)
        for ((i=0; i<CORES; i++)); do
            sh -c "while :; do :; done" &
            PIDS="$PIDS $!"
        done
    fi
    
    if [[ "$STAGE_NAME" == *"disk"* ]]; then
        sh -c "while :; do dd if=/dev/zero of=~/anc_logs/ddtest.bin bs=1M count=300 conv=fsync 2>/dev/null; rm -f ~/anc_logs/ddtest.bin; done" &
        PIDS="$PIDS $!"
    fi
    
    for i in {1..30}; do
        check_abort
        sleep 1
    done
    
    kill $PIDS 2>/dev/null || true
    wait $PIDS 2>/dev/null || true
    rm -f ~/anc_logs/ddtest.bin
}

rest_stage
run_stage "cpu1"
rest_stage
run_stage "cpu2"
rest_stage
run_stage "cpu3"
rest_stage
run_stage "cpu4"
rest_stage
run_stage "disk"
rest_stage
run_stage "cpu4+disk"
rest_stage

echo "DONE" > ~/anc_logs/stage.txt
kill $LOGGER_PID 2>/dev/null || true
INNER_EOF
chmod +x ~/anc_logs/loadtest.sh
'

echo "=== Running load test ==="
ssh shreyas@shreyas.local 'nohup ~/anc_logs/loadtest.sh > ~/anc_logs/loadtest.log 2>&1 < /dev/null &'

echo "=== Waiting for load test to complete ==="
while ssh -o ConnectTimeout=5 shreyas@shreyas.local 'pgrep -f loadtest.sh >/dev/null'; do
    sleep 5
done

echo "=== 14d. Extract results ==="
scp -o ConnectTimeout=5 shreyas@shreyas.local:~/anc_logs/power_load1.csv . || (echo "PI IS UNREACHABLE" && exit 1)

awk -F, '
NR>1 {
  stage=$12; ext5v=$3; vdda=$5; clk=$6; temp=$7; throt=$8; mem=$9
  if (stage == "") stage = "unknown"
  
  if (!(stage in seen)) {
    stages[++n] = stage
    seen[stage] = 1
    min_ext5v[stage] = ext5v; max_ext5v[stage] = ext5v
    max_vdda[stage] = vdda
    min_clk[stage] = clk; max_clk[stage] = clk
    max_temp[stage] = temp
    min_mem[stage] = mem
  }
  
  if (ext5v < min_ext5v[stage]) min_ext5v[stage] = ext5v
  if (ext5v > max_ext5v[stage]) max_ext5v[stage] = ext5v
  sum_ext5v[stage] += ext5v
  count[stage]++
  
  if (vdda > max_vdda[stage]) max_vdda[stage] = vdda
  
  if (clk < min_clk[stage]) min_clk[stage] = clk
  if (clk > max_clk[stage]) max_clk[stage] = clk
  
  if (temp > max_temp[stage]) max_temp[stage] = temp
  if (mem < min_mem[stage]) min_mem[stage] = mem
  
  throt_key = stage SUBSEP throt
  if (!(throt_key in throt_seen)) {
      throt_seen[throt_key] = 1
      throt_list[stage] = throt_list[stage] throt " "
  }
}
END {
  printf "%-25s | %-18s | %-8s | %-21s | %-8s | %-15s | %-10s\n", "Stage", "EXT5V (min/u/max)", "VDD_A", "Clk (min/max)", "Temp", "Throttled", "MemMin"
  print "--------------------------------------------------------------------------------------------------------------------------"
  for (i=1; i<=n; i++) {
    s = stages[i]
    printf "%-25s | %4.2f / %4.2f / %4.2f | %-8s | %9d / %9d | %4.1f C | %-15s | %-10s\n", s, min_ext5v[s], sum_ext5v[s]/count[s], max_ext5v[s], max_vdda[s], min_clk[s], max_clk[s], max_temp[s], throt_list[s], min_mem[s]
  }
}
' power_load1.csv

echo "=== Tail of CSV ==="
tail -n 10 power_load1.csv
