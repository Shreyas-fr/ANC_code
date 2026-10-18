#!/bin/bash

echo "=== 20c. Copy files ==="
scp dfn3_paced2.py run_s1.sh shreyas@shreyas.local:~/anc_logs/
ssh shreyas@shreyas.local 'chmod +x ~/anc_logs/run_s1.sh'

echo "=== 20c. Run stage s1 ==="
ssh shreyas@shreyas.local 'nohup ~/anc_logs/run_s1.sh > ~/anc_logs/run_s1.log 2>&1 < /dev/null &'

echo "=== Waiting for load test to complete ==="
while ssh -o ConnectTimeout=5 shreyas@shreyas.local 'pgrep -f "run_s1.sh" >/dev/null'; do
    sleep 10
done

echo "=== Extract results ==="
scp -o ConnectTimeout=5 shreyas@shreyas.local:/dev/shm/anc_run/power.csv . || true
scp -o ConnectTimeout=5 shreyas@shreyas.local:/dev/shm/anc_run/lowest_pmic.txt . || true
scp -o ConnectTimeout=5 shreyas@shreyas.local:/dev/shm/anc_run/dfn3_paced2_t1.json . || true
scp -o ConnectTimeout=5 shreyas@shreyas.local:/dev/shm/anc_run/E.json . || true
