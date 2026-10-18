#!/bin/bash
lsof -ti :5007 | xargs kill -9 2>/dev/null

echo "Starting udp_record.py on Mac for Phase C (DFN3)..."
./pc_venv/bin/python udp_record.py --port 5007 --out ~/anc_tests/C_dfn3.wav --duration 65 > mac_C.log 2>&1 &
REC_PID=$!

echo "Starting Pi sender Phase C (DFN3)..."
ssh -o StrictHostKeyChecking=no shreyas@"${SIH_PI_IP:?Error: SIH_PI_IP required}" '
  # Start thermal monitor in background
  (for i in {1..13}; do vcgencmd measure_temp; vcgencmd get_throttled; top -bn1 | head -5; sleep 5; done) > /tmp/thermal_C.log 2>&1 &
  
  . /home/shreyas/env/bin/activate
  cd ~/sih26052_edge/anc_fix_v2/anc_fix
  python pi_sender_v2.py --mode dfn3 --target-ip "${SIH_PC_IP:?Error: SIH_PC_IP required}" --name-match Rockerz --duration 60 --report /tmp/C.json
' > pi_C.log 2>&1

echo "Waiting for Mac receiver..."
wait $REC_PID
echo "Done Phase C."
