#!/bin/bash
echo "=== 22c. Copy files ==="
scp dfn3_paced2.py run_s2.sh shreyas@shreyas.local:~/anc_logs/
ssh shreyas@shreyas.local 'chmod +x ~/anc_logs/run_s2.sh'

echo "=== 22c. Run stage s2 ==="
ssh shreyas@shreyas.local 'nohup ~/anc_logs/run_s2.sh > ~/anc_logs/run_s2.log 2>&1 < /dev/null &'

echo "=== Waiting for load test to complete (5 mins) ==="
while ssh -o ConnectTimeout=5 shreyas@shreyas.local 'pgrep -f "[r]un_s2.sh" >/dev/null'; do
    sleep 10
done

echo "=== Stage ended. Waiting 60s quiet period ==="
sleep 60

echo "=== 22d. Extract results ==="
mkdir -p ~/anc_tests/E2
scp -o ConnectTimeout=5 shreyas@shreyas.local:/dev/shm/anc_run/* ~/anc_tests/E2/ || true
