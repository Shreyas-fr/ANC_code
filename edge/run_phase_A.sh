#!/bin/bash
mkdir -p ~/anc_tests
# Stop old receiver if any
lsof -ti :5007 | xargs kill -9 2>/dev/null

echo "Starting udp_record.py on Mac..."
./pc_venv/bin/python udp_record.py --port 5007 --out ~/anc_tests/A_raw.wav --duration 65 > mac_A.log 2>&1 &
REC_PID=$!

echo "Starting Pi sender..."
ssh -o StrictHostKeyChecking=no shreyas@2401:4900:c309:4993:9afe:54ff:fe39:9c4e '
  # Start thermal monitor in background
  (for i in {1..13}; do vcgencmd measure_temp; vcgencmd get_throttled; top -bn1 | head -5; sleep 5; done) > /tmp/thermal_A.log 2>&1 &
  
  . /home/shreyas/env/bin/activate
  cd ~/sih26052_edge/anc_fix_v2/anc_fix
  python pi_sender_v2.py --mode raw --target-ip "${SIH_PC_IP:?Error: SIH_PC_IP required}" --name-match Rockerz --duration 60 --report /tmp/A2.json
' > pi_A.log 2>&1

echo "Waiting for Mac receiver..."
wait $REC_PID
echo "Done Phase A."
